from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from itertools import pairwise
from math import isfinite

from backend.app.adapters.open_meteo import NormalizedWeatherRecord

VARIABLE_BOUNDS: dict[str, tuple[float, float]] = {
    "temperature_2m": (-80.0, 60.0),
    "precipitation": (0.0, 500.0),
    "rain": (0.0, 500.0),
    "weather_code": (0.0, 99.0),
    "cloud_cover": (0.0, 100.0),
    "wind_speed_10m": (0.0, 150.0),
}
EXPECTED_UNITS: dict[str, frozenset[str]] = {
    "temperature_2m": frozenset({"C", "\N{DEGREE SIGN}C"}),
    "precipitation": frozenset({"mm"}),
    "rain": frozenset({"mm"}),
    "weather_code": frozenset({"wmo code"}),
    "cloud_cover": frozenset({"%"}),
    "wind_speed_10m": frozenset({"km/h"}),
}


@dataclass(frozen=True)
class WeatherQualityIssueDraft:
    issue_code: str
    severity: str
    message: str
    variable: str | None = None
    forecast_time: datetime | None = None
    record_content_hash: str | None = None
    details: dict[str, object] | None = None


@dataclass(frozen=True)
class WeatherQualityAssessment:
    records: tuple[NormalizedWeatherRecord, ...]
    issues: tuple[WeatherQualityIssueDraft, ...]
    quality_status: str


def assess_weather_records(
    records: tuple[NormalizedWeatherRecord, ...],
) -> WeatherQualityAssessment:
    issues = _assess_hourly_continuity(records)
    assessed_records: list[NormalizedWeatherRecord] = []

    for record in records:
        quality_flag = record.quality_flag
        if record.value is None:
            issues.append(
                WeatherQualityIssueDraft(
                    issue_code="missing_value",
                    severity="error",
                    message=f"Weather variable '{record.variable}' is missing an hourly value.",
                    variable=record.variable,
                    forecast_time=record.forecast_time,
                    record_content_hash=record.content_hash,
                )
            )
        elif not isfinite(record.value):
            quality_flag = "invalid_non_finite"
            issues.append(
                WeatherQualityIssueDraft(
                    issue_code="non_finite_value",
                    severity="error",
                    message=f"Weather variable '{record.variable}' contains a non-finite value.",
                    variable=record.variable,
                    forecast_time=record.forecast_time,
                    record_content_hash=record.content_hash,
                    details={"value": str(record.value)},
                )
            )
        elif not _uses_expected_unit(record.variable, record.unit):
            quality_flag = "suspect_unexpected_unit"
            issues.append(
                WeatherQualityIssueDraft(
                    issue_code="unexpected_unit",
                    severity="warning",
                    message=f"Weather variable '{record.variable}' uses an unexpected unit.",
                    variable=record.variable,
                    forecast_time=record.forecast_time,
                    record_content_hash=record.content_hash,
                    details={"unit": record.unit},
                )
            )
        elif _is_out_of_range(record.variable, record.value):
            quality_flag = "suspect_out_of_range"
            lower, upper = VARIABLE_BOUNDS[record.variable]
            issues.append(
                WeatherQualityIssueDraft(
                    issue_code="out_of_range",
                    severity="warning",
                    message=f"Weather variable '{record.variable}' is outside its review range.",
                    variable=record.variable,
                    forecast_time=record.forecast_time,
                    record_content_hash=record.content_hash,
                    details={"value": record.value, "minimum": lower, "maximum": upper},
                )
            )
        elif record.variable == "weather_code" and not record.value.is_integer():
            quality_flag = "suspect_invalid_discrete_value"
            issues.append(
                WeatherQualityIssueDraft(
                    issue_code="invalid_discrete_value",
                    severity="warning",
                    message="Weather code must be an integer WMO interpretation code.",
                    variable=record.variable,
                    forecast_time=record.forecast_time,
                    record_content_hash=record.content_hash,
                    details={"value": record.value},
                )
            )
        assessed_records.append(replace(record, quality_flag=quality_flag))

    issues.extend(_assess_precipitation_consistency(tuple(assessed_records)))
    return WeatherQualityAssessment(
        records=tuple(assessed_records),
        issues=tuple(issues),
        quality_status="warning" if issues else "valid",
    )


def _assess_hourly_continuity(
    records: tuple[NormalizedWeatherRecord, ...],
) -> list[WeatherQualityIssueDraft]:
    forecast_times = sorted({record.forecast_time for record in records})
    issues: list[WeatherQualityIssueDraft] = []
    for previous, current in pairwise(forecast_times):
        interval = current - previous
        if interval != timedelta(hours=1):
            issues.append(
                WeatherQualityIssueDraft(
                    issue_code="unexpected_hourly_interval",
                    severity="error",
                    message="Weather forecast timestamps are not a continuous hourly series.",
                    forecast_time=current,
                    details={
                        "previous_forecast_time": previous.isoformat(),
                        "interval_seconds": interval.total_seconds(),
                    },
                )
            )
    return issues


def _assess_precipitation_consistency(
    records: tuple[NormalizedWeatherRecord, ...],
) -> list[WeatherQualityIssueDraft]:
    values: dict[tuple[datetime, str], NormalizedWeatherRecord] = {
        (record.forecast_time, record.variable): record for record in records
    }
    issues: list[WeatherQualityIssueDraft] = []
    forecast_times = sorted({record.forecast_time for record in records})
    for forecast_time in forecast_times:
        precipitation = values.get((forecast_time, "precipitation"))
        rain = values.get((forecast_time, "rain"))
        if (
            precipitation is None
            or rain is None
            or precipitation.value is None
            or rain.value is None
            or rain.value <= precipitation.value + 1e-9
        ):
            continue
        issues.append(
            WeatherQualityIssueDraft(
                issue_code="inconsistent_precipitation_components",
                severity="warning",
                message="Hourly rain exceeds total hourly precipitation.",
                variable="rain",
                forecast_time=forecast_time,
                record_content_hash=rain.content_hash,
                details={"rain": rain.value, "precipitation": precipitation.value},
            )
        )
    return issues


def _is_out_of_range(variable: str, value: float) -> bool:
    bounds = VARIABLE_BOUNDS.get(variable)
    return bounds is not None and not bounds[0] <= value <= bounds[1]


def _uses_expected_unit(variable: str, unit: str) -> bool:
    expected_units = EXPECTED_UNITS.get(variable)
    return expected_units is None or unit in expected_units
