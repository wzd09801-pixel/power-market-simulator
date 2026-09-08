from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_forecast_training_trial.py"
POWERSHELL_ENTRYPOINT = ROOT / "scripts" / "validate_forecast_training_trial.ps1"


def test_forecast_training_trial_validator_script_passes_host_only_flow() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "empty overview" in completed.stdout
    assert "valid import" in completed.stdout
    assert "invalid quality" in completed.stdout
    assert "backtest" in completed.stdout
    assert "predictions" in completed.stdout
    assert "review package" in completed.stdout
    assert "recommendation isolation" in completed.stdout


def test_forecast_training_trial_validator_json_output_marks_local_boundaries() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--json"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["ok"] is True
    assert payload["host_only"] is True
    assert payload["external_network_access"] is False
    assert payload["persistent_database_access"] is False
    assert payload["model_promotion"] is False
    assert payload["no_auto_trading"] is True


def test_forecast_training_trial_scripts_keep_mvp_boundaries() -> None:
    text = "\n".join(
        [
            SCRIPT.read_text(encoding="utf-8"),
            POWERSHELL_ENTRYPOINT.read_text(encoding="utf-8"),
        ]
    )
    normalized = " ".join(text.lower().split())

    assert "requests." not in normalized
    assert "httpx." not in normalized
    assert "invoke-webrequest" not in normalized
    assert "invoke-restmethod" not in normalized
    assert "docker compose" not in normalized
    assert "alembic downgrade" not in normalized
    assert 'registry_status="production"' not in normalized
    assert '"registry_status": "production"' not in normalized
    assert "no_auto_trading=false" not in normalized
    assert "scenario_simulated" in normalized
    assert "research_only" in normalized
    assert "candidate" in normalized
