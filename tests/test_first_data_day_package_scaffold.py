from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAFFOLD_SCRIPT = ROOT / "scripts" / "scaffold_first_data_day_package.py"
VALIDATOR_SCRIPT = ROOT / "scripts" / "validate_first_data_day_package.py"


def _run_scaffold(*args: str | Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCAFFOLD_SCRIPT), *[str(arg) for arg in args]],
        check=False,
        capture_output=True,
        text=True,
    )


def _run_validator(*args: str | Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(VALIDATOR_SCRIPT), *[str(arg) for arg in args]],
        check=False,
        capture_output=True,
        text=True,
    )


def test_scaffold_creates_empty_package_skeleton(tmp_path: Path) -> None:
    package_dir = tmp_path / "first-data-day"

    completed = _run_scaffold("--output-dir", package_dir, "--json")

    assert completed.returncode == 0, completed.stdout + completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["suite"] == "first_data_day_package_scaffold"
    assert payload["ok"] is True
    assert payload["status"] == "scaffold_created"
    assert payload["creates_data_files"] is False
    assert payload["database_write"] is False
    assert payload["external_network_access"] is False
    assert payload["external_model_call"] is False
    assert payload["no_auto_trading"] is True
    for directory_name in ["forecast", "rag", "market", "weather", "recommendation"]:
        assert (package_dir / directory_name).is_dir()
    manifest = json.loads((package_dir / "first_data_day_package.json").read_text())
    assert manifest["template_mode"] is False
    assert (package_dir / "README.md").is_file()


def test_scaffold_refuses_to_overwrite_without_force(tmp_path: Path) -> None:
    package_dir = tmp_path / "first-data-day"
    first = _run_scaffold("--output-dir", package_dir, "--json")

    second = _run_scaffold("--output-dir", package_dir, "--json")

    assert first.returncode == 0, first.stdout + first.stderr
    assert second.returncode == 1
    payload = json.loads(second.stdout)
    assert payload["status"] == "refusing_to_overwrite"
    assert str(package_dir / "first_data_day_package.json") in payload["existing_items"]
    assert str(package_dir / "README.md") in payload["existing_items"]


def test_scaffold_force_overwrites_generated_metadata(tmp_path: Path) -> None:
    package_dir = tmp_path / "first-data-day"
    first = _run_scaffold("--output-dir", package_dir, "--json")
    (package_dir / "README.md").write_text("local edit", encoding="utf-8")

    second = _run_scaffold("--output-dir", package_dir, "--force", "--json")

    assert first.returncode == 0, first.stdout + first.stderr
    assert second.returncode == 0, second.stdout + second.stderr
    assert "local edit" not in (package_dir / "README.md").read_text(encoding="utf-8")


def test_scaffold_then_dry_run_reports_all_missing_workflows(tmp_path: Path) -> None:
    package_dir = tmp_path / "first-data-day"
    scaffolded = _run_scaffold("--output-dir", package_dir, "--json")

    completed = _run_validator("--package-dir", package_dir, "--json")

    assert scaffolded.returncode == 0, scaffolded.stdout + scaffolded.stderr
    assert completed.returncode == 1
    payload = json.loads(completed.stdout)
    assert payload["ok"] is False
    assert payload["status"] == "missing_required_inputs"
    assert "forecast/forecast_research_curve_placeholder.csv" in payload["missing_items"]
    assert "rag/policy_document_placeholder.pdf" in payload["missing_items"]
    assert "market/public_artifact_placeholder.html" in payload["missing_items"]
    assert "weather/open_meteo_reference_placeholder.json" in payload["missing_items"]
    assert "recommendation/review_context_placeholder.json" in payload["missing_items"]
    assert payload["workflow_readiness"] == {
        "rag": "missing_required_inputs",
        "forecast": "missing_required_inputs",
        "backtest": "missing_required_inputs",
        "market_weather": "missing_required_inputs",
        "recommendation": "missing_required_inputs",
    }
