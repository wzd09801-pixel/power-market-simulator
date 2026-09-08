from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import pytest
import requests

from backend.app.adapters.open_meteo import (
    OpenMeteoAdapterError,
    OpenMeteoClient,
    OpenMeteoForecastQuery,
)


class FakeResponse:
    def __init__(self, *, text: str, status_code: int = 200) -> None:
        self.text = text
        self.status_code = status_code


class FakeSession:
    def __init__(self, outcomes: list[FakeResponse | requests.RequestException]) -> None:
        self.outcomes = outcomes
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, *, params: Mapping[str, str], timeout: float) -> FakeResponse:
        self.calls.append({"url": url, "params": dict(params), "timeout": timeout})
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, requests.RequestException):
            raise outcome
        return outcome


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


def query() -> OpenMeteoForecastQuery:
    return OpenMeteoForecastQuery(
        location_id="demo_hydro_a_reference",
        latitude=30.0,
        longitude=110.0,
        timezone="Asia/Shanghai",
        forecast_days=1,
        hourly_variables=("temperature_2m", "precipitation"),
    )


def test_open_meteo_adapter_normalizes_hourly_records() -> None:
    session = FakeSession([FakeResponse(text=json.dumps(sample_payload()))])
    client = OpenMeteoClient(
        forecast_url="https://api.open-meteo.com/v1/forecast",
        timeout_seconds=3.0,
        max_retries=0,
        retry_backoff_seconds=0,
        session=session,
    )

    result = client.fetch_forecast(
        query(),
        issue_time=datetime(2026, 6, 1, 8, tzinfo=ZoneInfo("Asia/Shanghai")),
    )

    assert len(result.records) == 4
    assert result.records[2].variable == "precipitation"
    assert result.records[3].value == 1.4
    assert result.records[3].unit == "mm"
    assert result.records[3].forecast_time.isoformat() == "2026-06-01T01:00:00+08:00"
    assert session.calls[0]["timeout"] == 3.0
    assert session.calls[0]["params"]["hourly"] == "temperature_2m,precipitation"


@pytest.mark.parametrize(
    ("raw_content", "expected_code"),
    [
        ("", "open_meteo_empty_response"),
        ("{", "open_meteo_parse_error"),
        (
            json.dumps(
                {
                    "timezone": "Asia/Shanghai",
                    "hourly_units": {"temperature_2m": "C", "precipitation": "mm"},
                    "hourly": {"time": [], "temperature_2m": [], "precipitation": []},
                }
            ),
            "open_meteo_validation_error",
        ),
    ],
)
def test_open_meteo_adapter_rejects_invalid_responses(
    raw_content: str,
    expected_code: str,
) -> None:
    client = OpenMeteoClient(
        forecast_url="https://api.open-meteo.com/v1/forecast",
        timeout_seconds=3.0,
        max_retries=0,
        retry_backoff_seconds=0,
        session=FakeSession([FakeResponse(text=raw_content)]),
    )

    with pytest.raises(OpenMeteoAdapterError) as raised:
        client.fetch_forecast(
            query(),
            issue_time=datetime(2026, 6, 1, 8, tzinfo=ZoneInfo("Asia/Shanghai")),
        )

    assert raised.value.code == expected_code


def test_open_meteo_adapter_retries_timeout_then_returns_structured_error() -> None:
    session = FakeSession(
        [
            requests.Timeout("first timeout"),
            requests.Timeout("second timeout"),
            requests.Timeout("third timeout"),
        ]
    )
    delays: list[float] = []
    client = OpenMeteoClient(
        forecast_url="https://api.open-meteo.com/v1/forecast",
        timeout_seconds=3.0,
        max_retries=2,
        retry_backoff_seconds=0.25,
        session=session,
        sleep=delays.append,
    )

    with pytest.raises(OpenMeteoAdapterError) as raised:
        client.fetch_forecast(
            query(),
            issue_time=datetime(2026, 6, 1, 8, tzinfo=ZoneInfo("Asia/Shanghai")),
        )

    assert raised.value.code == "open_meteo_network_error"
    assert len(session.calls) == 3
    assert delays == [0.25, 0.5]


def test_open_meteo_adapter_preserves_local_missing_value_for_quality_review() -> None:
    payload = sample_payload()
    payload["hourly"]["precipitation"][1] = None  # type: ignore[index]
    client = OpenMeteoClient(
        forecast_url="https://api.open-meteo.com/v1/forecast",
        timeout_seconds=3.0,
        max_retries=0,
        retry_backoff_seconds=0,
        session=FakeSession([FakeResponse(text=json.dumps(payload))]),
    )

    result = client.fetch_forecast(
        query(),
        issue_time=datetime(2026, 6, 1, 8, tzinfo=ZoneInfo("Asia/Shanghai")),
    )

    assert result.records[3].value is None
    assert result.records[3].quality_flag == "missing_value"


def test_open_meteo_adapter_rejects_non_standard_json_numeric_constant() -> None:
    raw_content = json.dumps(sample_payload()).replace("20.5", "NaN")
    client = OpenMeteoClient(
        forecast_url="https://api.open-meteo.com/v1/forecast",
        timeout_seconds=3.0,
        max_retries=0,
        retry_backoff_seconds=0,
        session=FakeSession([FakeResponse(text=raw_content)]),
    )

    with pytest.raises(OpenMeteoAdapterError) as raised:
        client.fetch_forecast(
            query(),
            issue_time=datetime(2026, 6, 1, 8, tzinfo=ZoneInfo("Asia/Shanghai")),
        )

    assert raised.value.code == "open_meteo_parse_error"
