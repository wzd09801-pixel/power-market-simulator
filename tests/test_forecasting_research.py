from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.models.forecasting import (
    ForecastResearchDataset,
    ForecastResearchDatasetImportRun,
    ForecastResearchModelRun,
    ForecastResearchPrediction,
    ForecastResearchPricePoint,
    ForecastResearchQualityIssue,
)
from backend.app.models.recommendation import RecommendationRun


def research_dataset_payload(*, days: int = 15) -> dict[str, Any]:
    start = datetime.fromisoformat("2026-01-01T00:00:00+08:00")
    points = []
    for offset in range(days * 96):
        interval_start = start + timedelta(minutes=15 * offset)
        day_number = offset // 96
        interval_index = offset % 96
        points.append(
            {
                "interval_start": interval_start.isoformat(),
                "price": 100 + day_number + interval_index / 10,
            }
        )
    return {
        "name": "Explicitly simulated 15-minute research curve",
        "source_name": "Test scenario generator",
        "source_url": "https://example.invalid/scenarios/interval-price-v1.json",
        "region_code": "TEST",
        "region_name": "Explicit simulated test region",
        "market_scope": "research_fixture",
        "market_stage": "day_ahead",
        "price_scope": "regional_reference_price",
        "interval_minutes": 15,
        "timezone": "Asia/Shanghai",
        "currency": "CNY",
        "price_unit": "CNY_per_MWh",
        "data_mode": "scenario_simulated",
        "usage_scope": "research_only",
        "notes": "Synthetic test fixture only. It is not observed Example Province market data.",
        "points": points,
    }


def import_dataset(client: TestClient, *, days: int = 15) -> dict[str, Any]:
    response = client.post(
        "/v1/forecasting/research/datasets/manual",
        json=research_dataset_payload(days=days),
    )
    assert response.status_code == 200
    return response.json()


def test_manual_research_dataset_import_preserves_complete_curve_and_deduplicates(
    client: TestClient,
    db_session_factory: sessionmaker[Session],
) -> None:
    payload = research_dataset_payload(days=2)
    first = client.post("/v1/forecasting/research/datasets/manual", json=payload)
    second = client.post("/v1/forecasting/research/datasets/manual", json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["status"] == "accepted"
    assert first.json()["normalized_point_count"] == 192
    assert first.json()["trade_date_count"] == 2
    assert first.json()["usage_scope"] == "research_only"
    assert first.json()["data_mode"] == "scenario_simulated"
    assert second.json()["status"] == "duplicate"
    assert second.json()["duplicate_dataset"] is True
    assert second.json()["dataset_id"] == first.json()["dataset_id"]

    datasets = client.get("/v1/forecasting/research/datasets")
    points = client.get(
        f"/v1/forecasting/research/datasets/{first.json()['dataset_id']}/points",
        params={"limit": 2},
    )
    runs = client.get(
        "/v1/forecasting/research/import-runs",
        params={"dataset_id": first.json()["dataset_id"]},
    )
    assert datasets.json()["items"][0]["source_url"] == payload["source_url"]
    assert datasets.json()["items"][0]["usage_scope"] == "research_only"
    assert [item["interval_index"] for item in points.json()["items"]] == [1, 2]
    assert {item["status"] for item in runs.json()["items"]} == {"accepted", "duplicate"}

    with db_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(ForecastResearchDataset)) == 1
        assert session.scalar(select(func.count()).select_from(ForecastResearchPricePoint)) == 192
        assert (
            session.scalar(select(func.count()).select_from(ForecastResearchDatasetImportRun)) == 2
        )


def test_forecast_research_overview_empty_database_returns_warning(client: TestClient) -> None:
    response = client.get("/v1/forecasting/research/overview")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "warning"
    assert payload["dataset_count"] == 0
    assert payload["valid_dataset_count"] == 0
    assert payload["invalid_dataset_count"] == 0
    assert payload["candidate_model_run_count"] == 0
    assert payload["bench_missing_regions"] == ["NSW1", "QLD1", "SA1", "TAS1", "VIC1"]
    assert payload["network_probe_performed"] is False
    assert payload["fetch_performed"] is False
    assert payload["no_auto_trading"] is True
    assert payload["recommendation_chain_isolated"] is True


def test_forecast_research_overview_aggregates_research_state_without_recommendations(
    client: TestClient,
    db_session_factory: sessionmaker[Session],
) -> None:
    valid_dataset = import_dataset(client)
    invalid_payload = research_dataset_payload(days=2)
    invalid_payload["name"] = "Invalid incomplete research curve"
    invalid_payload["points"].pop()
    invalid_response = client.post("/v1/forecasting/research/datasets/manual", json=invalid_payload)
    bench_payload = research_dataset_payload(days=1)
    bench_payload.update(
        {
            "name": "BENCH NSW1 research benchmark fixture",
            "source_name": "Australian Energy Market Operator (BENCH) NEM DispatchIS",
            "source_url": "https://archive.benchmark.example.invalid/Reports/Current/DispatchIS_Reports/",
            "region_code": "BENCH_NEM_NSW1",
            "region_name": "BENCH NEM region NSW1",
            "market_scope": "bench_nem_dispatch_benchmark",
            "market_stage": "real_time",
            "price_scope": "regional_reference_price_15_minute_arithmetic_mean",
            "currency": "AUD",
            "price_unit": "AUD_per_MWh",
            "data_mode": "public_derived",
            "notes": "BENCH public benchmark fixture only; research_only and isolated.",
        }
    )
    bench_response = client.post("/v1/forecasting/research/datasets/manual", json=bench_payload)
    backtest = client.post(
        f"/v1/forecasting/research/datasets/{valid_dataset['dataset_id']}/backtests",
        json={"model_key": "seasonal_naive", "evaluation_days": 3, "lag_days": 7},
    )

    assert invalid_response.status_code == 200
    assert invalid_response.json()["status"] == "rejected"
    assert bench_response.status_code == 200
    assert backtest.status_code == 200

    overview = client.get("/v1/forecasting/research/overview")

    assert overview.status_code == 200
    payload = overview.json()
    assert payload["status"] == "warning"
    assert payload["dataset_count"] == 3
    assert payload["valid_dataset_count"] == 2
    assert payload["invalid_dataset_count"] == 1
    assert payload["research_only_dataset_count"] == 3
    assert payload["candidate_model_run_count"] == 1
    assert payload["succeeded_model_run_count"] == 1
    assert payload["bench_available_regions"] == ["NSW1"]
    assert payload["bench_region_count"] == 1
    assert set(payload["bench_missing_regions"]) == {"QLD1", "SA1", "TAS1", "VIC1"}
    assert payload["recent_import_runs"][0]["status"] in {"accepted", "rejected"}
    assert payload["recent_model_runs"][0]["registry_status"] == "candidate"
    assert payload["recent_model_runs"][0]["usage_scope"] == "research_only"
    assert "incomplete_trade_date" in {
        issue["issue_code"] for issue in payload["recent_quality_issues"]
    }
    assert {dataset["usage_scope"] for dataset in payload["datasets"]} == {"research_only"}
    assert payload["no_auto_trading"] is True
    assert payload["recommendation_chain_isolated"] is True

    with db_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(RecommendationRun)) == 0


def test_forecast_research_review_package_returns_read_only_operator_snapshot(
    client: TestClient,
    db_session_factory: sessionmaker[Session],
) -> None:
    dataset = import_dataset(client)
    dataset_id = dataset["dataset_id"]
    backtest = client.post(
        f"/v1/forecasting/research/datasets/{dataset_id}/backtests",
        json={"model_key": "seasonal_naive", "evaluation_days": 3, "lag_days": 7},
    )

    assert backtest.status_code == 200

    response = client.get(f"/v1/forecasting/research/datasets/{dataset_id}/review-package")

    assert response.status_code == 200
    package = response.json()
    assert package["package_version"] == "forecast_research_review_package_v1"
    assert package["dataset"]["dataset_id"] == dataset_id
    assert (
        package["dataset"]["source_url"]
        == "https://example.invalid/scenarios/interval-price-v1.json"
    )
    assert package["dataset"]["content_sha256"] == dataset["content_sha256"]
    assert package["dataset"]["data_mode"] == "scenario_simulated"
    assert package["dataset"]["usage_scope"] == "research_only"
    assert package["import_runs"][0]["status"] == "accepted"
    assert package["quality_issue_summary"] == {
        "total_count": 0,
        "severity_counts": {},
        "issue_code_counts": {},
        "displayed_issue_count": 0,
    }
    assert package["quality_issues"] == []
    assert package["model_runs"][0]["model_run_id"] == backtest.json()["model_run_id"]
    assert package["model_runs"][0]["registry_status"] == "candidate"
    assert package["model_runs"][0]["usage_scope"] == "research_only"
    assert package["no_auto_trading"] is True
    assert package["recommendation_chain_isolated"] is True
    assert package["network_probe_performed"] is False
    assert package["fetch_performed"] is False

    with db_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(RecommendationRun)) == 0


def test_forecast_research_review_package_summarizes_invalid_dataset_quality(
    client: TestClient,
) -> None:
    payload = research_dataset_payload(days=2)
    payload["points"].pop()
    imported = client.post("/v1/forecasting/research/datasets/manual", json=payload)

    assert imported.status_code == 200
    dataset = imported.json()
    assert dataset["status"] == "rejected"

    response = client.get(
        f"/v1/forecasting/research/datasets/{dataset['dataset_id']}/review-package"
    )

    assert response.status_code == 200
    package = response.json()
    summary = package["quality_issue_summary"]
    assert package["dataset"]["quality_status"] == "invalid"
    assert summary["total_count"] == dataset["quality_issue_count"]
    assert summary["displayed_issue_count"] == len(package["quality_issues"])
    assert summary["severity_counts"]["error"] == dataset["quality_issue_count"]
    assert summary["issue_code_counts"]["incomplete_trade_date"] == 1
    assert "incomplete_trade_date" in {issue["issue_code"] for issue in package["quality_issues"]}
    assert package["model_runs"] == []
    assert package["no_auto_trading"] is True
    assert package["recommendation_chain_isolated"] is True


def test_forecast_research_review_package_missing_dataset_returns_stable_error(
    client: TestClient,
) -> None:
    response = client.get("/v1/forecasting/research/datasets/forecast_missing/review-package")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "forecast_research_dataset_not_found"


def test_invalid_manual_curve_preserves_raw_dataset_and_quality_issues(
    client: TestClient,
    db_session_factory: sessionmaker[Session],
) -> None:
    payload = research_dataset_payload(days=2)
    payload["points"].pop()

    response = client.post("/v1/forecasting/research/datasets/manual", json=payload)

    assert response.status_code == 200
    dataset = response.json()
    assert dataset["status"] == "rejected"
    assert dataset["quality_status"] == "invalid"
    assert dataset["normalized_point_count"] == 0
    assert dataset["quality_issue_count"] >= 1

    issues = client.get(
        "/v1/forecasting/research/quality/issues",
        params={"dataset_id": dataset["dataset_id"]},
    )
    assert issues.status_code == 200
    assert "incomplete_trade_date" in {item["issue_code"] for item in issues.json()["items"]}

    points = client.get(f"/v1/forecasting/research/datasets/{dataset['dataset_id']}/points")
    assert points.json()["items"] == []

    backtest = client.post(
        f"/v1/forecasting/research/datasets/{dataset['dataset_id']}/backtests",
        json={"model_key": "seasonal_naive"},
    )
    assert backtest.status_code == 409
    assert backtest.json()["error"]["code"] == "forecast_research_dataset_not_usable"

    with db_session_factory() as session:
        stored = session.get(ForecastResearchDataset, dataset["dataset_id"])
        assert stored is not None
        stored_points = stored.raw_payload_json["points"]
        assert isinstance(stored_points, list)
        assert len(stored_points) == len(payload["points"])
        assert stored_points[0] == {
            "interval_start": "2026-01-01T00:00:00+08:00",
            "price": "100.0",
        }
        assert session.scalar(select(func.count()).select_from(ForecastResearchPricePoint)) == 0
        quality_issue_count = session.scalar(
            select(func.count()).select_from(ForecastResearchQualityIssue)
        )
        assert quality_issue_count is not None
        assert quality_issue_count >= 1


def test_research_backtests_persist_candidate_runs_and_predictions(
    client: TestClient,
    db_session_factory: sessionmaker[Session],
) -> None:
    dataset = import_dataset(client)
    dataset_id = dataset["dataset_id"]

    seasonal = client.post(
        f"/v1/forecasting/research/datasets/{dataset_id}/backtests",
        json={"model_key": "seasonal_naive", "evaluation_days": 3, "lag_days": 7},
    )
    calendar = client.post(
        f"/v1/forecasting/research/datasets/{dataset_id}/backtests",
        json={"model_key": "calendar_mean", "evaluation_days": 3, "lookback_days": 7},
    )

    assert seasonal.status_code == 200
    assert calendar.status_code == 200
    seasonal_run = seasonal.json()
    assert seasonal_run["registry_status"] == "candidate"
    assert seasonal_run["usage_scope"] == "research_only"
    assert seasonal_run["data_mode"] == "public_derived"
    assert seasonal_run["horizon_intervals"] == 96
    assert seasonal_run["metrics"]["prediction_count"] == 288
    assert set(seasonal_run["metrics"]) == {
        "direction_accuracy",
        "high_price_window_recall",
        "mae",
        "peak_period_mae",
        "peak_valley_spread_mae",
        "prediction_count",
        "rmse",
        "smape",
        "valley_period_mae",
    }
    assert calendar.json()["metrics"]["prediction_count"] == 288

    predictions = client.get(
        f"/v1/forecasting/research/model-runs/{seasonal_run['model_run_id']}/predictions",
        params={"limit": 500},
    )
    runs = client.get("/v1/forecasting/research/model-runs", params={"dataset_id": dataset_id})
    assert predictions.status_code == 200
    assert len(predictions.json()["items"]) == 288
    assert {item["model_key"] for item in runs.json()["items"]} == {
        "seasonal_naive",
        "calendar_mean",
    }

    with db_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(ForecastResearchModelRun)) == 2
        assert session.scalar(select(func.count()).select_from(ForecastResearchPrediction)) == 576


def test_research_backtest_rejects_insufficient_history(client: TestClient) -> None:
    dataset = import_dataset(client, days=2)

    response = client.post(
        f"/v1/forecasting/research/datasets/{dataset['dataset_id']}/backtests",
        json={"model_key": "seasonal_naive", "evaluation_days": 1, "lag_days": 7},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "forecast_research_dataset_not_usable"


def test_research_dataset_request_rejects_non_15_minute_contract(client: TestClient) -> None:
    payload = research_dataset_payload(days=1)
    payload["interval_minutes"] = 5

    response = client.post("/v1/forecasting/research/datasets/manual", json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
