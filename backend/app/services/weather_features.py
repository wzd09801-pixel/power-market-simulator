from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
from statistics import mean

from backend.app.adapters.open_meteo import NormalizedWeatherRecord

FEATURE_VERSION = "hydro_weather_v1"


@dataclass(frozen=True)
class WeatherFeatureSpec:
    field: str
    variable: str
    hours: int
    formula: str
    aggregate: Callable[[list[float]], float]


@dataclass(frozen=True)
class WeatherFeatureDraft:
    content_hash: str
    feature_version: str
    forecast_start: datetime
    quality_status: str
    features: dict[str, float | None]
    evidence: list[dict[str, object]]
    missing_data_warnings: list[str]


FEATURE_SPECS = (
    WeatherFeatureSpec(
        field="precipitation_sum_24h",
        variable="precipitation",
        hours=24,
        formula="sum",
        aggregate=sum,
    ),
    WeatherFeatureSpec(
        field="precipitation_sum_72h",
        variable="precipitation",
        hours=72,
        formula="sum",
        aggregate=sum,
    ),
    WeatherFeatureSpec(
        field="rain_sum_24h",
        variable="rain",
        hours=24,
        formula="sum",
        aggregate=sum,
    ),
    WeatherFeatureSpec(
        field="rain_sum_72h",
        variable="rain",
        hours=72,
        formula="sum",
        aggregate=sum,
    ),
    WeatherFeatureSpec(
        field="temperature_mean_24h",
        variable="temperature_2m",
        hours=24,
        formula="mean",
        aggregate=mean,
    ),
    WeatherFeatureSpec(
        field="temperature_min_24h",
        variable="temperature_2m",
        hours=24,
        formula="minimum",
        aggregate=min,
    ),
    WeatherFeatureSpec(
        field="temperature_max_24h",
        variable="temperature_2m",
        hours=24,
        formula="maximum",
        aggregate=max,
    ),
)
REQUIRED_HYDRO_WEATHER_FEATURES = frozenset(spec.field for spec in FEATURE_SPECS)


def derive_hydro_weather_features(
    records: tuple[NormalizedWeatherRecord, ...],
    *,
    provider: str,
    location_id: str,
    raw_payload_id: str,
    source_quality_status: str,
) -> WeatherFeatureDraft:
    window_start = min(record.forecast_time for record in records)
    features: dict[str, float | None] = {}
    evidence: list[dict[str, object]] = []
    warnings: list[str] = []

    for spec in FEATURE_SPECS:
        value, source_records, warning = _derive_feature(records, spec=spec, start=window_start)
        features[spec.field] = value
        if warning is not None:
            warnings.append(warning)
            continue
        evidence.append(
            {
                "source": provider,
                "source_type": "weather_api",
                "data_mode": "public_observed",
                "field": spec.field,
                "value": value,
                "unit": source_records[0].unit,
                "formula": spec.formula,
                "window_start": window_start.isoformat(),
                "window_end": (window_start + timedelta(hours=spec.hours)).isoformat(),
                "raw_payload_id": raw_payload_id,
                "source_record_ids": [record.content_hash for record in source_records],
            }
        )

    quality_status = "warning" if warnings or source_quality_status != "valid" else "valid"
    content_hash = _hash_json(
        {
            "provider": provider,
            "location_id": location_id,
            "raw_payload_id": raw_payload_id,
            "feature_version": FEATURE_VERSION,
            "forecast_start": window_start.isoformat(),
            "features": features,
            "missing_data_warnings": warnings,
        }
    )
    return WeatherFeatureDraft(
        content_hash=content_hash,
        feature_version=FEATURE_VERSION,
        forecast_start=window_start,
        quality_status=quality_status,
        features=features,
        evidence=evidence,
        missing_data_warnings=warnings,
    )


def _derive_feature(
    records: tuple[NormalizedWeatherRecord, ...],
    *,
    spec: WeatherFeatureSpec,
    start: datetime,
) -> tuple[float | None, list[NormalizedWeatherRecord], str | None]:
    expected_times = {start + timedelta(hours=offset) for offset in range(spec.hours)}
    by_time = {
        record.forecast_time: record
        for record in records
        if record.variable == spec.variable and record.forecast_time in expected_times
    }
    source_records = [by_time[forecast_time] for forecast_time in sorted(by_time)]

    if len(source_records) != spec.hours:
        return (
            None,
            source_records,
            f"{spec.field} requires {spec.hours} complete hourly '{spec.variable}' values.",
        )
    if any(record.value is None or record.quality_flag != "valid" for record in source_records):
        return (
            None,
            source_records,
            f"{spec.field} was not derived because its source values require review.",
        )

    units = {record.unit for record in source_records}
    if len(units) != 1:
        return (
            None,
            source_records,
            f"{spec.field} was not derived because its source units are inconsistent.",
        )

    values = [record.value for record in source_records if record.value is not None]
    return float(spec.aggregate(values)), source_records, None


def _hash_json(value: object) -> str:
    serialized = json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return sha256(serialized.encode("utf-8")).hexdigest()
