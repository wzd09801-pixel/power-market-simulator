from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).parents[1]
MANIFEST_PATH = ROOT / "docs" / "evidence" / "anonymous_market_field_verification.json"
SCHEMA_PATH = ROOT / "docs" / "evidence" / "anonymous_market_field_verification.schema.json"
ALLOWED_CONCLUSIONS = {"blocked", "eligible_for_adapter_design"}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _validate(value: Any, schema: dict[str, Any], *, path: str = "$") -> None:
    if "const" in schema:
        assert value == schema["const"], f"{path} does not match const"
    if "enum" in schema:
        assert value in schema["enum"], f"{path} is outside enum"

    schema_type = schema.get("type")
    if schema_type == "object":
        assert isinstance(value, dict), f"{path} must be an object"
        required = set(schema.get("required", []))
        assert required <= set(value), f"{path} is missing {required - set(value)}"
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            assert set(value) <= set(properties), f"{path} has unexpected properties"
        for key, item in value.items():
            if key in properties:
                _validate(item, properties[key], path=f"{path}.{key}")
    elif schema_type == "array":
        assert isinstance(value, list), f"{path} must be an array"
        assert len(value) >= schema.get("minItems", 0), f"{path} has too few items"
        item_schema = schema.get("items")
        if item_schema is not None:
            for index, item in enumerate(value):
                _validate(item, item_schema, path=f"{path}[{index}]")
    elif schema_type == "string":
        assert isinstance(value, str), f"{path} must be a string"
        assert len(value) >= schema.get("minLength", 0), f"{path} is too short"
        if schema.get("format") == "date-time":
            datetime.fromisoformat(value)
        elif schema.get("format") == "uri":
            parsed = urlparse(value)
            assert parsed.scheme in {"http", "https"} and parsed.hostname, f"{path} is not a URL"
    elif schema_type == "boolean":
        assert isinstance(value, bool), f"{path} must be a boolean"


def test_manifest_matches_bundled_json_schema() -> None:
    _validate(_load_json(MANIFEST_PATH), _load_json(SCHEMA_PATH))


def test_manifest_evidence_ids_are_unique_and_urls_use_official_domains() -> None:
    manifest = _load_json(MANIFEST_PATH)
    evidence_ids = [item["evidence_id"] for item in manifest["evidence"]]
    official_domains = set(manifest["official_domains"])

    assert len(evidence_ids) == len(set(evidence_ids))
    for item in manifest["evidence"]:
        for url in item["evidence_urls"]:
            assert urlparse(url).hostname in official_domains


def test_manifest_keeps_adapter_design_blocked_without_verified_curve() -> None:
    manifest = _load_json(MANIFEST_PATH)

    assert manifest["adapter_gate"]["conclusion"] in ALLOWED_CONCLUSIONS
    assert manifest["adapter_gate"]["conclusion"] == "blocked"
    assert all(item["conclusion"] in ALLOWED_CONCLUSIONS for item in manifest["evidence"])
    assert all(item["conclusion"] == "blocked" for item in manifest["evidence"])
    assert not any(item["confirmed_96_point_curve"] for item in manifest["evidence"])


def test_reports_weekly_report_fields_remain_aggregate_flash_report_values() -> None:
    manifest = _load_json(MANIFEST_PATH)
    sample = next(
        item
        for item in manifest["evidence"]
        if item["evidence_id"] == "reports_weekly_report_sample_20260529"
    )
    fields = {item["field_name"]: item for item in sample["field_findings"]}

    assert sample["granularity"] == "weekly_report_with_daily_average_aggregates"
    assert fields["average_traded_energy"]["unit"] == "100_million_kwh"
    assert fields["weighted_average_price"]["unit"] == "cny_per_mwh"
    assert all(
        item["settlement_status"] == "preliminary_flash_not_final_settlement"
        for item in fields.values()
    )


def test_southern_public_bundle_hints_remain_non_interval_discovery_evidence() -> None:
    manifest = _load_json(MANIFEST_PATH)
    bundle = next(
        item
        for item in manifest["evidence"]
        if item["evidence_id"] == "southern_spot_public_bundle_contract_20260601"
    )
    probe = next(
        item
        for item in manifest["evidence"]
        if item["evidence_id"] == "southern_spot_gateway_probe_20260601"
    )
    fields = {item["field_name"]: item for item in bundle["field_findings"]}

    assert bundle["granularity"] == "monthly_and_year_to_date_ui_aggregates"
    assert fields["otherData.energyPrice"]["unit"] == "fen"
    assert fields["otherData.currentYearTotalEnergy"]["unit"] == "100_million_kwh"
    assert probe["anonymous_access_status"] == "route_not_found"
    assert probe["conclusion"] == "blocked"
    assert bundle["confirmed_96_point_curve"] is False
