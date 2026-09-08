from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_framework_readiness.py"
POWERSHELL_ENTRYPOINT = ROOT / "scripts" / "validate_framework_readiness.ps1"


def test_framework_readiness_script_passes_static_gate() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    for name in [
        "import contracts",
        "first data day package dry-run",
        "forecast dataset manifest",
        "rag document readiness",
        "market weather readiness",
        "training backtest prerequisites",
        "recommendation safety boundaries",
    ]:
        assert name in completed.stdout
    assert "framework boundaries" in completed.stdout


def test_framework_readiness_json_output_marks_local_boundaries() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--json"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["suite"] == "framework_readiness_host_only"
    assert payload["ok"] is True
    assert payload["host_only"] is True
    assert payload["read_only"] is True
    assert payload["docker_required"] is False
    assert payload["external_network_access"] is False
    assert payload["persistent_database_access"] is False
    assert payload["external_model_call"] is False
    assert payload["model_promotion"] is False
    assert payload["schema_migration_required"] is False
    assert payload["no_auto_trading"] is True
    assert [check["name"] for check in payload["checks"]] == [
        "import contracts",
        "first data day package dry-run",
        "forecast dataset manifest",
        "rag document readiness",
        "market weather readiness",
        "training backtest prerequisites",
        "recommendation safety boundaries",
    ]


def test_framework_readiness_scripts_keep_read_only_boundaries() -> None:
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

    assert "validate_import_contracts" in normalized
    assert "validate_first_data_day_package" in normalized
    assert "scaffold_first_data_day_package" in normalized
    assert "external_network_access" in normalized
    assert "schema_migration_required" in normalized


def test_framework_readiness_covers_required_subsystems() -> None:
    normalized = " ".join(SCRIPT.read_text(encoding="utf-8").lower().split())

    for phrase in [
        "forecast dataset manifest",
        "first data day package dry-run",
        "rag document readiness",
        "market weather readiness",
        "training backtest prerequisites",
        "recommendation safety boundaries",
        "first_data_day_package.example.json",
        "scaffold_first_data_day_package.py",
        "forecast_research_dataset.example.json",
        "policy_document_upload.example.json",
        "market_artifact_manual_submission.example.json",
        "weather_open_meteo_reference_request.example.json",
        "recommendation_request.example.json",
    ]:
        assert phrase in normalized
