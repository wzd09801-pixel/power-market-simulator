from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class Evidence(BaseModel):
    model_config = ConfigDict(frozen=True)

    source: str
    source_type: str
    data_mode: str
    timestamp: datetime
    field: str
    value: str | float | int | bool
    unit: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    url: str | None = None
    note: str | None = None


class RecommendedWindow(BaseModel):
    model_config = ConfigDict(frozen=True)

    time: str
    stance: str
    reason: str
