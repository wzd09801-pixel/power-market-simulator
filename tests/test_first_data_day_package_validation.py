from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_first_data_day_package.py"
POWERSHELL_ENTRYPOINT = ROOT / "scripts" / "validate_first_data_day_package.ps1"
TEMPLATE_MANIFEST = ROOT / "docs" / "import_contracts" / "first_data_day_package.example.json"


def _run_validator(*args: str | Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *[str(arg) for arg in args]],
        check=False,
        capture_output=True,
        text=True,
    )


def _payload(completed: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    return json.loads(completed.stdout)


def _metadata(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "data_mode": "user_uploaded",
        "source_name": "Local operator package",
        "source_url": None,
        "source_timestamp": None,
        "timezone": "Asia/Shanghai",
        "unit": "CNY_per_MWh",
        "permission": "local_operator_upload",
        "visibility_scope": "local_only",
        "human_review_required": True,
        "no_auto_trading": True,
    }
    base.update(overrides)
    return base


def _manifest(*, files: list[dict[str, Any]], template_mode: bool = True) -> dict[str, Any]:
    return {
        "package_version": "first_data_day_package_v1",
        "package_name": "Test first data day package",
        "template_mode": template_mode,
        "safety": {
            "no_auto_trading": True,
            "external_model_call": False,
            "model_promotion": False,
            "database_write": False,
            "network_access": False,
        },
        "capability_defaults": {
            "rag_answering_enabled": False,
            "forecast_training_enabled": False,
            "backtest_enabled": False,
            "recommendation_mode": "scenario_simulated_only",
            "external_model_call": False,
            "no_auto_trading": True,
        },
        "recommendation_boundaries": {
            "data_mode_until_reviewed_evidence": "scenario_simulated",
            "human_review_required": True,
            "research_only_evidence_allowed": False,
            "no_auto_trading": True,
        },
        "files": files,
    }


def test_first_data_day_template_manifest_passes() -> None:
    completed = _run_validator("--manifest", TEMPLATE_MANIFEST, "--json")

    assert completed.returncode == 0, completed.stdout + completed.stderr
    payload = _payload(completed)
    assert payload["suite"] == "first_data_day_package_dry_run"
    assert payload["ok"] is True
    assert payload["status"] == "ready_for_manual_review"
    assert payload["host_only"] is True
    assert payload["read_only"] is True
    assert payload["docker_required"] is False
    assert payload["network_access"] is False
    assert payload["external_network_access"] is False
    assert payload["database_access"] is False
    assert payload["persistent_database_access"] is False
    assert payload["database_write"] is False
    assert payload["external_model_call"] is False
    assert payload["model_promotion"] is False
    assert payload["schema_migration_required"] is False
    assert payload["file_upload"] is False
    assert payload["recommendation_execution_change"] is False
    assert payload["no_auto_trading"] is True
    assert payload["workflow_readiness"] == {
        "rag": "ready_for_manual_review",
        "forecast": "ready_for_manual_review",
        "backtest": "ready_for_manual_review",
        "market_weather": "ready_for_manual_review",
        "recommendation": "ready_for_manual_review",
    }


def test_empty_package_directory_reports_missing_inputs_without_traceback(tmp_path: Path) -> None:
    completed = _run_validator("--package-dir", tmp_path, "--json")

    assert completed.returncode == 1
    assert "Traceback" not in completed.stderr
    payload = _payload(completed)
    assert payload["ok"] is False
    assert payload["status"] == "missing_required_inputs"
    assert "first_data_day_package.json" in payload["missing_items"]
    assert "forecast/forecast_research_curve.csv" in payload["missing_items"]
    assert "rag/policy_document.pdf" in payload["missing_items"]
    assert "weather/open_meteo_reference.json" in payload["missing_items"]
    assert "recommendation/review_context.json" in payload["missing_items"]
    assert payload["workflow_readiness"] == {
        "rag": "missing_required_inputs",
        "forecast": "missing_required_inputs",
        "backtest": "missing_required_inputs",
        "market_weather": "missing_required_inputs",
        "recommendation": "missing_required_inputs",
    }
    assert payload["disabled_capabilities"]
    assert payload["simulated_only_capabilities"]
    assert payload["capability_flags"]["rag_answering_enabled"] is False
    assert payload["capability_flags"]["forecast_training_enabled"] is False
    assert payload["capability_flags"]["backtest_enabled"] is False
    assert payload["capability_flags"]["recommendation_mode"] == "scenario_simulated_only"
    assert payload["external_model_call"] is False
    assert payload["file_upload"] is False
    assert payload["recommendation_execution_change"] is False
    assert payload["no_auto_trading"] is True
    assert payload["next_actions"]


def test_malformed_manifest_reports_field_level_errors(tmp_path: Path) -> None:
    manifest = tmp_path / "first_data_day_package.json"
    manifest.write_text(
        json.dumps(
            {
                "package_version": "wrong",
                "package_name": "Bad package",
                "template_mode": False,
                "files": [],
            }
        ),
        encoding="utf-8",
    )

    completed = _run_validator("--package-dir", tmp_path, "--manifest", manifest, "--json")

    assert completed.returncode == 1
    payload = _payload(completed)
    assert payload["status"] == "invalid_manifest"
    messages = " ".join(check["message"] for check in payload["checks"])
    assert "package_version" in messages
    assert "safety" in messages
    assert "files" in messages


def test_unsupported_extension_and_path_traversal_are_rejected(tmp_path: Path) -> None:
    manifest = tmp_path / "first_data_day_package.json"
    payload = _manifest(
        files=[
            {
                "entry_id": "unsafe",
                "relative_path": "../outside.exe",
                "file_type": "exe",
                "target_workflow": "forecast_research_curve",
                "metadata": _metadata(
                    usage_scope="research_only",
                    interval_minutes=15,
                    price_unit="CNY_per_MWh",
                ),
            }
        ]
    )
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    completed = _run_validator("--package-dir", tmp_path, "--manifest", manifest, "--json")

    assert completed.returncode == 1
    messages = " ".join(check["message"] for check in _payload(completed)["checks"])
    assert "unsupported file type" in messages
    assert "traversal" in messages


def test_local_csv_and_json_shapes_are_checked_without_import(tmp_path: Path) -> None:
    forecast_dir = tmp_path / "forecast"
    forecast_dir.mkdir()
    (forecast_dir / "curve.csv").write_text(
        "interval_start,price\n2026-06-17T00:00:00+08:00,320.5\n",
        encoding="utf-8",
    )
    (forecast_dir / "dataset.json").write_text(
        json.dumps(
            {
                "points": [],
                "usage_scope": "research_only",
                "interval_minutes": 15,
            }
        ),
        encoding="utf-8",
    )
    manifest = tmp_path / "first_data_day_package.json"
    manifest.write_text(
        json.dumps(
            _manifest(
                template_mode=False,
                files=[
                    {
                        "entry_id": "curve",
                        "relative_path": "forecast/curve.csv",
                        "file_type": "csv",
                        "target_workflow": "forecast_research_curve",
                        "required_columns": ["interval_start", "price"],
                        "metadata": _metadata(
                            usage_scope="research_only",
                            interval_minutes=15,
                            price_unit="CNY_per_MWh",
                        ),
                    },
                    {
                        "entry_id": "dataset",
                        "relative_path": "forecast/dataset.json",
                        "file_type": "json",
                        "target_workflow": "forecast_dataset_manifest",
                        "required_fields": [
                            "points",
                            "usage_scope",
                            "data_mode",
                            "interval_minutes",
                        ],
                        "metadata": _metadata(
                            usage_scope="research_only",
                            interval_minutes=15,
                            price_unit="CNY_per_MWh",
                        ),
                    },
                ],
            )
        ),
        encoding="utf-8",
    )

    completed = _run_validator("--package-dir", tmp_path, "--manifest", manifest, "--json")

    assert completed.returncode == 0, completed.stdout + completed.stderr
    payload = _payload(completed)
    assert payload["ok"] is True
    assert payload["status"] == "ready_for_manual_review"
    assert payload["workflow_readiness"]["forecast"] == "ready_for_manual_review"
    assert payload["workflow_readiness"]["backtest"] == "ready_for_manual_review"


def test_weather_and_recommendation_json_shapes_are_checked_without_import(
    tmp_path: Path,
) -> None:
    (tmp_path / "weather").mkdir()
    (tmp_path / "recommendation").mkdir()
    (tmp_path / "weather" / "reference.json").write_text(
        json.dumps(
            {
                "location_id": "demo_hydro_a_reference",
                "location_name": "Demo Hydro A reference",
                "latitude": 30.0,
                "longitude": 110.0,
                "timezone": "Asia/Shanghai",
                "hourly_variables": ["temperature_2m", "precipitation"],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "recommendation" / "review_context.json").write_text(
        json.dumps(
            {
                "scenario_id": "demo_hydro_a_normal_storage_normal_inflow_v1",
                "data_mode": "scenario_simulated",
                "human_review_required": True,
                "no_auto_trading": True,
                "evidence_ready": False,
            }
        ),
        encoding="utf-8",
    )
    manifest = tmp_path / "first_data_day_package.json"
    manifest.write_text(
        json.dumps(
            _manifest(
                template_mode=False,
                files=[
                    {
                        "entry_id": "weather",
                        "relative_path": "weather/reference.json",
                        "file_type": "json",
                        "target_workflow": "weather_reference_request",
                        "required_fields": [
                            "location_id",
                            "location_name",
                            "latitude",
                            "longitude",
                            "timezone",
                            "hourly_variables",
                        ],
                        "metadata": _metadata(
                            unit="weather_reference",
                            manual_submission_only=True,
                            fetch_performed=False,
                            network_probe_performed=False,
                            review_package_required=True,
                            no_auto_recommendation=True,
                        ),
                    },
                    {
                        "entry_id": "recommendation",
                        "relative_path": "recommendation/review_context.json",
                        "file_type": "json",
                        "target_workflow": "recommendation_review_context",
                        "required_fields": [
                            "scenario_id",
                            "data_mode",
                            "human_review_required",
                            "no_auto_trading",
                            "evidence_ready",
                        ],
                        "metadata": _metadata(
                            data_mode="scenario_simulated",
                            unit="review_context",
                            recommendation_mode="scenario_simulated_only",
                            no_auto_recommendation_execution=True,
                            evidence_ready=False,
                        ),
                    },
                ],
            )
        ),
        encoding="utf-8",
    )

    completed = _run_validator("--package-dir", tmp_path, "--manifest", manifest, "--json")

    assert completed.returncode == 0, completed.stdout + completed.stderr
    payload = _payload(completed)
    assert payload["workflow_readiness"]["market_weather"] == "ready_for_manual_review"
    assert payload["workflow_readiness"]["recommendation"] == "ready_for_manual_review"


def test_first_data_day_scripts_keep_static_safety_boundaries() -> None:
    text = "\n".join(
        [
            SCRIPT.read_text(encoding="utf-8"),
            POWERSHELL_ENTRYPOINT.read_text(encoding="utf-8"),
            (ROOT / "scripts" / "scaffold_first_data_day_package.py").read_text(encoding="utf-8"),
            (ROOT / "scripts" / "scaffold_first_data_day_package.ps1").read_text(encoding="utf-8"),
        ]
    )
    normalized = " ".join(text.lower().split())

    forbidden = [
        "requests.",
        "httpx.",
        "urllib.request",
        "invoke-webrequest",
        "invoke-restmethod",
        "docker compose",
        "remove-item",
        "remove-volume",
        "--volumes",
        "alembic downgrade",
        "no_auto_trading=false",
        '"no_auto_trading": false',
        'registry_status="production"',
        '"registry_status": "production"',
        "model_promotion=true",
        '"model_promotion": true',
        "subprocess",
    ]
    for phrase in forbidden:
        assert phrase not in normalized
