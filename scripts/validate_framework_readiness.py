from __future__ import annotations

# ruff: noqa: E402, I001

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "docs" / "import_contracts"
SCRIPTS = ROOT / "scripts"

sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT))

from validate_import_contracts import validate_contracts  # noqa: E402
from validate_first_data_day_package import build_report  # noqa: E402


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    message: str


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate framework readiness for first-data-day dry runs using local files only."
        )
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable results.")
    args = parser.parse_args()

    results = run_checks()
    ok = all(result.ok for result in results)
    payload = {
        "suite": "framework_readiness_host_only",
        "ok": ok,
        "checks": [result.__dict__ for result in results],
        "host_only": True,
        "read_only": True,
        "docker_required": False,
        "external_network_access": False,
        "persistent_database_access": False,
        "external_model_call": False,
        "model_promotion": False,
        "schema_migration_required": False,
        "no_auto_trading": True,
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=True, indent=2))
    else:
        for result in results:
            status = "ok" if result.ok else "fail"
            print(f"[{status}] {result.name}: {result.message}")
        print(
            "[ok] framework boundaries: host_only=true, read_only=true, "
            "external_network_access=false, schema_migration_required=false, "
            "no_auto_trading=true"
            if ok
            else "[fail] framework boundaries: one or more readiness checks failed"
        )

    return 0 if ok else 1


def run_checks() -> list[CheckResult]:
    checks = (
        ("import contracts", _check_import_contracts),
        ("first data day package dry-run", _check_first_data_day_package_dry_run),
        ("forecast dataset manifest", _check_forecast_dataset_manifest),
        ("rag document readiness", _check_rag_document_readiness),
        ("market weather readiness", _check_market_weather_readiness),
        ("training backtest prerequisites", _check_training_backtest_prerequisites),
        ("recommendation safety boundaries", _check_recommendation_safety_boundaries),
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


def _check_import_contracts() -> str:
    results = validate_contracts(CONTRACTS)
    failed = [f"{result.name}: {result.message}" for result in results if not result.ok]
    assert not failed, "; ".join(failed)
    return f"{len(results)} import contract checks passed"


def _check_first_data_day_package_dry_run() -> str:
    manifest = CONTRACTS / "first_data_day_package.example.json"
    report = build_report(package_dir=CONTRACTS, manifest_path=manifest)
    failed = [
        f"{result['name']}: {result['message']}" for result in report["checks"] if not result["ok"]
    ]
    assert report["ok"], "; ".join(failed) or report["status"]
    assert report["status"] == "ready_for_manual_review"
    assert report["host_only"] is True
    assert report["read_only"] is True
    assert report["docker_required"] is False
    assert report["network_access"] is False
    assert report["external_network_access"] is False
    assert report["database_access"] is False
    assert report["persistent_database_access"] is False
    assert report["database_write"] is False
    assert report["external_model_call"] is False
    assert report["model_promotion"] is False
    assert report["schema_migration_required"] is False
    assert report["file_upload"] is False
    assert report["recommendation_execution_change"] is False
    assert report["no_auto_trading"] is True
    assert report["workflow_readiness"] == {
        "rag": "ready_for_manual_review",
        "forecast": "ready_for_manual_review",
        "backtest": "ready_for_manual_review",
        "market_weather": "ready_for_manual_review",
        "recommendation": "ready_for_manual_review",
    }
    flags = report["capability_flags"]
    assert flags["rag_answering_enabled"] is False
    assert flags["forecast_training_enabled"] is False
    assert flags["backtest_enabled"] is False
    assert flags["recommendation_mode"] == "scenario_simulated_only"
    scaffold_py = SCRIPTS / "scaffold_first_data_day_package.py"
    scaffold_ps1 = SCRIPTS / "scaffold_first_data_day_package.ps1"
    assert scaffold_py.exists()
    assert scaffold_ps1.exists()
    scaffold_text = "\n".join(
        [
            scaffold_py.read_text(encoding="utf-8"),
            scaffold_ps1.read_text(encoding="utf-8"),
        ]
    )
    _require_all(
        " ".join(scaffold_text.lower().split()),
        [
            "first_data_day_package_scaffold",
            "creates_data_files",
            "external_network_access",
            "database_write",
            "no_auto_trading",
        ],
        "first-data-day scaffold scripts",
    )
    return "package manifest template and dry-run boundaries are valid"


def _check_forecast_dataset_manifest() -> str:
    dataset = _read_json(CONTRACTS / "forecast_research_dataset.example.json")
    backtest = _read_json(CONTRACTS / "forecast_backtest_request.example.json")
    schema = _normalized_text(ROOT / "backend" / "app" / "schemas" / "forecasting.py")
    docs = _normalized_text(ROOT / "docs" / "interval_forecasting_research_foundation.md")

    _require_keys(
        dataset,
        {
            "name",
            "source_name",
            "source_url",
            "region_code",
            "market_scope",
            "market_stage",
            "price_scope",
            "interval_minutes",
            "timezone",
            "currency",
            "price_unit",
            "data_mode",
            "usage_scope",
            "points",
        },
        "forecast_research_dataset.example.json",
    )
    assert dataset["interval_minutes"] == 15
    assert dataset["usage_scope"] == "research_only"
    assert dataset["data_mode"] in {
        "public_observed",
        "public_derived",
        "scenario_simulated",
        "user_uploaded",
    }
    assert len(dataset["points"]) == 96
    assert backtest["model_key"] in {"seasonal_naive", "calendar_mean"}
    _require_all(
        schema,
        [
            "class manualforecastresearchdatasetrequest",
            "class forecastresearchbacktestrequest",
            "literal[15]",
            'usage_scope: literal["research_only"]',
            "source_url: httpurl",
            "timezone:",
            "price_unit:",
            "data_mode:",
        ],
        "forecasting schema",
    )
    _require_all(
        docs,
        [
            "interval_minutes=15",
            "usage_scope=research_only",
            "exactly 96 unique points",
            "manual import endpoint never fetches",
            "url is evidence metadata only",
            "review-package",
        ],
        "forecasting foundation docs",
    )
    return "forecast dataset templates, schema, and docs preserve 96-point research scope"


def _check_rag_document_readiness() -> str:
    policy_upload = _read_json(CONTRACTS / "policy_document_upload.example.json")
    knowledge_schema = _normalized_text(ROOT / "backend" / "app" / "schemas" / "knowledge.py")
    intelligence_schema = _normalized_text(ROOT / "backend" / "app" / "schemas" / "intelligence.py")
    docs = " ".join(
        [
            _normalized_text(ROOT / "docs" / "policy_knowledge_foundation.md"),
            _normalized_text(ROOT / "README.md"),
            _normalized_text(ROOT / "docs" / "no_data_trial_framework.md"),
        ]
    )

    defaults = policy_upload["expected_defaults"]
    assert policy_upload["target_endpoint"] == "POST /v1/policy/documents/upload"
    assert policy_upload["form_fields"]["document_layer"] == "user_uploaded"
    assert defaults["external_processing_allowed"] is False
    assert defaults["human_review_status"] == "pending_review"
    assert defaults["no_auto_trading"] is True
    _require_all(
        knowledge_schema,
        [
            "externalprocessingauthorizationrequest",
            "knowledgedocumentreviewpackageresponse",
            "external_processing_allowed",
            "external_processing_allowed_default",
            "human_review_status",
            "no_auto_trading",
        ],
        "knowledge schema",
    )
    _require_all(
        intelligence_schema,
        [
            "citationresponse",
            "intelligencequestionresponse",
            "citations:",
            "human_review_required",
            "llm_used",
            "no_auto_trading",
        ],
        "intelligence schema",
    )
    _require_all(
        docs,
        [
            "external_processing_allowed=false",
            "review package",
            "cited",
            "human review",
            "external model processing requires an explicit per-document operator authorization",
        ],
        "rag readiness docs",
    )
    return "RAG upload, citation, review, and external-processing boundaries are documented"


def _check_market_weather_readiness() -> str:
    market = _read_json(CONTRACTS / "market_artifact_manual_submission.example.json")
    weather = _read_json(CONTRACTS / "weather_open_meteo_reference_request.example.json")
    market_schema = _normalized_text(ROOT / "backend" / "app" / "schemas" / "market.py")
    weather_schema = _normalized_text(ROOT / "backend" / "app" / "schemas" / "weather.py")
    docs = " ".join(
        [
            _normalized_text(ROOT / "docs" / "public_market_data_foundation.md"),
            _normalized_text(ROOT / "docs" / "open_meteo_data_foundation.md"),
            _normalized_text(ROOT / "docs" / "no_data_trial_framework.md"),
        ]
    )

    _require_keys(market, {"endpoint_id", "source_url", "title", "media_type"}, "market artifact")
    assert "inline_text" in market or "inline_json" in market
    _require_keys(
        weather,
        {"location_id", "location_name", "latitude", "longitude", "timezone", "hourly_variables"},
        "weather reference request",
    )
    assert weather["timezone"] == "Asia/Shanghai"
    assert weather["hourly_variables"]
    _require_all(
        market_schema,
        [
            "class manualmarketartifactrequest",
            "class marketartifactreviewpackageresponse",
            "source_url: httpurl",
            "human_review_status",
            "no_auto_trading",
            "fetch_performed",
            "network_probe_performed",
        ],
        "market schema",
    )
    _require_all(
        weather_schema,
        [
            "class openmeteoforecastingestrequest",
            "class weatherfeaturereviewpackageresponse",
            "human_review_status",
            "quality_status",
            "no_auto_trading",
            "recommendation_chain_requires_approved_snapshot",
        ],
        "weather schema",
    )
    _require_all(
        docs,
        [
            "never fetches the submitted url",
            "manual preservation",
            "review-package",
            "do not automatically change recommendation generation",
            "approved snapshot may be explicitly attached",
        ],
        "market and weather docs",
    )
    return "manual market artifacts and weather references remain review-gated"


def _check_training_backtest_prerequisites() -> str:
    backtest = _read_json(CONTRACTS / "forecast_backtest_request.example.json")
    baselines = _normalized_text(ROOT / "backend" / "app" / "forecasting" / "baselines.py")
    service = _normalized_text(ROOT / "backend" / "app" / "services" / "forecasting.py")
    docs = _normalized_text(ROOT / "docs" / "interval_forecasting_research_foundation.md")

    assert backtest["model_key"] == "seasonal_naive"
    assert backtest["evaluation_days"] >= 1
    assert backtest["lag_days"] >= 1
    assert backtest["lookback_days"] >= 2
    _require_all(
        baselines,
        [
            "seasonal_naive",
            "calendar_mean",
            "evaluation_days",
            "lag_days",
            "lookback_days",
            "at least",
            "eligible evaluation days are required",
        ],
        "baseline implementation",
    )
    _require_all(
        service,
        [
            'registry_status="candidate"',
            "usage_scope=research_only",
            "candidate_model_run_count",
            "recommendation_chain_isolated=true",
            "fetch_performed=false",
        ],
        "forecasting service",
    )
    _require_all(
        docs,
        [
            "seasonal_naive",
            "calendar_mean",
            "no model is automatically promoted",
            "registry_status=candidate",
            "usage_scope=research_only",
            "training, promote models, or execute trades",
        ],
        "forecast training docs",
    )
    return "baseline backtests require accepted research data and remain candidate-only"


def _check_recommendation_safety_boundaries() -> str:
    request = _read_json(CONTRACTS / "recommendation_request.example.json")
    schema = _normalized_text(ROOT / "backend" / "app" / "schemas" / "recommendation.py")
    service = _normalized_text(ROOT / "backend" / "app" / "services" / "recommendations.py")
    system = _normalized_text(ROOT / "backend" / "app" / "services" / "system.py")
    docs = " ".join(
        [
            _normalized_text(ROOT / "docs" / "no_data_trial_framework.md"),
            _normalized_text(ROOT / "docs" / "v0_1_rc_runbook.md"),
        ]
    )

    _require_keys(request, {"trade_date", "asset_id", "scenario_id"}, "recommendation request")
    _require_all(
        schema,
        [
            "class recommendationrunrequest",
            "class recommendationauditresponse",
            "evidence: list[evidence]",
            "human_check_required",
            "no_auto_trading",
            "research_only_evidence_count",
            "bench_evidence_count",
            "policy_watch_evidence_count",
        ],
        "recommendation schema",
    )
    _require_all(
        service,
        [
            "human_check_required=true",
            "no_auto_trading=true",
            "recommendation_chain_isolation",
            "research_only",
            "bench",
            "policy_watch",
            "resolve critical safety or evidence issues before operator approval",
        ],
        "recommendation service",
    )
    _require_all(
        system,
        [
            "recommendation_forbidden_evidence_markers",
            "research_only",
            "policy_watch",
            "bench",
            "no_auto_trading=true",
        ],
        "system readiness service",
    )
    _require_all(
        docs,
        [
            "no_auto_trading=true",
            "human-reviewed",
            "forecast research datasets and model runs remain `research_only`",
            "bench",
            "policy-watch",
        ],
        "recommendation safety docs",
    )
    return "recommendation boundaries keep research artifacts out of trading advice"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _normalized_text(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").lower().split())


def _require_keys(payload: dict[str, Any], keys: set[str], label: str) -> None:
    missing = sorted(keys - set(payload))
    assert not missing, f"{label} missing keys: {', '.join(missing)}"


def _require_all(text: str, phrases: list[str], label: str) -> None:
    missing = [phrase for phrase in phrases if phrase.lower() not in text]
    assert not missing, f"{label} missing phrases: {', '.join(missing)}"


if __name__ == "__main__":
    raise SystemExit(main())
