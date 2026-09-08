from __future__ import annotations

# ruff: noqa: E402, I001

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "docs" / "import_contracts"
SCRIPTS = ROOT / "scripts"

sys.path.insert(0, str(SCRIPTS))

from scaffold_first_data_day_package import scaffold_package  # noqa: E402
from validate_first_data_day_package import build_report  # noqa: E402

REQUIRED_TARGET_WORKFLOWS = {
    "forecast_research_curve",
    "forecast_dataset_manifest",
    "rag_document_upload",
    "market_artifact_manual_preservation",
    "weather_reference_request",
    "recommendation_review_context",
}
REQUIRED_FILE_TYPES = {"csv", "json", "pdf", "docx", "html"}
REQUIRED_METADATA_FIELDS = {
    "data_mode",
    "source_name",
    "source_timestamp",
    "timezone",
    "unit",
    "permission",
    "visibility_scope",
    "human_review_required",
    "no_auto_trading",
}
REQUIRED_WORKFLOW_READINESS = {
    "rag": "missing_required_inputs",
    "forecast": "missing_required_inputs",
    "backtest": "missing_required_inputs",
    "market_weather": "missing_required_inputs",
    "recommendation": "missing_required_inputs",
}


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    message: str


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate the zero-data first-data-day framework closure locally."
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable results.")
    args = parser.parse_args()

    results = run_checks()
    ok = all(result.ok for result in results)
    payload = {
        "suite": "zero_data_first_data_day_framework_closure",
        "ok": ok,
        "checks": [result.__dict__ for result in results],
        "host_only": True,
        "read_only_repo": True,
        "docker_required": False,
        "external_network_access": False,
        "persistent_database_access": False,
        "external_model_call": False,
        "model_promotion": False,
        "schema_migration_required": False,
        "recommendation_execution_change": False,
        "no_auto_trading": True,
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=True, indent=2))
    else:
        for result in results:
            status = "ok" if result.ok else "fail"
            print(f"[{status}] {result.name}: {result.message}")
        print(
            "[ok] zero-data closure: contracts, dry-run, and empty-state boundaries are complete"
            if ok
            else "[fail] zero-data closure: one or more checks failed"
        )
    return 0 if ok else 1


def run_checks() -> list[CheckResult]:
    checks = (
        ("contract and template coverage", _check_contract_and_template_coverage),
        ("first data day scaffold dry-run", _check_scaffold_dry_run),
        ("empty-state safety closure", _check_empty_state_safety_closure),
    )
    results: list[CheckResult] = []
    for name, check in checks:
        try:
            message = check()
        except (AssertionError, FileNotFoundError, KeyError, ValueError) as exc:
            results.append(CheckResult(name=name, ok=False, message=str(exc)))
        else:
            results.append(CheckResult(name=name, ok=True, message=message))
    return results


def _check_contract_and_template_coverage() -> str:
    payload = _read_json(CONTRACTS / "first_data_day_package.example.json")
    files = payload.get("files")
    assert isinstance(files, list) and files, "first-data-day manifest must define files"
    workflows = {item.get("target_workflow") for item in files if isinstance(item, dict)}
    file_types = {item.get("file_type") for item in files if isinstance(item, dict)}
    assert REQUIRED_TARGET_WORKFLOWS <= workflows, "missing target workflows: " + ", ".join(
        sorted(REQUIRED_TARGET_WORKFLOWS - workflows)
    )
    assert REQUIRED_FILE_TYPES <= file_types, "missing file types: " + ", ".join(
        sorted(REQUIRED_FILE_TYPES - file_types)
    )
    assert payload["safety"]["no_auto_trading"] is True
    assert payload["safety"]["external_model_call"] is False
    assert payload["safety"]["model_promotion"] is False
    assert payload["safety"]["database_write"] is False
    assert payload["safety"]["network_access"] is False
    for index, item in enumerate(files):
        assert isinstance(item, dict), f"files[{index}] must be an object"
        metadata = item.get("metadata")
        assert isinstance(metadata, dict), f"files[{index}].metadata must be an object"
        missing = REQUIRED_METADATA_FIELDS - set(metadata)
        assert not missing, f"files[{index}].metadata missing: {', '.join(sorted(missing))}"
        assert metadata["human_review_required"] is True
        assert metadata["no_auto_trading"] is True
    return (
        "package contract covers CSV, JSON, PDF, DOCX, HTML, weather, and recommendation metadata"
    )


def _check_scaffold_dry_run() -> str:
    with TemporaryDirectory(prefix="eee-zero-data-framework-") as temp_dir:
        package_dir = Path(temp_dir) / "first-data-day"
        scaffold = scaffold_package(output_dir=package_dir)
        assert scaffold["ok"] is True
        assert scaffold["creates_data_files"] is False
        report = build_report(
            package_dir=package_dir,
            manifest_path=package_dir / "first_data_day_package.json",
        )
        assert report["ok"] is False
        assert report["status"] == "missing_required_inputs"
        assert report["workflow_readiness"] == REQUIRED_WORKFLOW_READINESS
        assert report["capability_flags"]["rag_answering_enabled"] is False
        assert report["capability_flags"]["forecast_training_enabled"] is False
        assert report["capability_flags"]["backtest_enabled"] is False
        assert report["capability_flags"]["recommendation_mode"] == "scenario_simulated_only"
        assert report["external_model_call"] is False
        assert report["file_upload"] is False
        assert report["recommendation_execution_change"] is False
        assert report["no_auto_trading"] is True
        data_files = [
            path
            for path in package_dir.rglob("*")
            if path.is_file() and path.name not in {"README.md", "first_data_day_package.json"}
        ]
        assert not data_files, "scaffold must not create data files"
    return "scaffolded empty package returns controlled missing-input readiness"


def _check_empty_state_safety_closure() -> str:
    docs = _normalized_text(ROOT / "docs" / "no_data_trial_framework.md")
    required_docs = [
        "that is a valid operator state while no data exists",
        "rag answering stays disabled",
        "forecast training and backtests stay disabled",
        "scenario_simulated_only",
        "no_auto_trading=true",
        "does not upload files",
        "does not start docker",
        "call external models",
    ]
    _require_all(docs, required_docs, "no-data framework docs")
    test_requirements = {
        ROOT / "tests" / "test_system_readiness.py": [
            "test_system_readiness_empty_database_returns_warning",
            "no_auto_trading",
        ],
        ROOT / "tests" / "test_policy_knowledge.py": [
            "test_empty_corpus_overview_warns_without_fetching",
            "no_auto_trading",
        ],
        ROOT / "tests" / "test_forecasting_research.py": [
            "test_forecast_research_overview_empty_database_returns_warning",
            "no_auto_trading",
        ],
        ROOT / "tests" / "test_recommendations.py": [
            "test_recommendation_feedback_overview_empty_database_returns_warning",
            "no_auto_trading",
        ],
    }
    for path, phrases in test_requirements.items():
        _require_all(_normalized_text(path), phrases, str(path.relative_to(ROOT)))
    return (
        "empty system, RAG corpus, forecast overview, and recommendation safety tests are present"
    )


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _normalized_text(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").lower().split())


def _require_all(text: str, phrases: list[str], label: str) -> None:
    missing = [phrase for phrase in phrases if phrase.lower() not in text]
    assert not missing, f"{label} missing phrases: {', '.join(missing)}"


if __name__ == "__main__":
    raise SystemExit(main())
