from __future__ import annotations

import csv
import json
import logging
import re
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from hashlib import sha256
from io import BytesIO, StringIO
from typing import Protocol, cast
from zipfile import BadZipFile, ZipFile, ZipInfo
from zoneinfo import ZoneInfo

import requests

logger = logging.getLogger(__name__)

BENCH_DISPATCH_ARCHIVE_BASE_URL = (
    "https://archive.benchmark.example.invalid/Reports/ARCHIVE/DispatchIS_Reports/"
)
BENCH_DISPATCH_SOURCE_PAGE_URL = (
    "https://operator.benchmark.example.invalid/energy-systems/electricity/"
    "national-electricity-market-nem/data-nem/market-management-system-mms-data/dispatch"
)
BENCH_DISPATCHPRICE_DATA_MODEL_URL = (
    "https://models.benchmark.example.invalid/bench/nemweb/mmsdatamodelreport/"
    "electricity/mms%20data%20model%20report_files/MMS_130.htm"
)
BENCH_MARKET_TIMEZONE = "Australia/Brisbane"
BENCH_NEM_REGION_IDS = frozenset({"NSW1", "QLD1", "SA1", "TAS1", "VIC1"})
PUBLIC_OBSERVED = "public_observed"
PUBLIC_DERIVED = "public_derived"
RESEARCH_ONLY = "research_only"
SOURCE_NATIVE_INTERVAL_MINUTES = 5
TARGET_INTERVAL_MINUTES = 15
SOURCE_POINTS_PER_TARGET_INTERVAL = TARGET_INTERVAL_MINUTES // SOURCE_NATIVE_INTERVAL_MINUTES
MAX_DAILY_ARCHIVE_BYTES = 20_000_000
MAX_INTERVAL_ZIP_BYTES = 512_000
MAX_CSV_BYTES = 2_000_000
MAX_INTERVAL_ZIP_MEMBERS = 300
RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})

DAILY_ARCHIVE_FILENAME_PATTERN = re.compile(r"^PUBLIC_DISPATCHIS_(?P<date>\d{8})\.zip$")
INTERVAL_ZIP_FILENAME_PATTERN = re.compile(
    r"^PUBLIC_DISPATCHIS_(?P<interval>\d{12})_(?P<sequence>\d{16})\.zip$"
)


class HttpResponse(Protocol):
    status_code: int
    headers: Mapping[str, str]

    def iter_content(self, *, chunk_size: int) -> Iterator[bytes]: ...

    def close(self) -> None: ...


class HttpSession(Protocol):
    def get(
        self,
        url: str,
        *,
        timeout: float,
        allow_redirects: bool,
        stream: bool,
    ) -> HttpResponse: ...


@dataclass(frozen=True)
class FetchedBenchDispatchDailyArchive:
    report_filename: str
    source_url: str
    fetched_at: datetime
    content_type: str | None
    last_modified: str | None
    zip_content: bytes
    zip_sha256: str


@dataclass(frozen=True)
class BenchDispatchCsvMetadata:
    csv_filename: str
    csv_size_bytes: int
    csv_compressed_size_bytes: int
    csv_crc32: int
    csv_sha256: str


@dataclass(frozen=True)
class BenchDispatchIntervalZipMetadata:
    interval_zip_filename: str
    interval_zip_size_bytes: int
    interval_zip_compressed_size_bytes: int
    interval_zip_crc32: int
    interval_zip_sha256: str
    csv: BenchDispatchCsvMetadata


@dataclass(frozen=True)
class BenchDispatchDailyArchiveMetadata:
    report_filename: str
    source_url: str
    fetched_at: datetime
    content_type: str | None
    last_modified: str | None
    zip_size_bytes: int
    zip_sha256: str
    deduplication_status: str
    interval_zips: tuple[BenchDispatchIntervalZipMetadata, ...] = ()


@dataclass(frozen=True)
class BenchDispatchPriceRecord:
    settlement_interval_end: datetime
    interval_start: datetime
    run_no: int
    region_id: str
    dispatch_interval: str
    intervention: int
    rrp: Decimal
    rop: Decimal | None
    apc_flag: int | None
    market_suspended_flag: int | None
    last_changed: datetime
    price_status: str | None
    source_report_filename: str
    source_interval_zip_filename: str
    source_csv_filename: str
    source_daily_zip_sha256: str
    source_interval_zip_sha256: str
    source_csv_sha256: str


@dataclass(frozen=True)
class BenchDispatchAggregatedPricePoint:
    interval_start: datetime
    price: Decimal
    source_settlement_interval_ends: tuple[datetime, ...]
    source_csv_sha256s: tuple[str, ...]


@dataclass(frozen=True)
class BenchDispatchBenchmarkDraft:
    region_id: str
    archives: tuple[BenchDispatchDailyArchiveMetadata, ...]
    selected_region_records: tuple[BenchDispatchPriceRecord, ...]
    selected_revision_records: tuple[BenchDispatchPriceRecord, ...]
    points: tuple[BenchDispatchAggregatedPricePoint, ...]

    @property
    def content_sha256(self) -> str:
        return _hash_json(
            {
                "adapter": "bench_dispatch_archive:v1",
                "region_id": self.region_id,
                "daily_zip_sha256s": sorted(
                    {
                        archive.zip_sha256
                        for archive in self.archives
                        if archive.deduplication_status == "accepted"
                    }
                ),
                "aggregation_rule": (
                    "arithmetic_mean_of_three_consecutive_source_native_rrp_values"
                ),
                "rounding": "ROUND_HALF_UP_to_4_decimal_places",
            }
        )

    def to_source_metadata(self) -> dict[str, object]:
        selected_revision_identities = {
            _record_identity(record) for record in self.selected_revision_records
        }
        return {
            "adapter": "bench_dispatch_archive:v1",
            "provider": "bench",
            "market_scope": "bench_nem",
            "selected_region_id": self.region_id,
            "official_archive_base_url": BENCH_DISPATCH_ARCHIVE_BASE_URL,
            "official_source_page_url": BENCH_DISPATCH_SOURCE_PAGE_URL,
            "dispatchprice_data_model_url": BENCH_DISPATCHPRICE_DATA_MODEL_URL,
            "timezone": BENCH_MARKET_TIMEZONE,
            "native_data_mode": PUBLIC_OBSERVED,
            "derived_data_mode": PUBLIC_DERIVED,
            "usage_scope": RESEARCH_ONLY,
            "benchmark_content_sha256": self.content_sha256,
            "source_native_interval_minutes": SOURCE_NATIVE_INTERVAL_MINUTES,
            "aggregation": {
                "target_interval_minutes": TARGET_INTERVAL_MINUTES,
                "rule": "arithmetic_mean_of_three_consecutive_source_native_rrp_values",
                "rounding": "ROUND_HALF_UP_to_4_decimal_places",
                "price_field": "RRP",
            },
            "revision_fields_preserved": [
                "ROP",
                "INTERVENTION",
                "RUNNO",
                "DISPATCHINTERVAL",
                "LASTCHANGED",
                "APCFLAG",
                "MARKETSUSPENDEDFLAG",
                "PRICE_STATUS",
            ],
            "archives": [_archive_metadata_to_dict(archive) for archive in self.archives],
            "selected_region_records": [
                _price_record_to_dict(
                    record,
                    selected_revision=_record_identity(record) in selected_revision_identities,
                )
                for record in self.selected_region_records
            ],
        }


class BenchDispatchAdapterError(Exception):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        report_filename: str | None = None,
        source_url: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.report_filename = report_filename
        self.source_url = source_url


class BenchDispatchClient:
    provider = "bench"

    def __init__(
        self,
        *,
        timeout_seconds: float,
        max_retries: int,
        retry_backoff_seconds: float,
        session: HttpSession | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("BENCH Dispatch timeout_seconds must be positive.")
        if not 0 <= max_retries <= 5:
            raise ValueError("BENCH Dispatch max_retries must be between 0 and 5.")
        if retry_backoff_seconds < 0:
            raise ValueError("BENCH Dispatch retry_backoff_seconds must not be negative.")
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._retry_backoff_seconds = retry_backoff_seconds
        self._session = session or cast(HttpSession, requests.Session())
        self._sleep = sleep

    def fetch_daily_archive(
        self,
        report_filename: str,
        *,
        fetched_at: datetime,
    ) -> FetchedBenchDispatchDailyArchive:
        _validate_daily_archive_filename(report_filename)
        source_url = f"{BENCH_DISPATCH_ARCHIVE_BASE_URL}{report_filename}"
        response = self._request_with_retry(
            report_filename=report_filename,
            source_url=source_url,
        )
        try:
            zip_content = _read_bounded_response_content(
                response,
                max_bytes=MAX_DAILY_ARCHIVE_BYTES,
                report_filename=report_filename,
                source_url=source_url,
            )
        finally:
            response.close()
        if not zip_content:
            raise BenchDispatchAdapterError(
                code="bench_dispatch_empty_archive",
                message="BENCH Dispatch returned an empty daily ZIP.",
                report_filename=report_filename,
                source_url=source_url,
            )
        return FetchedBenchDispatchDailyArchive(
            report_filename=report_filename,
            source_url=source_url,
            fetched_at=fetched_at,
            content_type=response.headers.get("Content-Type"),
            last_modified=response.headers.get("Last-Modified"),
            zip_content=zip_content,
            zip_sha256=_hash_bytes(zip_content),
        )

    def _request_with_retry(self, *, report_filename: str, source_url: str) -> HttpResponse:
        for attempt in range(self._max_retries + 1):
            try:
                response = self._session.get(
                    source_url,
                    timeout=self._timeout_seconds,
                    allow_redirects=False,
                    stream=True,
                )
            except requests.RequestException as exc:
                if attempt < self._max_retries:
                    self._retry(attempt=attempt, reason=type(exc).__name__)
                    continue
                raise BenchDispatchAdapterError(
                    code="bench_dispatch_network_error",
                    message=f"BENCH Dispatch request failed after retries: {type(exc).__name__}.",
                    report_filename=report_filename,
                    source_url=source_url,
                ) from exc
            if response.status_code < 300:
                return response
            if response.status_code in RETRYABLE_STATUS_CODES and attempt < self._max_retries:
                response.close()
                self._retry(attempt=attempt, reason=f"http_{response.status_code}")
                continue
            if 300 <= response.status_code < 400:
                response.close()
                raise BenchDispatchAdapterError(
                    code="bench_dispatch_redirect_rejected",
                    message="BENCH Dispatch archive redirect was rejected.",
                    report_filename=report_filename,
                    source_url=source_url,
                )
            response.close()
            raise BenchDispatchAdapterError(
                code="bench_dispatch_http_error",
                message=f"BENCH Dispatch returned HTTP {response.status_code}.",
                report_filename=report_filename,
                source_url=source_url,
            )
        raise AssertionError("BENCH Dispatch retry loop exited unexpectedly.")

    def _retry(self, *, attempt: int, reason: str) -> None:
        delay = self._retry_backoff_seconds * (2**attempt)
        logger.warning("Retrying BENCH Dispatch request after %s; delay=%s", reason, delay)
        self._sleep(delay)


def build_bench_dispatch_benchmark(
    archives: Sequence[FetchedBenchDispatchDailyArchive],
    *,
    region_id: str,
) -> BenchDispatchBenchmarkDraft:
    return build_bench_dispatch_benchmarks(archives, region_ids=(region_id,))[region_id]


def build_bench_dispatch_benchmarks(
    archives: Sequence[FetchedBenchDispatchDailyArchive],
    *,
    region_ids: Sequence[str],
) -> dict[str, BenchDispatchBenchmarkDraft]:
    requested_regions = tuple(dict.fromkeys(region_ids))
    if not requested_regions:
        raise BenchDispatchAdapterError(
            code="bench_dispatch_regions_required",
            message="At least one BENCH Dispatch region is required.",
        )
    for region_id in requested_regions:
        if region_id not in BENCH_NEM_REGION_IDS:
            raise BenchDispatchAdapterError(
                code="bench_dispatch_region_not_allowed",
                message=f"BENCH Dispatch region '{region_id}' is not in the NEM region allowlist.",
            )
    if not archives:
        raise BenchDispatchAdapterError(
            code="bench_dispatch_archives_required",
            message="At least one BENCH Dispatch daily archive is required.",
        )

    archive_metadata: list[BenchDispatchDailyArchiveMetadata] = []
    records: list[BenchDispatchPriceRecord] = []
    seen_daily_zip_sha256s: set[str] = set()
    for archive in archives:
        if archive.zip_sha256 in seen_daily_zip_sha256s:
            archive_metadata.append(_duplicate_archive_metadata(archive))
            continue
        seen_daily_zip_sha256s.add(archive.zip_sha256)
        parsed_metadata, parsed_records = _parse_daily_archive(archive)
        archive_metadata.append(parsed_metadata)
        records.extend(parsed_records)

    drafts: dict[str, BenchDispatchBenchmarkDraft] = {}
    for region_id in requested_regions:
        selected_region_records = sorted(
            (record for record in records if record.region_id == region_id),
            key=_record_sort_key,
        )
        if not selected_region_records:
            raise BenchDispatchAdapterError(
                code="bench_dispatch_region_missing",
                message=f"BENCH Dispatch archives contain no RRP rows for region '{region_id}'.",
            )
        selected_revisions = _select_latest_revisions(selected_region_records)
        points = _aggregate_rrp_to_fifteen_minutes(selected_revisions)
        drafts[region_id] = BenchDispatchBenchmarkDraft(
            region_id=region_id,
            archives=tuple(archive_metadata),
            selected_region_records=tuple(selected_region_records),
            selected_revision_records=tuple(selected_revisions),
            points=tuple(points),
        )
    return drafts


def _parse_daily_archive(
    archive: FetchedBenchDispatchDailyArchive,
) -> tuple[BenchDispatchDailyArchiveMetadata, list[BenchDispatchPriceRecord]]:
    try:
        with ZipFile(BytesIO(archive.zip_content)) as daily_zip:
            infos = daily_zip.infolist()
            if not infos:
                raise _archive_error(
                    archive,
                    "bench_dispatch_empty_archive",
                    "Daily ZIP has no files.",
                )
            if len(infos) > MAX_INTERVAL_ZIP_MEMBERS:
                raise _archive_error(
                    archive,
                    "bench_dispatch_archive_member_limit_exceeded",
                    "Daily ZIP contains too many interval ZIP files.",
                )
            interval_metadata: list[BenchDispatchIntervalZipMetadata] = []
            records: list[BenchDispatchPriceRecord] = []
            seen_interval_zip_sha256s: set[str] = set()
            for info in infos:
                _validate_interval_zip_info(archive, info)
                interval_zip_content = daily_zip.read(info)
                interval_zip_sha256 = _hash_bytes(interval_zip_content)
                if interval_zip_sha256 in seen_interval_zip_sha256s:
                    continue
                seen_interval_zip_sha256s.add(interval_zip_sha256)
                metadata, interval_records = _parse_interval_zip(
                    archive,
                    info=info,
                    interval_zip_content=interval_zip_content,
                    interval_zip_sha256=interval_zip_sha256,
                )
                interval_metadata.append(metadata)
                records.extend(interval_records)
    except BadZipFile as exc:
        raise _archive_error(
            archive,
            "bench_dispatch_malformed_zip",
            "BENCH Dispatch daily ZIP or nested interval ZIP is malformed.",
        ) from exc
    return (
        BenchDispatchDailyArchiveMetadata(
            report_filename=archive.report_filename,
            source_url=archive.source_url,
            fetched_at=archive.fetched_at,
            content_type=archive.content_type,
            last_modified=archive.last_modified,
            zip_size_bytes=len(archive.zip_content),
            zip_sha256=archive.zip_sha256,
            deduplication_status="accepted",
            interval_zips=tuple(interval_metadata),
        ),
        records,
    )


def _parse_interval_zip(
    archive: FetchedBenchDispatchDailyArchive,
    *,
    info: ZipInfo,
    interval_zip_content: bytes,
    interval_zip_sha256: str,
) -> tuple[BenchDispatchIntervalZipMetadata, list[BenchDispatchPriceRecord]]:
    with ZipFile(BytesIO(interval_zip_content)) as interval_zip:
        csv_infos = interval_zip.infolist()
        if len(csv_infos) != 1:
            raise _archive_error(
                archive,
                "bench_dispatch_interval_zip_member_count_invalid",
                "BENCH Dispatch interval ZIP must contain exactly one CSV file.",
            )
        csv_info = csv_infos[0]
        expected_csv_filename = f"{info.filename[:-4]}.CSV"
        if csv_info.filename != expected_csv_filename:
            raise _archive_error(
                archive,
                "bench_dispatch_csv_filename_invalid",
                "BENCH Dispatch interval CSV filename does not match its interval ZIP.",
            )
        if csv_info.is_dir() or csv_info.file_size > MAX_CSV_BYTES:
            raise _archive_error(
                archive,
                "bench_dispatch_csv_too_large",
                "BENCH Dispatch interval CSV exceeds the configured size limit.",
            )
        csv_content = interval_zip.read(csv_info)
        csv_sha256 = _hash_bytes(csv_content)
        metadata = BenchDispatchIntervalZipMetadata(
            interval_zip_filename=info.filename,
            interval_zip_size_bytes=info.file_size,
            interval_zip_compressed_size_bytes=info.compress_size,
            interval_zip_crc32=info.CRC,
            interval_zip_sha256=interval_zip_sha256,
            csv=BenchDispatchCsvMetadata(
                csv_filename=csv_info.filename,
                csv_size_bytes=csv_info.file_size,
                csv_compressed_size_bytes=csv_info.compress_size,
                csv_crc32=csv_info.CRC,
                csv_sha256=csv_sha256,
            ),
        )
        records = _parse_dispatchprice_csv(
            archive,
            interval_zip_filename=info.filename,
            interval_zip_sha256=interval_zip_sha256,
            csv_filename=csv_info.filename,
            csv_sha256=csv_sha256,
            csv_content=csv_content,
        )
    return metadata, records


def _parse_dispatchprice_csv(
    archive: FetchedBenchDispatchDailyArchive,
    *,
    interval_zip_filename: str,
    interval_zip_sha256: str,
    csv_filename: str,
    csv_sha256: str,
    csv_content: bytes,
) -> list[BenchDispatchPriceRecord]:
    try:
        text = csv_content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise _archive_error(
            archive,
            "bench_dispatch_csv_encoding_error",
            "BENCH Dispatch interval CSV must be UTF-8 encoded.",
        ) from exc
    rows = csv.reader(StringIO(text, newline=""))
    price_header: list[str] | None = None
    records: list[BenchDispatchPriceRecord] = []
    try:
        for row in rows:
            if row[:3] == ["I", "DISPATCH", "PRICE"]:
                price_header = row[4:]
                continue
            if row[:3] != ["D", "DISPATCH", "PRICE"]:
                continue
            if price_header is None:
                raise ValueError("DISPATCH PRICE data row precedes its header")
            values = dict(zip(price_header, row[4:], strict=True))
            records.append(
                _build_price_record(
                    archive,
                    interval_zip_filename=interval_zip_filename,
                    interval_zip_sha256=interval_zip_sha256,
                    csv_filename=csv_filename,
                    csv_sha256=csv_sha256,
                    values=values,
                )
            )
    except (csv.Error, InvalidOperation, TypeError, ValueError) as exc:
        raise _archive_error(
            archive,
            "bench_dispatch_csv_parse_error",
            f"BENCH Dispatch interval CSV could not be parsed: {exc}.",
        ) from exc
    if not records:
        raise _archive_error(
            archive,
            "bench_dispatch_price_rows_missing",
            "BENCH Dispatch interval CSV contains no DISPATCH PRICE rows.",
        )
    return records


def _build_price_record(
    archive: FetchedBenchDispatchDailyArchive,
    *,
    interval_zip_filename: str,
    interval_zip_sha256: str,
    csv_filename: str,
    csv_sha256: str,
    values: Mapping[str, str],
) -> BenchDispatchPriceRecord:
    settlement_interval_end = _parse_bench_datetime(_required(values, "SETTLEMENTDATE"))
    return BenchDispatchPriceRecord(
        settlement_interval_end=settlement_interval_end,
        interval_start=settlement_interval_end - timedelta(minutes=SOURCE_NATIVE_INTERVAL_MINUTES),
        run_no=int(_required(values, "RUNNO")),
        region_id=_required(values, "REGIONID"),
        dispatch_interval=_required(values, "DISPATCHINTERVAL"),
        intervention=int(_required(values, "INTERVENTION")),
        rrp=Decimal(_required(values, "RRP")),
        rop=_optional_decimal(values.get("ROP")),
        apc_flag=_optional_int(values.get("APCFLAG")),
        market_suspended_flag=_optional_int(values.get("MARKETSUSPENDEDFLAG")),
        last_changed=_parse_bench_datetime(_required(values, "LASTCHANGED")),
        price_status=_optional_text(values.get("PRICE_STATUS")),
        source_report_filename=archive.report_filename,
        source_interval_zip_filename=interval_zip_filename,
        source_csv_filename=csv_filename,
        source_daily_zip_sha256=archive.zip_sha256,
        source_interval_zip_sha256=interval_zip_sha256,
        source_csv_sha256=csv_sha256,
    )


def _select_latest_revisions(
    records: Sequence[BenchDispatchPriceRecord],
) -> list[BenchDispatchPriceRecord]:
    latest_by_source_key: dict[tuple[object, ...], BenchDispatchPriceRecord] = {}
    for record in records:
        source_key = (
            record.settlement_interval_end,
            record.run_no,
            record.region_id,
            record.dispatch_interval,
            record.intervention,
        )
        previous = latest_by_source_key.get(source_key)
        if previous is None or _record_sort_key(record) > _record_sort_key(previous):
            latest_by_source_key[source_key] = record

    selected_by_interval: dict[datetime, BenchDispatchPriceRecord] = {}
    for record in latest_by_source_key.values():
        previous = selected_by_interval.get(record.interval_start)
        if previous is not None and _record_identity(previous) != _record_identity(record):
            raise BenchDispatchAdapterError(
                code="bench_dispatch_ambiguous_interval",
                message=(
                    "BENCH Dispatch contains multiple semantic variants for interval "
                    f"'{record.interval_start.isoformat()}'."
                ),
            )
        selected_by_interval[record.interval_start] = record
    return sorted(selected_by_interval.values(), key=_record_sort_key)


def _aggregate_rrp_to_fifteen_minutes(
    records: Sequence[BenchDispatchPriceRecord],
) -> list[BenchDispatchAggregatedPricePoint]:
    grouped: dict[datetime, list[BenchDispatchPriceRecord]] = {}
    for record in records:
        bucket = record.interval_start.replace(
            minute=(record.interval_start.minute // TARGET_INTERVAL_MINUTES)
            * TARGET_INTERVAL_MINUTES,
            second=0,
            microsecond=0,
        )
        grouped.setdefault(bucket, []).append(record)

    points: list[BenchDispatchAggregatedPricePoint] = []
    for bucket, bucket_records in sorted(grouped.items()):
        ordered = sorted(bucket_records, key=_record_sort_key)
        expected_starts = [
            bucket + timedelta(minutes=SOURCE_NATIVE_INTERVAL_MINUTES * offset)
            for offset in range(SOURCE_POINTS_PER_TARGET_INTERVAL)
        ]
        actual_starts = [record.interval_start for record in ordered]
        if actual_starts != expected_starts:
            raise BenchDispatchAdapterError(
                code="bench_dispatch_incomplete_aggregation_bucket",
                message=(
                    "BENCH Dispatch 15-minute aggregation requires exactly three consecutive "
                    f"five-minute RRP values starting at '{bucket.isoformat()}'."
                ),
            )
        average = sum((record.rrp for record in ordered), start=Decimal("0")) / Decimal(
            SOURCE_POINTS_PER_TARGET_INTERVAL
        )
        points.append(
            BenchDispatchAggregatedPricePoint(
                interval_start=bucket,
                price=average.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP),
                source_settlement_interval_ends=tuple(
                    record.settlement_interval_end for record in ordered
                ),
                source_csv_sha256s=tuple(record.source_csv_sha256 for record in ordered),
            )
        )
    return points


def _validate_daily_archive_filename(report_filename: str) -> None:
    if DAILY_ARCHIVE_FILENAME_PATTERN.fullmatch(report_filename) is None:
        raise BenchDispatchAdapterError(
            code="bench_dispatch_report_filename_not_allowed",
            message=("BENCH Dispatch report filename must match 'PUBLIC_DISPATCHIS_YYYYMMDD.zip'."),
            report_filename=report_filename,
        )


def _read_bounded_response_content(
    response: HttpResponse,
    *,
    max_bytes: int,
    report_filename: str,
    source_url: str,
) -> bytes:
    content = bytearray()
    for chunk in response.iter_content(chunk_size=64 * 1024):
        if not chunk:
            continue
        if len(content) + len(chunk) > max_bytes:
            raise BenchDispatchAdapterError(
                code="bench_dispatch_archive_too_large",
                message="BENCH Dispatch daily ZIP exceeds the configured size limit.",
                report_filename=report_filename,
                source_url=source_url,
            )
        content.extend(chunk)
    return bytes(content)


def _validate_interval_zip_info(
    archive: FetchedBenchDispatchDailyArchive,
    info: ZipInfo,
) -> None:
    if (
        info.is_dir()
        or INTERVAL_ZIP_FILENAME_PATTERN.fullmatch(info.filename) is None
        or info.file_size > MAX_INTERVAL_ZIP_BYTES
    ):
        raise _archive_error(
            archive,
            "bench_dispatch_interval_zip_invalid",
            "BENCH Dispatch daily ZIP contains an invalid interval ZIP member.",
        )


def _required(values: Mapping[str, str], field: str) -> str:
    value = values.get(field)
    if value is None or not value.strip():
        raise ValueError(f"required DISPATCH PRICE field '{field}' is missing")
    return value.strip()


def _optional_decimal(value: str | None) -> Decimal | None:
    text = _optional_text(value)
    return Decimal(text) if text is not None else None


def _optional_int(value: str | None) -> int | None:
    text = _optional_text(value)
    return int(text) if text is not None else None


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


def _parse_bench_datetime(value: str) -> datetime:
    return datetime.strptime(value, "%Y/%m/%d %H:%M:%S").replace(
        tzinfo=ZoneInfo(BENCH_MARKET_TIMEZONE)
    )


def _hash_bytes(content: bytes) -> str:
    return sha256(content).hexdigest()


def _hash_json(value: object) -> str:
    serialized = json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return sha256(serialized.encode("utf-8")).hexdigest()


def _record_sort_key(record: BenchDispatchPriceRecord) -> tuple[object, ...]:
    return (
        record.interval_start,
        record.last_changed,
        record.source_report_filename,
        record.source_interval_zip_filename,
        record.source_csv_sha256,
    )


def _record_identity(record: BenchDispatchPriceRecord) -> tuple[object, ...]:
    return (
        record.settlement_interval_end,
        record.run_no,
        record.region_id,
        record.dispatch_interval,
        record.intervention,
        record.last_changed,
        record.source_csv_sha256,
    )


def _archive_error(
    archive: FetchedBenchDispatchDailyArchive,
    code: str,
    message: str,
) -> BenchDispatchAdapterError:
    return BenchDispatchAdapterError(
        code=code,
        message=message,
        report_filename=archive.report_filename,
        source_url=archive.source_url,
    )


def _duplicate_archive_metadata(
    archive: FetchedBenchDispatchDailyArchive,
) -> BenchDispatchDailyArchiveMetadata:
    return BenchDispatchDailyArchiveMetadata(
        report_filename=archive.report_filename,
        source_url=archive.source_url,
        fetched_at=archive.fetched_at,
        content_type=archive.content_type,
        last_modified=archive.last_modified,
        zip_size_bytes=len(archive.zip_content),
        zip_sha256=archive.zip_sha256,
        deduplication_status="duplicate_zip_sha256",
    )


def _archive_metadata_to_dict(archive: BenchDispatchDailyArchiveMetadata) -> dict[str, object]:
    return {
        "report_filename": archive.report_filename,
        "source_url": archive.source_url,
        "fetched_at": archive.fetched_at.isoformat(),
        "content_type": archive.content_type,
        "last_modified": archive.last_modified,
        "zip_size_bytes": archive.zip_size_bytes,
        "zip_sha256": archive.zip_sha256,
        "deduplication_status": archive.deduplication_status,
        "interval_zips": [
            {
                "interval_zip_filename": item.interval_zip_filename,
                "interval_zip_size_bytes": item.interval_zip_size_bytes,
                "interval_zip_compressed_size_bytes": item.interval_zip_compressed_size_bytes,
                "interval_zip_crc32": item.interval_zip_crc32,
                "interval_zip_sha256": item.interval_zip_sha256,
                "csv": {
                    "csv_filename": item.csv.csv_filename,
                    "csv_size_bytes": item.csv.csv_size_bytes,
                    "csv_compressed_size_bytes": item.csv.csv_compressed_size_bytes,
                    "csv_crc32": item.csv.csv_crc32,
                    "csv_sha256": item.csv.csv_sha256,
                },
            }
            for item in archive.interval_zips
        ],
    }


def _price_record_to_dict(
    record: BenchDispatchPriceRecord,
    *,
    selected_revision: bool,
) -> dict[str, object]:
    return {
        "settlement_interval_end": record.settlement_interval_end.isoformat(),
        "interval_start": record.interval_start.isoformat(),
        "run_no": record.run_no,
        "region_id": record.region_id,
        "dispatch_interval": record.dispatch_interval,
        "intervention": record.intervention,
        "rrp": str(record.rrp),
        "rop": str(record.rop) if record.rop is not None else None,
        "apc_flag": record.apc_flag,
        "market_suspended_flag": record.market_suspended_flag,
        "last_changed": record.last_changed.isoformat(),
        "price_status": record.price_status,
        "source_report_filename": record.source_report_filename,
        "source_interval_zip_filename": record.source_interval_zip_filename,
        "source_csv_filename": record.source_csv_filename,
        "source_daily_zip_sha256": record.source_daily_zip_sha256,
        "source_interval_zip_sha256": record.source_interval_zip_sha256,
        "source_csv_sha256": record.source_csv_sha256,
        "selected_revision": selected_revision,
    }
