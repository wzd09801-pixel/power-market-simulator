import { Alert, Button, Card, Checkbox, Col, Empty, Input, List, Row, Select, Space, Statistic, Table, Tag, Typography } from "antd";
import { useCallback, useEffect, useState } from "react";

import { api } from "../api";
import type {
  Evidence,
  HydroOptimizationPricePoint,
  HydroOptimizationRun,
  HydroScenario,
  Recommendation,
  RecommendationAudit,
  RecommendationAuditCheck,
  RecommendationDecision,
  RecommendationDecisionFeedback,
  RecommendationDetail,
  RecommendationEvidenceExport,
  RecommendationFeedbackAnalytics,
  RecommendedWindow,
} from "../types";

const REVIEW_OPTIONS = [
  { label: "通过", value: "approved" },
  { label: "驳回", value: "rejected" },
  { label: "退回修改", value: "needs_revision" },
];

const DECISION_OPTIONS = [
  { label: "采纳", value: "adopted" },
  { label: "部分采纳", value: "partially_adopted" },
  { label: "不采纳", value: "not_adopted" },
  { label: "暂缓", value: "deferred" },
];

const OUTCOME_OPTIONS = [
  { label: "待观察", value: "pending_observation" },
  { label: "有帮助", value: "useful" },
  { label: "中性", value: "neutral" },
  { label: "无帮助", value: "not_useful" },
  { label: "不确定", value: "uncertain" },
];

function localIsoDate() {
  const today = new Date();
  const year = today.getFullYear();
  const month = String(today.getMonth() + 1).padStart(2, "0");
  const day = String(today.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function auditColor(status: string) {
  if (status === "healthy") return "green";
  if (status === "warning") return "gold";
  if (status === "critical") return "red";
  return "default";
}

function normalizeHydroPricePoints(
  points: Array<{ interval_index: number; price: unknown }>,
): { priceSignal?: HydroOptimizationPricePoint[]; error?: string } {
  if (points.length !== 96) {
    return { error: "价格曲线必须包含 96 个 15 分钟价格点。" };
  }
  const normalized = points.map((point) => ({
    interval_index: Number(point.interval_index),
    price: String(point.price),
  }));
  const indexes = normalized.map((point) => point.interval_index);
  const sorted = [...indexes].sort((a, b) => a - b);
  const complete = sorted.every((value, index) => value === index + 1);
  if (!complete) {
    return { error: "价格曲线必须且只能覆盖 interval_index 1-96。" };
  }
  if (normalized.some((point) => !Number.isFinite(Number(point.price)))) {
    return { error: "价格曲线包含无法解析的价格。" };
  }
  return { priceSignal: normalized };
}

function parseHydroPriceSignalText(
  value: string,
): { priceSignal?: HydroOptimizationPricePoint[]; error?: string } {
  const trimmed = value.trim();
  if (!trimmed) return {};
  try {
    const parsed = JSON.parse(trimmed) as unknown;
    if (Array.isArray(parsed)) {
      if (parsed.every((item) => typeof item === "number" || typeof item === "string")) {
        return normalizeHydroPricePoints(parsed.map((price, index) => ({
          interval_index: index + 1,
          price,
        })));
      }
      if (
        parsed.every((item) => (
          typeof item === "object"
          && item !== null
          && "interval_index" in item
          && "price" in item
        ))
      ) {
        return normalizeHydroPricePoints(parsed as Array<{ interval_index: number; price: unknown }>);
      }
    }
  } catch {
    // Fall through to delimited text parsing.
  }

  const lines = trimmed.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  const pairs = lines.map((line) => line.split(/[\s,，;；\t]+/).filter(Boolean));
  if (pairs.length === 96 && pairs.every((parts) => parts.length === 2)) {
    return normalizeHydroPricePoints(pairs.map(([interval, price]) => ({
      interval_index: Number(interval),
      price,
    })));
  }

  const prices = trimmed.split(/[\s,，;；\t]+/).filter(Boolean);
  if (prices.length === 96) {
    return normalizeHydroPricePoints(prices.map((price, index) => ({
      interval_index: index + 1,
      price,
    })));
  }
  return { error: "请粘贴 96 个价格，或 96 行 interval_index,price。" };
}

export function RecommendationWorkspace(props: {
  targetRecommendationId?: string | null;
}) {
  const [scenario, setScenario] = useState<HydroScenario | null>(null);
  const [optimizationRun, setOptimizationRun] = useState<HydroOptimizationRun | null>(null);
  const [recentOptimizations, setRecentOptimizations] = useState<HydroOptimizationRun[]>([]);
  const [recent, setRecent] = useState<Recommendation[]>([]);
  const [recommendation, setRecommendation] = useState<RecommendationDetail | null>(null);
  const [audit, setAudit] = useState<RecommendationAudit | null>(null);
  const [evidenceExport, setEvidenceExport] = useState<RecommendationEvidenceExport | null>(null);
  const [decisions, setDecisions] = useState<RecommendationDecision[]>([]);
  const [feedbackAnalytics, setFeedbackAnalytics] = useState<RecommendationFeedbackAnalytics | null>(null);
  const [tradeDate, setTradeDate] = useState(localIsoDate);
  const [optimizationTradeDate, setOptimizationTradeDate] = useState(localIsoDate);
  const [energyBudgetMwh, setEnergyBudgetMwh] = useState("");
  const [minOutputMw, setMinOutputMw] = useState("");
  const [maxOutputMw, setMaxOutputMw] = useState("");
  const [priceSignalText, setPriceSignalText] = useState("");
  const [priceSignalError, setPriceSignalError] = useState<string | null>(null);
  const [reviewStatus, setReviewStatus] = useState("approved");
  const [reviewNote, setReviewNote] = useState("");
  const [decisionStatus, setDecisionStatus] = useState<RecommendationDecision["decision_status"]>("deferred");
  const [selectedWindows, setSelectedWindows] = useState<string[]>([]);
  const [decisionNote, setDecisionNote] = useState("");
  const [safetyAcknowledged, setSafetyAcknowledged] = useState(false);
  const [feedbackDrafts, setFeedbackDrafts] = useState<Record<string, {
    outcome_status: RecommendationDecisionFeedback["outcome_status"];
    observed_at: string;
    note: string;
  }>>({});
  const [loading, setLoading] = useState(false);
  const [optimizationLoading, setOptimizationLoading] = useState(false);
  const [decisionLoading, setDecisionLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [auditError, setAuditError] = useState<string | null>(null);
  const [evidenceExportError, setEvidenceExportError] = useState<string | null>(null);
  const [decisionError, setDecisionError] = useState<string | null>(null);
  const [feedbackAnalyticsError, setFeedbackAnalyticsError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const refresh = async () => {
    try {
      const [scenarioItem, recentItems, optimizationItems] = await Promise.all([
        api.scenario(),
        api.recentRecommendations(),
        api.recentHydroOptimizations(),
      ]);
      setScenario(scenarioItem);
      setRecent(recentItems);
      setRecentOptimizations(optimizationItems);
      setError(null);
    } catch {
      setError("场景建议 API 暂不可用，请检查数据库迁移和服务状态。");
    }
  };

  const refreshFeedbackAnalytics = async () => {
    try {
      setFeedbackAnalytics(await api.recommendationFeedbackAnalytics());
      setFeedbackAnalyticsError(null);
    } catch {
      setFeedbackAnalytics(null);
      setFeedbackAnalyticsError("Recommendation feedback analytics API is unavailable.");
    }
  };

  const loadRecommendationWithAudit = useCallback(async (recommendationId: string) => {
    const detail = await api.recommendation(recommendationId);
    setRecommendation(detail);
    try {
      setAudit(await api.recommendationAudit(recommendationId));
      setAuditError(null);
    } catch {
      setAudit(null);
      setAuditError("证据审计暂不可用，请检查本地 API 状态。");
    }
    try {
      setEvidenceExport(await api.recommendationEvidenceExport(recommendationId));
      setEvidenceExportError(null);
    } catch {
      setEvidenceExport(null);
      setEvidenceExportError("证据导出包暂不可用，请检查本地 API 状态。");
    }
    try {
      setDecisions(await api.recommendationDecisions(recommendationId));
      setDecisionError(null);
    } catch {
      setDecisions([]);
      setDecisionError("人工决策日志暂不可用，请检查本地 API 状态。");
    }
  }, []);

  const generate = async () => {
    setLoading(true);
    setSuccess(null);
    try {
      const generated = await api.runRecommendation(tradeDate);
      await loadRecommendationWithAudit(generated.recommendation_id);
      setRecent(await api.recentRecommendations());
      await refreshFeedbackAnalytics();
      setError(null);
    } catch {
      setError("建议生成失败，请检查本地 API 状态。");
    } finally {
      setLoading(false);
    }
  };

  const openRecommendation = useCallback(async (recommendationId: string) => {
    setLoading(true);
    try {
      await loadRecommendationWithAudit(recommendationId);
      setError(null);
    } catch {
      setError("建议草稿加载失败，请检查本地 API 状态。");
    } finally {
      setLoading(false);
    }
  }, [loadRecommendationWithAudit]);

  useEffect(() => {
    void refresh();
    void refreshFeedbackAnalytics();
    if (props.targetRecommendationId) {
      void openRecommendation(props.targetRecommendationId);
    }
  }, [openRecommendation, props.targetRecommendationId]);

  useEffect(() => {
    if (!scenario) return;
    setEnergyBudgetMwh(String(scenario.available_energy_mwh));
    setMinOutputMw(String(scenario.firm_output_mw));
    setMaxOutputMw(String(scenario.installed_capacity_mw));
  }, [scenario]);

  const runHydroOptimizationPreview = async () => {
    setOptimizationLoading(true);
    setSuccess(null);
    setPriceSignalError(null);
    try {
      const parsedPriceSignal = parseHydroPriceSignalText(priceSignalText);
      if (parsedPriceSignal.error) {
        setPriceSignalError(parsedPriceSignal.error);
        setError(parsedPriceSignal.error);
        return;
      }
      const run = await api.runHydroOptimization({
        trade_date: optimizationTradeDate,
        energy_budget_mwh: Number(energyBudgetMwh),
        min_output_mw: Number(minOutputMw),
        max_output_mw: Number(maxOutputMw),
        ...(parsedPriceSignal.priceSignal ? { price_signal: parsedPriceSignal.priceSignal } : {}),
      });
      setOptimizationRun(run);
      setRecentOptimizations(await api.recentHydroOptimizations());
      setSuccess("水电约束预演已保存为本地审计记录。");
      setError(null);
    } catch {
      setError("水电约束预演失败，请检查能量预算、出力边界和本地 API 状态。");
    } finally {
      setOptimizationLoading(false);
    }
  };

  const submitReview = async () => {
    if (!recommendation || !reviewNote.trim()) {
      setError("请填写人工复核备注。");
      return;
    }
    setLoading(true);
    try {
      await api.reviewRecommendation(recommendation.recommendation_id, reviewStatus, reviewNote);
      await loadRecommendationWithAudit(recommendation.recommendation_id);
      setRecent(await api.recentRecommendations());
      setReviewNote("");
      setSuccess("复核结果已保存，并写入审计记录。");
      setError(null);
    } catch {
      setError("复核提交失败，请检查输入和本地 API 状态。");
    } finally {
      setLoading(false);
    }
  };

  const refreshDecisions = async (recommendationId: string) => {
    setDecisions(await api.recommendationDecisions(recommendationId));
    setDecisionError(null);
  };

  const submitDecision = async () => {
    if (!recommendation) return;
    if (!decisionNote.trim()) {
      setDecisionError("请填写人工决策说明。");
      return;
    }
    if (!safetyAcknowledged) {
      setDecisionError("请先确认该记录不是交易指令，且不会触发自动交易。");
      return;
    }
    setDecisionLoading(true);
    try {
      await api.createRecommendationDecision(recommendation.recommendation_id, {
        decision_status: decisionStatus,
        selected_windows: selectedWindows,
        note: decisionNote,
        safety_boundary_acknowledged: safetyAcknowledged,
      });
      await refreshDecisions(recommendation.recommendation_id);
      await refreshFeedbackAnalytics();
      setDecisionNote("");
      setSelectedWindows([]);
      setSafetyAcknowledged(false);
      setSuccess("人工决策日志已保存。");
    } catch {
      setDecisionError("人工决策日志保存失败，请检查审计状态、安全确认或本地 API 状态。");
    } finally {
      setDecisionLoading(false);
    }
  };

  const updateFeedbackDraft = (
    decisionId: string,
    patch: Partial<{
      outcome_status: RecommendationDecisionFeedback["outcome_status"];
      observed_at: string;
      note: string;
    }>,
  ) => {
    setFeedbackDrafts((current) => {
      const existing = current[decisionId];
      const defaultDraft: {
        outcome_status: RecommendationDecisionFeedback["outcome_status"];
        observed_at: string;
        note: string;
      } = {
        outcome_status: "pending_observation",
        observed_at: localIsoDate(),
        note: "",
      };
      const next = existing
        ? { ...existing, ...patch }
        : { ...defaultDraft, ...patch };
      return {
        ...current,
        [decisionId]: next,
      };
    });
  };

  const submitFeedback = async (decisionId: string) => {
    if (!recommendation) return;
    const draft = feedbackDrafts[decisionId] ?? {
      outcome_status: "pending_observation",
      observed_at: localIsoDate(),
      note: "",
    };
    if (!draft.note.trim()) {
      setDecisionError("请填写复盘反馈说明。");
      return;
    }
    setDecisionLoading(true);
    try {
      await api.createRecommendationDecisionFeedback(decisionId, {
        outcome_status: draft.outcome_status,
        observed_at: draft.observed_at || null,
        note: draft.note,
      });
      await refreshDecisions(recommendation.recommendation_id);
      await refreshFeedbackAnalytics();
      setFeedbackDrafts((current) => ({
        ...current,
        [decisionId]: {
          outcome_status: "pending_observation",
          observed_at: localIsoDate(),
          note: "",
        },
      }));
      setSuccess("复盘反馈已保存。");
    } catch {
      setDecisionError("复盘反馈保存失败，请检查本地 API 状态。");
    } finally {
      setDecisionLoading(false);
    }
  };

  return (
    <Space orientation="vertical" size={16} className="full-width" data-testid="recommendation-workspace">
      <Card title="场景建议与人工审核">
        <Alert
          data-testid="recommendation-isolation"
          type="info"
          showIcon
          message="建议模块保持独立"
          description="场景建议通过审计 API 生成并由人工审核。本工作台不会提交交易、登录交易平台或自动采纳研究输出。"
        />
      </Card>

      {error && <Alert type="warning" showIcon message={error} />}
      {success && <Alert type="success" showIcon message={success} />}

      {scenario && (
        <Card title={`${scenario.asset_name} 模拟场景`} extra={<Tag color="orange">{scenario.data_mode}</Tag>}>
          <Alert type="warning" showIcon message={scenario.warning} />
          <Row gutter={[16, 16]} className="card-footer">
            <Col xs={12} lg={6}><Statistic title="装机容量" value={scenario.installed_capacity_mw} suffix="MW" /></Col>
            <Col xs={12} lg={6}><Statistic title="保证出力" value={scenario.firm_output_mw} suffix="MW" /></Col>
            <Col xs={12} lg={6}><Statistic title="当前水位" value={scenario.current_water_level_m} suffix="m" /></Col>
            <Col xs={12} lg={6}><Statistic title="可用电量" value={scenario.available_energy_mwh} suffix="MWh" /></Col>
          </Row>
          <List size="small" header="场景假设" dataSource={scenario.assumptions} renderItem={(assumption) => <List.Item>{assumption}</List.Item>} />
        </Card>
      )}

      <Card title="生成模拟建议">
        <Space wrap>
          <Input data-testid="recommendation-trade-date" aria-label="交易日期" type="date" value={tradeDate} onChange={(event) => setTradeDate(event.target.value)} />
          <Button data-testid="generate-recommendation" type="primary" loading={loading} onClick={() => void generate()}>生成建议</Button>
        </Space>
      </Card>

      <HydroOptimizationPreviewCard
        tradeDate={optimizationTradeDate}
        energyBudgetMwh={energyBudgetMwh}
        minOutputMw={minOutputMw}
        maxOutputMw={maxOutputMw}
        priceSignalText={priceSignalText}
        priceSignalError={priceSignalError}
        optimizationRun={optimizationRun}
        recentOptimizations={recentOptimizations}
        loading={optimizationLoading}
        onTradeDateChange={setOptimizationTradeDate}
        onEnergyBudgetChange={setEnergyBudgetMwh}
        onMinOutputChange={setMinOutputMw}
        onMaxOutputChange={setMaxOutputMw}
        onPriceSignalChange={setPriceSignalText}
        onRun={() => void runHydroOptimizationPreview()}
      />

      <RecommendationFeedbackAnalyticsCard
        analytics={feedbackAnalytics}
        error={feedbackAnalyticsError}
      />

      {recommendation ? (
        <RecommendationCard
          recommendation={recommendation}
          loading={loading}
          reviewStatus={reviewStatus}
          reviewNote={reviewNote}
          audit={audit}
          auditError={auditError}
          evidenceExport={evidenceExport}
          evidenceExportError={evidenceExportError}
          decisions={decisions}
          decisionStatus={decisionStatus}
          selectedWindows={selectedWindows}
          decisionNote={decisionNote}
          safetyAcknowledged={safetyAcknowledged}
          decisionLoading={decisionLoading}
          decisionError={decisionError}
          feedbackDrafts={feedbackDrafts}
          onReviewStatusChange={setReviewStatus}
          onReviewNoteChange={setReviewNote}
          onReview={() => void submitReview()}
          onDecisionStatusChange={setDecisionStatus}
          onSelectedWindowsChange={setSelectedWindows}
          onDecisionNoteChange={setDecisionNote}
          onSafetyAcknowledgedChange={setSafetyAcknowledged}
          onDecision={() => void submitDecision()}
          onFeedbackDraftChange={updateFeedbackDraft}
          onFeedback={(decisionId) => void submitFeedback(decisionId)}
        />
      ) : <Empty description="请选择交易日期并生成一条模拟建议，或打开最近草稿。" />}

      <Card title="最近建议草稿">
        <List
          dataSource={recent}
          locale={{ emptyText: "暂无建议草稿" }}
          renderItem={(item) => (
            <List.Item actions={[<Button key={item.recommendation_id} onClick={() => void openRecommendation(item.recommendation_id)}>查看</Button>]}>
              <List.Item.Meta title={`${item.trade_date} · ${item.risk_level}`} description={`${item.review_status} · ${item.recommendation_id}`} />
            </List.Item>
          )}
        />
      </Card>
    </Space>
  );
}

type RecommendationCardProps = {
  recommendation: RecommendationDetail;
  loading: boolean;
  reviewStatus: string;
  reviewNote: string;
  audit: RecommendationAudit | null;
  auditError: string | null;
  evidenceExport: RecommendationEvidenceExport | null;
  evidenceExportError: string | null;
  decisions: RecommendationDecision[];
  decisionStatus: RecommendationDecision["decision_status"];
  selectedWindows: string[];
  decisionNote: string;
  safetyAcknowledged: boolean;
  decisionLoading: boolean;
  decisionError: string | null;
  feedbackDrafts: Record<string, {
    outcome_status: RecommendationDecisionFeedback["outcome_status"];
    observed_at: string;
    note: string;
  }>;
  onReviewStatusChange: (value: string) => void;
  onReviewNoteChange: (value: string) => void;
  onReview: () => void;
  onDecisionStatusChange: (value: RecommendationDecision["decision_status"]) => void;
  onSelectedWindowsChange: (value: string[]) => void;
  onDecisionNoteChange: (value: string) => void;
  onSafetyAcknowledgedChange: (value: boolean) => void;
  onDecision: () => void;
  onFeedbackDraftChange: (
    decisionId: string,
    patch: Partial<{
      outcome_status: RecommendationDecisionFeedback["outcome_status"];
      observed_at: string;
      note: string;
    }>,
  ) => void;
  onFeedback: (decisionId: string) => void;
};

function HydroOptimizationPreviewCard(props: {
  tradeDate: string;
  energyBudgetMwh: string;
  minOutputMw: string;
  maxOutputMw: string;
  priceSignalText: string;
  priceSignalError: string | null;
  optimizationRun: HydroOptimizationRun | null;
  recentOptimizations: HydroOptimizationRun[];
  loading: boolean;
  onTradeDateChange: (value: string) => void;
  onEnergyBudgetChange: (value: string) => void;
  onMinOutputChange: (value: string) => void;
  onMaxOutputChange: (value: string) => void;
  onPriceSignalChange: (value: string) => void;
  onRun: () => void;
}) {
  const { optimizationRun } = props;
  const comparisonRows = props.recentOptimizations.map((run) => ({
    key: run.optimization_run_id,
    trade_date: run.trade_date,
    energy_budget_mwh: run.energy_budget_mwh,
    output_bounds: `${run.min_output_mw}-${run.max_output_mw} MW`,
    price_signal_used: run.price_signal_used ? "已使用" : "未使用",
    top_intervals: run.top_priority_intervals
      .slice(0, 3)
      .map((interval) => `#${interval.interval_index}`)
      .join(", "),
    warning_count: run.missing_data_warnings.length,
    optimization_run_id: run.optimization_run_id,
  }));
  return (
    <Card
      title="水电约束预演"
      data-testid="hydro-optimization-preview"
      extra={<Tag color="orange">scenario_simulated</Tag>}
    >
      <Alert
        type="warning"
        showIcon
        message="本预演只生成本地研究审计记录，不是调度指令或交易建议。"
      />
      <Space wrap className="card-footer">
        <Input
          data-testid="hydro-optimization-trade-date"
          aria-label="预演交易日期"
          type="date"
          value={props.tradeDate}
          onChange={(event) => props.onTradeDateChange(event.target.value)}
        />
        <Input
          data-testid="hydro-energy-budget"
          aria-label="能量预算 MWh"
          type="number"
          value={props.energyBudgetMwh}
          addonAfter="MWh"
          onChange={(event) => props.onEnergyBudgetChange(event.target.value)}
        />
        <Input
          data-testid="hydro-min-output"
          aria-label="最小出力 MW"
          type="number"
          value={props.minOutputMw}
          addonAfter="MW"
          onChange={(event) => props.onMinOutputChange(event.target.value)}
        />
        <Input
          data-testid="hydro-max-output"
          aria-label="最大出力 MW"
          type="number"
          value={props.maxOutputMw}
          addonAfter="MW"
          onChange={(event) => props.onMaxOutputChange(event.target.value)}
        />
        <Input.TextArea
          data-testid="hydro-price-signal"
          aria-label="96 点价格曲线"
          rows={4}
          value={props.priceSignalText}
          placeholder="可粘贴 96 个价格，或 96 行 interval_index,price；留空则执行约束均衡预演。"
          onChange={(event) => props.onPriceSignalChange(event.target.value)}
        />
        <Button
          data-testid="run-hydro-optimization"
          type="primary"
          loading={props.loading}
          onClick={props.onRun}
        >
          运行预演
        </Button>
      </Space>
      {props.priceSignalError ? (
        <Alert
          className="card-footer"
          type="error"
          showIcon
          message={props.priceSignalError}
        />
      ) : (
        <Typography.Paragraph className="card-footer" type="secondary">
          价格曲线作为本地上传预演输入处理，后端 evidence 标记为 user_uploaded；不会作为已核验示例甲省现货曲线。
        </Typography.Paragraph>
      )}
      {optimizationRun ? (
        <Space orientation="vertical" className="full-width card-footer">
          <Row gutter={[16, 16]}>
            <Col xs={12} lg={6}><Statistic title="能量预算" value={optimizationRun.energy_budget_mwh} suffix="MWh" /></Col>
            <Col xs={12} lg={6}><Statistic title="最小出力" value={optimizationRun.min_output_mw} suffix="MW" /></Col>
            <Col xs={12} lg={6}><Statistic title="最大出力" value={optimizationRun.max_output_mw} suffix="MW" /></Col>
            <Col xs={12} lg={6}><Statistic title="价格信号" value={optimizationRun.price_signal_used ? "已使用" : "未使用"} /></Col>
          </Row>
          <Space wrap>
            <Tag color="blue">{optimizationRun.algorithm_key}</Tag>
            <Tag color="orange">{optimizationRun.data_mode}</Tag>
            <Tag color={optimizationRun.price_signal_used ? "blue" : "default"}>
              price_signal={optimizationRun.price_signal_used ? "user_uploaded" : "missing"}
            </Tag>
            <Tag color={optimizationRun.no_auto_trading ? "green" : "red"}>
              no_auto_trading={String(optimizationRun.no_auto_trading)}
            </Tag>
            <Tag color={optimizationRun.human_review_required ? "green" : "red"}>
              human_review_required={String(optimizationRun.human_review_required)}
            </Tag>
          </Space>
          <Table
            size="small"
            pagination={false}
            rowKey="interval_index"
            data-testid="hydro-top-intervals"
            dataSource={optimizationRun.top_priority_intervals}
            columns={[
              { title: "序号", dataIndex: "interval_index" },
              { title: "开始时间", dataIndex: "interval_start" },
              { title: "目标出力 MW", dataIndex: "target_output_mw" },
              { title: "电量 MWh", dataIndex: "energy_mwh" },
              { title: "价格", dataIndex: "price_signal", render: (value: string | null) => value ?? "-" },
              { title: "优先级", dataIndex: "priority_rank", render: (value: number | null) => value ?? "-" },
              { title: "约束", dataIndex: "binding_constraints", render: (value: string[]) => value.join(", ") },
            ]}
          />
          <List
            size="small"
            header="约束解释"
            data-testid="hydro-constraint-explanation"
            dataSource={optimizationRun.constraint_explanation}
            renderItem={(item) => <List.Item>{item}</List.Item>}
          />
          <List
            size="small"
            header="预演提示"
            data-testid="hydro-optimization-warnings"
            dataSource={optimizationRun.missing_data_warnings}
            renderItem={(warning) => <List.Item><Typography.Text type="warning">{warning}</Typography.Text></List.Item>}
          />
        </Space>
      ) : (
        <Empty description="填写约束后运行一条本地水电预演。" />
      )}
      <List
        size="small"
        className="card-footer"
        header="最近预演"
        data-testid="hydro-optimization-recent"
        dataSource={props.recentOptimizations}
        locale={{ emptyText: "暂无水电约束预演记录" }}
        renderItem={(run) => (
          <List.Item>
            <Space wrap>
              <Typography.Text>{run.trade_date}</Typography.Text>
              <Tag>{run.data_mode}</Tag>
              <Typography.Text>{run.optimization_run_id}</Typography.Text>
            </Space>
          </List.Item>
        )}
      />
      <Table
        size="small"
        className="card-footer"
        pagination={false}
        rowKey="key"
        data-testid="hydro-optimization-comparison"
        dataSource={comparisonRows}
        locale={{ emptyText: "暂无可对比的水电预演记录" }}
        columns={[
          { title: "交易日", dataIndex: "trade_date" },
          { title: "能量 MWh", dataIndex: "energy_budget_mwh" },
          { title: "出力边界", dataIndex: "output_bounds" },
          { title: "价格信号", dataIndex: "price_signal_used" },
          { title: "Top intervals", dataIndex: "top_intervals" },
          { title: "Warnings", dataIndex: "warning_count" },
        ]}
      />
    </Card>
  );
}

function RecommendationFeedbackAnalyticsCard(props: {
  analytics: RecommendationFeedbackAnalytics | null;
  error: string | null;
}) {
  if (props.error) {
    return (
      <Card title="Feedback analytics" data-testid="recommendation-feedback-analytics">
        <Alert type="warning" showIcon message={props.error} />
      </Card>
    );
  }
  if (!props.analytics) {
    return (
      <Card title="Feedback analytics" data-testid="recommendation-feedback-analytics">
        <Empty description="Feedback analytics is loading." />
      </Card>
    );
  }
  const { analytics } = props;
  const summary = analytics.summary;
  const auditStatusTags = Object.entries(summary.audit_status_counts);
  const reviewStatusTags = Object.entries(summary.review_status_counts);
  const outcomeTags = Object.entries(summary.outcome_status_counts);
  return (
    <Card
      title="Feedback analytics"
      data-testid="recommendation-feedback-analytics"
      extra={<Tag color={auditColor(analytics.status)}>{analytics.status}</Tag>}
    >
      <Alert
        type="info"
        showIcon
        message="Read-only local operator feedback summary"
        description={analytics.message}
      />
      <Row gutter={[16, 16]} className="card-footer">
        <Col xs={12} lg={6}><Statistic title="Recommendations" value={summary.recommendation_count} /></Col>
        <Col xs={12} lg={6}><Statistic title="Decisions" value={summary.decision_count} /></Col>
        <Col xs={12} lg={6}><Statistic title="Feedback" value={summary.feedback_count} /></Col>
        <Col xs={12} lg={6}><Statistic title="Pending observation" value={summary.pending_observation_count} /></Col>
      </Row>
      <Space wrap className="card-footer">
        <Tag color={analytics.no_auto_trading ? "green" : "red"}>
          no_auto_trading={String(analytics.no_auto_trading)}
        </Tag>
        <Tag color={summary.critical_audit_not_adopted_count ? "gold" : "green"}>
          critical_not_adopted={summary.critical_audit_not_adopted_count}
        </Tag>
        <Tag color={summary.no_auto_trading_false_count ? "red" : "green"}>
          no_auto_false={summary.no_auto_trading_false_count}
        </Tag>
        <Tag color={summary.safety_boundary_unacknowledged_count ? "red" : "green"}>
          safety_unack={summary.safety_boundary_unacknowledged_count}
        </Tag>
        {auditStatusTags.map(([status, count]) => (
          <Tag key={`audit-${status}`} color={auditColor(status)}>
            audit_{status}={count}
          </Tag>
        ))}
        {reviewStatusTags.map(([status, count]) => (
          <Tag key={`review-${status}`}>review_{status}={count}</Tag>
        ))}
        {outcomeTags.map(([status, count]) => (
          <Tag key={status}>{status}={count}</Tag>
        ))}
      </Space>
      <List
        size="small"
        data-testid="feedback-analytics-actions"
        header="Recommended follow-up"
        dataSource={analytics.recommended_actions}
        renderItem={(action) => <List.Item>{action}</List.Item>}
      />
      <List
        size="small"
        data-testid="feedback-analytics-pending"
        header="Pending observation"
        dataSource={analytics.pending_observation_decisions}
        locale={{ emptyText: "No pending observation decisions." }}
        renderItem={(decision) => (
          <List.Item>
            <Space wrap>
              <Tag>{decision.decision_status}</Tag>
              <Typography.Text>{decision.recommendation_id}</Typography.Text>
              <Typography.Text>{decision.note}</Typography.Text>
            </Space>
          </List.Item>
        )}
      />
      <List
        size="small"
        data-testid="feedback-analytics-recent-feedback"
        header="Recent feedback"
        dataSource={analytics.recent_feedback}
        locale={{ emptyText: "No follow-up feedback yet." }}
        renderItem={(feedback) => (
          <List.Item>
            <Space wrap>
              <Tag>{feedback.outcome_status}</Tag>
              <Typography.Text>{feedback.recommendation_id}</Typography.Text>
              <Typography.Text>{feedback.note}</Typography.Text>
              <Tag>{feedback.data_mode}</Tag>
            </Space>
          </List.Item>
        )}
      />
    </Card>
  );
}

function RecommendationCard(props: RecommendationCardProps) {
  const { recommendation } = props;
  return (
    <Card data-testid="recommendation-card" title={`模拟建议 ${recommendation.trade_date}`} extra={<Tag color="gold">{recommendation.review_status}</Tag>}>
      <Alert type="warning" showIcon message="该建议基于 scenario_simulated 数据，不是真实公司持仓或水库调度数据。" />
      <Row gutter={[16, 16]} className="card-footer">
        <Col xs={12} lg={6}><Statistic title="风险等级" value={recommendation.risk_level} /></Col>
        <Col xs={12} lg={6}><Statistic title="置信度" value={recommendation.confidence} precision={2} /></Col>
        <Col xs={12} lg={6}><Statistic title="复核状态" value={recommendation.review_status} /></Col>
        <Col xs={12} lg={6}><Statistic title="自动交易" value={recommendation.no_auto_trading ? "禁用" : "异常"} /></Col>
      </Row>
      <Typography.Title level={4}>市场研判</Typography.Title>
      <Typography.Paragraph>{recommendation.market_view}</Typography.Paragraph>
      <Typography.Title level={4}>水电行动建议</Typography.Title>
      <Typography.Paragraph>{recommendation.hydro_action}</Typography.Paragraph>
      <Typography.Title level={4}>建议窗口</Typography.Title>
      <Table<RecommendedWindow> size="small" pagination={false} rowKey="time" dataSource={recommendation.recommended_windows} columns={[
        { title: "时间", dataIndex: "time" },
        { title: "姿态", dataIndex: "stance" },
        { title: "说明", dataIndex: "reason" },
      ]} />
      <Typography.Title level={4}>缺失数据提示</Typography.Title>
      <List size="small" dataSource={recommendation.missing_data_warnings} renderItem={(warning) => <List.Item><Typography.Text type="warning">{warning}</Typography.Text></List.Item>} />
      <Typography.Title level={4}>证据依据</Typography.Title>
      <Table<Evidence> size="small" pagination={false} rowKey={(item) => `${item.source}-${item.field}`} dataSource={recommendation.evidence} columns={[
        { title: "来源", dataIndex: "source" },
        { title: "字段", dataIndex: "field" },
        { title: "数值", dataIndex: "value", render: (value: Evidence["value"]) => String(value) },
        { title: "单位", dataIndex: "unit", render: (value: string | null) => value ?? "-" },
        { title: "置信度", dataIndex: "confidence", render: (value: number) => value.toFixed(2) },
        { title: "数据模式", dataIndex: "data_mode" },
      ]} />
      <RecommendationAuditCard audit={props.audit} auditError={props.auditError} />
      <RecommendationReviewPackageCard
        evidenceExport={props.evidenceExport}
        evidenceExportError={props.evidenceExportError}
      />
      <RecommendationDecisionLogCard
        recommendation={recommendation}
        audit={props.audit}
        decisions={props.decisions}
        decisionStatus={props.decisionStatus}
        selectedWindows={props.selectedWindows}
        decisionNote={props.decisionNote}
        safetyAcknowledged={props.safetyAcknowledged}
        decisionLoading={props.decisionLoading}
        decisionError={props.decisionError}
        feedbackDrafts={props.feedbackDrafts}
        onDecisionStatusChange={props.onDecisionStatusChange}
        onSelectedWindowsChange={props.onSelectedWindowsChange}
        onDecisionNoteChange={props.onDecisionNoteChange}
        onSafetyAcknowledgedChange={props.onSafetyAcknowledgedChange}
        onDecision={props.onDecision}
        onFeedbackDraftChange={props.onFeedbackDraftChange}
        onFeedback={props.onFeedback}
      />
      <Typography.Title level={4}>人工复核</Typography.Title>
      <Space orientation="vertical" className="full-width">
        <Select data-testid="review-status" aria-label="复核结果" value={props.reviewStatus} options={REVIEW_OPTIONS} onChange={props.onReviewStatusChange} />
        <Input.TextArea data-testid="review-note" aria-label="复核备注" value={props.reviewNote} onChange={(event) => props.onReviewNoteChange(event.target.value)} placeholder="请填写判断依据或需要补充的数据。" />
        <Button data-testid="submit-review" type="primary" loading={props.loading} onClick={props.onReview}>提交复核</Button>
      </Space>
      {recommendation.reviews.length > 0 && (
        <div data-testid="review-history">
          <Typography.Title level={4}>复核历史</Typography.Title>
          <List size="small" dataSource={recommendation.reviews} renderItem={(review) => <List.Item>{review.created_at} · {review.actor} · {review.review_status} · {review.note}</List.Item>} />
        </div>
      )}
    </Card>
  );
}

function RecommendationReviewPackageCard(props: {
  evidenceExport: RecommendationEvidenceExport | null;
  evidenceExportError: string | null;
}) {
  if (props.evidenceExportError) {
    return (
      <Card title="Review package" data-testid="recommendation-review-package">
        <Alert type="warning" showIcon message={props.evidenceExportError} />
      </Card>
    );
  }
  if (!props.evidenceExport) {
    return (
      <Card title="Review package" data-testid="recommendation-review-package">
        <Empty description="Review package is loading." />
      </Card>
    );
  }
  const { evidenceExport } = props;
  const exportJson = JSON.stringify(evidenceExport, null, 2);
  return (
    <Card
      title="Review package"
      data-testid="recommendation-review-package"
      extra={<Tag color={auditColor(evidenceExport.audit_status)}>{evidenceExport.audit_status}</Tag>}
    >
      <Alert
        type="info"
        showIcon
        message="只读证据导出包"
        description="用于人工复核、留痕和复制，不会改变建议状态、置信度或触发交易。"
      />
      <Row gutter={[16, 16]} className="card-footer">
        <Col xs={12} lg={6}>
          <Statistic title="证据数量" value={evidenceExport.evidence_summary.evidence_count} />
        </Col>
        <Col xs={12} lg={6}>
          <Statistic title="缺失项" value={evidenceExport.evidence_summary.missing_data_count} />
        </Col>
        <Col xs={12} lg={6}>
          <Statistic title="风险等级" value={evidenceExport.risk_level} />
        </Col>
        <Col xs={12} lg={6}>
          <Statistic title="置信度" value={evidenceExport.confidence} precision={2} />
        </Col>
      </Row>
      <Space wrap className="card-footer">
        <Tag color="orange">{evidenceExport.data_mode}</Tag>
        <Tag color={evidenceExport.no_auto_trading ? "green" : "red"}>
          no_auto_trading={String(evidenceExport.no_auto_trading)}
        </Tag>
        <Tag color={evidenceExport.human_check_required ? "green" : "red"}>
          human_check_required={String(evidenceExport.human_check_required)}
        </Tag>
        <Tag color="blue">review={evidenceExport.review_status}</Tag>
      </Space>
      <List
        size="small"
        header="Review actions"
        dataSource={evidenceExport.recommended_actions}
        renderItem={(action) => <List.Item>{action}</List.Item>}
      />
      <Input.TextArea
        data-testid="recommendation-evidence-export-json"
        aria-label="evidence export JSON"
        readOnly
        rows={8}
        value={exportJson}
      />
    </Card>
  );
}

function RecommendationDecisionLogCard(props: {
  recommendation: RecommendationDetail;
  audit: RecommendationAudit | null;
  decisions: RecommendationDecision[];
  decisionStatus: RecommendationDecision["decision_status"];
  selectedWindows: string[];
  decisionNote: string;
  safetyAcknowledged: boolean;
  decisionLoading: boolean;
  decisionError: string | null;
  feedbackDrafts: Record<string, {
    outcome_status: RecommendationDecisionFeedback["outcome_status"];
    observed_at: string;
    note: string;
  }>;
  onDecisionStatusChange: (value: RecommendationDecision["decision_status"]) => void;
  onSelectedWindowsChange: (value: string[]) => void;
  onDecisionNoteChange: (value: string) => void;
  onSafetyAcknowledgedChange: (value: boolean) => void;
  onDecision: () => void;
  onFeedbackDraftChange: (
    decisionId: string,
    patch: Partial<{
      outcome_status: RecommendationDecisionFeedback["outcome_status"];
      observed_at: string;
      note: string;
    }>,
  ) => void;
  onFeedback: (decisionId: string) => void;
}) {
  const windowOptions = props.recommendation.recommended_windows.map((item) => ({
    label: `${item.time} · ${item.stance}`,
    value: item.time,
  }));
  return (
    <Card title="人工决策日志" data-testid="decision-log-card">
      <Alert
        type="info"
        showIcon
        message="本区域只记录人工研究决策与复盘，不是交易指令，不触发自动交易。"
      />
      {props.decisionError && <Alert type="warning" showIcon message={props.decisionError} />}
      <Space wrap className="card-footer">
        <Tag color={auditColor(props.audit?.overall_status ?? "warning")}>
          audit={props.audit?.overall_status ?? "unavailable"}
        </Tag>
        <Tag color={props.recommendation.no_auto_trading ? "green" : "red"}>
          no_auto_trading={String(props.recommendation.no_auto_trading)}
        </Tag>
      </Space>
      <Space orientation="vertical" className="full-width">
        <Select
          data-testid="decision-status"
          aria-label="人工决策状态"
          value={props.decisionStatus}
          options={DECISION_OPTIONS}
          onChange={props.onDecisionStatusChange}
        />
        <Checkbox.Group
          data-testid="decision-windows"
          options={windowOptions}
          value={props.selectedWindows}
          onChange={(values) => props.onSelectedWindowsChange(values.map(String))}
        />
        <Input.TextArea
          data-testid="decision-note"
          aria-label="人工决策说明"
          value={props.decisionNote}
          onChange={(event) => props.onDecisionNoteChange(event.target.value)}
          placeholder="记录是否采纳、采纳原因、仍缺少的数据和人工判断依据。"
        />
        <Checkbox
          data-testid="decision-safety-ack"
          checked={props.safetyAcknowledged}
          onChange={(event) => props.onSafetyAcknowledgedChange(event.target.checked)}
        >
          我确认该记录仅为本地研究日志，不是交易指令，也不会触发自动交易。
        </Checkbox>
        <Button
          data-testid="submit-decision"
          type="primary"
          loading={props.decisionLoading}
          onClick={props.onDecision}
        >
          保存人工决策
        </Button>
      </Space>
      <div data-testid="decision-history" className="card-footer">
        <Typography.Title level={4}>决策与复盘历史</Typography.Title>
        <List
          size="small"
          dataSource={props.decisions}
          locale={{ emptyText: "暂无人工决策日志" }}
          renderItem={(decision) => (
            <List.Item>
              <Space orientation="vertical" className="full-width">
                <Space wrap>
                  <Tag color="blue">{decision.decision_status}</Tag>
                  <Typography.Text>{decision.created_at}</Typography.Text>
                  <Typography.Text>{decision.actor}</Typography.Text>
                  <Tag color={decision.no_auto_trading ? "green" : "red"}>
                    no_auto_trading={String(decision.no_auto_trading)}
                  </Tag>
                </Space>
                <Typography.Text>{decision.note}</Typography.Text>
                <Typography.Text type="secondary">
                  窗口：{decision.selected_windows.length ? decision.selected_windows.join(", ") : "未选择"}
                </Typography.Text>
                <List
                  size="small"
                  dataSource={decision.feedback}
                  locale={{ emptyText: "暂无复盘反馈" }}
                  renderItem={(feedback) => (
                    <List.Item>
                      <Space wrap>
                        <Tag>{feedback.outcome_status}</Tag>
                        <Typography.Text>{feedback.observed_at ?? "-"}</Typography.Text>
                        <Typography.Text>{feedback.note}</Typography.Text>
                        <Tag>{feedback.data_mode}</Tag>
                      </Space>
                    </List.Item>
                  )}
                />
                <Space orientation="vertical" className="full-width">
                  <Space wrap>
                    <Select
                      data-testid={`feedback-outcome-${decision.decision_id}`}
                      aria-label="复盘结果"
                      value={
                        props.feedbackDrafts[decision.decision_id]?.outcome_status
                        ?? "pending_observation"
                      }
                      options={OUTCOME_OPTIONS}
                      onChange={(value) => props.onFeedbackDraftChange(decision.decision_id, {
                        outcome_status: value,
                      })}
                    />
                    <Input
                      data-testid={`feedback-observed-${decision.decision_id}`}
                      aria-label="观察日期"
                      type="date"
                      value={props.feedbackDrafts[decision.decision_id]?.observed_at ?? localIsoDate()}
                      onChange={(event) => props.onFeedbackDraftChange(decision.decision_id, {
                        observed_at: event.target.value,
                      })}
                    />
                  </Space>
                  <Input.TextArea
                    data-testid={`feedback-note-${decision.decision_id}`}
                    aria-label="复盘说明"
                    value={props.feedbackDrafts[decision.decision_id]?.note ?? ""}
                    onChange={(event) => props.onFeedbackDraftChange(decision.decision_id, {
                      note: event.target.value,
                    })}
                    placeholder="记录后续观察、是否有帮助和仍需补充的证据。"
                  />
                  <Button
                    data-testid={`submit-feedback-${decision.decision_id}`}
                    loading={props.decisionLoading}
                    onClick={() => props.onFeedback(decision.decision_id)}
                  >
                    保存复盘反馈
                  </Button>
                </Space>
              </Space>
            </List.Item>
          )}
        />
      </div>
    </Card>
  );
}

function RecommendationAuditCard(props: {
  audit: RecommendationAudit | null;
  auditError: string | null;
}) {
  if (props.auditError) {
    return (
      <Card title="证据审计" data-testid="recommendation-audit">
        <Alert type="warning" showIcon message={props.auditError} />
      </Card>
    );
  }
  if (!props.audit) {
    return null;
  }
  const { audit } = props;
  return (
    <Card
      title="证据审计"
      data-testid="recommendation-audit"
      extra={<Tag color={auditColor(audit.overall_status)}>{audit.overall_status}</Tag>}
    >
      <Row gutter={[16, 16]}>
        <Col xs={12} lg={6}><Statistic title="证据数量" value={audit.evidence_summary.evidence_count} /></Col>
        <Col xs={12} lg={6}><Statistic title="缺失项" value={audit.evidence_summary.missing_data_count} /></Col>
        <Col xs={12} lg={6}><Statistic title="BENCH 证据" value={audit.evidence_summary.bench_evidence_count} /></Col>
        <Col xs={12} lg={6}><Statistic title="research_only" value={audit.evidence_summary.research_only_evidence_count} /></Col>
      </Row>
      <Space wrap className="card-footer">
        <Tag color={audit.no_auto_trading ? "green" : "red"}>
          no_auto_trading={String(audit.no_auto_trading)}
        </Tag>
        <Tag color={audit.human_check_required ? "green" : "red"}>
          human_check_required={String(audit.human_check_required)}
        </Tag>
        <Tag color="blue">review={audit.review_status}</Tag>
        <Tag color={audit.evidence_summary.weather_evidence_present ? "green" : "gold"}>
          weather_evidence={String(audit.evidence_summary.weather_evidence_present)}
        </Tag>
      </Space>
      <List<RecommendationAuditCheck>
        size="small"
        dataSource={audit.checks}
        renderItem={(check) => (
          <List.Item>
            <Space orientation="vertical" size={2}>
              <Space wrap>
                <Tag color={auditColor(check.status)}>{check.status}</Tag>
                <Typography.Text strong>{check.label}</Typography.Text>
              </Space>
              <Typography.Text>{check.message}</Typography.Text>
            </Space>
          </List.Item>
        )}
      />
      <List
        size="small"
        header="建议处理动作"
        dataSource={audit.recommended_actions}
        renderItem={(action) => <List.Item>{action}</List.Item>}
      />
    </Card>
  );
}
