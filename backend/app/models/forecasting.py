from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


class ForecastResearchDataset(Base):
    __tablename__ = "forecast_research_datasets"

    dataset_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    source_name: Mapped[str] = mapped_column(String(160))
    source_url: Mapped[str] = mapped_column(Text)
    region_code: Mapped[str] = mapped_column(String(40), index=True)
    region_name: Mapped[str] = mapped_column(String(120))
    market_scope: Mapped[str] = mapped_column(String(80))
    market_stage: Mapped[str] = mapped_column(String(40), index=True)
    price_scope: Mapped[str] = mapped_column(String(80))
    interval_minutes: Mapped[int] = mapped_column(Integer)
    timezone: Mapped[str] = mapped_column(String(80))
    currency: Mapped[str] = mapped_column(String(16))
    price_unit: Mapped[str] = mapped_column(String(40))
    data_mode: Mapped[str] = mapped_column(String(40))
    usage_scope: Mapped[str] = mapped_column(String(40), index=True)
    content_sha256: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    raw_payload_json: Mapped[dict[str, object]] = mapped_column(JSON)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    quality_status: Mapped[str] = mapped_column(String(40), index=True)
    quality_issue_count: Mapped[int] = mapped_column(Integer)
    normalized_point_count: Mapped[int] = mapped_column(Integer)
    trade_date_count: Mapped[int] = mapped_column(Integer)
    notes: Mapped[str] = mapped_column(Text)


class ForecastResearchDatasetImportRun(Base):
    __tablename__ = "forecast_research_dataset_import_runs"

    import_run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(
        ForeignKey("forecast_research_datasets.dataset_id"), index=True
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(40), index=True)
    submitted_point_count: Mapped[int] = mapped_column(Integer)
    normalized_point_count: Mapped[int] = mapped_column(Integer)
    quality_status: Mapped[str] = mapped_column(String(40))
    quality_issue_count: Mapped[int] = mapped_column(Integer)
    data_mode: Mapped[str] = mapped_column(String(40))
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class ForecastResearchPricePoint(Base):
    __tablename__ = "forecast_research_price_points"
    __table_args__ = (
        UniqueConstraint(
            "dataset_id",
            "interval_start",
            name="uq_forecast_research_price_points_dataset_time",
        ),
        UniqueConstraint(
            "dataset_id",
            "trade_date",
            "interval_index",
            name="uq_forecast_research_price_points_dataset_trade_interval",
        ),
    )

    point_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(
        ForeignKey("forecast_research_datasets.dataset_id"), index=True
    )
    interval_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    trade_date: Mapped[date] = mapped_column(Date, index=True)
    interval_index: Mapped[int] = mapped_column(Integer)
    price: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    data_mode: Mapped[str] = mapped_column(String(40))


class ForecastResearchQualityIssue(Base):
    __tablename__ = "forecast_research_quality_issues"

    quality_issue_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(
        ForeignKey("forecast_research_datasets.dataset_id"), index=True
    )
    import_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("forecast_research_dataset_import_runs.import_run_id"),
        nullable=True,
        index=True,
    )
    issue_code: Mapped[str] = mapped_column(String(80), index=True)
    severity: Mapped[str] = mapped_column(String(40))
    message: Mapped[str] = mapped_column(Text)
    details_json: Mapped[dict[str, object]] = mapped_column(JSON)
    data_mode: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ForecastResearchModelRun(Base):
    __tablename__ = "forecast_research_model_runs"

    model_run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(
        ForeignKey("forecast_research_datasets.dataset_id"), index=True
    )
    model_key: Mapped[str] = mapped_column(String(80), index=True)
    model_version: Mapped[str] = mapped_column(String(40))
    feature_version: Mapped[str] = mapped_column(String(80))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(40), index=True)
    registry_status: Mapped[str] = mapped_column(String(40), index=True)
    train_start: Mapped[date] = mapped_column(Date)
    train_end: Mapped[date] = mapped_column(Date)
    evaluation_start: Mapped[date] = mapped_column(Date)
    evaluation_end: Mapped[date] = mapped_column(Date)
    horizon_intervals: Mapped[int] = mapped_column(Integer)
    parameters_json: Mapped[dict[str, object]] = mapped_column(JSON)
    metrics_json: Mapped[dict[str, object]] = mapped_column(JSON)
    artifact_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    usage_scope: Mapped[str] = mapped_column(String(40), index=True)
    data_mode: Mapped[str] = mapped_column(String(40))
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class ForecastResearchPrediction(Base):
    __tablename__ = "forecast_research_predictions"
    __table_args__ = (
        UniqueConstraint(
            "model_run_id",
            "target_interval_start",
            name="uq_forecast_research_predictions_run_time",
        ),
    )

    prediction_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    model_run_id: Mapped[str] = mapped_column(
        ForeignKey("forecast_research_model_runs.model_run_id"), index=True
    )
    target_interval_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    trade_date: Mapped[date] = mapped_column(Date, index=True)
    interval_index: Mapped[int] = mapped_column(Integer)
    actual_price: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    predicted_price: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    data_mode: Mapped[str] = mapped_column(String(40))
