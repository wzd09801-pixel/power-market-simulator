from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Literal
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from backend.app.core.errors import (
    HydroOptimizationRequestNotUsableError,
    HydroOptimizationRunNotFoundError,
)
from backend.app.models.scenario import HydroOptimizationRun
from backend.app.repositories.scenarios import (
    add_hydro_optimization_run,
    get_hydro_optimization_run,
    list_hydro_optimization_runs,
)
from backend.app.schemas.common import Evidence
from backend.app.schemas.scenario import (
    HydroOptimizationInterval,
    HydroOptimizationRunListResponse,
    HydroOptimizationRunRequest,
    HydroOptimizationRunResponse,
    HydroScenario,
)

ALGORITHM_KEY: Literal["deterministic_priority_v1"] = "deterministic_priority_v1"
DATA_MODE: Literal["scenario_simulated"] = "scenario_simulated"
INTERVAL_COUNT = 96
INTERVAL_HOURS = 0.25
TOP_PRIORITY_COUNT = 8
TIMEZONE = ZoneInfo("Asia/Shanghai")


def _now() -> datetime:
    return datetime.now(tz=TIMEZONE)


def get_default_demo_hydro_scenario() -> HydroScenario:
    evidence = [
        Evidence(
            source="synthetic_hydro_fixture",
            source_type="scenario_assumption",
            data_mode="scenario_simulated",
            timestamp=_now(),
            field="installed_capacity_mw",
            value=1000.0,
            unit="MW",
            confidence=0.8,
            url=None,
            note="Invented demonstration parameter; no real asset is represented.",
        ),
        Evidence(
            source="synthetic_hydro_fixture",
            source_type="scenario_assumption",
            data_mode="scenario_simulated",
            timestamp=_now(),
            field="firm_output_mw",
            value=300.0,
            unit="MW",
            confidence=0.75,
            url=None,
            note="Firm output is treated as a scenario boundary, not an internal dispatch value.",
        ),
    ]
    return HydroScenario(
        scenario_id="demo_hydro_a_normal_storage_normal_inflow_v1",
        scenario_type="normal_storage_normal_inflow",
        asset_id="demo_hydro_a",
        asset_name="Demo Hydro A Hydropower Station",
        installed_capacity_mw=1000.0,
        firm_output_mw=300.0,
        normal_pool_level_m=500.0,
        dead_water_level_m=450.0,
        total_storage_bcm=8.0,
        regulating_storage_bcm=4.0,
        current_water_level_m=480.0,
        inflow_regime="normal",
        storage_condition="normal",
        flood_control_pressure="low",
        available_energy_mwh=12000.0,
        assumptions=[
            "All physical parameters are invented demonstration assumptions.",
            "No verified internal reservoir operation, position, or dispatch data is used.",
            "Example Province spot price series is not connected in this first skeleton.",
        ],
        evidence=evidence,
        warning="Scenario data is simulated and is not verified company operational data.",
    )


def create_demo_hydro_optimization_run(
    request: HydroOptimizationRunRequest,
    *,
    session: Session,
) -> HydroOptimizationRunResponse:
    scenario = get_default_demo_hydro_scenario()
    _ensure_default_demo_hydro_request(request, scenario)
    min_output_mw = request.min_output_mw or scenario.firm_output_mw
    max_output_mw = request.max_output_mw or scenario.installed_capacity_mw
    energy_budget_mwh = request.energy_budget_mwh or scenario.available_energy_mwh
    _ensure_energy_budget_is_feasible(
        energy_budget_mwh=energy_budget_mwh,
        min_output_mw=min_output_mw,
        max_output_mw=max_output_mw,
    )
    intervals = _build_preview_intervals(
        request=request,
        energy_budget_mwh=energy_budget_mwh,
        min_output_mw=min_output_mw,
        max_output_mw=max_output_mw,
    )
    created_at = _now()
    evidence = [
        *scenario.evidence,
        *_constraint_evidence(
            created_at=created_at,
            energy_budget_mwh=energy_budget_mwh,
            min_output_mw=min_output_mw,
            max_output_mw=max_output_mw,
        ),
        *(
            _price_signal_evidence(created_at=created_at)
            if request.price_signal is not None
            else []
        ),
    ]
    missing_data_warnings = _optimization_warnings(
        price_signal_used=request.price_signal is not None
    )
    constraints = {
        "interval_count": INTERVAL_COUNT,
        "interval_minutes": 15,
        "min_output_mw": min_output_mw,
        "max_output_mw": max_output_mw,
        "min_energy_mwh": round(min_output_mw * 24, 4),
        "max_energy_mwh": round(max_output_mw * 24, 4),
        "energy_budget_mwh": round(energy_budget_mwh, 4),
        "algorithm_key": ALGORITHM_KEY,
        "recommendation_chain_isolated": True,
    }
    run = HydroOptimizationRun(
        optimization_run_id=f"hydro_opt_{uuid4().hex}",
        created_at=created_at,
        trade_date=request.trade_date,
        asset_id=scenario.asset_id,
        scenario_id=scenario.scenario_id,
        algorithm_key=ALGORITHM_KEY,
        data_mode=DATA_MODE,
        energy_budget_mwh=energy_budget_mwh,
        min_output_mw=min_output_mw,
        max_output_mw=max_output_mw,
        request_json={
            "request": request.model_dump(mode="json"),
            "scenario": scenario.model_dump(mode="json", exclude={"evidence"}),
        },
        constraints_json=constraints,
        result_json={
            "price_signal_used": request.price_signal is not None,
            "intervals": [interval.model_dump(mode="json") for interval in intervals],
            "top_priority_interval_indexes": [
                interval.interval_index for interval in _top_priority_intervals(intervals)
            ],
        },
        evidence_json=[item.model_dump(mode="json") for item in evidence],
        missing_data_warnings_json=missing_data_warnings,
        human_review_required=True,
        no_auto_trading=True,
    )
    with session.begin():
        add_hydro_optimization_run(session, run)
    return _to_optimization_response(run)


def get_demo_hydro_optimization_run(
    optimization_run_id: str,
    *,
    session: Session,
) -> HydroOptimizationRunResponse:
    run = get_hydro_optimization_run(session, optimization_run_id)
    if run is None:
        raise HydroOptimizationRunNotFoundError(optimization_run_id)
    return _to_optimization_response(run)


def get_recent_demo_hydro_optimization_runs(
    *,
    limit: int,
    session: Session,
) -> HydroOptimizationRunListResponse:
    return HydroOptimizationRunListResponse(
        items=[
            _to_optimization_response(run)
            for run in list_hydro_optimization_runs(session, limit=limit)
        ]
    )


def _ensure_default_demo_hydro_request(
    request: HydroOptimizationRunRequest,
    scenario: HydroScenario,
) -> None:
    if request.asset_id != scenario.asset_id or request.scenario_id != scenario.scenario_id:
        raise HydroOptimizationRequestNotUsableError(
            "only the default Demo Hydro A simulated scenario is supported"
        )


def _ensure_energy_budget_is_feasible(
    *,
    energy_budget_mwh: float,
    min_output_mw: float,
    max_output_mw: float,
) -> None:
    if max_output_mw <= min_output_mw:
        raise HydroOptimizationRequestNotUsableError(
            "max_output_mw must be greater than min_output_mw"
        )
    min_energy_mwh = min_output_mw * 24
    max_energy_mwh = max_output_mw * 24
    if energy_budget_mwh < min_energy_mwh:
        raise HydroOptimizationRequestNotUsableError(
            "energy_budget_mwh is below the 24-hour minimum output energy"
        )
    if energy_budget_mwh > max_energy_mwh:
        raise HydroOptimizationRequestNotUsableError(
            "energy_budget_mwh exceeds the 24-hour installed-capacity energy"
        )


def _build_preview_intervals(
    *,
    request: HydroOptimizationRunRequest,
    energy_budget_mwh: float,
    min_output_mw: float,
    max_output_mw: float,
) -> list[HydroOptimizationInterval]:
    price_by_interval = (
        {point.interval_index: point.price for point in request.price_signal}
        if request.price_signal is not None
        else {}
    )
    output_by_interval = {interval: min_output_mw for interval in range(1, INTERVAL_COUNT + 1)}
    remaining_energy = energy_budget_mwh - min_output_mw * 24
    priority_rank_by_interval: dict[int, int] = {}
    if price_by_interval:
        ranked_intervals = sorted(
            price_by_interval,
            key=lambda interval: (-price_by_interval[interval], interval),
        )
        priority_rank_by_interval = {
            interval: rank for rank, interval in enumerate(ranked_intervals, start=1)
        }
        interval_room_mwh = (max_output_mw - min_output_mw) * INTERVAL_HOURS
        for interval in ranked_intervals:
            if remaining_energy <= 0:
                break
            added_mwh = min(remaining_energy, interval_room_mwh)
            output_by_interval[interval] += added_mwh / INTERVAL_HOURS
            remaining_energy -= added_mwh
    else:
        balanced_extra_mw = remaining_energy / 24
        for interval in output_by_interval:
            output_by_interval[interval] += balanced_extra_mw

    return [
        HydroOptimizationInterval(
            interval_index=interval,
            interval_start=datetime.combine(request.trade_date, time(), tzinfo=TIMEZONE)
            + timedelta(minutes=15 * (interval - 1)),
            target_output_mw=round(output_by_interval[interval], 4),
            energy_mwh=round(output_by_interval[interval] * INTERVAL_HOURS, 4),
            price_signal=price_by_interval.get(interval),
            priority_rank=priority_rank_by_interval.get(interval),
            binding_constraints=_binding_constraints(
                output_mw=output_by_interval[interval],
                min_output_mw=min_output_mw,
                max_output_mw=max_output_mw,
                price_signal_used=bool(price_by_interval),
            ),
        )
        for interval in range(1, INTERVAL_COUNT + 1)
    ]


def _binding_constraints(
    *,
    output_mw: float,
    min_output_mw: float,
    max_output_mw: float,
    price_signal_used: bool,
) -> list[str]:
    constraints: list[str] = []
    if abs(output_mw - min_output_mw) < 0.0001:
        constraints.append("minimum_output_floor")
    if abs(output_mw - max_output_mw) < 0.0001:
        constraints.append("installed_capacity_ceiling")
    if not constraints:
        constraints.append(
            "price_priority_energy_balance" if price_signal_used else "constraint_only_balance"
        )
    return constraints


def _optimization_warnings(*, price_signal_used: bool) -> list[str]:
    warnings = [
        "预演仅使用公开校准的 scenario_simulated 场景，不能作为交易或调度指令。",
        "没有使用经过核验的公司水库运行数据、中长期持仓数据或真实调度边界。",
    ]
    if price_signal_used:
        warnings.append("价格信号是本地预演输入，未被标记为核验后的示例甲省现货价格序列。")
    else:
        warnings.append("尚未接入经过核验的示例甲省现货 96 点价格曲线；本次按约束均衡分配。")
    return warnings


def _constraint_evidence(
    *,
    created_at: datetime,
    energy_budget_mwh: float,
    min_output_mw: float,
    max_output_mw: float,
) -> list[Evidence]:
    return [
        Evidence(
            source="local_hydro_optimization_preview",
            source_type="operator_scenario_constraint",
            data_mode=DATA_MODE,
            timestamp=created_at,
            field="energy_budget_mwh",
            value=round(energy_budget_mwh, 4),
            unit="MWh",
            confidence=0.6,
            url=None,
            note="Local scenario preview input; not verified company operational data.",
        ),
        Evidence(
            source="local_hydro_optimization_preview",
            source_type="operator_scenario_constraint",
            data_mode=DATA_MODE,
            timestamp=created_at,
            field="output_bounds_mw",
            value=f"{min_output_mw:.4f}-{max_output_mw:.4f}",
            unit="MW",
            confidence=0.6,
            url=None,
            note="Local scenario preview bounds; not dispatch instructions.",
        ),
    ]


def _price_signal_evidence(*, created_at: datetime) -> list[Evidence]:
    return [
        Evidence(
            source="local_hydro_price_signal_input",
            source_type="operator_uploaded_price_curve",
            data_mode="user_uploaded",
            timestamp=created_at,
            field="price_signal_96_point_curve",
            value="96 intervals supplied",
            unit="CNY/MWh",
            confidence=0.5,
            url=None,
            note=(
                "Operator-supplied local preview curve; not verified as an official "
                "Example Province spot price series."
            ),
        )
    ]


def _top_priority_intervals(
    intervals: list[HydroOptimizationInterval],
) -> list[HydroOptimizationInterval]:
    if any(interval.priority_rank is not None for interval in intervals):
        return sorted(
            intervals,
            key=lambda interval: (
                interval.priority_rank if interval.priority_rank is not None else 999,
                interval.interval_index,
            ),
        )[:TOP_PRIORITY_COUNT]
    return intervals[:TOP_PRIORITY_COUNT]


def _constraint_explanation(
    *,
    run: HydroOptimizationRun,
    price_signal_used: bool,
    intervals: list[HydroOptimizationInterval],
) -> list[str]:
    min_count = sum(
        1 for interval in intervals if "minimum_output_floor" in interval.binding_constraints
    )
    max_count = sum(
        1 for interval in intervals if "installed_capacity_ceiling" in interval.binding_constraints
    )
    price_message = (
        "Price signal supplied: 96 user_uploaded interval prices were ranked from "
        "highest to lowest before assigning energy above the minimum output."
        if price_signal_used
        else "No price signal supplied: the run used a constraint-only balanced allocation."
    )
    return [
        (
            f"{ALGORITHM_KEY} evaluates 96 fifteen-minute intervals for "
            f"{run.asset_id} on {run.trade_date}."
        ),
        (
            f"Energy budget {run.energy_budget_mwh:.4f} MWh is bounded by "
            f"{run.min_output_mw:.4f} MW minimum output and "
            f"{run.max_output_mw:.4f} MW maximum output."
        ),
        price_message,
        (
            f"Binding result: {min_count} intervals at the minimum-output floor and "
            f"{max_count} intervals at the installed-capacity ceiling."
        ),
        (
            "This preview remains scenario_simulated, requires human review, and "
            "does not execute or submit trades."
        ),
    ]


def _to_optimization_response(run: HydroOptimizationRun) -> HydroOptimizationRunResponse:
    raw_intervals = run.result_json.get("intervals", [])
    interval_items = raw_intervals if isinstance(raw_intervals, list) else []
    intervals = [
        HydroOptimizationInterval.model_validate(item)
        for item in interval_items
        if isinstance(item, dict)
    ]
    price_signal_used = bool(run.result_json.get("price_signal_used"))
    return HydroOptimizationRunResponse(
        optimization_run_id=run.optimization_run_id,
        created_at=run.created_at,
        trade_date=run.trade_date,
        asset_id=run.asset_id,
        scenario_id=run.scenario_id,
        algorithm_key=ALGORITHM_KEY,
        data_mode=DATA_MODE,
        energy_budget_mwh=run.energy_budget_mwh,
        min_output_mw=run.min_output_mw,
        max_output_mw=run.max_output_mw,
        price_signal_used=price_signal_used,
        intervals=intervals,
        top_priority_intervals=_top_priority_intervals(intervals),
        missing_data_warnings=list(run.missing_data_warnings_json),
        constraint_explanation=_constraint_explanation(
            run=run,
            price_signal_used=price_signal_used,
            intervals=intervals,
        ),
        evidence=[
            Evidence.model_validate(item) for item in run.evidence_json if isinstance(item, dict)
        ],
        request_snapshot=dict(run.request_json),
        constraints=dict(run.constraints_json),
        human_review_required=run.human_review_required,
        no_auto_trading=run.no_auto_trading,
    )
