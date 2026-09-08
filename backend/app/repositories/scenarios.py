from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.scenario import HydroOptimizationRun


def add_hydro_optimization_run(
    session: Session,
    run: HydroOptimizationRun,
) -> HydroOptimizationRun:
    session.add(run)
    return run


def get_hydro_optimization_run(
    session: Session,
    optimization_run_id: str,
) -> HydroOptimizationRun | None:
    return session.get(HydroOptimizationRun, optimization_run_id)


def list_hydro_optimization_runs(
    session: Session,
    *,
    limit: int,
) -> list[HydroOptimizationRun]:
    statement = (
        select(HydroOptimizationRun).order_by(HydroOptimizationRun.created_at.desc()).limit(limit)
    )
    return list(session.scalars(statement))
