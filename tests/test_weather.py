from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, cast

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.adapters.open_meteo import OpenMeteoClient
from backend.app.models.weather import (
    WeatherFeatureReview,
    WeatherFeatureSnapshot,
    WeatherIngestionRun,
    WeatherLocation,
    WeatherQualityIssue,
    WeatherRawPayload,
    WeatherRecord,
)
from backend.app.services.weather import get_open_meteo_client


class RepeatingResponse:
    status_code = 200

    def __init__(self, payload: dict[str, object] | str) -> None:
        self.text = payload if isinstance(payload, str) else json.dumps(payload)


class RepeatingSession:
    def __init__(self, payload: dict[str, object] | str) -> None:
        self.response = RepeatingResponse(payload)
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, *, params: Mapping[str, str], timeout: float) -> RepeatingResponse:
        self.calls.append({"url": url, "params": dict(params), "timeout": timeout})
        return self.response


def sample_payload() -> dict[str, object]:
    return {
        "latitude": 30.0,
        "longitude": 110.0,
        "timezone": "Asia/Shanghai",
        "hourly_units": {
            "time": "iso8601",
            "temperature_2m": "C",
            "precipitation": "mm",
        },
        "hourly": {
            "time": ["2026-06-01T00:00", "2026-06-01T01:00"],
            "temperature_2m": [20.5, 21.0],
            "precipitation": [0.0, 1.4],
        },
    }


def complete_feature_payload() -> dict[str, object]:
    times = [f"2026-06-{1 + hour // 24:02d}T{hour % 24:02d}:00" for hour in range(72)]
    return {
        "latitude": 30.0,
        "longitude": 110.0,
        "timezone": "Asia/Shanghai",
        "hourly_units": {
            "time": "iso8601",
            "temperature_2m": "C",
            "precipitation": "mm",
            "rain": "mm",
        },
        "hourly": {
            "time": times,
            "temperature_2m": [22.0] * 72,
            "precipitation": [1.0] * 72,
            "rain": [0.5] * 72,
        },
    }


def request_payload() -> dict[str, object]:
    return {
        "location_id": "demo_hydro_a_reference",
        "location_name": "Demo Hydro A public reference point",
        "latitude": 30.0,
        "longitude": 110.0,
        "timezone": "Asia/Shanghai",
        "forecast_days": 1,
        "hourly_variables": ["temperature_2m", "precipitation"],
    }


def build_client(payload: dict[str, object] | str) -> OpenMeteoClient:
    return OpenMeteoClient(
        forecast_url="https://api.open-meteo.com/v1/forecast",
        timeout_seconds=3.0,
        max_retries=0,
        retry_backoff_seconds=0,
        session=RepeatingSession(payload),
    )


def override_open_meteo_client(client: TestClient, open_meteo_client: OpenMeteoClient) -> None:
    cast(FastAPI, client.app).dependency_overrides[get_open_meteo_client] = lambda: (
        open_meteo_client
    )


def test_weather_ingestion_persists_raw_payload_records_and_deduplicates(
    client: TestClient,
    db_session_factory: sessionmaker[Session],
) -> None:
    override_open_meteo_client(client, build_client(sample_payload()))

    first = client.post("/v1/weather/open-meteo/forecast", json=request_payload())
    second = client.post("/v1/weather/open-meteo/forecast", json=request_payload())

    assert first.status_code == 200
    assert first.json()["records_received"] == 4
    assert first.json()["records_inserted"] == 4
    assert first.json()["duplicate_records"] == 0
    assert first.json()["quality_status"] == "valid"
    assert first.json()["quality_issue_count"] == 0
    assert first.json()["data_mode"] == "public_observed"
    assert second.status_code == 200
    assert second.json()["records_received"] == 4
    assert second.json()["records_inserted"] == 0
    assert second.json()["duplicate_records"] == 4

    feature_response = client.get(
        "/v1/weather/features/latest",
        params={"location_id": "demo_hydro_a_reference"},
    )
    assert feature_response.status_code == 200
    assert feature_response.json()["data_mode"] == "public_derived"
    assert feature_response.json()["quality_status"] == "warning"

    records = client.get(
        "/v1/weather/records",
        params={"location_id": "demo_hydro_a_reference", "variable": "precipitation"},
    )
    assert records.status_code == 200
    assert len(records.json()["items"]) == 2
    assert {item["data_mode"] for item in records.json()["items"]} == {"public_observed"}

    with db_session_factory() as session:
        location_count = session.scalar(select(func.count()).select_from(WeatherLocation))
        raw_payload_count = session.scalar(select(func.count()).select_from(WeatherRawPayload))
        ingestion_run_count = session.scalar(select(func.count()).select_from(WeatherIngestionRun))
        weather_record_count = session.scalar(select(func.count()).select_from(WeatherRecord))
        feature_snapshot_count = session.scalar(
            select(func.count()).select_from(WeatherFeatureSnapshot)
        )

    assert location_count == 1
    assert raw_payload_count == 1
    assert ingestion_run_count == 2
    assert weather_record_count == 4
    assert feature_snapshot_count == 1


def test_weather_ingestion_preserves_malformed_raw_payload_and_failed_run(
    client: TestClient,
    db_session_factory: sessionmaker[Session],
) -> None:
    override_open_meteo_client(client, build_client("{"))

    response = client.post("/v1/weather/open-meteo/forecast", json=request_payload())

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "open_meteo_parse_error"

    with db_session_factory() as session:
        run = session.scalar(select(WeatherIngestionRun))
        raw_payload = session.scalar(select(WeatherRawPayload))

    assert run is not None
    assert run.status == "failed"
    assert run.error_code == "open_meteo_parse_error"
    assert raw_payload is not None
    assert raw_payload.raw_content == "{"
    assert raw_payload.quality_flag == "invalid"


def test_weather_location_identity_cannot_be_silently_remapped(client: TestClient) -> None:
    override_open_meteo_client(client, build_client(sample_payload()))
    created = client.post("/v1/weather/open-meteo/forecast", json=request_payload())
    remapped_payload = {**request_payload(), "latitude": 25.5}

    response = client.post("/v1/weather/open-meteo/forecast", json=remapped_payload)

    assert created.status_code == 200
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "weather_location_conflict"


def test_weather_ingestion_rejects_unsupported_variable(client: TestClient) -> None:
    payload = {**request_payload(), "hourly_variables": ["temperature_2m", "unsupported"]}

    response = client.post("/v1/weather/open-meteo/forecast", json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_weather_ingestion_persists_local_quality_issues(
    client: TestClient,
    db_session_factory: sessionmaker[Session],
) -> None:
    payload = sample_payload()
    payload["hourly"]["temperature_2m"][0] = 99.0  # type: ignore[index]
    payload["hourly"]["precipitation"][1] = None  # type: ignore[index]
    override_open_meteo_client(client, build_client(payload))

    response = client.post("/v1/weather/open-meteo/forecast", json=request_payload())

    assert response.status_code == 200
    assert response.json()["quality_status"] == "warning"
    assert response.json()["quality_issue_count"] == 2

    records = client.get(
        "/v1/weather/records",
        params={"location_id": "demo_hydro_a_reference"},
    )
    assert records.status_code == 200
    assert {item["quality_flag"] for item in records.json()["items"]} >= {
        "missing_value",
        "suspect_out_of_range",
    }

    with db_session_factory() as session:
        issues = list(session.scalars(select(WeatherQualityIssue)))

    assert {issue.issue_code for issue in issues} == {"missing_value", "out_of_range"}
    assert {issue.data_mode for issue in issues} == {"public_derived"}

    issue_response = client.get(
        "/v1/weather/quality/issues",
        params={"location_id": "demo_hydro_a_reference", "issue_code": "missing_value"},
    )
    assert issue_response.status_code == 200
    assert len(issue_response.json()["items"]) == 1
    assert issue_response.json()["items"][0]["issue_code"] == "missing_value"


def test_latest_weather_features_returns_stable_not_found_error(client: TestClient) -> None:
    response = client.get(
        "/v1/weather/features/latest",
        params={"location_id": "missing_reference"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "weather_feature_snapshot_not_found"


def test_weather_feature_review_package_valid_snapshot_is_read_only(
    client: TestClient,
    db_session_factory: sessionmaker[Session],
) -> None:
    override_open_meteo_client(client, build_client(complete_feature_payload()))
    payload = {
        **request_payload(),
        "forecast_days": 3,
        "hourly_variables": ["temperature_2m", "precipitation", "rain"],
    }
    ingestion = client.post("/v1/weather/open-meteo/forecast", json=payload)
    feature_snapshot_id = ingestion.json()["feature_snapshot_id"]
    with db_session_factory() as session:
        before_counts = _weather_counts(session)

    response = client.get(f"/v1/weather/features/{feature_snapshot_id}/review-package")

    with db_session_factory() as session:
        after_counts = _weather_counts(session)
    assert ingestion.status_code == 200
    assert response.status_code == 200
    assert before_counts == after_counts
    body = response.json()
    assert body["package_version"] == "weather_feature_review_package_v1"
    assert body["snapshot"]["feature_snapshot_id"] == feature_snapshot_id
    assert body["quality_issue_summary"] == {
        "total_count": 0,
        "severity_counts": {},
        "issue_code_counts": {},
        "displayed_issue_count": 0,
    }
    assert body["approval"]["can_approve"] is True
    assert body["approval"]["blockers"] == []
    assert body["no_auto_trading"] is True
    assert body["recommendation_chain_requires_approved_snapshot"] is True
    assert body["network_probe_performed"] is False
    assert body["fetch_performed"] is False


def test_weather_feature_review_package_reports_quality_blockers(
    client: TestClient,
    db_session_factory: sessionmaker[Session],
) -> None:
    payload = sample_payload()
    payload["hourly"]["temperature_2m"][0] = 99.0  # type: ignore[index]
    payload["hourly"]["precipitation"][1] = None  # type: ignore[index]
    override_open_meteo_client(client, build_client(payload))
    ingestion = client.post("/v1/weather/open-meteo/forecast", json=request_payload())
    feature_snapshot_id = ingestion.json()["feature_snapshot_id"]
    review = client.post(
        f"/v1/weather/features/{feature_snapshot_id}/reviews",
        json={"review_status": "needs_revision", "note": "Quality issues need review."},
    )
    with db_session_factory() as session:
        before_counts = _weather_counts(session)

    response = client.get(f"/v1/weather/features/{feature_snapshot_id}/review-package")

    with db_session_factory() as session:
        after_counts = _weather_counts(session)
    assert ingestion.status_code == 200
    assert review.status_code == 200
    assert response.status_code == 200
    assert before_counts == after_counts
    body = response.json()
    assert body["quality_issue_summary"]["total_count"] == 2
    assert body["quality_issue_summary"]["issue_code_counts"] == {
        "out_of_range": 1,
        "missing_value": 1,
    }
    assert body["approval"]["can_approve"] is False
    assert any(
        "required derived features are missing" in item for item in body["approval"]["blockers"]
    )
    assert body["reviews"][0]["review_status"] == "needs_revision"


def test_weather_feature_review_package_missing_snapshot_returns_error(client: TestClient) -> None:
    response = client.get("/v1/weather/features/missing_snapshot/review-package")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "weather_feature_snapshot_not_found"


def test_valid_weather_feature_snapshot_can_be_approved(
    client: TestClient,
    db_session_factory: sessionmaker[Session],
) -> None:
    override_open_meteo_client(client, build_client(complete_feature_payload()))
    payload = {
        **request_payload(),
        "forecast_days": 3,
        "hourly_variables": ["temperature_2m", "precipitation", "rain"],
    }
    ingestion = client.post("/v1/weather/open-meteo/forecast", json=payload)
    feature_snapshot_id = ingestion.json()["feature_snapshot_id"]

    response = client.post(
        f"/v1/weather/features/{feature_snapshot_id}/reviews",
        json={"review_status": "approved", "note": "Reviewed public reference-point features."},
    )

    assert ingestion.status_code == 200
    assert ingestion.json()["quality_status"] == "valid"
    assert response.status_code == 200
    assert response.json()["review_status"] == "approved"

    latest = client.get(
        "/v1/weather/features/latest",
        params={"location_id": "demo_hydro_a_reference"},
    )
    assert latest.status_code == 200
    assert latest.json()["human_review_status"] == "approved"
    assert latest.json()["forecast_start"] == "2026-06-01T00:00:00"

    with db_session_factory() as session:
        review_count = session.scalar(select(func.count()).select_from(WeatherFeatureReview))

    assert review_count == 1


def test_weather_feature_snapshot_with_quality_warning_cannot_be_approved(
    client: TestClient,
) -> None:
    override_open_meteo_client(client, build_client(sample_payload()))
    ingestion = client.post("/v1/weather/open-meteo/forecast", json=request_payload())
    feature_snapshot_id = ingestion.json()["feature_snapshot_id"]

    response = client.post(
        f"/v1/weather/features/{feature_snapshot_id}/reviews",
        json={"review_status": "approved", "note": "Attempt approval."},
    )

    assert ingestion.status_code == 200
    assert ingestion.json()["quality_status"] == "valid"
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "weather_feature_snapshot_not_usable"


def _weather_counts(session: Session) -> dict[str, int]:
    return {
        "ingestion_runs": int(
            session.scalar(select(func.count()).select_from(WeatherIngestionRun)) or 0
        ),
        "raw_payloads": int(
            session.scalar(select(func.count()).select_from(WeatherRawPayload)) or 0
        ),
        "records": int(session.scalar(select(func.count()).select_from(WeatherRecord)) or 0),
        "quality_issues": int(
            session.scalar(select(func.count()).select_from(WeatherQualityIssue)) or 0
        ),
        "feature_snapshots": int(
            session.scalar(select(func.count()).select_from(WeatherFeatureSnapshot)) or 0
        ),
        "feature_reviews": int(
            session.scalar(select(func.count()).select_from(WeatherFeatureReview)) or 0
        ),
    }
