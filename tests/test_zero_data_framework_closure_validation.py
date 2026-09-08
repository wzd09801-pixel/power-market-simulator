from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_zero_data_framework_closure.py"
POWERSHELL_ENTRYPOINT = ROOT / "scripts" / "validate_zero_data_framework_closure.ps1"


def test_zero_data_framework_closure_script_passes() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "contract and template coverage" in completed.stdout
    assert "first data day scaffold dry-run" in completed.stdout
    assert "empty-state safety closure" in completed.stdout
    assert "zero-data closure" in completed.stdout


def test_zero_data_framework_closure_json_marks_local_boundaries() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--json"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["suite"] == "zero_data_first_data_day_framework_closure"
    assert payload["ok"] is True
    assert [check["name"] for check in payload["checks"]] == [
        "contract and template coverage",
        "first data day scaffold dry-run",
        "empty-state safety closure",
    ]
    assert payload["host_only"] is True
    assert payload["read_only_repo"] is True
    assert payload["docker_required"] is False
    assert payload["external_network_access"] is False
    assert payload["persistent_database_access"] is False
    assert payload["external_model_call"] is False
    assert payload["model_promotion"] is False
    assert payload["schema_migration_required"] is False
    assert payload["recommendation_execution_change"] is False
    assert payload["no_auto_trading"] is True


def test_zero_data_framework_closure_scripts_keep_static_safety_boundaries() -> None:
    text = "\n".join(
        [
            SCRIPT.read_text(encoding="utf-8"),
            POWERSHELL_ENTRYPOINT.read_text(encoding="utf-8"),
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

    for phrase in [
        "scaffold_package",
        "missing_required_inputs",
        "workflow_readiness",
        "scenario_simulated_only",
        "test_empty_corpus_overview_warns_without_fetching",
        "test_forecast_research_overview_empty_database_returns_warning",
    ]:
        assert phrase in normalized
