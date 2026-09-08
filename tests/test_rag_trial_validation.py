from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_rag_trial.py"
POWERSHELL_ENTRYPOINT = ROOT / "scripts" / "validate_rag_trial.ps1"


def test_rag_trial_validator_script_passes_host_only_flow() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "empty corpus" in completed.stdout
    assert "local upload" in completed.stdout
    assert "review package" in completed.stdout
    assert "search" in completed.stdout
    assert "unauthorized Q&A" in completed.stdout
    assert "authorized fake Q&A" in completed.stdout
    assert "document review" in completed.stdout


def test_rag_trial_validator_json_output_marks_local_boundaries() -> None:
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
    assert payload["external_model_call"] is False
    assert payload["no_auto_trading"] is True


def test_rag_trial_scripts_keep_non_external_boundaries() -> None:
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
    assert "memoryblobstore" in normalized
    assert "hashembeddingclient" in normalized
    assert "local-fake-deepseek" in normalized
