from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, String, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


class HydroOptimizationRun(Base):
    __tablename__ = "hydro_optimization_runs"

    optimization_run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    trade_date: Mapped[date] = mapped_column(Date, index=True)
    asset_id: Mapped[str] = mapped_column(String(80), index=True)
    scenario_id: Mapped[str] = mapped_column(String(120), index=True)
    algorithm_key: Mapped[str] = mapped_column(String(80))
    data_mode: Mapped[str] = mapped_column(String(40), index=True)
    energy_budget_mwh: Mapped[float] = mapped_column(Float)
    min_output_mw: Mapped[float] = mapped_column(Float)
    max_output_mw: Mapped[float] = mapped_column(Float)
    request_json: Mapped[dict[str, object]] = mapped_column(JSON)
    constraints_json: Mapped[dict[str, object]] = mapped_column(JSON)
    result_json: Mapped[dict[str, object]] = mapped_column(JSON)
    evidence_json: Mapped[list[dict[str, object]]] = mapped_column(JSON)
    missing_data_warnings_json: Mapped[list[str]] = mapped_column(JSON)
    human_review_required: Mapped[bool] = mapped_column(Boolean)
    no_auto_trading: Mapped[bool] = mapped_column(Boolean)
