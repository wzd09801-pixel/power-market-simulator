from __future__ import annotations

# ruff: noqa: E402, I001

import argparse
import json
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy import create_engine

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.core.config import get_settings  # noqa: E402
from backend.app.db.base import Base  # noqa: E402
from backend.app.db.session import get_db_session, get_engine, get_session_factory  # noqa: E402
from backend.app.main import create_app  # noqa: E402
from backend.app.models import forecasting as _forecasting  # noqa: F401, E402
from backend.app.models import intelligence as _intelligence  # noqa: F401, E402
from backend.app.models import knowledge as _knowledge  # noqa: F401, E402
from backend.app.models import market as _market  # noqa: F401, E402
from backend.app.models import operations as _operations  # noqa: F401, E402
from backend.app.models import recommendation as _recommendation  # noqa: F401, E402
from backend.app.models import scenario as _scenario  # noqa: F401, E402
from backend.app.models import weather as _weather  # noqa: F401, E402
from backend.app.models.forecasting import (  # noqa: E402
    ForecastResearchModelRun,
    ForecastResearchPrediction,
)
from backend.app.models.recommendation import RecommendationRun  # noqa: E402


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    message: str


@dataclass(frozen=True)
class TrialState:
    valid_dataset_id: str
    invalid_dataset_id: str
    seasonal_model_run_id: str
    calendar_model_run_id: str


@dataclass(frozen=True)
class TrialContext:
    client: TestClient
    session_factory: sessionmaker[Session]


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run a host-only forecast training trial smoke without external network "
            "or persistent DB access."
        )
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON results.")
    args = parser.parse_args()

    results = run_trial()
    ok = all(result.ok for result in results)
    if args.json:
        print(
            json.dumps(
                {
                    "ok": ok,
                    "checks": [result.__dict__ for result in results],
                    "host_only": True,
                    "external_network_access": False,
                    "persistent_database_access": False,
                    "model_promotion": False,
                    "no_auto_trading": True,
                },
                ensure_ascii=True,
                indent=2,
            )
        )
    else:
        for result in results:
            status = "ok" if result.ok else "fail"
            print(f"[{status}] {result.name}: {result.message}")
    return 0 if ok else 1


def run_trial() -> list[CheckResult]:
    results: list[CheckResult] = []
    with _trial_client() as context:
        client = context.client
        if not _record(results, "empty overview", lambda: _check_empty_overview(client)):
            return results
        state: TrialState | None = None
        try:
            state = _run_dataset_and_backtest_flow(client)
            results.extend(
                [
                    CheckResult(
                        name="valid import",
                        ok=True,
                        message="valid simulated 96-point dataset is accepted as research_only",
                    ),
                    CheckResult(
                        name="invalid quality",
                        ok=True,
                        message="incomplete curve records quality issues and rejects backtest",
                    ),
                    CheckResult(
                        name="backtest",
                        ok=True,
                        message="seasonal_naive and calendar_mean persist candidate runs",
                    ),
                ]
            )
        except (AssertionError, KeyError, IndexError, RuntimeError) as exc:
            results.append(CheckResult(name="forecast training flow", ok=False, message=str(exc)))
            return results
        checks: tuple[tuple[str, Callable[[], str]], ...] = (
            ("predictions", lambda: _check_predictions(client, state)),
            ("review package", lambda: _check_review_package(client, state)),
            (
                "recommendation isolation",
                lambda: _check_recommendation_isolation(client, state, context.session_factory),
            ),
        )
        for name, check in checks:
            if not _record(results, name, check):
                break
    return results


def _record(results: list[CheckResult], name: str, check: Callable[[], str]) -> bool:
    try:
        message = check()
    except (AssertionError, KeyError, IndexError, RuntimeError) as exc:
        results.append(CheckResult(name=name, ok=False, message=str(exc)))
        return False
    results.append(CheckResult(name=name, ok=True, message=message))
    return True


@contextmanager
def _trial_client() -> Iterator[TrialContext]:
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    app = create_app()

    def override_db_session() -> Iterator[Session]:
        with factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_db_session
    try:
        with TestClient(app) as client:
            yield TrialContext(client=client, session_factory=factory)
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()
        get_settings.cache_clear()
        get_engine.cache_clear()
        get_session_factory.cache_clear()


def _check_empty_overview(client: TestClient) -> str:
    response = client.get("/v1/forecasting/research/overview")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "warning"
    assert payload["dataset_count"] == 0
    assert payload["candidate_model_run_count"] == 0
    assert payload["no_auto_trading"] is True
    assert payload["recommendation_chain_isolated"] is True
    assert payload["fetch_performed"] is False
    assert payload["network_probe_performed"] is False
    return "empty forecast overview returns warning with safe local-only flags"


def _run_dataset_and_backtest_flow(client: TestClient) -> TrialState:
    valid = client.post(
        "/v1/forecasting/research/datasets/manual",
        json=_research_dataset_payload(days=15, name="Host-only training trial curve"),
    )
    assert valid.status_code == 200, valid.text
    valid_payload = valid.json()
    assert valid_payload["status"] == "accepted"
    assert valid_payload["quality_status"] == "valid"
    assert valid_payload["normalized_point_count"] == 15 * 96
    assert valid_payload["trade_date_count"] == 15
    assert valid_payload["data_mode"] == "scenario_simulated"
    assert valid_payload["usage_scope"] == "research_only"

    invalid_request = _research_dataset_payload(days=2, name="Invalid host-only trial curve")
    invalid_request["points"].pop()
    invalid = client.post("/v1/forecasting/research/datasets/manual", json=invalid_request)
    assert invalid.status_code == 200, invalid.text
    invalid_payload = invalid.json()
    assert invalid_payload["status"] == "rejected"
    assert invalid_payload["quality_status"] == "invalid"
    assert invalid_payload["normalized_point_count"] == 0
    issues = client.get(
        "/v1/forecasting/research/quality/issues",
        params={"dataset_id": invalid_payload["dataset_id"]},
    )
    assert issues.status_code == 200, issues.text
    assert "incomplete_trade_date" in {item["issue_code"] for item in issues.json()["items"]}
    rejected_backtest = client.post(
        f"/v1/forecasting/research/datasets/{invalid_payload['dataset_id']}/backtests",
        json={"model_key": "seasonal_naive", "evaluation_days": 1, "lag_days": 7},
    )
    assert rejected_backtest.status_code == 409, rejected_backtest.text

    seasonal = _run_backtest(client, valid_payload["dataset_id"], "seasonal_naive")
    calendar = _run_backtest(client, valid_payload["dataset_id"], "calendar_mean")
    return TrialState(
        valid_dataset_id=valid_payload["dataset_id"],
        invalid_dataset_id=invalid_payload["dataset_id"],
        seasonal_model_run_id=seasonal["model_run_id"],
        calendar_model_run_id=calendar["model_run_id"],
    )


def _run_backtest(client: TestClient, dataset_id: str, model_key: str) -> dict[str, Any]:
    response = client.post(
        f"/v1/forecasting/research/datasets/{dataset_id}/backtests",
        json={"model_key": model_key, "evaluation_days": 3, "lag_days": 7, "lookback_days": 7},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["model_key"] == model_key
    assert payload["status"] == "succeeded"
    assert payload["registry_status"] == "candidate"
    assert payload["usage_scope"] == "research_only"
    assert payload["data_mode"] == "public_derived"
    assert payload["artifact_path"] is None
    assert payload["metrics"]["prediction_count"] == 288
    return payload


def _check_predictions(client: TestClient, state: TrialState) -> str:
    seasonal = client.get(
        f"/v1/forecasting/research/model-runs/{state.seasonal_model_run_id}/predictions",
        params={"limit": 500},
    )
    assert seasonal.status_code == 200, seasonal.text
    assert len(seasonal.json()["items"]) == 288
    assert {item["data_mode"] for item in seasonal.json()["items"]} == {"public_derived"}
    runs = client.get(
        "/v1/forecasting/research/model-runs",
        params={"dataset_id": state.valid_dataset_id},
    )
    assert runs.status_code == 200, runs.text
    assert {item["model_run_id"] for item in runs.json()["items"]} == {
        state.seasonal_model_run_id,
        state.calendar_model_run_id,
    }
    return "candidate runs expose auditable predictions and model listing"


def _check_review_package(client: TestClient, state: TrialState) -> str:
    package = client.get(
        f"/v1/forecasting/research/datasets/{state.valid_dataset_id}/review-package"
    )
    assert package.status_code == 200, package.text
    payload = package.json()
    assert payload["dataset"]["usage_scope"] == "research_only"
    assert payload["dataset"]["data_mode"] == "scenario_simulated"
    assert payload["quality_issue_summary"]["total_count"] == 0
    assert {run["model_run_id"] for run in payload["model_runs"]} == {
        state.seasonal_model_run_id,
        state.calendar_model_run_id,
    }
    assert {run["registry_status"] for run in payload["model_runs"]} == {"candidate"}
    assert payload["no_auto_trading"] is True
    assert payload["recommendation_chain_isolated"] is True
    assert payload["fetch_performed"] is False
    assert payload["network_probe_performed"] is False
    invalid_package = client.get(
        f"/v1/forecasting/research/datasets/{state.invalid_dataset_id}/review-package"
    )
    assert invalid_package.status_code == 200, invalid_package.text
    assert invalid_package.json()["dataset"]["quality_status"] == "invalid"
    assert invalid_package.json()["model_runs"] == []
    return "review packages show candidate metrics and invalid quality diagnostics"


def _check_recommendation_isolation(
    client: TestClient, state: TrialState, factory: sessionmaker[Session]
) -> str:
    overview = client.get("/v1/forecasting/research/overview")
    assert overview.status_code == 200, overview.text
    payload = overview.json()
    assert payload["dataset_count"] == 2
    assert payload["valid_dataset_count"] == 1
    assert payload["invalid_dataset_count"] == 1
    assert payload["research_only_dataset_count"] == 2
    assert payload["candidate_model_run_count"] == 2
    assert payload["succeeded_model_run_count"] == 2
    assert payload["no_auto_trading"] is True
    assert payload["recommendation_chain_isolated"] is True
    with factory() as session:
        recommendation_count = session.scalar(select(func.count()).select_from(RecommendationRun))
        model_count = session.scalar(select(func.count()).select_from(ForecastResearchModelRun))
        prediction_count = session.scalar(
            select(func.count()).select_from(ForecastResearchPrediction)
        )
    assert recommendation_count == 0
    assert model_count == 2
    assert prediction_count == 576
    return "forecast trial remains isolated from recommendations and automatic trading"


def _research_dataset_payload(*, days: int, name: str) -> dict[str, Any]:
    start = datetime.fromisoformat("2026-01-01T00:00:00+08:00")
    points = []
    for offset in range(days * 96):
        interval_start = start + timedelta(minutes=15 * offset)
        day_number = offset // 96
        interval_index = offset % 96
        points.append(
            {
                "interval_start": interval_start.isoformat(),
                "price": str(100 + day_number + interval_index / 10),
            }
        )
    return {
        "name": name,
        "source_name": "Host-only forecast training trial",
        "source_url": "https://example.invalid/forecast-training-trial.json",
        "region_code": "TRIAL",
        "region_name": "Host-only trial region",
        "market_scope": "forecast_training_trial",
        "market_stage": "day_ahead",
        "price_scope": "regional_reference_price",
        "interval_minutes": 15,
        "timezone": "Asia/Shanghai",
        "currency": "CNY",
        "price_unit": "CNY_per_MWh",
        "data_mode": "scenario_simulated",
        "usage_scope": "research_only",
        "notes": (
            "Synthetic host-only trial fixture. It is not observed Example Province market data "
            "and cannot enter recommendation evidence."
        ),
        "points": points,
    }


if __name__ == "__main__":
    raise SystemExit(main())
