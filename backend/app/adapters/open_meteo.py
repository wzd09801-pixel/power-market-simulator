from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import Any, Protocol, cast
from urllib.parse import urlencode
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests

logger = logging.getLogger(__name__)

RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


class HttpResponse(Protocol):
    status_code: int
    text: str


class HttpSession(Protocol):
    def get(
        self,
        url: str,
        *,
        params: Mapping[str, str],
        timeout: float,
    ) -> HttpResponse: ...


@dataclass(frozen=True)
class OpenMeteoForecastQuery:
    location_id: str
    latitude: float
    longitude: float
    timezone: str
    forecast_days: int
    hourly_variables: tuple[str, ...]


@dataclass(frozen=True)
class NormalizedWeatherRecord:
    content_hash: str
    issue_time: datetime
    forecast_time: datetime
    variable: str
    value: float | None
    unit: str
    quality_flag: str = "valid"


@dataclass(frozen=True)
class OpenMeteoFetchResult:
    provider: str
    request_url: str
    request_params: dict[str, str]
    raw_content: str
    payload_json: dict[str, Any]
    payload_hash: str
    records: tuple[NormalizedWeatherRecord, ...]


class OpenMeteoAdapterError(Exception):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        request_url: str,
        request_params: dict[str, str],
        raw_content: str | None = None,
        payload_json: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.request_url = request_url
        self.request_params = request_params
        self.raw_content = raw_content
        self.payload_json = payload_json


class OpenMeteoClient:
    provider = "open_meteo"

    def __init__(
        self,
        *,
        forecast_url: str,
        timeout_seconds: float,
        max_retries: int,
        retry_backoff_seconds: float,
        session: HttpSession | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._forecast_url = forecast_url
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._retry_backoff_seconds = retry_backoff_seconds
        self._session = session or cast(HttpSession, requests.Session())
        self._sleep = sleep

    def fetch_forecast(
        self,
        query: OpenMeteoForecastQuery,
        *,
        issue_time: datetime,
    ) -> OpenMeteoFetchResult:
        params = self._build_params(query)
        request_url = f"{self._forecast_url}?{urlencode(sorted(params.items()))}"
        response = self._request_with_retry(request_url=request_url, params=params)
        raw_content = response.text

        if not raw_content.strip():
            raise OpenMeteoAdapterError(
                code="open_meteo_empty_response",
                message="Open-Meteo returned an empty response.",
                request_url=request_url,
                request_params=params,
                raw_content=raw_content,
            )

        try:
            payload = json.loads(raw_content, parse_constant=_reject_json_constant)
        except (json.JSONDecodeError, ValueError) as exc:
            raise OpenMeteoAdapterError(
                code="open_meteo_parse_error",
                message="Open-Meteo returned malformed JSON.",
                request_url=request_url,
                request_params=params,
                raw_content=raw_content,
            ) from exc

        if not isinstance(payload, dict):
            raise OpenMeteoAdapterError(
                code="open_meteo_validation_error",
                message="Open-Meteo returned a JSON payload with an invalid root type.",
                request_url=request_url,
                request_params=params,
                raw_content=raw_content,
            )

        try:
            records = self._normalize_records(payload, query=query, issue_time=issue_time)
        except (TypeError, ValueError, ZoneInfoNotFoundError) as exc:
            raise OpenMeteoAdapterError(
                code="open_meteo_validation_error",
                message=f"Open-Meteo returned an invalid forecast payload: {exc}",
                request_url=request_url,
                request_params=params,
                raw_content=raw_content,
                payload_json=payload,
            ) from exc

        return OpenMeteoFetchResult(
            provider=self.provider,
            request_url=request_url,
            request_params=params,
            raw_content=raw_content,
            payload_json=payload,
            payload_hash=_hash_json(
                {
                    "provider": self.provider,
                    "location_id": query.location_id,
                    "payload": payload,
                }
            ),
            records=records,
        )

    def _request_with_retry(
        self,
        *,
        request_url: str,
        params: dict[str, str],
    ) -> HttpResponse:
        for attempt in range(self._max_retries + 1):
            try:
                response = self._session.get(
                    self._forecast_url,
                    params=params,
                    timeout=self._timeout_seconds,
                )
            except requests.RequestException as exc:
                if attempt < self._max_retries:
                    self._retry(attempt=attempt, reason=type(exc).__name__)
                    continue
                raise OpenMeteoAdapterError(
                    code="open_meteo_network_error",
                    message=f"Open-Meteo request failed after retries: {type(exc).__name__}.",
                    request_url=request_url,
                    request_params=params,
                ) from exc

            if response.status_code < 400:
                return response

            if response.status_code in RETRYABLE_STATUS_CODES and attempt < self._max_retries:
                self._retry(attempt=attempt, reason=f"http_{response.status_code}")
                continue

            raise OpenMeteoAdapterError(
                code="open_meteo_http_error",
                message=f"Open-Meteo returned HTTP {response.status_code}.",
                request_url=request_url,
                request_params=params,
                raw_content=response.text,
            )

        raise AssertionError("Open-Meteo retry loop exited unexpectedly.")

    def _retry(self, *, attempt: int, reason: str) -> None:
        delay = self._retry_backoff_seconds * (2**attempt)
        logger.warning("Retrying Open-Meteo request after %s; delay=%s", reason, delay)
        self._sleep(delay)

    @staticmethod
    def _build_params(query: OpenMeteoForecastQuery) -> dict[str, str]:
        return {
            "latitude": str(query.latitude),
            "longitude": str(query.longitude),
            "timezone": query.timezone,
            "forecast_days": str(query.forecast_days),
            "hourly": ",".join(query.hourly_variables),
        }

    @staticmethod
    def _normalize_records(
        payload: dict[str, Any],
        *,
        query: OpenMeteoForecastQuery,
        issue_time: datetime,
    ) -> tuple[NormalizedWeatherRecord, ...]:
        hourly = payload.get("hourly")
        units = payload.get("hourly_units")
        if not isinstance(hourly, dict) or not isinstance(units, dict):
            raise ValueError("hourly and hourly_units must be objects")

        raw_times = hourly.get("time")
        if not isinstance(raw_times, list) or not raw_times:
            raise ValueError("hourly.time must contain at least one timestamp")

        timezone = ZoneInfo(query.timezone)
        forecast_times = tuple(_parse_forecast_time(value, timezone) for value in raw_times)
        if len(set(forecast_times)) != len(forecast_times):
            raise ValueError("hourly.time must not contain duplicate timestamps")
        records: list[NormalizedWeatherRecord] = []

        for variable in query.hourly_variables:
            raw_values = hourly.get(variable)
            unit = units.get(variable)
            if not isinstance(raw_values, list) or len(raw_values) != len(forecast_times):
                raise ValueError(f"hourly.{variable} must align with hourly.time")
            if not isinstance(unit, str) or not unit:
                raise ValueError(f"hourly_units.{variable} must be a non-empty string")

            for forecast_time, value in zip(forecast_times, raw_values, strict=True):
                if value is None:
                    normalized_value = None
                    quality_flag = "missing_value"
                elif isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise ValueError(f"hourly.{variable} contains a non-numeric value")
                else:
                    normalized_value = float(value)
                    quality_flag = "valid"
                content_hash = _hash_json(
                    {
                        "provider": OpenMeteoClient.provider,
                        "location_id": query.location_id,
                        "forecast_time": forecast_time.isoformat(),
                        "variable": variable,
                        "value": normalized_value,
                        "unit": unit,
                    }
                )
                records.append(
                    NormalizedWeatherRecord(
                        content_hash=content_hash,
                        issue_time=issue_time,
                        forecast_time=forecast_time,
                        variable=variable,
                        value=normalized_value,
                        unit=unit,
                        quality_flag=quality_flag,
                    )
                )

        if not records:
            raise ValueError("no normalized records were produced")
        return tuple(records)


def _parse_forecast_time(value: object, timezone: ZoneInfo) -> datetime:
    if not isinstance(value, str):
        raise ValueError("hourly.time contains a non-string timestamp")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone)
    return parsed


def _hash_json(value: object) -> str:
    serialized = json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return sha256(serialized.encode("utf-8")).hexdigest()


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"invalid JSON numeric constant: {value}")
