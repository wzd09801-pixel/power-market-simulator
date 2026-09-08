from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

SystemReadinessStatus = Literal["healthy", "warning", "critical"]


class SystemStatus(BaseModel):
    model_config = ConfigDict(frozen=True)

    app_name: str
    app_version: str
    environment: str
    database_connected: bool
    data_modes: list[str]
    no_auto_trading: bool


class DemoSeedSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    seed_key: str
    created: dict[str, bool]
    object_ids: dict[str, str]
    data_modes: dict[str, str]
    research_only: bool
    no_auto_trading: bool


class SystemReadinessCheck(BaseModel):
    model_config = ConfigDict(frozen=True)

    key: str
    label: str
    status: SystemReadinessStatus
    message: str
    details: dict[str, object]


class SystemReadinessResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    generated_at: datetime
    status: SystemReadinessStatus
    checks: list[SystemReadinessCheck]
    demo_seed: DemoSeedSummary | None
    table_counts: dict[str, int]
    missing_demo_items: list[str]
    recommended_actions: list[str]
    no_auto_trading: bool
