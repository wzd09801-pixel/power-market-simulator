from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


class RawObject(Base):
    __tablename__ = "raw_objects"

    raw_object_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    content_sha256: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    storage_backend: Mapped[str] = mapped_column(String(40))
    bucket_name: Mapped[str] = mapped_column(String(120))
    object_key: Mapped[str] = mapped_column(Text, unique=True)
    media_type: Mapped[str] = mapped_column(String(160))
    byte_length: Mapped[int] = mapped_column(Integer)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    metadata_json: Mapped[dict[str, object]] = mapped_column(JSON)
    data_mode: Mapped[str] = mapped_column(String(40))


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"

    workflow_run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workflow_key: Mapped[str] = mapped_column(String(80), index=True)
    trigger_mode: Mapped[str] = mapped_column(String(40))
    prefect_flow_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    schedule_identity: Mapped[str | None] = mapped_column(String(160), nullable=True, unique=True)
    status: Mapped[str] = mapped_column(String(40), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    worker_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    lease_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    summary_json: Mapped[dict[str, object]] = mapped_column(JSON)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class WorkdayCalendarOverride(Base):
    __tablename__ = "workday_calendar_overrides"

    calendar_date: Mapped[date] = mapped_column(Date, primary_key=True)
    is_workday: Mapped[bool] = mapped_column(Boolean)
    source_kind: Mapped[str] = mapped_column(String(40))
    source_url: Mapped[str] = mapped_column(Text)
    note: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
