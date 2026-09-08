from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Protocol, cast

import requests

from backend.app.core.config import get_settings


class DeepSeekProviderError(RuntimeError):
    pass


class DeepSeekClient(Protocol):
    def complete_json(
        self, *, prompt: str, deep_analysis: bool
    ) -> tuple[dict[str, object], str]: ...


class DisabledDeepSeekClient:
    def complete_json(self, *, prompt: str, deep_analysis: bool) -> tuple[dict[str, object], str]:
        del prompt, deep_analysis
        raise DeepSeekProviderError("DeepSeek is not configured.")


class HttpDeepSeekClient:
    def __init__(
        self,
        *,
        api_url: str,
        api_key: str,
        default_model: str,
        deep_analysis_model: str,
        timeout_seconds: float,
        max_retries: int,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.api_url = api_url
        self.api_key = api_key
        self.default_model = default_model
        self.deep_analysis_model = deep_analysis_model
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.sleep = sleep

    def complete_json(self, *, prompt: str, deep_analysis: bool) -> tuple[dict[str, object], str]:
        model = self.deep_analysis_model if deep_analysis else self.default_model
        for attempt in range(self.max_retries + 1):
            try:
                response = requests.post(
                    self.api_url,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": prompt}],
                        "response_format": {"type": "json_object"},
                    },
                    timeout=self.timeout_seconds,
                )
                response.raise_for_status()
                content = response.json()["choices"][0]["message"].get("content")
                if content:
                    return cast(dict[str, object], json.loads(content)), model
            except (KeyError, TypeError, ValueError, requests.RequestException) as exc:
                if attempt >= self.max_retries:
                    raise DeepSeekProviderError("DeepSeek JSON completion failed.") from exc
            if attempt < self.max_retries:
                self.sleep(0.5 * (2**attempt))
        raise DeepSeekProviderError("DeepSeek returned empty JSON content.")


def get_deepseek_client() -> DeepSeekClient:
    settings = get_settings()
    if settings.deepseek_api_key is None or not settings.deepseek_api_key.get_secret_value():
        return DisabledDeepSeekClient()
    return HttpDeepSeekClient(
        api_url=settings.deepseek_api_url,
        api_key=settings.deepseek_api_key.get_secret_value(),
        default_model=settings.deepseek_default_model,
        deep_analysis_model=settings.deepseek_deep_analysis_model,
        timeout_seconds=settings.deepseek_timeout_seconds,
        max_retries=settings.deepseek_max_retries,
    )
