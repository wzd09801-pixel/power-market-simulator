from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from backend.app.adapters.open_meteo import NormalizedWeatherRecord
from backend.app.services.weather_features import derive_hydro_weather_features


def records_for_hours(hours: int) -> tuple[NormalizedWeatherRecord, ...]:
    issue_time = datetime(2026, 6, 1, 8, tzinfo=ZoneInfo("Asia/Shanghai"))
    start = datetime(2026, 6, 2, tzinfo=ZoneInfo("Asia/Shanghai"))
    records: list[NormalizedWeatherRecord] = []
    for hour in range(hours):
        forecast_time = start + timedelta(hours=hour)
        for variable, value, unit in (
            ("precipitation", 1.0, "mm"),
            ("rain", 0.5, "mm"),
            ("temperature_2m", 20.0 + hour % 5, "C"),
        ):
            records.append(
                NormalizedWeatherRecord(
                    content_hash=f"{variable}_{hour}",
                    issue_time=issue_time,
                    forecast_time=forecast_time,
                    variable=variable,
                    value=value,
                    unit=unit,
                )
            )
    return tuple(records)


def test_complete_weather_series_derives_hydro_features_with_evidence() -> None:
    draft = derive_hydro_weather_features(
        records_for_hours(72),
        provider="open_meteo",
        location_id="demo_hydro_a_reference",
        raw_payload_id="raw_payload",
        source_quality_status="valid",
    )

    assert draft.quality_status == "valid"
    assert draft.features["precipitation_sum_24h"] == 24.0
    assert draft.features["precipitation_sum_72h"] == 72.0
    assert draft.features["rain_sum_72h"] == 36.0
    assert draft.features["temperature_min_24h"] == 20.0
    assert draft.features["temperature_max_24h"] == 24.0
    assert len(draft.evidence) == 7
    assert not draft.missing_data_warnings


def test_incomplete_weather_series_does_not_publish_partial_aggregates() -> None:
    draft = derive_hydro_weather_features(
        records_for_hours(24),
        provider="open_meteo",
        location_id="demo_hydro_a_reference",
        raw_payload_id="raw_payload",
        source_quality_status="valid",
    )

    assert draft.quality_status == "warning"
    assert draft.features["precipitation_sum_24h"] == 24.0
    assert draft.features["precipitation_sum_72h"] is None
    assert draft.features["rain_sum_72h"] is None
    assert len(draft.missing_data_warnings) == 2
