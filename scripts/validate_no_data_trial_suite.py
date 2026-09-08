from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class TrialRunner:
    name: str
    script: Path
    expected_flags: dict[str, bool]


TRIAL_RUNNERS = [
    TrialRunner(
        name="import contracts",
        script=ROOT / "scripts" / "validate_import_contracts.py",
        expected_flags={
            "no_auto_trading": True,
            "network_access": False,
            "database_access": False,
        },
    ),
    TrialRunner(
        name="rag local trial",
        script=ROOT / "scripts" / "validate_rag_trial.py",
        expected_flags={
            "host_only": True,
            "external_network_access": False,
            "persistent_database_access": False,
            "external_model_call": False,
            "no_auto_trading": True,
        },
    ),
    TrialRunner(
        name="forecast training trial",
        script=ROOT / "scripts" / "validate_forecast_training_trial.py",
        expected_flags={
            "host_only": True,
            "external_network_access": False,
            "persistent_database_access": False,
            "model_promotion": False,
            "no_auto_trading": True,
        },
    ),
]


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run host-only no-data trial validations without Docker, credentials, or network."
        )
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON results.",
    )
    args = parser.parse_args()

    results = [_run_trial(runner) for runner in TRIAL_RUNNERS]
    ok = all(result["ok"] for result in results)
    payload = {
        "suite": "no_data_host_only",
        "ok": ok,
        "checks": results,
        "host_only": True,
        "docker_required": False,
        "external_network_access": False,
        "persistent_database_access": False,
        "external_model_call": False,
        "model_promotion": False,
        "no_auto_trading": True,
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=True, indent=2))
    else:
        for result in results:
            status = "ok" if result["ok"] else "fail"
            print(f"[{status}] {result['name']}: {result['message']}")
        print(
            "[ok] suite boundaries: host_only=true, external_network_access=false, "
            "persistent_database_access=false, no_auto_trading=true"
            if ok
            else "[fail] suite boundaries: one or more host-only checks failed"
        )

    return 0 if ok else 1


def _run_trial(runner: TrialRunner) -> dict[str, Any]:
    command = [sys.executable, str(runner.script), "--json"]
    completed = subprocess.run(
        command,
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=180,
    )
    if completed.returncode != 0:
        message = _summarize_output(completed.stdout, completed.stderr)
        return {
            "name": runner.name,
            "ok": False,
            "message": message,
            "command": _display_command(command),
        }

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        return {
            "name": runner.name,
            "ok": False,
            "message": f"invalid JSON output: {exc}",
            "command": _display_command(command),
        }

    failed_flags = [
        f"{flag}={payload.get(flag)!r}"
        for flag, expected in runner.expected_flags.items()
        if payload.get(flag) is not expected
    ]
    if payload.get("ok") is not True:
        failed_flags.append(f"ok={payload.get('ok')!r}")

    if failed_flags:
        return {
            "name": runner.name,
            "ok": False,
            "message": "unexpected safety flags: " + ", ".join(failed_flags),
            "command": _display_command(command),
        }

    checks = payload.get("checks", [])
    return {
        "name": runner.name,
        "ok": True,
        "message": f"{len(checks)} checks passed with expected local-only flags",
        "command": _display_command(command),
    }


def _summarize_output(stdout: str, stderr: str) -> str:
    text = "\n".join(part.strip() for part in [stdout, stderr] if part.strip())
    if not text:
        return "command failed without output"
    lines = text.splitlines()
    return lines[-1][:300]


def _display_command(command: list[str]) -> list[str]:
    return ["python" if item == sys.executable else item for item in command]


if __name__ == "__main__":
    raise SystemExit(main())
