from __future__ import annotations

import csv
from collections.abc import Iterator, Mapping
from datetime import datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from io import BytesIO, StringIO
from typing import Any, cast
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile
from zoneinfo import ZoneInfo

import pytest
import requests
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.adapters import bench_dispatch as bench_dispatch_adapter
from backend.app.adapters.bench_dispatch import (
    BENCH_DISPATCH_ARCHIVE_BASE_URL,
    BENCH_MARKET_TIMEZONE,
    BenchDispatchAdapterError,
    BenchDispatchClient,
    FetchedBenchDispatchDailyArchive,
    build_bench_dispatch_benchmark,
    build_bench_dispatch_benchmarks,
)
from backend.app.models.forecasting import ForecastResearchDataset, ForecastResearchPricePoint
from backend.app.services.forecasting import get_bench_dispatch_client

AEST = ZoneInfo(BENCH_MARKET_TIMEZONE)
DAILY_REPORT_FILENAME = "PUBLIC_DISPATCHIS_20260531.zip"


class FakeResponse:
    def __init__(
        self,
        *,
        content: bytes,
        status_code: int = 200,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        self.content = content
        self.status_code = status_code
        self.headers = headers or {}
        self.closed = False

    def iter_content(self, *, chunk_size: int) -> Iterator[bytes]:
        for offset in range(0, len(self.content), chunk_size):
            yield self.content[offset : offset + chunk_size]

    def close(self) -> None:
        self.closed = True


class FakeSession:
    def __init__(self, outcomes: list[FakeResponse | requests.RequestException]) -> None:
        self.outcomes = outcomes
        self.calls: list[dict[str, object]] = []

    def get(
        self,
        url: str,
        *,
        timeout: float,
        allow_redirects: bool,
        stream: bool,
    ) -> FakeResponse:
        self.calls.append(
            {
                "url": url,
                "timeout": timeout,
                "allow_redirects": allow_redirects,
                "stream": stream,
            }
        )
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, requests.RequestException):
            raise outcome
        return outcome


def _make_dispatchprice_csv(
    *,
    settlement_interval_end: datetime,
    rrp: Decimal,
    sequence: int,
    rop: Decimal | None = None,
    last_changed: datetime | None = None,
    region_id: str = "NSW1",
    region_ids: tuple[str, ...] | None = None,
    dispatch_interval_sequence: int | None = None,
) -> tuple[str, bytes]:
    dispatch_interval = (
        f"{settlement_interval_end:%Y%m%d}{dispatch_interval_sequence or sequence:03d}"
    )
    csv_filename = f"PUBLIC_DISPATCHIS_{settlement_interval_end:%Y%m%d%H%M}_{sequence:016d}.CSV"
    output = StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(
        [
            "I",
            "DISPATCH",
            "PRICE",
            "5",
            "SETTLEMENTDATE",
            "RUNNO",
            "REGIONID",
            "DISPATCHINTERVAL",
            "INTERVENTION",
            "RRP",
            "ROP",
            "APCFLAG",
            "MARKETSUSPENDEDFLAG",
            "LASTCHANGED",
            "PRICE_STATUS",
        ]
    )
    for selected_region_id in region_ids or (region_id,):
        writer.writerow(
            [
                "D",
                "DISPATCH",
                "PRICE",
                "5",
                settlement_interval_end.strftime("%Y/%m/%d %H:%M:%S"),
                1,
                selected_region_id,
                dispatch_interval,
                0,
                str(rrp),
                str(rop if rop is not None else rrp),
                0,
                0,
                (last_changed or settlement_interval_end - timedelta(minutes=5)).strftime(
                    "%Y/%m/%d %H:%M:%S"
                ),
                "FIRM",
            ]
        )
    return csv_filename, output.getvalue().encode("utf-8")


def _make_interval_zip(
    *,
    settlement_interval_end: datetime,
    rrp: Decimal,
    sequence: int,
    rop: Decimal | None = None,
    last_changed: datetime | None = None,
    dispatch_interval_sequence: int | None = None,
    region_ids: tuple[str, ...] | None = None,
) -> tuple[str, bytes]:
    csv_filename, csv_content = _make_dispatchprice_csv(
        settlement_interval_end=settlement_interval_end,
        rrp=rrp,
        sequence=sequence,
        rop=rop,
        last_changed=last_changed,
        dispatch_interval_sequence=dispatch_interval_sequence,
        region_ids=region_ids,
    )
    output = BytesIO()
    with ZipFile(output, mode="w", compression=ZIP_DEFLATED) as interval_zip:
        interval_zip.writestr(csv_filename, csv_content)
    return f"{csv_filename[:-4]}.zip", output.getvalue()


def _make_daily_archive(
    *,
    interval_count: int = 3,
    revisions: list[tuple[int, Decimal, datetime]] | None = None,
    region_ids: tuple[str, ...] | None = None,
) -> bytes:
    first_interval_end = datetime(2026, 5, 31, 0, 5, tzinfo=AEST)
    output = BytesIO()
    with ZipFile(output, mode="w", compression=ZIP_STORED) as daily_zip:
        for offset in range(interval_count):
            interval_end = first_interval_end + timedelta(minutes=5 * offset)
            filename, content = _make_interval_zip(
                settlement_interval_end=interval_end,
                rrp=Decimal(10 + offset),
                sequence=offset + 1,
                rop=Decimal(9 + offset),
                region_ids=region_ids,
            )
            daily_zip.writestr(filename, content)
        for offset, rrp, last_changed in revisions or []:
            interval_end = first_interval_end + timedelta(minutes=5 * offset)
            filename, content = _make_interval_zip(
                settlement_interval_end=interval_end,
                rrp=rrp,
                sequence=10_000 + offset,
                rop=rrp - 1,
                last_changed=last_changed,
                dispatch_interval_sequence=offset + 1,
                region_ids=region_ids,
            )
            daily_zip.writestr(filename, content)
    return output.getvalue()


def _fetched_archive(
    zip_content: bytes,
    *,
    report_filename: str = DAILY_REPORT_FILENAME,
) -> FetchedBenchDispatchDailyArchive:
    return FetchedBenchDispatchDailyArchive(
        report_filename=report_filename,
        source_url=f"{BENCH_DISPATCH_ARCHIVE_BASE_URL}{report_filename}",
        fetched_at=datetime(2026, 6, 1, 8, tzinfo=AEST),
        content_type="application/x-zip-compressed",
        last_modified="Mon, 01 Jun 2026 15:03:13 GMT",
        zip_content=zip_content,
        zip_sha256=sha256(zip_content).hexdigest(),
    )


def _client(session: FakeSession, *, max_retries: int = 0) -> BenchDispatchClient:
    return BenchDispatchClient(
        timeout_seconds=3,
        max_retries=max_retries,
        retry_backoff_seconds=0.25,
        session=session,
    )


def test_client_fetches_only_fixed_official_daily_archive_url_and_hashes_zip() -> None:
    zip_content = _make_daily_archive()
    response = FakeResponse(
        content=zip_content,
        headers={
            "Content-Type": "application/x-zip-compressed",
            "Last-Modified": "Mon, 01 Jun 2026 15:03:13 GMT",
        },
    )
    session = FakeSession([response])

    result = _client(session).fetch_daily_archive(
        DAILY_REPORT_FILENAME,
        fetched_at=datetime(2026, 6, 1, 8, tzinfo=AEST),
    )

    assert result.source_url == f"{BENCH_DISPATCH_ARCHIVE_BASE_URL}{DAILY_REPORT_FILENAME}"
    assert result.zip_sha256 == sha256(zip_content).hexdigest()
    assert result.last_modified == "Mon, 01 Jun 2026 15:03:13 GMT"
    assert response.closed is True
    assert session.calls == [
        {
            "url": f"{BENCH_DISPATCH_ARCHIVE_BASE_URL}{DAILY_REPORT_FILENAME}",
            "timeout": 3,
            "allow_redirects": False,
            "stream": True,
        }
    ]


def test_client_rejects_arbitrary_url_before_network_access() -> None:
    session = FakeSession([])

    with pytest.raises(BenchDispatchAdapterError) as raised:
        _client(session).fetch_daily_archive(
            "https://example.invalid/PUBLIC_DISPATCHIS_20260531.zip",
            fetched_at=datetime(2026, 6, 1, 8, tzinfo=AEST),
        )

    assert raised.value.code == "bench_dispatch_report_filename_not_allowed"
    assert session.calls == []


def test_client_stops_stream_when_daily_archive_exceeds_size_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(bench_dispatch_adapter, "MAX_DAILY_ARCHIVE_BYTES", 3)
    response = FakeResponse(content=b"four")

    with pytest.raises(BenchDispatchAdapterError) as raised:
        _client(FakeSession([response])).fetch_daily_archive(
            DAILY_REPORT_FILENAME,
            fetched_at=datetime(2026, 6, 1, 8, tzinfo=AEST),
        )

    assert raised.value.code == "bench_dispatch_archive_too_large"
    assert response.closed is True


def test_client_retries_timeout_with_bounded_exponential_backoff() -> None:
    session = FakeSession(
        [
            requests.Timeout("first"),
            requests.Timeout("second"),
            requests.Timeout("third"),
        ]
    )
    delays: list[float] = []
    client = BenchDispatchClient(
        timeout_seconds=3,
        max_retries=2,
        retry_backoff_seconds=0.25,
        session=session,
        sleep=delays.append,
    )

    with pytest.raises(BenchDispatchAdapterError) as raised:
        client.fetch_daily_archive(
            DAILY_REPORT_FILENAME,
            fetched_at=datetime(2026, 6, 1, 8, tzinfo=AEST),
        )

    assert raised.value.code == "bench_dispatch_network_error"
    assert len(session.calls) == 3
    assert delays == [0.25, 0.5]


def test_parser_preserves_layered_metadata_revision_fields_and_explicit_mean() -> None:
    archive = _fetched_archive(_make_daily_archive())

    result = build_bench_dispatch_benchmark([archive], region_id="NSW1")

    assert len(result.selected_region_records) == 3
    assert len(result.points) == 1
    assert result.points[0].interval_start.isoformat() == "2026-05-31T00:00:00+10:00"
    assert result.points[0].price == Decimal("11.0000")
    source_record = result.selected_region_records[0]
    assert source_record.rrp == Decimal("10")
    assert source_record.rop == Decimal("9")
    assert source_record.intervention == 0
    assert source_record.run_no == 1
    assert source_record.dispatch_interval == "20260531001"
    assert source_record.price_status == "FIRM"
    metadata = result.to_source_metadata()
    assert metadata["native_data_mode"] == "public_observed"
    assert metadata["derived_data_mode"] == "public_derived"
    archives = metadata["archives"]
    assert isinstance(archives, list)
    interval_zips = archives[0]["interval_zips"]
    assert len(interval_zips) == 3
    assert interval_zips[0]["interval_zip_sha256"]
    assert interval_zips[0]["csv"]["csv_sha256"]


def test_parser_deduplicates_unchanged_daily_archive_by_sha256() -> None:
    zip_content = _make_daily_archive()

    result = build_bench_dispatch_benchmark(
        [
            _fetched_archive(zip_content),
            _fetched_archive(zip_content, report_filename="PUBLIC_DISPATCHIS_20260601.zip"),
        ],
        region_id="NSW1",
    )

    assert len(result.selected_region_records) == 3
    assert len(result.archives) == 2
    assert result.archives[1].deduplication_status == "duplicate_zip_sha256"
    assert result.archives[1].interval_zips == ()


def test_parser_builds_all_regions_from_one_daily_archive_parse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    regions = ("NSW1", "QLD1", "SA1", "TAS1", "VIC1")
    archive = _fetched_archive(_make_daily_archive(region_ids=regions))
    original = bench_dispatch_adapter._parse_daily_archive
    parsed: list[str] = []

    def track_parse(
        candidate: FetchedBenchDispatchDailyArchive,
    ) -> tuple[
        bench_dispatch_adapter.BenchDispatchDailyArchiveMetadata,
        list[bench_dispatch_adapter.BenchDispatchPriceRecord],
    ]:
        parsed.append(candidate.report_filename)
        return original(candidate)

    monkeypatch.setattr(bench_dispatch_adapter, "_parse_daily_archive", track_parse)

    drafts = build_bench_dispatch_benchmarks([archive], region_ids=regions)

    assert parsed == [DAILY_REPORT_FILENAME]
    assert set(drafts) == set(regions)
    assert {draft.points[0].price for draft in drafts.values()} == {Decimal("11.0000")}


def test_parser_preserves_revisions_and_aggregates_latest_last_changed_row() -> None:
    revised_at = datetime(2026, 5, 31, 0, 4, tzinfo=AEST)
    archive = _fetched_archive(_make_daily_archive(revisions=[(0, Decimal("40"), revised_at)]))

    result = build_bench_dispatch_benchmark([archive], region_id="NSW1")

    assert len(result.selected_region_records) == 4
    assert len(result.selected_revision_records) == 3
    assert result.selected_revision_records[0].rrp == Decimal("40")
    assert result.selected_revision_records[0].last_changed == revised_at
    assert result.points[0].price == Decimal("21.0000")
    metadata = result.to_source_metadata()
    source_records = metadata["selected_region_records"]
    assert isinstance(source_records, list)
    assert [record["selected_revision"] for record in source_records].count(True) == 3


def test_parser_rejects_incomplete_five_minute_aggregation_bucket() -> None:
    with pytest.raises(BenchDispatchAdapterError) as raised:
        build_bench_dispatch_benchmark(
            [_fetched_archive(_make_daily_archive(interval_count=2))],
            region_id="NSW1",
        )

    assert raised.value.code == "bench_dispatch_incomplete_aggregation_bucket"


def test_api_imports_bench_as_research_only_public_derived_non_example_province_dataset(
    client: TestClient,
    db_session_factory: sessionmaker[Session],
) -> None:
    zip_content = _make_daily_archive(interval_count=288)
    session = FakeSession([FakeResponse(content=zip_content), FakeResponse(content=zip_content)])
    adapter_client = _client(session)
    cast(FastAPI, client.app).dependency_overrides[get_bench_dispatch_client] = lambda: (
        adapter_client
    )
    request = {"archive_filenames": [DAILY_REPORT_FILENAME], "region_id": "NSW1"}

    first = client.post("/v1/forecasting/research/benchmarks/bench-dispatch/archive", json=request)
    second = client.post("/v1/forecasting/research/benchmarks/bench-dispatch/archive", json=request)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["status"] == "accepted"
    assert first.json()["normalized_point_count"] == 96
    assert first.json()["data_mode"] == "public_derived"
    assert first.json()["usage_scope"] == "research_only"
    assert second.json()["status"] == "duplicate"

    with db_session_factory() as db_session:
        dataset = db_session.scalar(select(ForecastResearchDataset))
        assert dataset is not None
        assert dataset.region_code == "BENCH_NEM_NSW1"
        assert dataset.region_name == "BENCH NEM region NSW1"
        assert dataset.market_scope == "bench_nem_dispatch_benchmark"
        assert "Example Province" not in dataset.name
        source_metadata = cast(dict[str, Any], dataset.raw_payload_json["source_metadata"])
        assert source_metadata["provider"] == "bench"
        assert source_metadata["native_data_mode"] == "public_observed"
        assert source_metadata["derived_data_mode"] == "public_derived"
        assert source_metadata["usage_scope"] == "research_only"
        assert len(source_metadata["selected_region_records"]) == 288
        assert db_session.scalar(select(func.count()).select_from(ForecastResearchPricePoint)) == 96


def test_api_rejects_non_allowlisted_report_filename_without_fetching(client: TestClient) -> None:
    session = FakeSession([])
    cast(FastAPI, client.app).dependency_overrides[get_bench_dispatch_client] = lambda: _client(
        session
    )

    response = client.post(
        "/v1/forecasting/research/benchmarks/bench-dispatch/archive",
        json={
            "archive_filenames": ["https://example.invalid/PUBLIC_DISPATCHIS_20260531.zip"],
            "region_id": "NSW1",
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert session.calls == []
