from __future__ import annotations

# ruff: noqa: E402, I001

import argparse
import csv
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACTS = ROOT / "docs" / "import_contracts"

sys.path.insert(0, str(ROOT))

from backend.app.schemas.forecasting import (  # noqa: E402
    ForecastResearchBacktestRequest,
    ManualForecastResearchDatasetRequest,
)
from backend.app.schemas.market import ManualMarketArtifactRequest  # noqa: E402
from backend.app.schemas.recommendation import RecommendationRunRequest  # noqa: E402
from backend.app.schemas.scenario import HydroOptimizationRunRequest  # noqa: E402
from backend.app.schemas.weather import OpenMeteoForecastIngestRequest  # noqa: E402


REQUIRED_FILES = {
    "README.md",
    "first_data_day_package.example.json",
    "policy_document_upload.example.json",
    "market_artifact_manual_submission.example.json",
    "weather_open_meteo_reference_request.example.json",
    "forecast_research_curve.example.csv",
    "forecast_research_dataset.example.json",
    "forecast_backtest_request.example.json",
    "hydro_optimization_request.example.json",
    "recommendation_request.example.json",
}


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    message: str


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate no-data trial import contract examples without network or DB access."
    )
    parser.add_argument(
        "--contracts-dir",
        type=Path,
        default=DEFAULT_CONTRACTS,
        help="Directory containing import contract examples.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON results.",
    )
    args = parser.parse_args()

    contracts_dir = args.contracts_dir.resolve()
    results = validate_contracts(contracts_dir)
    if args.json:
        print(
            json.dumps(
                {
                    "contracts_dir": str(contracts_dir),
                    "ok": all(result.ok for result in results),
                    "checks": [result.__dict__ for result in results],
                    "no_auto_trading": True,
                    "network_access": False,
                    "database_access": False,
                },
                ensure_ascii=True,
                indent=2,
            )
        )
    else:
        for result in results:
            status = "ok" if result.ok else "fail"
            print(f"[{status}] {result.name}: {result.message}")

    return 0 if all(result.ok for result in results) else 1


def validate_contracts(contracts_dir: Path) -> list[CheckResult]:
    checks = [
        ("required files", lambda: _check_required_files(contracts_dir)),
        ("schema examples", lambda: _check_schema_examples(contracts_dir)),
        ("policy upload defaults", lambda: _check_policy_upload_defaults(contracts_dir)),
        ("forecast csv curve", lambda: _check_forecast_csv(contracts_dir)),
        ("forecast json matches csv", lambda: _check_forecast_json_matches_csv(contracts_dir)),
        ("safety boundaries", lambda: _check_safety_boundaries(contracts_dir)),
    ]
    results: list[CheckResult] = []
    for name, check in checks:
        try:
            message = check()
        except (AssertionError, FileNotFoundError, KeyError, ValueError, ValidationError) as exc:
            results.append(CheckResult(name=name, ok=False, message=str(exc)))
        else:
            results.append(CheckResult(name=name, ok=True, message=message))
    return results


def _check_required_files(contracts_dir: Path) -> str:
    if not contracts_dir.exists():
        raise FileNotFoundError(f"{contracts_dir} does not exist")
    present = {path.name for path in contracts_dir.iterdir()}
    missing = sorted(REQUIRED_FILES - present)
    assert not missing, f"missing required files: {', '.join(missing)}"
    return f"{len(REQUIRED_FILES)} expected files found"


def _check_schema_examples(contracts_dir: Path) -> str:
    ManualMarketArtifactRequest.model_validate(
        _read_json(contracts_dir / "market_artifact_manual_submission.example.json")
    )
    OpenMeteoForecastIngestRequest.model_validate(
        _read_json(contracts_dir / "weather_open_meteo_reference_request.example.json")
    )
    ManualForecastResearchDatasetRequest.model_validate(
        _read_json(contracts_dir / "forecast_research_dataset.example.json")
    )
    ForecastResearchBacktestRequest.model_validate(
        _read_json(contracts_dir / "forecast_backtest_request.example.json")
    )
    HydroOptimizationRunRequest.model_validate(
        _read_json(contracts_dir / "hydro_optimization_request.example.json")
    )
    RecommendationRunRequest.model_validate(
        _read_json(contracts_dir / "recommendation_request.example.json")
    )
    return "JSON examples match existing Pydantic request schemas"


def _check_policy_upload_defaults(contracts_dir: Path) -> str:
    payload = _read_json(contracts_dir / "policy_document_upload.example.json")
    defaults = payload["expected_defaults"]
    assert payload["target_endpoint"] == "POST /v1/policy/documents/upload"
    assert payload["form_fields"]["document_layer"] == "user_uploaded"
    assert defaults["data_mode"] == "user_uploaded"
    assert defaults["external_processing_allowed"] is False
    assert defaults["human_review_status"] == "pending_review"
    assert defaults["no_auto_trading"] is True
    return "policy upload remains local-only by default"


def _check_forecast_csv(contracts_dir: Path) -> str:
    rows = _read_csv(contracts_dir / "forecast_research_curve.example.csv")
    assert len(rows) == 96, f"expected 96 points, found {len(rows)}"
    starts = [_parse_interval(row["interval_start"]) for row in rows]
    assert len(set(starts)) == 96, "interval_start values must be unique"
    assert all(start.utcoffset() is not None for start in starts), (
        "interval_start values must include timezone offsets"
    )
    assert all(
        starts[index + 1] - starts[index] == timedelta(minutes=15)
        for index in range(len(starts) - 1)
    ), "interval_start values must be contiguous 15-minute intervals"
    for row in rows:
        _parse_price(row["price"])
    return "CSV is one complete timezone-aware 96-point curve"


def _check_forecast_json_matches_csv(contracts_dir: Path) -> str:
    dataset = _read_json(contracts_dir / "forecast_research_dataset.example.json")
    rows = _read_csv(contracts_dir / "forecast_research_curve.example.csv")
    assert dataset["usage_scope"] == "research_only"
    assert dataset["data_mode"] == "user_uploaded"
    assert len(dataset["points"]) == 96
    assert [(point["interval_start"], str(point["price"])) for point in dataset["points"]] == [
        (row["interval_start"], row["price"]) for row in rows
    ]
    return "forecast JSON points match the CSV curve"


def _check_safety_boundaries(contracts_dir: Path) -> str:
    text = "\n".join(path.read_text(encoding="utf-8") for path in contracts_dir.iterdir())
    normalized = " ".join(text.lower().split())
    required = [
        "no_auto_trading=true",
        "external model calls",
        "model promotion",
        "trading execution",
        "scenario_simulated",
        "user_uploaded",
        "research_only",
    ]
    for phrase in required:
        assert phrase in normalized, f"missing safety phrase: {phrase}"
    assert '"no_auto_trading": false' not in normalized
    return "MVP safety boundary text is present"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _parse_interval(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"invalid interval_start {value!r}") from exc


def _parse_price(value: str) -> Decimal:
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"invalid price {value!r}") from exc


if __name__ == "__main__":
    raise SystemExit(main())
