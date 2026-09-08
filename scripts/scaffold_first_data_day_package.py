from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_MANIFEST = ROOT / "docs" / "import_contracts" / "first_data_day_package.example.json"
PACKAGE_DIRS = ("forecast", "rag", "market", "weather", "recommendation")
MANIFEST_NAME = "first_data_day_package.json"
README_NAME = "README.md"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a local first-data-day package skeleton without adding data files."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Package directory to create.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite the generated manifest and README if they already exist.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable results.")
    args = parser.parse_args()

    report = scaffold_package(output_dir=args.output_dir, force=args.force)
    if args.json:
        print(json.dumps(report, ensure_ascii=True, indent=2))
    else:
        print(f"[{'ok' if report['ok'] else 'fail'}] scaffold status: {report['status']}")
        for item in report["created_items"]:
            print(f"created: {item}")
        for item in report["existing_items"]:
            print(f"exists: {item}")
        for action in report["next_actions"]:
            print(f"- {action}")
    return 0 if report["ok"] else 1


def scaffold_package(*, output_dir: Path, force: bool = False) -> dict[str, Any]:
    output_dir = output_dir.resolve()
    manifest_path = output_dir / MANIFEST_NAME
    readme_path = output_dir / README_NAME
    existing_blockers = [
        str(path) for path in (manifest_path, readme_path) if path.exists() and not force
    ]
    if existing_blockers:
        return _report(
            output_dir=output_dir,
            ok=False,
            status="refusing_to_overwrite",
            created_items=[],
            existing_items=existing_blockers,
            next_actions=[
                "Review the existing package files.",
                "Run again with --force only when replacing generated scaffold "
                "metadata is intended.",
            ],
        )

    created_items: list[str] = []
    existing_items: list[str] = []
    output_dir.mkdir(parents=True, exist_ok=True)
    for directory_name in PACKAGE_DIRS:
        directory = output_dir / directory_name
        if directory.exists():
            existing_items.append(str(directory))
        else:
            directory.mkdir()
            created_items.append(str(directory))

    manifest_payload = _scaffold_manifest()
    manifest_path.write_text(json.dumps(manifest_payload, ensure_ascii=True, indent=2) + "\n")
    readme_path.write_text(_readme_text(), encoding="utf-8")
    created_items.extend([str(manifest_path), str(readme_path)])

    return _report(
        output_dir=output_dir,
        ok=True,
        status="scaffold_created",
        created_items=created_items,
        existing_items=existing_items,
        next_actions=[
            "Copy future files into the declared subdirectories only after metadata is known.",
            "Edit first_data_day_package.json to replace placeholders with reviewed "
            "source metadata.",
            "Run validate_first_data_day_package.py --package-dir on this directory before import.",
        ],
    )


def _scaffold_manifest() -> dict[str, Any]:
    payload = json.loads(TEMPLATE_MANIFEST.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Template manifest root must be an object.")
    payload["package_name"] = "Local first-data-day package"
    payload["template_mode"] = False
    payload["description"] = (
        "Local package scaffold. It contains no data files until the operator copies "
        "future reviewed inputs into the declared relative paths."
    )
    return payload


def _readme_text() -> str:
    return "\n".join(
        [
            "# First-Data-Day Local Package",
            "",
            "This directory is a local scaffold for future operator-provided files.",
            "It intentionally contains no real data.",
            "",
            "Expected subdirectories:",
            "- `forecast/`: 15-minute research curves and dataset manifests.",
            "- `rag/`: local policy or market documents for cited review.",
            "- `market/`: manually preserved public market artifacts.",
            "- `weather/`: local weather reference request metadata.",
            "- `recommendation/`: human review context, not execution commands.",
            "",
            "Run before any manual import:",
            "",
            "```powershell",
            ".\\scripts\\validate_first_data_day_package.ps1 --package-dir <this-directory> --json",
            "```",
            "",
            "The expected initial result is `missing_required_inputs` until files are provided.",
            "Do not paste credentials, cookies, private trading exports, or live "
            "account data here.",
            "",
        ]
    )


def _report(
    *,
    output_dir: Path,
    ok: bool,
    status: str,
    created_items: list[str],
    existing_items: list[str],
    next_actions: list[str],
) -> dict[str, Any]:
    return {
        "suite": "first_data_day_package_scaffold",
        "ok": ok,
        "status": status,
        "output_dir": str(output_dir),
        "created_items": created_items,
        "existing_items": existing_items,
        "next_actions": next_actions,
        "host_only": True,
        "read_only": False,
        "writes_package_scaffold_only": True,
        "creates_data_files": False,
        "docker_required": False,
        "external_network_access": False,
        "database_write": False,
        "external_model_call": False,
        "model_promotion": False,
        "schema_migration_required": False,
        "no_auto_trading": True,
    }


if __name__ == "__main__":
    raise SystemExit(main())
