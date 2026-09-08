from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from json import JSONDecodeError
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST_NAME = "first_data_day_package.json"

DATA_MODES = {"public_observed", "public_derived", "scenario_simulated", "user_uploaded"}
FILE_TYPES = {"csv", "json", "pdf", "docx", "html", "txt", "md"}
EXPECTED_SUFFIXES = {
    "csv": {".csv"},
    "json": {".json"},
    "pdf": {".pdf"},
    "docx": {".docx"},
    "html": {".html", ".htm"},
    "txt": {".txt"},
    "md": {".md", ".markdown"},
}
DEFAULT_DISABLED_CAPABILITIES = [
    "rag_answering",
    "forecast_training",
    "backtest",
    "external_model_call",
    "production_model_promotion",
]
DEFAULT_SIMULATED_ONLY_CAPABILITIES = [
    "recommendation_generation",
    "hydro_optimization_preview",
]
DEFAULT_CAPABILITY_FLAGS = {
    "rag_answering_enabled": False,
    "forecast_training_enabled": False,
    "backtest_enabled": False,
    "recommendation_mode": "scenario_simulated_only",
    "external_model_call": False,
    "no_auto_trading": True,
}
WORKFLOW_TARGETS = {
    "rag": {"rag_document_upload"},
    "forecast": {"forecast_research_curve", "forecast_dataset_manifest"},
    "backtest": {"forecast_dataset_manifest"},
    "market_weather": {"market_artifact_manual_preservation", "weather_reference_request"},
    "recommendation": {"recommendation_review_context"},
}


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    message: str


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Dry-run validate a local first-data-day package without importing data."
    )
    parser.add_argument(
        "--package-dir",
        type=Path,
        default=None,
        help="Local directory that will eventually contain first-data-day files.",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="Manifest JSON path. Defaults to first_data_day_package.json in package-dir.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable results.")
    args = parser.parse_args()

    package_dir, manifest_path = _resolve_inputs(args.package_dir, args.manifest)
    report = build_report(package_dir=package_dir, manifest_path=manifest_path)

    if args.json:
        print(json.dumps(report, ensure_ascii=True, indent=2))
    else:
        for result in report["checks"]:
            status = "ok" if result["ok"] else "fail"
            print(f"[{status}] {result['name']}: {result['message']}")
        print(f"[{'ok' if report['ok'] else 'fail'}] package status: {report['status']}")
        if report["missing_items"]:
            print("Missing inputs:")
            for item in report["missing_items"]:
                print(f"- {item}")
        print("Next actions:")
        for action in report["next_actions"]:
            print(f"- {action}")

    return 0 if report["ok"] else 1


def build_report(*, package_dir: Path, manifest_path: Path) -> dict[str, Any]:
    package_dir = package_dir.resolve()
    manifest_path = manifest_path.resolve()
    if not package_dir.exists() or not manifest_path.exists():
        missing_items = _missing_required_inputs(package_dir, manifest_path)
        return _base_report(
            package_dir=package_dir,
            manifest_path=manifest_path,
            ok=False,
            status="missing_required_inputs",
            checks=[
                CheckResult(
                    name="required inputs",
                    ok=False,
                    message="First-data-day package directory or manifest is missing.",
                )
            ],
            missing_items=missing_items,
            next_actions=_missing_next_actions(missing_items),
            workflow_readiness=_workflow_readiness_without_manifest(missing_items),
        )
    if manifest_path.stat().st_size == 0:
        return _base_report(
            package_dir=package_dir,
            manifest_path=manifest_path,
            ok=False,
            status="missing_required_inputs",
            checks=[
                CheckResult(
                    name="manifest content",
                    ok=False,
                    message="Manifest file is empty.",
                )
            ],
            missing_items=[_relative_display(package_dir, manifest_path)],
            next_actions=[
                "Populate the package manifest from "
                "docs/import_contracts/first_data_day_package.example.json.",
                "Run this dry-run again before any manual import.",
            ],
            workflow_readiness=_workflow_readiness_without_manifest(
                [_relative_display(package_dir, manifest_path)]
            ),
        )

    try:
        payload = _read_json(manifest_path)
    except (JSONDecodeError, OSError, ValueError) as exc:
        return _base_report(
            package_dir=package_dir,
            manifest_path=manifest_path,
            ok=False,
            status="invalid_manifest",
            checks=[
                CheckResult(
                    name="manifest JSON",
                    ok=False,
                    message=f"Manifest JSON could not be parsed: {exc}",
                )
            ],
            missing_items=[],
            next_actions=[
                "Fix manifest JSON syntax.",
                "Run this dry-run again before any manual import.",
            ],
            workflow_readiness=_workflow_readiness_without_manifest([]),
        )

    return validate_package_manifest(
        payload=payload,
        package_dir=package_dir,
        manifest_path=manifest_path,
    )


def validate_package_manifest(
    *, payload: dict[str, Any], package_dir: Path, manifest_path: Path
) -> dict[str, Any]:
    checks: list[CheckResult] = []
    missing_items: list[str] = []
    template_mode = bool(payload.get("template_mode") is True)

    checks.append(_check_manifest_envelope(payload))
    checks.append(_check_safety_defaults(payload))
    checks.extend(_check_file_entries(payload, package_dir, template_mode, missing_items))

    ok = all(check.ok for check in checks) and not missing_items
    status = "ready_for_manual_review" if ok else "invalid_manifest"
    if missing_items:
        status = "missing_required_inputs"
    next_actions = (
        [
            "Copy real files into the package directory only after their source, "
            "permission, timestamp, unit, and data mode are known.",
            "Run the dry-run again, then use existing manual import and review APIs.",
        ]
        if ok
        else _package_missing_next_actions(missing_items)
    )
    if not ok and not missing_items:
        next_actions = [
            "Fix manifest field-level validation errors.",
            "Run this dry-run again before any manual import.",
        ]
    return _base_report(
        package_dir=package_dir,
        manifest_path=manifest_path,
        ok=ok,
        status=status,
        checks=checks,
        missing_items=missing_items,
        next_actions=next_actions,
        workflow_readiness=_workflow_readiness(payload, checks, missing_items),
    )


def _resolve_inputs(package_dir: Path | None, manifest: Path | None) -> tuple[Path, Path]:
    if package_dir is None and manifest is not None:
        package_dir = manifest.parent
    resolved_package_dir = (package_dir or Path.cwd()).resolve()
    resolved_manifest = (
        manifest.resolve() if manifest is not None else resolved_package_dir / DEFAULT_MANIFEST_NAME
    )
    return resolved_package_dir, resolved_manifest


def _base_report(
    *,
    package_dir: Path,
    manifest_path: Path,
    ok: bool,
    status: str,
    checks: list[CheckResult],
    missing_items: list[str],
    next_actions: list[str],
    workflow_readiness: dict[str, str],
) -> dict[str, Any]:
    return {
        "suite": "first_data_day_package_dry_run",
        "ok": ok,
        "status": status,
        "package_dir": str(package_dir),
        "manifest": str(manifest_path),
        "checks": [check.__dict__ for check in checks],
        "missing_items": missing_items,
        "disabled_capabilities": DEFAULT_DISABLED_CAPABILITIES,
        "simulated_only_capabilities": DEFAULT_SIMULATED_ONLY_CAPABILITIES,
        "workflow_readiness": workflow_readiness,
        "next_actions": next_actions,
        "capability_flags": DEFAULT_CAPABILITY_FLAGS,
        "host_only": True,
        "read_only": True,
        "docker_required": False,
        "database_access": False,
        "database_write": False,
        "network_access": False,
        "external_network_access": False,
        "persistent_database_access": False,
        "external_model_call": False,
        "model_promotion": False,
        "schema_migration_required": False,
        "file_upload": False,
        "recommendation_execution_change": False,
        "no_auto_trading": True,
    }


def _check_manifest_envelope(payload: dict[str, Any]) -> CheckResult:
    errors: list[str] = []
    _expect(
        payload.get("package_version") == "first_data_day_package_v1",
        errors,
        "package_version",
    )
    _expect(isinstance(payload.get("package_name"), str), errors, "package_name")
    _expect(isinstance(payload.get("template_mode"), bool), errors, "template_mode")
    files = payload.get("files")
    _expect(isinstance(files, list) and len(files) > 0, errors, "files")
    return _result("manifest envelope", errors, "manifest envelope is complete")


def _check_safety_defaults(payload: dict[str, Any]) -> CheckResult:
    errors: list[str] = []
    safety = payload.get("safety")
    capability_defaults = payload.get("capability_defaults")
    recommendation = payload.get("recommendation_boundaries")
    if not isinstance(safety, dict):
        errors.append("safety: required object")
    else:
        _expect(safety.get("no_auto_trading") is True, errors, "safety.no_auto_trading")
        _expect(safety.get("external_model_call") is False, errors, "safety.external_model_call")
        _expect(safety.get("model_promotion") is False, errors, "safety.model_promotion")
        _expect(safety.get("database_write") is False, errors, "safety.database_write")
        _expect(safety.get("network_access") is False, errors, "safety.network_access")
    if not isinstance(capability_defaults, dict):
        errors.append("capability_defaults: required object")
    else:
        for field, expected in DEFAULT_CAPABILITY_FLAGS.items():
            _expect(
                capability_defaults.get(field) == expected,
                errors,
                f"capability_defaults.{field}",
            )
    if not isinstance(recommendation, dict):
        errors.append("recommendation_boundaries: required object")
    else:
        _expect(
            recommendation.get("data_mode_until_reviewed_evidence") == "scenario_simulated",
            errors,
            "recommendation_boundaries.data_mode_until_reviewed_evidence",
        )
        _expect(
            recommendation.get("human_review_required") is True,
            errors,
            "recommendation_boundaries.human_review_required",
        )
        _expect(
            recommendation.get("research_only_evidence_allowed") is False,
            errors,
            "recommendation_boundaries.research_only_evidence_allowed",
        )
        _expect(
            recommendation.get("no_auto_trading") is True,
            errors,
            "recommendation_boundaries.no_auto_trading",
        )
    return _result("safety defaults", errors, "safe disabled and simulated-only defaults are set")


def _check_file_entries(
    payload: dict[str, Any], package_dir: Path, template_mode: bool, missing_items: list[str]
) -> list[CheckResult]:
    files = payload.get("files")
    if not isinstance(files, list):
        return [CheckResult(name="file entries", ok=False, message="files: required list")]

    errors: list[str] = []
    content_errors: list[str] = []
    entry_ids: set[str] = set()
    for index, item in enumerate(files):
        label = _entry_label(item, index)
        if not isinstance(item, dict):
            errors.append(f"files[{index}]: expected object")
            continue
        entry_id = item.get("entry_id")
        if not isinstance(entry_id, str) or not entry_id.strip():
            errors.append(f"{label}.entry_id: required string")
        elif entry_id in entry_ids:
            errors.append(f"{label}.entry_id: duplicate value")
        else:
            entry_ids.add(entry_id)
        file_type = item.get("file_type")
        target = item.get("target_workflow")
        metadata = item.get("metadata")
        relative_path = item.get("relative_path")
        if file_type not in FILE_TYPES:
            errors.append(f"{label}.file_type: unsupported file type")
        if not isinstance(target, str) or not target.strip():
            errors.append(f"{label}.target_workflow: required string")
        if not isinstance(metadata, dict):
            errors.append(f"{label}.metadata: required object")
            metadata = {}
        if not isinstance(relative_path, str) or not relative_path.strip():
            errors.append(f"{label}.relative_path: required string")
            continue
        local_path, path_error = _safe_local_path(package_dir, relative_path)
        if path_error is not None:
            errors.append(f"{label}.relative_path: {path_error}")
            continue
        if file_type in FILE_TYPES:
            suffixes = EXPECTED_SUFFIXES[str(file_type)]
            if local_path.suffix.lower() not in suffixes:
                errors.append(f"{label}.relative_path: suffix does not match file_type")
        _validate_metadata(label, str(target), str(file_type), metadata, item, errors)
        if not template_mode:
            if not local_path.exists():
                missing_items.append(relative_path)
                continue
            content_errors.extend(
                _validate_existing_file(label, str(file_type), str(target), item, local_path)
            )

    return [
        _result("file metadata", errors, "all file entries have safe metadata"),
        _result(
            "local file dry-run",
            content_errors,
            "local files match declared lightweight shapes",
        ),
    ]


def _validate_metadata(
    label: str,
    target: str,
    file_type: str,
    metadata: dict[str, Any],
    entry: dict[str, Any],
    errors: list[str],
) -> None:
    for key in [
        "data_mode",
        "source_name",
        "source_url",
        "source_timestamp",
        "timezone",
        "unit",
        "permission",
        "visibility_scope",
        "human_review_required",
    ]:
        if key not in metadata:
            errors.append(f"{label}.metadata.{key}: required field")
    if metadata.get("data_mode") not in DATA_MODES:
        errors.append(f"{label}.metadata.data_mode: unsupported data mode")
    _expect(
        metadata.get("human_review_required") is True,
        errors,
        f"{label}.metadata.human_review_required",
    )
    _expect(metadata.get("no_auto_trading") is True, errors, f"{label}.metadata.no_auto_trading")
    if target == "rag_document_upload":
        _expect(
            metadata.get("external_processing_allowed") is False,
            errors,
            f"{label}.metadata.external_processing_allowed",
        )
        _expect(
            metadata.get("cited_evidence_required") is True,
            errors,
            f"{label}.metadata.cited_evidence_required",
        )
        if target == "rag_document_upload":
            _expect(
                isinstance(metadata.get("document_layer"), str),
                errors,
                f"{label}.metadata.document_layer",
            )
    if target in {"forecast_research_curve", "forecast_dataset_manifest"}:
        _expect(
            metadata.get("usage_scope") == "research_only",
            errors,
            f"{label}.metadata.usage_scope",
        )
        _expect(
            metadata.get("interval_minutes") == 15,
            errors,
            f"{label}.metadata.interval_minutes",
        )
        _expect(isinstance(metadata.get("price_unit"), str), errors, f"{label}.metadata.price_unit")
    if target == "forecast_research_curve":
        columns = entry.get("required_columns")
        _expect(isinstance(columns, list), errors, f"{label}.required_columns")
        if isinstance(columns, list):
            for column in ["interval_start", "price"]:
                _expect(column in columns, errors, f"{label}.required_columns.{column}")
    if target == "forecast_dataset_manifest":
        fields = entry.get("required_fields")
        _expect(isinstance(fields, list), errors, f"{label}.required_fields")
        if isinstance(fields, list):
            for field in ["points", "usage_scope", "data_mode", "interval_minutes"]:
                _expect(field in fields, errors, f"{label}.required_fields.{field}")
    if target == "market_artifact_manual_preservation":
        _expect(
            metadata.get("manual_submission_only") is True,
            errors,
            f"{label}.metadata.manual_submission_only",
        )
        _expect(
            metadata.get("fetch_performed") is False,
            errors,
            f"{label}.metadata.fetch_performed",
        )
        _expect(
            metadata.get("network_probe_performed") is False,
            errors,
            f"{label}.metadata.network_probe_performed",
        )
    if target == "weather_reference_request":
        fields = entry.get("required_fields")
        _expect(isinstance(fields, list), errors, f"{label}.required_fields")
        if isinstance(fields, list):
            for field in [
                "location_id",
                "location_name",
                "latitude",
                "longitude",
                "timezone",
                "hourly_variables",
            ]:
                _expect(field in fields, errors, f"{label}.required_fields.{field}")
        _expect(
            metadata.get("manual_submission_only") is True,
            errors,
            f"{label}.metadata.manual_submission_only",
        )
        _expect(
            metadata.get("fetch_performed") is False,
            errors,
            f"{label}.metadata.fetch_performed",
        )
        _expect(
            metadata.get("network_probe_performed") is False,
            errors,
            f"{label}.metadata.network_probe_performed",
        )
        _expect(
            metadata.get("review_package_required") is True,
            errors,
            f"{label}.metadata.review_package_required",
        )
        _expect(
            metadata.get("no_auto_recommendation") is True,
            errors,
            f"{label}.metadata.no_auto_recommendation",
        )
    if target == "recommendation_review_context":
        fields = entry.get("required_fields")
        _expect(isinstance(fields, list), errors, f"{label}.required_fields")
        if isinstance(fields, list):
            for field in [
                "scenario_id",
                "data_mode",
                "human_review_required",
                "no_auto_trading",
                "evidence_ready",
            ]:
                _expect(field in fields, errors, f"{label}.required_fields.{field}")
        _expect(
            metadata.get("recommendation_mode") == "scenario_simulated_only",
            errors,
            f"{label}.metadata.recommendation_mode",
        )
        _expect(
            metadata.get("no_auto_recommendation_execution") is True,
            errors,
            f"{label}.metadata.no_auto_recommendation_execution",
        )
        _expect(
            metadata.get("evidence_ready") is False,
            errors,
            f"{label}.metadata.evidence_ready",
        )


def _validate_existing_file(
    label: str, file_type: str, target: str, entry: dict[str, Any], path: Path
) -> list[str]:
    errors: list[str] = []
    if file_type == "csv" and target == "forecast_research_curve":
        required_columns = entry.get("required_columns")
        if not isinstance(required_columns, list):
            return [f"{label}.required_columns: required for CSV dry-run"]
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            headers = {header.strip() for header in (reader.fieldnames or [])}
        for column in required_columns:
            if isinstance(column, str) and column not in headers:
                errors.append(f"{label}.csv.{column}: missing required column")
    if file_type == "json" and target == "forecast_dataset_manifest":
        try:
            payload = _read_json(path)
        except (JSONDecodeError, OSError) as exc:
            return [f"{label}.json: could not parse forecast manifest: {exc}"]
        if not isinstance(payload.get("points"), list):
            errors.append(f"{label}.json.points: required list")
        if payload.get("usage_scope") != "research_only":
            errors.append(f"{label}.json.usage_scope: must be research_only")
        if payload.get("interval_minutes") != 15:
            errors.append(f"{label}.json.interval_minutes: must be 15")
    if file_type == "json" and target == "weather_reference_request":
        try:
            payload = _read_json(path)
        except (JSONDecodeError, OSError, ValueError) as exc:
            return [f"{label}.json: could not parse weather reference: {exc}"]
        for field in [
            "location_id",
            "location_name",
            "latitude",
            "longitude",
            "timezone",
            "hourly_variables",
        ]:
            if field not in payload:
                errors.append(f"{label}.json.{field}: required field")
        if payload.get("timezone") != "Asia/Shanghai":
            errors.append(f"{label}.json.timezone: must be Asia/Shanghai")
        if not isinstance(payload.get("hourly_variables"), list) or not payload.get(
            "hourly_variables"
        ):
            errors.append(f"{label}.json.hourly_variables: required non-empty list")
    if file_type == "json" and target == "recommendation_review_context":
        try:
            payload = _read_json(path)
        except (JSONDecodeError, OSError, ValueError) as exc:
            return [f"{label}.json: could not parse recommendation review context: {exc}"]
        if payload.get("data_mode") != "scenario_simulated":
            errors.append(f"{label}.json.data_mode: must be scenario_simulated")
        if payload.get("human_review_required") is not True:
            errors.append(f"{label}.json.human_review_required: must be true")
        if payload.get("no_auto_trading") is not True:
            errors.append(f"{label}.json.no_auto_trading: must be true")
        if payload.get("evidence_ready") is not False:
            errors.append(f"{label}.json.evidence_ready: must be false before review")
    return errors


def _safe_local_path(package_dir: Path, relative_path: str) -> tuple[Path, str | None]:
    normalized = relative_path.replace("\\", "/")
    pure = PurePosixPath(normalized)
    if pure.is_absolute() or ":" in normalized:
        return package_dir, "path must be relative"
    if any(part in {"..", ""} for part in pure.parts):
        return package_dir, "path must not contain traversal segments"
    candidate = package_dir.joinpath(*pure.parts).resolve()
    try:
        candidate.relative_to(package_dir.resolve())
    except ValueError:
        return package_dir, "path escapes package directory"
    return candidate, None


def _missing_required_inputs(package_dir: Path, manifest_path: Path) -> list[str]:
    missing: list[str] = []
    if not package_dir.exists():
        missing.append("package_dir")
    if not manifest_path.exists():
        missing.append(_relative_display(package_dir, manifest_path))
    if package_dir.exists() and not any(package_dir.iterdir()):
        missing.extend(
            [
                "forecast/forecast_research_curve.csv",
                "forecast/forecast_research_dataset.json",
                "rag/policy_document.pdf",
                "market/public_artifact.html",
                "weather/open_meteo_reference.json",
                "recommendation/review_context.json",
            ]
        )
    return missing


def _missing_next_actions(missing_items: list[str]) -> list[str]:
    if not missing_items:
        return ["Fix manifest validation errors and run this dry-run again."]
    return [
        "Create a local first-data-day package directory.",
        "Copy docs/import_contracts/first_data_day_package.example.json to "
        "first_data_day_package.json.",
        "Fill metadata before adding files; keep placeholders when data is not available.",
        "Run this dry-run again before any manual import.",
    ]


def _package_missing_next_actions(missing_items: list[str]) -> list[str]:
    if not missing_items:
        return ["Fix manifest validation errors and run this dry-run again."]
    return [
        "Copy the missing future files into the declared package-relative paths only "
        "after source metadata is known.",
        "Keep unavailable files absent instead of inventing placeholder content.",
        "Update first_data_day_package.json metadata for provided files.",
        "Run this dry-run again before any manual import, RAG upload, training, "
        "backtest, or review use.",
    ]


def _entry_label(item: object, index: int) -> str:
    if isinstance(item, dict) and isinstance(item.get("entry_id"), str):
        return f"files[{index}]({item['entry_id']})"
    return f"files[{index}]"


def _relative_display(package_dir: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(package_dir.resolve()))
    except ValueError:
        return str(path)


def _workflow_readiness(
    payload: dict[str, Any], checks: list[CheckResult], missing_items: list[str]
) -> dict[str, str]:
    files = payload.get("files")
    if not isinstance(files, list):
        return _workflow_readiness_without_manifest(missing_items)
    missing = set(missing_items)
    metadata_ok = all(check.ok for check in checks)
    readiness: dict[str, str] = {}
    for workflow, targets in WORKFLOW_TARGETS.items():
        entries = [
            item
            for item in files
            if isinstance(item, dict) and item.get("target_workflow") in targets
        ]
        if not entries:
            readiness[workflow] = "disabled"
            continue
        entry_paths = {
            item.get("relative_path")
            for item in entries
            if isinstance(item.get("relative_path"), str)
        }
        if entry_paths & missing:
            readiness[workflow] = "missing_required_inputs"
        elif metadata_ok:
            readiness[workflow] = "ready_for_manual_review"
        else:
            readiness[workflow] = "disabled"
    return readiness


def _workflow_readiness_without_manifest(missing_items: list[str]) -> dict[str, str]:
    status = "missing_required_inputs" if missing_items else "disabled"
    return {workflow: status for workflow in WORKFLOW_TARGETS}


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("JSON root must be an object")
    return payload


def _expect(condition: bool, errors: list[str], field: str) -> None:
    if not condition:
        errors.append(f"{field}: invalid or missing")


def _result(name: str, errors: list[str], ok_message: str) -> CheckResult:
    if errors:
        return CheckResult(name=name, ok=False, message="; ".join(errors))
    return CheckResult(name=name, ok=True, message=ok_message)


if __name__ == "__main__":
    raise SystemExit(main())
