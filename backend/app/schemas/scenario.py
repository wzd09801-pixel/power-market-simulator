from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.app.schemas.common import Evidence


class HydroScenario(BaseModel):
    model_config = ConfigDict(frozen=True)

    scenario_id: str
    scenario_type: str
    asset_id: str
    asset_name: str
    data_mode: str = "scenario_simulated"
    installed_capacity_mw: float = Field(gt=0)
    firm_output_mw: float = Field(gt=0)
    normal_pool_level_m: float
    dead_water_level_m: float
    total_storage_bcm: float
    regulating_storage_bcm: float
    current_water_level_m: float
    inflow_regime: str
    storage_condition: str
    flood_control_pressure: str
    available_energy_mwh: float = Field(gt=0)
    assumptions: list[str]
    evidence: list[Evidence]
    warning: str


class HydroOptimizationPricePoint(BaseModel):
    model_config = ConfigDict(frozen=True)

    interval_index: int = Field(ge=1, le=96)
    price: Decimal = Field(ge=-100_000, le=100_000, max_digits=18, decimal_places=4)


class HydroOptimizationRunRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    trade_date: date
    asset_id: str = "demo_hydro_a"
    scenario_id: str = "demo_hydro_a_normal_storage_normal_inflow_v1"
    energy_budget_mwh: float | None = Field(default=None, gt=0)
    min_output_mw: float | None = Field(default=None, ge=0)
    max_output_mw: float | None = Field(default=None, gt=0)
    price_signal: list[HydroOptimizationPricePoint] | None = None

    @field_validator("price_signal")
    @classmethod
    def price_signal_must_be_complete_96_point_curve(
        cls,
        value: list[HydroOptimizationPricePoint] | None,
    ) -> list[HydroOptimizationPricePoint] | None:
        if value is None:
            return None
        indexes = [point.interval_index for point in value]
        if len(indexes) != 96 or sorted(indexes) != list(range(1, 97)):
            raise ValueError("Price signal must contain exactly one point for each interval 1-96.")
        return value

    @model_validator(mode="after")
    def max_output_must_exceed_min_output(self) -> HydroOptimizationRunRequest:
        if (
            self.min_output_mw is not None
            and self.max_output_mw is not None
            and self.max_output_mw <= self.min_output_mw
        ):
            raise ValueError("max_output_mw must be greater than min_output_mw.")
        return self


class HydroOptimizationInterval(BaseModel):
    model_config = ConfigDict(frozen=True)

    interval_index: int
    interval_start: datetime
    target_output_mw: float
    energy_mwh: float
    price_signal: Decimal | None
    priority_rank: int | None
    binding_constraints: list[str]


class HydroOptimizationRunResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    optimization_run_id: str
    created_at: datetime
    trade_date: date
    asset_id: str
    scenario_id: str
    algorithm_key: Literal["deterministic_priority_v1"]
    data_mode: Literal["scenario_simulated"]
    energy_budget_mwh: float
    min_output_mw: float
    max_output_mw: float
    price_signal_used: bool
    intervals: list[HydroOptimizationInterval]
    top_priority_intervals: list[HydroOptimizationInterval]
    missing_data_warnings: list[str]
    constraint_explanation: list[str]
    evidence: list[Evidence]
    request_snapshot: dict[str, object]
    constraints: dict[str, object]
    human_review_required: bool
    no_auto_trading: bool


class HydroOptimizationRunListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[HydroOptimizationRunResponse]
