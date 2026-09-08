from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from html.parser import HTMLParser

PARSER_KEY = "reports_weekly_market_report"
PARSER_VERSION = "v1"
GENERATION_SIDE = "generation"
PRELIMINARY_FLASH = "preliminary_flash"
PUBLIC_OBSERVED = "public_observed"

PROVINCES = (
    ("GD", "示例甲省"),
    ("GX", "示例乙省"),
    ("YN", "示例丙省"),
    ("GZ", "示例丁省"),
    ("HN", "示例戊省"),
)

PERIOD_PATTERN = re.compile(
    r"(?P<year>\d{4})年(?P<start_month>\d{1,2})月(?P<start_day>\d{1,2})日"
    r"[-—至](?:(?P<end_month>\d{1,2})月)?(?P<end_day>\d{1,2})日"
)
REGION_PATTERN = re.compile(
    r"日前市场日均成交电量(?P<day_energy>\d+(?:\.\d+)?)亿千瓦时"
    r".*?加权均价为(?P<day_price>\d+(?:\.\d+)?)元/兆瓦时"
    r".*?实时市场日均成交电量(?P<realtime_energy>\d+(?:\.\d+)?)亿千瓦时"
    r".*?加权均价为(?P<realtime_price>\d+(?:\.\d+)?)元/兆瓦时",
    re.DOTALL,
)
PROVINCE_PATTERN = re.compile(
    r"(?P<stage>日前|实时)市场，示例甲省、示例乙省、示例丙省、示例丁省、示例戊省"
    r"日均成交电量分别为(?P<energy>[\d.、]+)亿千瓦时，"
    r"加权均价分别为(?P<prices>[\d.、]+)元/兆瓦时"
)


class ReportsWeeklyMarketReportParserError(ValueError):
    def __init__(self, *, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class NormalizedMarketObservation:
    period_start: date
    period_end: date
    area_scope: str
    area_code: str
    area_name: str
    market_stage: str
    participant_side: str
    metric: str
    value: Decimal
    unit: str
    settlement_status: str
    data_mode: str


@dataclass(frozen=True)
class ReportsWeeklyMarketReportParseResult:
    parser_key: str
    parser_version: str
    observations: tuple[NormalizedMarketObservation, ...]
    has_unparsed_power_type_section: bool


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: list[str] = []
        self._ignored_depth = 0

    @property
    def text(self) -> str:
        return re.sub(r"\s+", "", "".join(self._chunks))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self._ignored_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self._ignored_depth:
            self._ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth:
            self._chunks.append(data)


def parse_reports_weekly_market_report(raw_html: str) -> ReportsWeeklyMarketReportParseResult:
    text = _extract_visible_text(raw_html)
    period_start, period_end = _parse_period(text)
    observations = [
        *_parse_regional_observations(text, period_start=period_start, period_end=period_end),
        *_parse_province_observations(text, period_start=period_start, period_end=period_end),
    ]
    expected_count = 24
    if len(observations) != expected_count:
        raise ReportsWeeklyMarketReportParserError(
            code="reports_weekly_report_incomplete",
            message=(
                f"Expected {expected_count} normalized regional and provincial observations, "
                f"received {len(observations)}."
            ),
        )
    return ReportsWeeklyMarketReportParseResult(
        parser_key=PARSER_KEY,
        parser_version=PARSER_VERSION,
        observations=tuple(observations),
        has_unparsed_power_type_section="分电源情况" in text,
    )


def _extract_visible_text(raw_html: str) -> str:
    parser = _VisibleTextParser()
    parser.feed(raw_html)
    parser.close()
    text = parser.text
    if not text:
        raise ReportsWeeklyMarketReportParserError(
            code="reports_weekly_report_empty",
            message="The preserved REPORTS weekly report HTML does not contain visible text.",
        )
    return text


def _parse_period(text: str) -> tuple[date, date]:
    match = PERIOD_PATTERN.search(text)
    if match is None:
        raise ReportsWeeklyMarketReportParserError(
            code="reports_weekly_report_period_missing",
            message="The REPORTS weekly report period could not be parsed.",
        )
    year = int(match.group("year"))
    start_month = int(match.group("start_month"))
    end_month = int(match.group("end_month") or start_month)
    start = date(year, start_month, int(match.group("start_day")))
    end_year = year + 1 if end_month < start_month else year
    end = date(end_year, end_month, int(match.group("end_day")))
    if end < start:
        raise ReportsWeeklyMarketReportParserError(
            code="reports_weekly_report_period_invalid",
            message="The REPORTS weekly report period end precedes its start.",
        )
    return start, end


def _parse_regional_observations(
    text: str, *, period_start: date, period_end: date
) -> list[NormalizedMarketObservation]:
    match = REGION_PATTERN.search(text)
    if match is None:
        raise ReportsWeeklyMarketReportParserError(
            code="reports_weekly_report_region_missing",
            message="The REPORTS weekly regional total could not be parsed.",
        )
    observations: list[NormalizedMarketObservation] = []
    for stage, energy_key, price_key in [
        ("day_ahead", "day_energy", "day_price"),
        ("real_time", "realtime_energy", "realtime_price"),
    ]:
        observations.extend(
            _make_metric_pair(
                period_start=period_start,
                period_end=period_end,
                area_scope="region",
                area_code="SOUTHERN_REGION",
                area_name="示例区域",
                market_stage=stage,
                energy=match.group(energy_key),
                price=match.group(price_key),
            )
        )
    return observations


def _parse_province_observations(
    text: str, *, period_start: date, period_end: date
) -> list[NormalizedMarketObservation]:
    matches = list(PROVINCE_PATTERN.finditer(text))
    if len(matches) != 2:
        raise ReportsWeeklyMarketReportParserError(
            code="reports_weekly_report_province_sections_missing",
            message="Expected one day-ahead and one real-time province section.",
        )
    observations: list[NormalizedMarketObservation] = []
    parsed_stages: set[str] = set()
    for match in matches:
        stage = "day_ahead" if match.group("stage") == "日前" else "real_time"
        if stage in parsed_stages:
            raise ReportsWeeklyMarketReportParserError(
                code="reports_weekly_report_province_sections_duplicate",
                message=f"Weekly report contains duplicate '{stage}' province sections.",
            )
        parsed_stages.add(stage)
        energies = match.group("energy").split("、")
        prices = match.group("prices").split("、")
        if len(energies) != len(PROVINCES) or len(prices) != len(PROVINCES):
            raise ReportsWeeklyMarketReportParserError(
                code="reports_weekly_report_province_values_incomplete",
                message=f"The REPORTS weekly report '{stage}' province values are incomplete.",
            )
        for (area_code, area_name), energy, price in zip(PROVINCES, energies, prices, strict=True):
            observations.extend(
                _make_metric_pair(
                    period_start=period_start,
                    period_end=period_end,
                    area_scope="province",
                    area_code=area_code,
                    area_name=area_name,
                    market_stage=stage,
                    energy=energy,
                    price=price,
                )
            )
    return observations


def _make_metric_pair(
    *,
    period_start: date,
    period_end: date,
    area_scope: str,
    area_code: str,
    area_name: str,
    market_stage: str,
    energy: str,
    price: str,
) -> list[NormalizedMarketObservation]:
    return [
        NormalizedMarketObservation(
            period_start=period_start,
            period_end=period_end,
            area_scope=area_scope,
            area_code=area_code,
            area_name=area_name,
            market_stage=market_stage,
            participant_side=GENERATION_SIDE,
            metric="average_traded_energy",
            value=Decimal(energy),
            unit="100_million_kwh",
            settlement_status=PRELIMINARY_FLASH,
            data_mode=PUBLIC_OBSERVED,
        ),
        NormalizedMarketObservation(
            period_start=period_start,
            period_end=period_end,
            area_scope=area_scope,
            area_code=area_code,
            area_name=area_name,
            market_stage=market_stage,
            participant_side=GENERATION_SIDE,
            metric="weighted_average_price",
            value=Decimal(price),
            unit="cny_per_mwh",
            settlement_status=PRELIMINARY_FLASH,
            data_mode=PUBLIC_OBSERVED,
        ),
    ]
