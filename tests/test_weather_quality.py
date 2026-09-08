from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from backend.app.adapters.open_meteo import NormalizedWeatherRecord
from backend.app.services.weather_quality import assess_weather_records


def record(
    *,
    variable: str,
    value: float | None,
    hour: int,
    quality_flag: str = "valid",
) -> NormalizedWeatherRecord:
    return NormalizedWeatherRecord(
        content_hash=f"{variable}_{hour}",
        issue_time=datetime(2026, 6, 1, 8, tzinfo=ZoneInfo("Asia/Shanghai")),
        forecast_time=datetime(2026, 6, 1, tzinfo=ZoneInfo("Asia/Shanghai"))
        + timedelta(hours=hour),
        variable=variable,
        value=value,
        unit="mm" if variable in {"precipitation", "rain"} else "C",
        quality_flag=quality_flag,
    )


def test_quality_assessment_marks_missing_outlier_gap_and_inconsistent_rain() -> None:
    records = (
        record(variable="temperature_2m", value=99.0, hour=0),
        record(variable="precipitation", value=1.0, hour=0),
        record(variable="rain", value=2.0, hour=0),
        record(variable="temperature_2m", value=20.0, hour=2),
        record(variable="precipitation", value=None, hour=2, quality_flag="missing_value"),
        record(variable="rain", value=0.0, hour=2),
    )

    assessment = assess_weather_records(records)

    assert assessment.quality_status == "warning"
    assert {issue.issue_code for issue in assessment.issues} == {
        "unexpected_hourly_interval",
        "out_of_range",
        "missing_value",
        "inconsistent_precipitation_components",
    }
    assert assessment.records[0].quality_flag == "suspect_out_of_range"
    assert assessment.records[4].quality_flag == "missing_value"


def test_quality_assessment_marks_unexpected_unit_before_applying_range_rule() -> None:
    source = record(variable="temperature_2m", value=30.0, hour=0)
    assessment = assess_weather_records((replace(source, unit="F"),))

    assert assessment.quality_status == "warning"
    assert assessment.records[0].quality_flag == "suspect_unexpected_unit"
    assert assessment.issues[0].issue_code == "unexpected_unit"
