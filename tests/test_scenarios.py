from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.models.recommendation import RecommendationRun
from backend.app.models.scenario import HydroOptimizationRun

EXPECTED_CONSTRAINT_ONLY_WARNINGS = [
    "预演仅使用公开校准的 scenario_simulated 场景，不能作为交易或调度指令。",
    "没有使用经过核验的公司水库运行数据、中长期持仓数据或真实调度边界。",
    "尚未接入经过核验的示例甲省现货 96 点价格曲线；本次按约束均衡分配。",
]

EXPECTED_PRICE_SIGNAL_WARNINGS = [
    "预演仅使用公开校准的 scenario_simulated 场景，不能作为交易或调度指令。",
    "没有使用经过核验的公司水库运行数据、中长期持仓数据或真实调度边界。",
    "价格信号是本地预演输入，未被标记为核验后的示例甲省现货价格序列。",
]


def test_default_demo_hydro_scenario_is_simulated(client: TestClient) -> None:
    response = client.get("/v1/scenarios/demo_hydro/default")
    assert response.status_code == 200
    payload = response.json()
    assert payload["asset_id"] == "demo_hydro_a"
    assert payload["data_mode"] == "scenario_simulated"
    assert "not verified company operational data" in payload["warning"]
    assert payload["installed_capacity_mw"] == 1000.0


def test_hydro_constraint_only_preview_is_persisted_without_recommendation(
    client: TestClient,
    db_session_factory: sessionmaker[Session],
) -> None:
    response = client.post(
        "/v1/scenarios/demo_hydro/optimization-runs",
        json={"trade_date": "2026-06-01"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["optimization_run_id"].startswith("hydro_opt_")
    assert payload["algorithm_key"] == "deterministic_priority_v1"
    assert payload["data_mode"] == "scenario_simulated"
    assert payload["price_signal_used"] is False
    assert payload["human_review_required"] is True
    assert payload["no_auto_trading"] is True
    assert len(payload["intervals"]) == 96
    assert len(payload["top_priority_intervals"]) == 8
    assert payload["missing_data_warnings"] == EXPECTED_CONSTRAINT_ONLY_WARNINGS
    assert any(
        "No price signal supplied" in explanation
        for explanation in payload["constraint_explanation"]
    )
    assert {item["data_mode"] for item in payload["evidence"]} == {
        "scenario_simulated",
    }

    detail = client.get(
        f"/v1/scenarios/demo_hydro/optimization-runs/{payload['optimization_run_id']}"
    )
    recent = client.get("/v1/scenarios/demo_hydro/optimization-runs/recent")

    assert detail.status_code == 200
    assert detail.json()["optimization_run_id"] == payload["optimization_run_id"]
    assert recent.status_code == 200
    assert recent.json()["items"][0]["optimization_run_id"] == payload["optimization_run_id"]

    with db_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(HydroOptimizationRun)) == 1
        assert session.scalar(select(func.count()).select_from(RecommendationRun)) == 0


def test_hydro_price_signal_preview_prioritizes_high_price_intervals(
    client: TestClient,
) -> None:
    price_signal = [{"interval_index": interval, "price": interval} for interval in range(1, 97)]

    response = client.post(
        "/v1/scenarios/demo_hydro/optimization-runs",
        json={
            "trade_date": "2026-06-01",
            "energy_budget_mwh": 9800.0,
            "min_output_mw": 400.0,
            "max_output_mw": 800.0,
            "price_signal": price_signal,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["price_signal_used"] is True
    assert payload["missing_data_warnings"] == EXPECTED_PRICE_SIGNAL_WARNINGS
    assert any(
        "Price signal supplied" in explanation for explanation in payload["constraint_explanation"]
    )
    assert "user_uploaded" in {item["data_mode"] for item in payload["evidence"]}
    assert payload["top_priority_intervals"][0]["interval_index"] == 96
    assert payload["top_priority_intervals"][0]["priority_rank"] == 1
    by_interval = {item["interval_index"]: item for item in payload["intervals"]}
    assert by_interval[96]["target_output_mw"] == 800.0
    assert by_interval[95]["target_output_mw"] == 800.0
    assert by_interval[1]["target_output_mw"] == 400.0
    assert "installed_capacity_ceiling" in by_interval[96]["binding_constraints"]
    assert "minimum_output_floor" in by_interval[1]["binding_constraints"]


def test_hydro_preview_rejects_infeasible_energy_budget(client: TestClient) -> None:
    too_low = client.post(
        "/v1/scenarios/demo_hydro/optimization-runs",
        json={
            "trade_date": "2026-06-01",
            "energy_budget_mwh": 9000.0,
            "min_output_mw": 400.0,
            "max_output_mw": 800.0,
        },
    )
    too_high = client.post(
        "/v1/scenarios/demo_hydro/optimization-runs",
        json={
            "trade_date": "2026-06-01",
            "energy_budget_mwh": 20_000.0,
            "min_output_mw": 400.0,
            "max_output_mw": 800.0,
        },
    )

    assert too_low.status_code == 409
    assert too_low.json()["error"]["code"] == "hydro_optimization_request_not_usable"
    assert "minimum output energy" in too_low.json()["error"]["message"]
    assert too_high.status_code == 409
    assert "installed-capacity energy" in too_high.json()["error"]["message"]


def test_hydro_preview_rejects_incomplete_price_signal(client: TestClient) -> None:
    response = client.post(
        "/v1/scenarios/demo_hydro/optimization-runs",
        json={
            "trade_date": "2026-06-01",
            "price_signal": [{"interval_index": 1, "price": 100}],
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_hydro_preview_missing_run_returns_stable_error(client: TestClient) -> None:
    response = client.get("/v1/scenarios/demo_hydro/optimization-runs/hydro_opt_missing")

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "hydro_optimization_run_not_found",
            "message": "Hydro optimization run 'hydro_opt_missing' was not found.",
        }
    }
