from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANUAL = ROOT / "docs" / "first_data_day_operator_manual.md"


def _manual_text() -> str:
    return MANUAL.read_text(encoding="utf-8")


def test_first_data_day_operator_manual_exists_and_covers_three_closures() -> None:
    text = _manual_text()

    assert MANUAL.exists()
    for phrase in [
        "契约和模板",
        "dry-run",
        "无数据是合法状态",
        "空状态",
        "先验收",
        "再人工导入和审查",
    ]:
        assert phrase in text


def test_first_data_day_operator_manual_lists_required_commands() -> None:
    text = _manual_text()

    for command in [
        "validate_framework_readiness.ps1",
        "scaffold_first_data_day_package.ps1",
        "validate_first_data_day_package.ps1",
    ]:
        assert command in text


def test_first_data_day_operator_manual_covers_all_workflows() -> None:
    normalized = _manual_text().lower()

    for phrase in [
        "rag",
        "forecast",
        "backtest",
        "market/weather",
        "recommendation",
        "workflow_readiness",
    ]:
        assert phrase in normalized


def test_first_data_day_operator_manual_preserves_safety_boundaries() -> None:
    text = _manual_text()
    normalized = " ".join(text.lower().split())

    for phrase in [
        "external_processing_allowed=false",
        "scenario_simulated_only",
        "no_auto_trading=true",
        "research_only",
        "human_review_required=true",
        "rag_answering_enabled=false",
        "forecast_training_enabled=false",
        "backtest_enabled=false",
    ]:
        assert phrase in normalized

    forbidden_positive_phrases = [
        "no_auto_trading=false",
        "external_processing_allowed=true",
        "model_promotion=true",
        "registry_status=production",
        "可以自动交易",
        "允许自动下单",
        "自动晋级到 production",
        "实现真实数据源接入",
        "调用真实外部模型",
    ]
    for phrase in forbidden_positive_phrases:
        assert phrase not in normalized


def test_existing_entry_docs_link_to_operator_manual() -> None:
    for path in [
        ROOT / "docs" / "no_data_trial_framework.md",
        ROOT / "docs" / "import_contracts" / "README.md",
        ROOT / "docs" / "v0_1_rc_runbook.md",
    ]:
        assert "docs/first_data_day_operator_manual.md" in path.read_text(encoding="utf-8")
