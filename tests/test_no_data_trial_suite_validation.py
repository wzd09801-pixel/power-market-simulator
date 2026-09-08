from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_no_data_trial_suite.py"
POWERSHELL_ENTRYPOINT = ROOT / "scripts" / "validate_no_data_trial_suite.ps1"


def test_no_data_trial_suite_script_passes_host_only_flow() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "import contracts" in completed.stdout
    assert "rag local trial" in completed.stdout
    assert "forecast training trial" in completed.stdout
    assert "suite boundaries" in completed.stdout


def test_no_data_trial_suite_json_output_marks_local_boundaries() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--json"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["suite"] == "no_data_host_only"
    assert payload["ok"] is True
    assert payload["host_only"] is True
    assert payload["docker_required"] is False
    assert payload["external_network_access"] is False
    assert payload["persistent_database_access"] is False
    assert payload["external_model_call"] is False
    assert payload["model_promotion"] is False
    assert payload["no_auto_trading"] is True
    assert [check["name"] for check in payload["checks"]] == [
        "import contracts",
        "rag local trial",
        "forecast training trial",
    ]


def test_no_data_trial_suite_keeps_non_external_boundaries() -> None:
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
    assert "no_auto_trading=false" not in normalized
    assert "validate_import_contracts.py" in normalized
    assert "validate_rag_trial.py" in normalized
    assert "validate_forecast_training_trial.py" in normalized
