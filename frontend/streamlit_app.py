from __future__ import annotations

import os
from datetime import date
from typing import Any

import requests
import streamlit as st

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
REVIEW_STATUS_LABELS = {
    "pending_review": "待复核",
    "approved": "已通过",
    "rejected": "已驳回",
    "needs_revision": "退回修改",
}
RISK_LEVEL_LABELS = {
    "medium": "中",
    "medium_high": "中高",
}
STANCE_LABELS = {
    "neutral": "保持中性",
    "preserve_flexibility": "保留调节灵活性",
}


def _get_json(path: str) -> dict[str, Any]:
    response = requests.get(f"{API_BASE_URL}{path}", timeout=8)
    response.raise_for_status()
    return response.json()


def _post_json(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = requests.post(f"{API_BASE_URL}{path}", json=payload, timeout=8)
    response.raise_for_status()
    return response.json()


def _window_rows(recommendation: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "时间窗口": window["time"],
            "建议姿态": STANCE_LABELS.get(window["stance"], window["stance"]),
            "说明": window["reason"],
        }
        for window in recommendation["recommended_windows"]
    ]


def _evidence_rows(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "来源": item["source"],
            "字段": item["field"],
            "数值": item["value"],
            "单位": item.get("unit") or "-",
            "置信度": f"{item['confidence']:.2f}",
            "数据模式": item["data_mode"],
        }
        for item in evidence
    ]


def _review_rows(reviews: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "时间": review["created_at"],
            "复核人": review["actor"],
            "结果": REVIEW_STATUS_LABELS.get(review["review_status"], review["review_status"]),
            "备注": review["note"],
        }
        for review in reviews
    ]


def _render_recommendation(recommendation: dict[str, Any], *, allow_review: bool) -> None:
    st.warning("该建议基于 scenario_simulated 数据，不是真实公司持仓或水库调度数据。")
    st.caption(
        f"草稿编号：{recommendation['recommendation_id']}  |  "
        f"输入快照：{recommendation['input_snapshot_id']}"
    )
    st.subheader(recommendation["market_view"])
    cols = st.columns(4)
    risk_level = recommendation["risk_level"]
    cols[0].metric("风险等级", RISK_LEVEL_LABELS.get(risk_level, risk_level))
    cols[1].metric("置信度", f"{recommendation['confidence']:.2f}")
    cols[2].metric(
        "复核状态",
        REVIEW_STATUS_LABELS.get(recommendation["review_status"], recommendation["review_status"]),
    )
    cols[3].metric("自动交易", "禁用")

    st.markdown("#### 水电行动建议")
    st.write(recommendation["hydro_action"])
    st.markdown("#### 建议窗口")
    st.table(_window_rows(recommendation))

    st.markdown("#### 缺失数据提示")
    for warning in recommendation["missing_data_warnings"]:
        st.warning(warning)

    st.markdown("#### 证据依据")
    st.dataframe(_evidence_rows(recommendation["evidence"]), width="stretch")

    reviews = recommendation.get("reviews", [])
    if reviews:
        st.markdown("#### 复核历史")
        st.dataframe(_review_rows(reviews), width="stretch")

    with st.expander("技术详情"):
        st.json(recommendation)

    if allow_review:
        st.markdown("#### 人工复核")
        with st.form(f"review_{recommendation['recommendation_id']}"):
            review_label = st.selectbox("复核结果", ["通过", "驳回", "退回修改"])
            note = st.text_area("复核备注", placeholder="请填写判断依据或需要补充的数据。")
            submitted = st.form_submit_button("提交复核")
        if submitted:
            if not note.strip():
                st.error("请填写复核备注。")
            else:
                review_status = {
                    "通过": "approved",
                    "驳回": "rejected",
                    "退回修改": "needs_revision",
                }[review_label]
                try:
                    _post_json(
                        f"/v1/recommendations/{recommendation['recommendation_id']}/reviews",
                        {"review_status": review_status, "note": note},
                    )
                    st.session_state["current_recommendation"] = _get_json(
                        f"/v1/recommendations/{recommendation['recommendation_id']}"
                    )
                    st.session_state["review_success"] = "复核结果已保存，并已写入审计记录。"
                    st.rerun()
                except requests.RequestException as exc:
                    st.error(f"复核提交失败：{exc}")


st.set_page_config(page_title="示例甲省电力交易 AI", layout="wide")
st.title("示例甲省电力交易 AI")
st.caption("示例水电站 A场景模拟 | 非真实公司内部数据 | 不执行自动交易")

tab_status, tab_scenario, tab_recommendation, tab_history = st.tabs(
    ["系统状态", "示例水电站 A", "建议与复核", "复核历史"]
)

with tab_status:
    try:
        status = _get_json("/v1/system/status")
        cols = st.columns(4)
        cols[0].metric("API", status["app_version"])
        cols[1].metric("环境", status["environment"])
        cols[2].metric("数据库", "已连接" if status["database_connected"] else "不可用")
        cols[3].metric("自动交易", "禁用" if status["no_auto_trading"] else "启用")
        st.markdown("#### 可用数据模式")
        st.table([{"数据模式": mode} for mode in status["data_modes"]])
    except requests.RequestException as exc:
        st.error(f"API 暂时不可用：{exc}")

with tab_scenario:
    try:
        scenario = _get_json("/v1/scenarios/demo_hydro/default")
        st.warning("该页面展示的是示例水电站 A模拟场景，不是经过核验的公司运行数据。")
        cols = st.columns(4)
        cols[0].metric("装机容量", f"{scenario['installed_capacity_mw']:.0f} MW")
        cols[1].metric("保证出力", f"{scenario['firm_output_mw']:.1f} MW")
        cols[2].metric("当前水位", f"{scenario['current_water_level_m']:.1f} m")
        cols[3].metric("可用电量", f"{scenario['available_energy_mwh']:.0f} MWh")
        st.markdown("#### 场景假设")
        for assumption in scenario["assumptions"]:
            st.write(f"- {assumption}")
        with st.expander("技术详情"):
            st.json(scenario)
    except requests.RequestException as exc:
        st.error(f"模拟场景暂时不可用：{exc}")

with tab_recommendation:
    selected_date = st.date_input("交易日期", value=date.today())
    if st.button("生成建议", type="primary"):
        try:
            generated = _post_json(
                "/v1/recommendations/run",
                {"trade_date": selected_date.isoformat()},
            )
            st.session_state["current_recommendation"] = _get_json(
                f"/v1/recommendations/{generated['recommendation_id']}"
            )
        except requests.RequestException as exc:
            st.error(f"建议生成失败：{exc}")

    if "review_success" in st.session_state:
        st.success(st.session_state.pop("review_success"))

    current_recommendation = st.session_state.get("current_recommendation")
    if current_recommendation:
        _render_recommendation(current_recommendation, allow_review=True)
    else:
        st.info("请选择交易日期并生成一条模拟建议。")

with tab_history:
    try:
        recent = _get_json("/v1/recommendations/recent?limit=20")["items"]
        if not recent:
            st.info("暂无建议草稿。")
        else:
            st.markdown("#### 最近建议草稿")
            st.dataframe(
                [
                    {
                        "草稿编号": item["recommendation_id"],
                        "交易日期": item["trade_date"],
                        "生成时间": item["created_at"],
                        "复核状态": REVIEW_STATUS_LABELS.get(
                            item["review_status"], item["review_status"]
                        ),
                        "风险等级": RISK_LEVEL_LABELS.get(item["risk_level"], item["risk_level"]),
                    }
                    for item in recent
                ],
                width="stretch",
            )
            selected_recommendation_id = st.selectbox(
                "查看草稿详情",
                [item["recommendation_id"] for item in recent],
            )
            selected_recommendation = _get_json(f"/v1/recommendations/{selected_recommendation_id}")
            _render_recommendation(selected_recommendation, allow_review=False)
    except requests.RequestException as exc:
        st.error(f"历史记录暂时不可用：{exc}")
