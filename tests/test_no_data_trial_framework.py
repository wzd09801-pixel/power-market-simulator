from __future__ import annotations

import csv
import json
import subprocess
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from backend.app.schemas.forecasting import (
    ForecastResearchBacktestRequest,
    ManualForecastResearchDatasetRequest,
)
from backend.app.schemas.market import ManualMarketArtifactRequest
from backend.app.schemas.recommendation import RecommendationRunRequest
from backend.app.schemas.scenario import HydroOptimizationRunRequest
from backend.app.schemas.weather import OpenMeteoForecastIngestRequest

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "docs" / "import_contracts"


def _json(name: str) -> dict[str, Any]:
    return json.loads((CONTRACTS / name).read_text(encoding="utf-8"))


def test_no_data_import_contract_files_are_present_and_linked() -> None:
    expected = {
        "README.md",
        "first_data_day_package.example.json",
        "policy_document_upload.example.json",
        "market_artifact_manual_submission.example.json",
        "weather_open_meteo_reference_request.example.json",
        "forecast_research_curve.example.csv",
        "forecast_research_dataset.example.json",
        "forecast_backtest_request.example.json",
        "hydro_optimization_request.example.json",
        "recommendation_request.example.json",
    }

    assert expected <= {path.name for path in CONTRACTS.iterdir()}
    assert "docs/no_data_trial_framework.md" in (ROOT / "README.md").read_text(encoding="utf-8")


def test_json_examples_match_existing_request_contracts() -> None:
    ManualMarketArtifactRequest.model_validate(
        _json("market_artifact_manual_submission.example.json")
    )
    OpenMeteoForecastIngestRequest.model_validate(
        _json("weather_open_meteo_reference_request.example.json")
    )
    ManualForecastResearchDatasetRequest.model_validate(
        _json("forecast_research_dataset.example.json")
    )
    ForecastResearchBacktestRequest.model_validate(_json("forecast_backtest_request.example.json"))
    HydroOptimizationRunRequest.model_validate(_json("hydro_optimization_request.example.json"))
    RecommendationRunRequest.model_validate(_json("recommendation_request.example.json"))


def test_policy_upload_contract_keeps_local_only_defaults() -> None:
    payload = _json("policy_document_upload.example.json")

    assert payload["target_endpoint"] == "POST /v1/policy/documents/upload"
    assert payload["form_fields"]["document_layer"] == "user_uploaded"
    assert payload["expected_defaults"]["data_mode"] == "user_uploaded"
    assert payload["expected_defaults"]["external_processing_allowed"] is False
    assert payload["expected_defaults"]["no_auto_trading"] is True


def test_forecast_csv_example_is_one_complete_96_point_curve() -> None:
    with (CONTRACTS / "forecast_research_curve.example.csv").open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 96
    starts = [datetime.fromisoformat(row["interval_start"]) for row in rows]
    assert len(set(starts)) == 96
    assert all(start.utcoffset() is not None for start in starts)
    assert all(
        starts[index + 1] - starts[index] == timedelta(minutes=15)
        for index in range(len(starts) - 1)
    )
    assert all(Decimal(row["price"]) >= Decimal("-100000") for row in rows)


def test_forecast_json_points_match_csv_contract() -> None:
    dataset = _json("forecast_research_dataset.example.json")
    with (CONTRACTS / "forecast_research_curve.example.csv").open(encoding="utf-8") as handle:
        csv_rows = list(csv.DictReader(handle))

    assert dataset["usage_scope"] == "research_only"
    assert dataset["data_mode"] == "user_uploaded"
    assert len(dataset["points"]) == 96
    assert [(point["interval_start"], point["price"]) for point in dataset["points"]] == [
        (row["interval_start"], row["price"]) for row in csv_rows
    ]


def test_no_data_framework_docs_preserve_mvp_boundaries() -> None:
    text = "\n".join(
        [
            (ROOT / "docs" / "no_data_trial_framework.md").read_text(encoding="utf-8"),
            (CONTRACTS / "README.md").read_text(encoding="utf-8"),
        ]
    ).lower()

    normalized = " ".join(text.split())
    required_phrases = [
        "no_auto_trading=true",
        "external model use remains opt-in",
        "arbitrary url",
        "trading platform login automation",
        "unreviewed model promotion",
        "research_only",
        "scenario_simulated",
        "user_uploaded",
    ]
    for phrase in required_phrases:
        assert phrase in normalized
    assert '"no_auto_trading": false' not in normalized


def test_no_data_validation_script_keeps_compose_run_non_destructive() -> None:
    script = (ROOT / "scripts" / "run_no_data_trial_validation.ps1").read_text(encoding="utf-8")
    normalized = " ".join(script.lower().split())

    assert "eee-no-data-" in normalized
    assert "new-trialtcpport" in normalized
    assert "/v1/system/readiness" in normalized
    assert "demo_research_workspace_seed" in normalized
    assert "/v1/operations/review-package" in normalized
    assert "docker compose -p $projectname stop" in normalized
    assert "docker compose -p $projectname down" not in normalized
    assert "remove-volume" not in normalized
    assert "--volumes" not in normalized
    assert "alembic downgrade" not in normalized
    assert "no_auto_trading" in normalized
    assert "fetch_performed" in normalized
    assert "network_probe_performed" in normalized


def test_no_data_workstation_gate_runs_host_only_checks() -> None:
    script = (ROOT / "scripts" / "validate_no_data_workstation.ps1").read_text(encoding="utf-8")
    normalized = " ".join(script.lower().split())

    assert "validate_no_data_trial_suite.ps1" in normalized
    assert "test:e2e:no-data-workspaces" in normalized
    assert "push-location" in normalized
    assert "pop-location" in normalized
    assert "docker compose" not in normalized
    assert "invoke-webrequest" not in normalized
    assert "invoke-restmethod" not in normalized
    assert "remove-item" not in normalized
    assert "--volumes" not in normalized
    assert "alembic downgrade" not in normalized
    assert "no_auto_trading=false" not in normalized


def test_import_contract_validator_script_passes_examples() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "validate_import_contracts.py"),
            "--contracts-dir",
            str(CONTRACTS),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "schema examples" in completed.stdout
    assert "forecast csv curve" in completed.stdout
