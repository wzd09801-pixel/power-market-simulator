from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.forecasting import (
    ForecastResearchDataset,
    ForecastResearchDatasetImportRun,
    ForecastResearchModelRun,
    ForecastResearchPrediction,
    ForecastResearchPricePoint,
    ForecastResearchQualityIssue,
)


def get_forecast_research_dataset(
    session: Session, dataset_id: str
) -> ForecastResearchDataset | None:
    return session.get(ForecastResearchDataset, dataset_id)


def get_forecast_research_dataset_by_hash(
    session: Session, content_sha256: str
) -> ForecastResearchDataset | None:
    return session.scalar(
        select(ForecastResearchDataset).where(
            ForecastResearchDataset.content_sha256 == content_sha256
        )
    )


def add_forecast_research_dataset(
    session: Session,
    **values: Any,
) -> ForecastResearchDataset:
    dataset = ForecastResearchDataset(**values)
    session.add(dataset)
    return dataset


def list_forecast_research_datasets(
    session: Session, *, limit: int
) -> list[ForecastResearchDataset]:
    statement = (
        select(ForecastResearchDataset)
        .order_by(ForecastResearchDataset.imported_at.desc())
        .limit(limit)
    )
    return list(session.scalars(statement))


def add_forecast_research_dataset_import_run(
    session: Session, **values: Any
) -> ForecastResearchDatasetImportRun:
    run = ForecastResearchDatasetImportRun(**values)
    session.add(run)
    return run


def list_forecast_research_dataset_import_runs(
    session: Session, *, dataset_id: str | None, limit: int
) -> list[ForecastResearchDatasetImportRun]:
    statement = select(ForecastResearchDatasetImportRun)
    if dataset_id is not None:
        statement = statement.where(ForecastResearchDatasetImportRun.dataset_id == dataset_id)
    statement = statement.order_by(ForecastResearchDatasetImportRun.completed_at.desc()).limit(
        limit
    )
    return list(session.scalars(statement))


def add_forecast_research_price_point(
    session: Session,
    *,
    point_id: str,
    dataset_id: str,
    interval_start: datetime,
    trade_date: date,
    interval_index: int,
    price: Decimal,
    data_mode: str,
) -> ForecastResearchPricePoint:
    point = ForecastResearchPricePoint(
        point_id=point_id,
        dataset_id=dataset_id,
        interval_start=interval_start,
        trade_date=trade_date,
        interval_index=interval_index,
        price=price,
        data_mode=data_mode,
    )
    session.add(point)
    return point


def list_forecast_research_price_points(
    session: Session, *, dataset_id: str, limit: int | None = None
) -> list[ForecastResearchPricePoint]:
    statement = (
        select(ForecastResearchPricePoint)
        .where(ForecastResearchPricePoint.dataset_id == dataset_id)
        .order_by(ForecastResearchPricePoint.interval_start)
    )
    if limit is not None:
        statement = statement.limit(limit)
    return list(session.scalars(statement))


def add_forecast_research_quality_issue(
    session: Session, **values: Any
) -> ForecastResearchQualityIssue:
    issue = ForecastResearchQualityIssue(**values)
    session.add(issue)
    return issue


def list_forecast_research_quality_issues(
    session: Session,
    *,
    dataset_id: str | None,
    issue_code: str | None,
    limit: int,
) -> list[ForecastResearchQualityIssue]:
    statement = select(ForecastResearchQualityIssue)
    if dataset_id is not None:
        statement = statement.where(ForecastResearchQualityIssue.dataset_id == dataset_id)
    if issue_code is not None:
        statement = statement.where(ForecastResearchQualityIssue.issue_code == issue_code)
    statement = statement.order_by(ForecastResearchQualityIssue.created_at.desc()).limit(limit)
    return list(session.scalars(statement))


def add_forecast_research_model_run(session: Session, **values: Any) -> ForecastResearchModelRun:
    run = ForecastResearchModelRun(**values)
    session.add(run)
    return run


def get_forecast_research_model_run(
    session: Session, model_run_id: str
) -> ForecastResearchModelRun | None:
    return session.get(ForecastResearchModelRun, model_run_id)


def list_forecast_research_model_runs(
    session: Session, *, dataset_id: str | None, limit: int
) -> list[ForecastResearchModelRun]:
    statement = select(ForecastResearchModelRun)
    if dataset_id is not None:
        statement = statement.where(ForecastResearchModelRun.dataset_id == dataset_id)
    statement = statement.order_by(ForecastResearchModelRun.completed_at.desc()).limit(limit)
    return list(session.scalars(statement))


def add_forecast_research_prediction(
    session: Session,
    *,
    prediction_id: str,
    model_run_id: str,
    target_interval_start: datetime,
    trade_date: date,
    interval_index: int,
    actual_price: Decimal,
    predicted_price: Decimal,
    data_mode: str,
) -> ForecastResearchPrediction:
    prediction = ForecastResearchPrediction(
        prediction_id=prediction_id,
        model_run_id=model_run_id,
        target_interval_start=target_interval_start,
        trade_date=trade_date,
        interval_index=interval_index,
        actual_price=actual_price,
        predicted_price=predicted_price,
        data_mode=data_mode,
    )
    session.add(prediction)
    return prediction


def list_forecast_research_predictions(
    session: Session, *, model_run_id: str, limit: int
) -> list[ForecastResearchPrediction]:
    statement = (
        select(ForecastResearchPrediction)
        .where(ForecastResearchPrediction.model_run_id == model_run_id)
        .order_by(ForecastResearchPrediction.target_interval_start)
        .limit(limit)
    )
    return list(session.scalars(statement))
