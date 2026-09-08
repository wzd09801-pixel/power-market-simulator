from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


class WeatherLocation(Base):
    __tablename__ = "weather_locations"

    location_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    timezone: Mapped[str] = mapped_column(String(80))
    data_mode: Mapped[str] = mapped_column(String(40))
    collection_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    verification_status: Mapped[str] = mapped_column(String(60), default="manual_input")
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WeatherRawPayload(Base):
    __tablename__ = "weather_raw_payloads"

    raw_payload_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    provider: Mapped[str] = mapped_column(String(40), index=True)
    location_id: Mapped[str] = mapped_column(
        ForeignKey("weather_locations.location_id"), index=True
    )
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    request_url: Mapped[str] = mapped_column(Text)
    request_params_json: Mapped[dict[str, object]] = mapped_column(JSON)
    payload_json: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    raw_content: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64), unique=True)
    data_mode: Mapped[str] = mapped_column(String(40))
    quality_flag: Mapped[str] = mapped_column(String(40))


class WeatherIngestionRun(Base):
    __tablename__ = "weather_ingestion_runs"

    ingestion_run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    provider: Mapped[str] = mapped_column(String(40), index=True)
    location_id: Mapped[str] = mapped_column(
        ForeignKey("weather_locations.location_id"), index=True
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(40), index=True)
    request_url: Mapped[str] = mapped_column(Text)
    raw_payload_id: Mapped[str | None] = mapped_column(
        ForeignKey("weather_raw_payloads.raw_payload_id"), nullable=True
    )
    records_received: Mapped[int] = mapped_column(Integer)
    records_inserted: Mapped[int] = mapped_column(Integer)
    duplicate_records: Mapped[int] = mapped_column(Integer)
    quality_status: Mapped[str] = mapped_column(String(40), default="valid")
    quality_issue_count: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class WeatherRecord(Base):
    __tablename__ = "weather_records"

    weather_record_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    raw_payload_id: Mapped[str] = mapped_column(
        ForeignKey("weather_raw_payloads.raw_payload_id"), index=True
    )
    provider: Mapped[str] = mapped_column(String(40), index=True)
    location_id: Mapped[str] = mapped_column(
        ForeignKey("weather_locations.location_id"), index=True
    )
    issue_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    forecast_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    variable: Mapped[str] = mapped_column(String(80), index=True)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str] = mapped_column(String(40))
    data_mode: Mapped[str] = mapped_column(String(40))
    quality_flag: Mapped[str] = mapped_column(String(40))
    content_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WeatherQualityIssue(Base):
    __tablename__ = "weather_quality_issues"

    quality_issue_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    ingestion_run_id: Mapped[str] = mapped_column(
        ForeignKey("weather_ingestion_runs.ingestion_run_id"), index=True
    )
    raw_payload_id: Mapped[str] = mapped_column(
        ForeignKey("weather_raw_payloads.raw_payload_id"), index=True
    )
    weather_record_id: Mapped[str | None] = mapped_column(
        ForeignKey("weather_records.weather_record_id"), nullable=True, index=True
    )
    provider: Mapped[str] = mapped_column(String(40), index=True)
    location_id: Mapped[str] = mapped_column(
        ForeignKey("weather_locations.location_id"), index=True
    )
    forecast_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    variable: Mapped[str | None] = mapped_column(String(80), nullable=True)
    issue_code: Mapped[str] = mapped_column(String(80), index=True)
    severity: Mapped[str] = mapped_column(String(40))
    message: Mapped[str] = mapped_column(Text)
    details_json: Mapped[dict[str, object]] = mapped_column(JSON)
    data_mode: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WeatherFeatureSnapshot(Base):
    __tablename__ = "weather_feature_snapshots"

    feature_snapshot_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    ingestion_run_id: Mapped[str] = mapped_column(
        ForeignKey("weather_ingestion_runs.ingestion_run_id"), index=True
    )
    raw_payload_id: Mapped[str] = mapped_column(
        ForeignKey("weather_raw_payloads.raw_payload_id"), index=True
    )
    provider: Mapped[str] = mapped_column(String(40), index=True)
    location_id: Mapped[str] = mapped_column(
        ForeignKey("weather_locations.location_id"), index=True
    )
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    forecast_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    feature_version: Mapped[str] = mapped_column(String(80))
    quality_status: Mapped[str] = mapped_column(String(40))
    human_review_status: Mapped[str] = mapped_column(String(40), default="pending_review")
    features_json: Mapped[dict[str, object]] = mapped_column(JSON)
    evidence_json: Mapped[list[dict[str, object]]] = mapped_column(JSON)
    missing_data_warnings_json: Mapped[list[str]] = mapped_column(JSON)
    content_hash: Mapped[str] = mapped_column(String(64), unique=True)
    data_mode: Mapped[str] = mapped_column(String(40))


class WeatherFeatureReview(Base):
    __tablename__ = "weather_feature_reviews"

    review_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    feature_snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("weather_feature_snapshots.feature_snapshot_id"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    actor: Mapped[str] = mapped_column(String(120), default="local_operator")
    review_status: Mapped[str] = mapped_column(String(40))
    note: Mapped[str] = mapped_column(Text)
