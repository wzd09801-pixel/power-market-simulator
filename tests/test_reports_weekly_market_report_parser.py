from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from backend.app.adapters.reports_weekly_market_report import (
    ReportsWeeklyMarketReportParserError,
    parse_reports_weekly_market_report,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "reports_weekly_market_report_example.html"


def test_parse_reports_weekly_market_report_normalizes_region_and_provinces() -> None:
    result = parse_reports_weekly_market_report(FIXTURE_PATH.read_text(encoding="utf-8"))

    assert result.parser_key == "reports_weekly_market_report"
    assert result.parser_version == "v1"
    assert len(result.observations) == 24
    assert result.has_unparsed_power_type_section is True

    values = {
        (item.area_code, item.market_stage, item.metric): item.value for item in result.observations
    }
    assert values[("SOUTHERN_REGION", "day_ahead", "weighted_average_price")] == Decimal("334")
    assert values[("GD", "day_ahead", "average_traded_energy")] == Decimal("18.04")
    assert values[("GD", "real_time", "weighted_average_price")] == Decimal("416")
    assert result.observations[0].period_start.isoformat() == "2026-05-18"
    assert result.observations[0].period_end.isoformat() == "2026-05-24"
    assert result.observations[0].settlement_status == "preliminary_flash"


def test_parse_reports_weekly_market_report_rejects_incomplete_province_section() -> None:
    raw_html = FIXTURE_PATH.read_text(encoding="utf-8").replace(
        "实时市场，示例甲省、示例乙省、示例丙省、示例丁省、示例戊省",
        "实时市场，示例甲省、示例乙省、示例丙省、示例丁省",
    )

    with pytest.raises(ReportsWeeklyMarketReportParserError) as exc_info:
        parse_reports_weekly_market_report(raw_html)

    assert exc_info.value.code == "reports_weekly_report_province_sections_missing"
