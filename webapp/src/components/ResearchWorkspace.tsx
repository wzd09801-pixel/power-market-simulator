import { DownloadOutlined, InboxOutlined, SendOutlined } from "@ant-design/icons";
import type { UploadRequestOption } from "@rc-component/upload/lib/interface";
import { Alert, Button, Card, Checkbox, Col, Descriptions, Empty, Input, List, Row, Select, Space, Statistic, Switch, Tag, Typography, Upload } from "antd";
import { LineChart } from "echarts/charts";
import { GridComponent, TooltipComponent } from "echarts/components";
import * as echarts from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import ReactEChartsCoreModule from "echarts-for-react/lib/core";
import { type ChangeEvent, useEffect, useState } from "react";

import { api } from "../api";
import {
  defaultManualForecastMetadata,
  metadataFromPreview,
  parseForecastImportText,
} from "../forecastImport";
import type { ForecastDataset, ForecastImportPreview, ForecastImportRun, ForecastModelRun, ForecastPoint, ForecastPrediction, ForecastQualityIssue, ForecastResearchOverview, ForecastReviewPackage, KnowledgeCorpusOverview, KnowledgeDocument, KnowledgeDocumentDetail, ManualForecastDatasetPayload, MarketEndpoint, MarketRawArtifact, MarketSource, QuestionAnswer } from "../types";

echarts.use([LineChart, GridComponent, TooltipComponent, CanvasRenderer]);

const ReactEChartsCore = (
  (ReactEChartsCoreModule as unknown as { default?: typeof ReactEChartsCoreModule }).default
  ?? ReactEChartsCoreModule
);

type BenchBenchmark = ForecastDataset;
type ForecastImportForm = Omit<ManualForecastDatasetPayload, "points">;

const FORECAST_MARKET_STAGE_OPTIONS = [
  { label: "day_ahead", value: "day_ahead" },
  { label: "real_time", value: "real_time" },
  { label: "other", value: "other" },
] as const;

const FORECAST_DATA_MODE_OPTIONS = [
  { label: "user_uploaded", value: "user_uploaded" },
  { label: "public_observed", value: "public_observed" },
  { label: "public_derived", value: "public_derived" },
  { label: "scenario_simulated", value: "scenario_simulated" },
] as const;

function statusColor(status: string) {
  if (status === "healthy") return "green";
  if (status === "warning") return "gold";
  if (status === "critical") return "red";
  return "default";
}

function percent(value: number) {
  return `${Math.round(value * 100)}%`;
}

function metricValue(metrics: Record<string, unknown>, key: string) {
  const value = metrics[key];
  if (typeof value === "number") return value.toFixed(3);
  if (typeof value === "string") return value;
  return "-";
}

function formatCounts(counts: Record<string, number>) {
  const entries = Object.entries(counts);
  if (entries.length === 0) return "none";
  return entries.map(([key, value]) => `${key}: ${value}`).join(", ");
}

function reviewPackageFilename(datasetId: string) {
  return `forecast-review-${datasetId.replace(/[^A-Za-z0-9_.-]/g, "_")}.json`;
}

function downloadReviewPackage(reviewPackage: ForecastReviewPackage) {
  const blob = new Blob([JSON.stringify(reviewPackage, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = reviewPackageFilename(reviewPackage.dataset.dataset_id);
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export function ResearchWorkspace() {
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [artifacts, setArtifacts] = useState<MarketRawArtifact[]>([]);
  const [sources, setSources] = useState<MarketSource[]>([]);
  const [endpoints, setEndpoints] = useState<MarketEndpoint[]>([]);
  const [corpusOverview, setCorpusOverview] = useState<KnowledgeCorpusOverview | null>(null);
  const [documentDetail, setDocumentDetail] = useState<KnowledgeDocumentDetail | null>(null);
  const [question, setQuestion] = useState("");
  const [deep, setDeep] = useState(false);
  const [answer, setAnswer] = useState<QuestionAnswer | null>(null);
  const [benchmarks, setBenchmarks] = useState<BenchBenchmark[]>([]);
  const [forecastDatasets, setForecastDatasets] = useState<ForecastDataset[]>([]);
  const [forecastOverview, setForecastOverview] = useState<ForecastResearchOverview | null>(null);
  const [forecastImportRuns, setForecastImportRuns] = useState<ForecastImportRun[]>([]);
  const [forecastQualityIssues, setForecastQualityIssues] = useState<ForecastQualityIssue[]>([]);
  const [forecastReviewPackage, setForecastReviewPackage] = useState<ForecastReviewPackage | null>(null);
  const [forecastModelRuns, setForecastModelRuns] = useState<ForecastModelRun[]>([]);
  const [predictionsByModelRun, setPredictionsByModelRun] = useState<Record<string, ForecastPrediction[]>>({});
  const [pointsByDataset, setPointsByDataset] = useState<Record<string, ForecastPoint[]>>({});
  const [forecastImportPreview, setForecastImportPreview] = useState<ForecastImportPreview | null>(null);
  const [forecastImportForm, setForecastImportForm] = useState<ForecastImportForm>(defaultManualForecastMetadata);
  const [forecastImportError, setForecastImportError] = useState<string | null>(null);
  const [forecastImportSuccess, setForecastImportSuccess] = useState<string | null>(null);
  const [submittingForecastImport, setSubmittingForecastImport] = useState(false);
  const [selectedDatasetId, setSelectedDatasetId] = useState<string | null>(null);
  const [selectedForecastDatasetId, setSelectedForecastDatasetId] = useState<string | null>(null);
  const [selectedModelRunId, setSelectedModelRunId] = useState<string | null>(null);
  const [runningBacktest, setRunningBacktest] = useState<string | null>(null);
  const [importingArtifactId, setImportingArtifactId] = useState<string | null>(null);
  const [loadingDocumentDetailId, setLoadingDocumentDetailId] = useState<string | null>(null);
  const [importStatus, setImportStatus] = useState<string | null>(null);
  const [corpusError, setCorpusError] = useState<string | null>(null);
  const [documentDetailError, setDocumentDetailError] = useState<string | null>(null);
  const [artifactError, setArtifactError] = useState<string | null>(null);
  const [forecastError, setForecastError] = useState<string | null>(null);
  const [reviewPackageError, setReviewPackageError] = useState<string | null>(null);
  const [backtestError, setBacktestError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    try {
      const [documentItems, sourceItems, endpointItems, datasets] = await Promise.all([
        api.documents(), api.sources(), api.endpoints(), api.datasets(),
      ]);
      const benchDatasets = datasets.filter((dataset) =>
        dataset.market_scope === "bench_nem_dispatch_benchmark"
        && dataset.usage_scope === "research_only",
      );
      const latestByRegion = new Map<string, ForecastDataset>();
      for (const dataset of benchDatasets) {
        const current = latestByRegion.get(dataset.region_code);
        if (!current || Date.parse(dataset.imported_at) > Date.parse(current.imported_at)) {
          latestByRegion.set(dataset.region_code, dataset);
        }
      }
      const benchBenchmarks = [...latestByRegion.values()]
        .sort((left, right) => left.region_code.localeCompare(right.region_code));
      setDocuments(documentItems);
      setSources(sourceItems);
      setEndpoints(endpointItems);
      setBenchmarks(benchBenchmarks);
      setForecastDatasets(datasets);
      setSelectedDatasetId((current) =>
        benchBenchmarks.some((benchmark) => benchmark.dataset_id === current)
          ? current
          : (benchBenchmarks[0]?.dataset_id ?? null),
      );
      setSelectedForecastDatasetId((current) =>
        datasets.some((dataset) => dataset.dataset_id === current)
          ? current
          : (datasets[0]?.dataset_id ?? null),
      );
      setError(null);
    } catch {
      setError("研究数据 API 暂不可用，请检查本地服务状态。");
    }
  };

  const loadArtifacts = async () => {
    try {
      setArtifacts(await api.marketArtifacts());
      setArtifactError(null);
    } catch {
      setArtifactError("已保全原文列表暂不可用；资料库、来源健康和 BENCH 研究视图不受影响。");
    }
  };

  const loadCorpusOverview = async () => {
    try {
      setCorpusOverview(await api.policyCorpusOverview());
      setCorpusError(null);
    } catch {
      setCorpusError("语料库健康状态暂不可用；资料列表、来源健康和 BENCH 研究视图不受影响。");
    }
  };

  const loadForecastOverview = async () => {
    try {
      setForecastOverview(await api.forecastOverview());
      setForecastError(null);
    } catch {
      setForecastError("Forecast research overview is unavailable; policy corpus and BENCH isolation are unaffected.");
    }
  };

  const loadForecastDatasetState = async (datasetId: string) => {
    try {
      const [runs, issues, modelRuns, reviewPackage] = await Promise.all([
        api.forecastImportRuns(datasetId),
        api.forecastQualityIssues(datasetId),
        api.forecastModelRuns(datasetId),
        api.forecastReviewPackage(datasetId),
      ]);
      setForecastImportRuns(runs);
      setForecastQualityIssues(issues);
      setForecastModelRuns(modelRuns);
      setForecastReviewPackage(reviewPackage);
      setSelectedModelRunId((current) =>
        modelRuns.some((run) => run.model_run_id === current)
          ? current
          : null,
      );
      setForecastError(null);
      setReviewPackageError(null);
    } catch {
      setForecastReviewPackage(null);
      setForecastError("Forecast research details are unavailable for the selected dataset.");
      setReviewPackageError("Forecast review package is unavailable for the selected dataset.");
    }
  };

  const updateForecastImportField = <K extends keyof ForecastImportForm>(
    key: K,
    value: ForecastImportForm[K],
  ) => {
    setForecastImportForm((current) => ({
      ...current,
      [key]: value,
      interval_minutes: 15,
      usage_scope: "research_only",
    }));
  };

  const handleForecastImportFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      const preview = parseForecastImportText(file.name, await file.text());
      setForecastImportPreview(preview);
      setForecastImportForm((current) => metadataFromPreview(preview, current));
      setForecastImportSuccess(null);
      setForecastImportError(preview.errors.length > 0 ? preview.errors.join(" ") : null);
    } catch {
      setForecastImportPreview(null);
      setForecastImportError("Forecast import file could not be read.");
    } finally {
      event.target.value = "";
    }
  };

  const submitForecastImport = async () => {
    if (forecastImportPreview === null) {
      setForecastImportError("Choose a local CSV or JSON file before importing.");
      return;
    }
    if (forecastImportPreview.errors.length > 0) {
      setForecastImportError(forecastImportPreview.errors.join(" "));
      return;
    }
    const requiredMetadata: Array<keyof ForecastImportForm> = [
      "name",
      "source_name",
      "source_url",
      "region_code",
      "region_name",
      "market_scope",
      "price_scope",
      "timezone",
      "currency",
      "price_unit",
      "notes",
    ];
    const missing = requiredMetadata.filter((key) => {
      const value = forecastImportForm[key];
      return typeof value === "string" && value.trim() === "";
    });
    if (missing.length > 0) {
      setForecastImportError(`Fill required forecast metadata: ${missing.join(", ")}.`);
      return;
    }

    const payload: ManualForecastDatasetPayload = {
      ...forecastImportForm,
      interval_minutes: 15,
      usage_scope: "research_only",
      points: forecastImportPreview.points.map((point) => ({
        interval_start: point.interval_start,
        price: point.price,
      })),
    };
    setSubmittingForecastImport(true);
    try {
      const result = await api.createManualForecastDataset(payload);
      setForecastImportSuccess(
        `Imported forecast dataset ${result.dataset_id}: ${result.status}, ${result.normalized_point_count} normalized points, ${result.quality_status}.`,
      );
      setForecastImportError(null);
      setPointsByDataset((current) => {
        const next = { ...current };
        delete next[result.dataset_id];
        return next;
      });
      await load();
      setSelectedForecastDatasetId(result.dataset_id);
      await loadForecastOverview();
      await loadForecastDatasetState(result.dataset_id);
    } catch {
      setForecastImportError("Forecast dataset import failed. Check metadata, timezone offsets, 96-point coverage, and backend quality issues.");
    } finally {
      setSubmittingForecastImport(false);
    }
  };

  const loadDocumentDetail = async (documentId: string) => {
    setLoadingDocumentDetailId(documentId);
    try {
      setDocumentDetail(await api.documentDetail(documentId));
      setDocumentDetailError(null);
    } catch {
      setDocumentDetailError("文档详情暂不可用，请检查本地 API 状态。");
    } finally {
      setLoadingDocumentDetailId(null);
    }
  };

  useEffect(() => {
    void load();
    void loadArtifacts();
    void loadCorpusOverview();
    void loadForecastOverview();
  }, []);

  useEffect(() => {
    if (selectedDatasetId === null || pointsByDataset[selectedDatasetId] !== undefined) return;
    let cancelled = false;
    void api.points(selectedDatasetId)
      .then((items) => {
        if (!cancelled) {
          setPointsByDataset((current) => ({ ...current, [selectedDatasetId]: items }));
        }
      })
      .catch(() => {
        if (!cancelled) setError("BENCH 研究曲线加载失败，请检查本地 API 状态。");
      });
    return () => {
      cancelled = true;
    };
  }, [pointsByDataset, selectedDatasetId]);

  useEffect(() => {
    if (selectedForecastDatasetId === null) {
      setForecastReviewPackage(null);
      return;
    }
    void loadForecastDatasetState(selectedForecastDatasetId);
  }, [selectedForecastDatasetId]);

  useEffect(() => {
    if (selectedModelRunId === null || predictionsByModelRun[selectedModelRunId] !== undefined) return;
    let cancelled = false;
    if (
      selectedForecastDatasetId !== null
      && pointsByDataset[selectedForecastDatasetId] === undefined
    ) {
      void api.points(selectedForecastDatasetId)
        .then((items) => {
          if (!cancelled) {
            setPointsByDataset((current) => ({ ...current, [selectedForecastDatasetId]: items }));
          }
        })
        .catch(() => {
          if (!cancelled) {
            setForecastError("Forecast price points are unavailable for the selected dataset.");
          }
        });
    }
    void api.forecastPredictions(selectedModelRunId)
      .then((items) => {
        if (!cancelled) {
          setPredictionsByModelRun((current) => ({ ...current, [selectedModelRunId]: items }));
        }
      })
      .catch(() => {
        if (!cancelled) setForecastError("Forecast predictions are unavailable for the selected model run.");
      });
    return () => {
      cancelled = true;
    };
  }, [pointsByDataset, predictionsByModelRun, selectedForecastDatasetId, selectedModelRunId]);

  const upload = async ({ file, onSuccess, onError }: UploadRequestOption) => {
    const form = new FormData();
    form.append("file", file as Blob);
    form.append("title", (file as File).name);
    form.append("document_layer", "user_uploaded");
    try {
      await api.upload(form);
      onSuccess?.({});
      await load();
      await loadCorpusOverview();
    } catch (uploadError) {
      onError?.(uploadError as Error);
    }
  };

  const ask = async () => {
    try {
      setAnswer(await api.ask(question, deep));
      setError(null);
    } catch {
      setError("证据问答失败，请检查本地检索和模型配置。");
    }
  };

  const authorize = async (documentId: string, allowed: boolean) => {
    try {
      await api.authorizeDocument(documentId, allowed);
      await load();
      await loadCorpusOverview();
      if (documentDetail?.document_id === documentId) {
        await loadDocumentDetail(documentId);
      }
    } catch {
      setError("资料外发授权更新失败，请检查本地 API 状态。");
    }
  };

  const importArtifact = async (artifactId: string) => {
    setImportingArtifactId(artifactId);
    try {
      const document = await api.importMarketArtifactToKnowledge(artifactId);
      let chunkStatus = "分块状态读取失败";
      try {
        const chunks = await api.documentChunks(document.document_id);
        chunkStatus = `${chunks.length} 个分块`;
      } catch {
        chunkStatus = "分块状态读取失败";
      }
      setImportStatus(
        `已转入知识库：${document.document_id}，${chunkStatus}，外部处理默认禁用。`,
      );
      setError(null);
      await load();
      await loadArtifacts();
      await loadCorpusOverview();
      await loadDocumentDetail(document.document_id);
    } catch {
      setError("保全原文转入知识库失败，请检查媒体类型、正文内容或 research_only 限制。");
    } finally {
      setImportingArtifactId(null);
    }
  };

  const runBacktest = async (modelKey: "seasonal_naive" | "calendar_mean") => {
    if (selectedForecastDatasetId === null) return;
    setRunningBacktest(modelKey);
    try {
      const run = await api.runForecastBacktest(selectedForecastDatasetId, modelKey);
      setSelectedModelRunId(run.model_run_id);
      setPredictionsByModelRun((current) => {
        const next = { ...current };
        delete next[run.model_run_id];
        return next;
      });
      await loadForecastOverview();
      await loadForecastDatasetState(selectedForecastDatasetId);
      setBacktestError(null);
    } catch {
      setBacktestError("Baseline backtest failed. Check dataset quality and history length.");
    } finally {
      setRunningBacktest(null);
    }
  };

  const points = selectedDatasetId === null ? [] : (pointsByDataset[selectedDatasetId] ?? []);
  const forecastPoints = selectedForecastDatasetId === null
    ? []
    : (pointsByDataset[selectedForecastDatasetId] ?? []);
  const forecastPredictions = selectedModelRunId === null
    ? []
    : (predictionsByModelRun[selectedModelRunId] ?? []);
  const predictedByInterval = new Map(
    forecastPredictions.map((prediction) => [
      prediction.target_interval_start,
      Number(prediction.predicted_price),
    ]),
  );
  const chart = {
    grid: { left: 48, right: 20, top: 20, bottom: 42 },
    xAxis: { type: "category", data: points.map((point) => point.interval_start.slice(11, 16)) },
    yAxis: { type: "value", name: "AUD/MWh" },
    series: [{ type: "line", showSymbol: false, smooth: true, data: points.map((point) => Number(point.price)), lineStyle: { color: "#26736a" } }],
    tooltip: { trigger: "axis" },
  };
  const forecastChart = {
    grid: { left: 48, right: 20, top: 20, bottom: 42 },
    xAxis: { type: "category", data: forecastPoints.map((point) => point.interval_start.slice(11, 16)) },
    yAxis: { type: "value", name: "Price" },
    series: [
      { name: "actual", type: "line", showSymbol: false, data: forecastPoints.map((point) => Number(point.price)), lineStyle: { color: "#26736a" } },
      { name: "predicted", type: "line", showSymbol: false, data: forecastPoints.map((point) => predictedByInterval.get(point.interval_start) ?? null), lineStyle: { color: "#d46b08" } },
    ],
    tooltip: { trigger: "axis" },
  };

  return (
    <Space orientation="vertical" size={18} className="full-width" data-testid="research-workspace">
      <section className="hero">
        <div>
          <Typography.Text className="eyebrow">RESEARCH WORKSPACE</Typography.Text>
          <Typography.Title level={2}>证据与研究</Typography.Title>
          <Typography.Paragraph>
            官方资料优先，公共研究分层展示，上传资料默认仅在本地处理。
          </Typography.Paragraph>
        </div>
      </section>
      {error && <Alert type="warning" showIcon message={error} />}
      {importStatus && <Alert type="success" showIcon message={importStatus} />}
      <Card
        title={<Space>语料库健康{corpusOverview && <Tag color={statusColor(corpusOverview.status)}>{corpusOverview.status}</Tag>}</Space>}
        data-testid="policy-corpus-overview"
      >
        {corpusError && <Alert type="warning" showIcon message={corpusError} />}
        {corpusOverview ? (
          <Space orientation="vertical" className="full-width">
            <Row gutter={[16, 16]}>
              <Col xs={12} lg={6}>
                <Statistic title="文档" value={corpusOverview.document_count} />
              </Col>
              <Col xs={12} lg={6}>
                <Statistic title="分块" value={corpusOverview.chunk_count} />
              </Col>
              <Col xs={12} lg={6}>
                <Statistic title="Embedding 覆盖" value={percent(corpusOverview.embedding_coverage)} />
              </Col>
              <Col xs={12} lg={6}>
                <Statistic title="Artifact 来源" value={corpusOverview.artifact_provenance_count} />
              </Col>
            </Row>
            <Space wrap>
              {corpusOverview.layers.map((layer) => (
                <Tag key={layer.document_layer}>
                  {layer.document_layer}: {layer.document_count} 文档 / {layer.chunk_count} 分块 / {percent(layer.embedding_coverage)}
                </Tag>
              ))}
              <Tag>外发授权 {corpusOverview.external_processing_allowed_count}</Tag>
              <Tag>外发禁用 {corpusOverview.external_processing_blocked_count}</Tag>
              <Tag>只读聚合</Tag>
              <Tag>无网络探测</Tag>
            </Space>
            <Typography.Text type="secondary">{corpusOverview.message}</Typography.Text>
          </Space>
        ) : (
          <Empty description="正在加载语料库健康状态" />
        )}
      </Card>
      <Row gutter={[16, 16]}>
        <Col xs={24} xl={13}>
          <Card title="政策与资料库" extra={<Upload customRequest={upload} showUploadList={false}><Button icon={<InboxOutlined />}>上传本地资料</Button></Upload>}>
            <List dataSource={documents} locale={{ emptyText: "暂无资料" }} renderItem={(document) => (
              <List.Item actions={[
                <Button
                  key={`${document.document_id}-detail`}
                  data-testid={`document-detail-${document.document_id}`}
                  size="small"
                  loading={loadingDocumentDetailId === document.document_id}
                  onClick={() => void loadDocumentDetail(document.document_id)}
                >
                  查看详情
                </Button>,
                <Switch key={document.document_id} size="small" checked={document.external_processing_allowed} onChange={(allowed) => void authorize(document.document_id, allowed)} />,
              ]}>
                <List.Item.Meta title={<Space>{document.title}<Tag>{document.document_layer}</Tag></Space>} description={`${document.source_name} · 外部处理 ${document.external_processing_allowed ? "已授权" : "禁用"}`} />
              </List.Item>
            )} />
            {documentDetailError && <Alert type="warning" showIcon message={documentDetailError} />}
            {documentDetail && (
              <Card type="inner" title="文档详情" data-testid="policy-document-detail">
                <Descriptions bordered size="small" column={1}>
                  <Descriptions.Item label="document id">
                    <Typography.Text code>{documentDetail.document_id}</Typography.Text>
                  </Descriptions.Item>
                  <Descriptions.Item label="来源">
                    {documentDetail.source_name}
                  </Descriptions.Item>
                  <Descriptions.Item label="文档层级">
                    <Space wrap>
                      <Tag>{documentDetail.document_layer}</Tag>
                      <Tag>{documentDetail.data_mode}</Tag>
                      <Tag>{documentDetail.external_processing_allowed ? "外发已授权" : "外发禁用"}</Tag>
                      <Tag>默认{documentDetail.external_processing_allowed_default ? "允许" : "禁用"}</Tag>
                    </Space>
                  </Descriptions.Item>
                  <Descriptions.Item label="分块状态">
                    {documentDetail.chunk_count} 个分块，{documentDetail.embedded_chunk_count} 个 embedding，覆盖 {percent(documentDetail.embedding_coverage)}
                  </Descriptions.Item>
                  <Descriptions.Item label="content sha256">
                    <Typography.Text code>{documentDetail.latest_version?.content_sha256 ?? "-"}</Typography.Text>
                  </Descriptions.Item>
                  <Descriptions.Item label="raw object">
                    <Typography.Text code>{documentDetail.raw_object?.raw_object_id ?? "-"}</Typography.Text>
                  </Descriptions.Item>
                </Descriptions>
                <List
                  data-testid="policy-document-provenance"
                  size="small"
                  header="Artifact provenance"
                  dataSource={documentDetail.artifact_provenance}
                  locale={{ emptyText: "无 artifact provenance；可能是本地上传资料。" }}
                  renderItem={(provenance) => (
                    <List.Item>
                      <Space orientation="vertical" size={2}>
                        <Space wrap>
                          <Typography.Text code>{provenance.artifact_id}</Typography.Text>
                          {provenance.source_id && <Tag>{provenance.source_id}</Tag>}
                          {provenance.endpoint_id && <Tag>{provenance.endpoint_id}</Tag>}
                        </Space>
                        <Typography.Text type="secondary">{provenance.source_url ?? documentDetail.source_url ?? "-"}</Typography.Text>
                      </Space>
                    </List.Item>
                  )}
                />
              </Card>
            )}
          </Card>
        </Col>
        <Col xs={24} xl={11}>
          <Card title="证据问答">
            <Space orientation="vertical" className="full-width">
              <Input.TextArea rows={3} value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="询问政策变化、风险或证据来源" />
              <Space>
                <Checkbox checked={deep} onChange={(event) => setDeep(event.target.checked)}>深度分析</Checkbox>
                <Button type="primary" icon={<SendOutlined />} disabled={!question.trim()} onClick={() => void ask()}>提交问题</Button>
              </Space>
              {answer && <div className="answer"><Typography.Paragraph>{answer.answer}</Typography.Paragraph><Space wrap>{answer.citations.map((citation) => <Tag key={citation.chunk_id} color="blue">{citation.title} · {citation.document_layer} · {citation.source_name}</Tag>)}{answer.excluded_restricted_chunks > 0 && <Tag color="gold">已排除 {answer.excluded_restricted_chunks} 个未授权分块</Tag>}</Space></div>}
            </Space>
          </Card>
        </Col>
      </Row>
      <Card
        title="已保全原文"
        data-testid="preserved-artifacts"
        extra={<Tag>artifact-id only</Tag>}
      >
        <Typography.Paragraph type="secondary">
          仅可把已保全的注册来源 artifact 转入知识库；这里不提供 URL 输入，也不会触发新的外部抓取。
        </Typography.Paragraph>
        {artifactError && <Alert type="warning" showIcon message={artifactError} />}
        <List
          dataSource={artifacts}
          locale={{ emptyText: "暂无已保全原文" }}
          renderItem={(artifact) => (
            <List.Item
              actions={[
                <Button
                  key={artifact.artifact_id}
                  data-testid={`import-artifact-${artifact.artifact_id}`}
                  size="small"
                  loading={importingArtifactId === artifact.artifact_id}
                  onClick={() => void importArtifact(artifact.artifact_id)}
                >
                  转入知识库
                </Button>,
              ]}
            >
              <List.Item.Meta
                title={<Space>{artifact.title || artifact.artifact_id}<Tag>{artifact.media_type}</Tag></Space>}
                description={(
                      <Space orientation="vertical" size={2}>
                    <Typography.Text type="secondary">
                      {artifact.source_id} / {artifact.endpoint_id} · {artifact.captured_at.slice(0, 10)}
                    </Typography.Text>
                    <Typography.Text code>{artifact.content_sha256.slice(0, 16)}</Typography.Text>
                  </Space>
                )}
              />
            </List.Item>
          )}
        />
      </Card>
      <Row gutter={[16, 16]}>
        <Col xs={24} xl={12}>
          <Card title="来源健康与启用状态" data-testid="source-health">
            <List dataSource={sources} renderItem={(source) => (
              <List.Item><List.Item.Meta title={<a href={source.official_url}>{source.name}</a>} description={<Space wrap><Tag>{source.trust_tier}</Tag><Typography.Text type="secondary">{source.collection_permission_note}</Typography.Text></Space>} /></List.Item>
            )} />
            <List size="small" dataSource={endpoints} renderItem={(endpoint) => (
              <List.Item><Space><Typography.Text>{endpoint.name}</Typography.Text><Tag color={endpoint.collection_enabled ? "green" : "default"}>{endpoint.lifecycle_status}</Tag></Space></List.Item>
            )} />
          </Card>
        </Col>
        <Col xs={24} xl={12}>
          <Card title={<Space>BENCH Dispatch 基准<Tag>research_only</Tag></Space>}>
            {benchmarks.length > 0 ? (
              <Space orientation="vertical" className="full-width">
                <Select
                  data-testid="bench-region-select"
                  value={selectedDatasetId}
                  onChange={setSelectedDatasetId}
                  options={benchmarks.map((dataset) => ({
                    label: `${dataset.region_name} · ${dataset.imported_at.slice(0, 10)}`,
                    value: dataset.dataset_id,
                  }))}
                />
                <Space wrap>
                  {benchmarks.map((dataset) => <Tag data-testid={`bench-region-${dataset.region_code}`} key={dataset.dataset_id}>{dataset.region_code}</Tag>)}
                </Space>
                <ReactEChartsCore echarts={echarts} option={chart} style={{ height: 280 }} />
              </Space>
            ) : <Empty description="尚未导入 BENCH 基准" />}
            <Typography.Text type="secondary" data-testid="bench-isolation">
              该曲线仅用于研究基础设施，不属于示例甲省市场数据，也不会进入推荐链路。
            </Typography.Text>
          </Card>
        </Col>
      </Row>
      <Card
        title={(
          <Space>
            Forecast Data Import
            <Tag>local file</Tag>
            <Tag>research_only</Tag>
          </Space>
        )}
        data-testid="forecast-import-workbench"
      >
        <Space orientation="vertical" className="full-width">
          <Alert
            type="info"
            showIcon
            message="Import local CSV or JSON only. source_url is stored as provenance metadata and is never fetched."
          />
          {forecastImportError && (
            <Alert
              data-testid="forecast-import-error"
              type="warning"
              showIcon
              message={forecastImportError}
            />
          )}
          {forecastImportSuccess && (
            <Alert
              data-testid="forecast-import-success"
              type="success"
              showIcon
              message={forecastImportSuccess}
            />
          )}
          <input
            data-testid="forecast-import-file-input"
            type="file"
            accept=".csv,.json,text/csv,application/json"
            onChange={(event) => void handleForecastImportFile(event)}
          />
          {forecastImportPreview ? (
            <Space orientation="vertical" className="full-width">
              <Descriptions
                size="small"
                column={{ xs: 1, md: 3 }}
                data-testid="forecast-import-preview"
              >
                <Descriptions.Item label="File">{forecastImportPreview.file_name}</Descriptions.Item>
                <Descriptions.Item label="Points">{forecastImportPreview.point_count}</Descriptions.Item>
                <Descriptions.Item label="Dates">{forecastImportPreview.date_range}</Descriptions.Item>
                <Descriptions.Item label="Duplicate intervals">{forecastImportPreview.duplicate_interval_count}</Descriptions.Item>
                <Descriptions.Item label="Incomplete dates">{forecastImportPreview.incomplete_trade_date_count}</Descriptions.Item>
                <Descriptions.Item label="Timezone issues">{forecastImportPreview.timezone_issue_count}</Descriptions.Item>
                <Descriptions.Item label="Invalid prices">{forecastImportPreview.invalid_price_count}</Descriptions.Item>
                <Descriptions.Item label="Min price">{forecastImportPreview.min_price ?? "-"}</Descriptions.Item>
                <Descriptions.Item label="Max price">{forecastImportPreview.max_price ?? "-"}</Descriptions.Item>
              </Descriptions>
              {forecastImportPreview.warnings.length > 0 && (
                <Alert
                  data-testid="forecast-import-warnings"
                  type="warning"
                  showIcon
                  message={forecastImportPreview.warnings.join(" ")}
                />
              )}
              <List
                data-testid="forecast-import-sample"
                size="small"
                header="Sample points"
                dataSource={forecastImportPreview.sample_points}
                renderItem={(point) => (
                  <List.Item>
                    <Space wrap>
                      <Typography.Text code>{point.interval_start}</Typography.Text>
                      <Typography.Text>{point.price}</Typography.Text>
                      {point.source_row && <Tag>row {point.source_row}</Tag>}
                    </Space>
                  </List.Item>
                )}
              />
            </Space>
          ) : (
            <Empty description="Choose a CSV or JSON file with interval_start and price columns." />
          )}
          <Row gutter={[12, 12]}>
            <Col xs={24} md={12} xl={8}>
              <Typography.Text type="secondary">Dataset name</Typography.Text>
              <Input
                data-testid="forecast-import-name"
                value={forecastImportForm.name}
                onChange={(event) => updateForecastImportField("name", event.target.value)}
              />
            </Col>
            <Col xs={24} md={12} xl={8}>
              <Typography.Text type="secondary">Source name</Typography.Text>
              <Input
                data-testid="forecast-import-source-name"
                value={forecastImportForm.source_name}
                onChange={(event) => updateForecastImportField("source_name", event.target.value)}
              />
            </Col>
            <Col xs={24} md={12} xl={8}>
              <Typography.Text type="secondary">Source URL metadata</Typography.Text>
              <Input
                data-testid="forecast-import-source-url"
                value={forecastImportForm.source_url}
                onChange={(event) => updateForecastImportField("source_url", event.target.value)}
              />
            </Col>
            <Col xs={12} md={6} xl={4}>
              <Typography.Text type="secondary">Region code</Typography.Text>
              <Input
                data-testid="forecast-import-region-code"
                value={forecastImportForm.region_code}
                onChange={(event) => updateForecastImportField("region_code", event.target.value)}
              />
            </Col>
            <Col xs={12} md={6} xl={4}>
              <Typography.Text type="secondary">Region name</Typography.Text>
              <Input
                data-testid="forecast-import-region-name"
                value={forecastImportForm.region_name}
                onChange={(event) => updateForecastImportField("region_name", event.target.value)}
              />
            </Col>
            <Col xs={24} md={12} xl={6}>
              <Typography.Text type="secondary">Market scope</Typography.Text>
              <Input
                data-testid="forecast-import-market-scope"
                value={forecastImportForm.market_scope}
                onChange={(event) => updateForecastImportField("market_scope", event.target.value)}
              />
            </Col>
            <Col xs={24} md={12} xl={5}>
              <Typography.Text type="secondary">Market stage</Typography.Text>
              <Select
                data-testid="forecast-import-market-stage"
                className="full-width"
                value={forecastImportForm.market_stage}
                options={[...FORECAST_MARKET_STAGE_OPTIONS]}
                onChange={(value) => updateForecastImportField("market_stage", value)}
              />
            </Col>
            <Col xs={24} md={12} xl={5}>
              <Typography.Text type="secondary">Data mode</Typography.Text>
              <Select
                data-testid="forecast-import-data-mode"
                className="full-width"
                value={forecastImportForm.data_mode}
                options={[...FORECAST_DATA_MODE_OPTIONS]}
                onChange={(value) => updateForecastImportField("data_mode", value)}
              />
            </Col>
            <Col xs={24} md={12} xl={6}>
              <Typography.Text type="secondary">Price scope</Typography.Text>
              <Input
                data-testid="forecast-import-price-scope"
                value={forecastImportForm.price_scope}
                onChange={(event) => updateForecastImportField("price_scope", event.target.value)}
              />
            </Col>
            <Col xs={12} md={6} xl={4}>
              <Typography.Text type="secondary">Timezone</Typography.Text>
              <Input
                data-testid="forecast-import-timezone"
                value={forecastImportForm.timezone}
                onChange={(event) => updateForecastImportField("timezone", event.target.value)}
              />
            </Col>
            <Col xs={12} md={6} xl={4}>
              <Typography.Text type="secondary">Currency</Typography.Text>
              <Input
                data-testid="forecast-import-currency"
                value={forecastImportForm.currency}
                onChange={(event) => updateForecastImportField("currency", event.target.value)}
              />
            </Col>
            <Col xs={24} md={12} xl={6}>
              <Typography.Text type="secondary">Price unit</Typography.Text>
              <Input
                data-testid="forecast-import-price-unit"
                value={forecastImportForm.price_unit}
                onChange={(event) => updateForecastImportField("price_unit", event.target.value)}
              />
            </Col>
            <Col xs={24}>
              <Typography.Text type="secondary">Notes</Typography.Text>
              <Input.TextArea
                data-testid="forecast-import-notes"
                rows={2}
                value={forecastImportForm.notes}
                onChange={(event) => updateForecastImportField("notes", event.target.value)}
              />
            </Col>
          </Row>
          <Space wrap>
            <Tag>interval_minutes=15</Tag>
            <Tag>usage_scope=research_only</Tag>
            <Tag>no recommendation evidence</Tag>
            <Tag>no automatic trading</Tag>
          </Space>
          <Button
            data-testid="forecast-import-submit"
            type="primary"
            loading={submittingForecastImport}
            disabled={!forecastImportPreview || forecastImportPreview.errors.length > 0}
            onClick={() => void submitForecastImport()}
          >
            Import local research dataset
          </Button>
        </Space>
      </Card>
      <Card
        title={(
          <Space>
            Forecast Research
            {forecastOverview && <Tag color={statusColor(forecastOverview.status)}>{forecastOverview.status}</Tag>}
            <Tag>research_only</Tag>
          </Space>
        )}
        data-testid="forecast-research-dashboard"
      >
        {forecastError && <Alert type="warning" showIcon message={forecastError} />}
        {backtestError && (
          <Alert
            data-testid="forecast-backtest-error"
            type="warning"
            showIcon
            message={backtestError}
          />
        )}
        {forecastOverview ? (
          <Space orientation="vertical" className="full-width">
            <Row gutter={[16, 16]}>
              <Col xs={12} lg={4}>
                <Statistic title="Datasets" value={forecastOverview.dataset_count} />
              </Col>
              <Col xs={12} lg={4}>
                <Statistic title="Valid" value={forecastOverview.valid_dataset_count} />
              </Col>
              <Col xs={12} lg={4}>
                <Statistic title="Invalid" value={forecastOverview.invalid_dataset_count} />
              </Col>
              <Col xs={12} lg={4}>
                <Statistic title="Candidates" value={forecastOverview.candidate_model_run_count} />
              </Col>
              <Col xs={12} lg={4}>
                <Statistic title="BENCH regions" value={`${forecastOverview.bench_region_count}/5`} />
              </Col>
              <Col xs={12} lg={4}>
                <Statistic title="No trading" value={forecastOverview.no_auto_trading ? "yes" : "no"} />
              </Col>
            </Row>
            <Typography.Text data-testid="forecast-overview-status" type="secondary">
              {forecastOverview.message}
            </Typography.Text>
            <Space wrap>
              <Tag>{forecastOverview.recommendation_chain_isolated ? "recommendation isolated" : "check isolation"}</Tag>
              <Tag>{forecastOverview.network_probe_performed ? "network probe" : "no network probe"}</Tag>
              <Tag>{forecastOverview.fetch_performed ? "fetch performed" : "no fetch"}</Tag>
              {forecastOverview.bench_missing_regions.length > 0 && (
                <Tag color="gold">BENCH missing: {forecastOverview.bench_missing_regions.join(", ")}</Tag>
              )}
            </Space>
            <Select
              data-testid="forecast-dataset-select"
              className="full-width"
              value={selectedForecastDatasetId ?? undefined}
              placeholder="Select research dataset"
              onChange={setSelectedForecastDatasetId}
              options={forecastDatasets.map((dataset) => ({
                label: `${dataset.name} / ${dataset.region_code} / ${dataset.imported_at.slice(0, 10)}`,
                value: dataset.dataset_id,
              }))}
            />
            {reviewPackageError && (
              <Alert
                data-testid="forecast-review-package-error"
                type="warning"
                showIcon
                message={reviewPackageError}
              />
            )}
            {forecastReviewPackage && (
              <section data-testid="forecast-review-package">
                <Space orientation="vertical" className="full-width">
                  <Space wrap>
                    <Typography.Text strong>Review package</Typography.Text>
                    <Tag>{forecastReviewPackage.package_version}</Tag>
                    <Tag>{forecastReviewPackage.dataset.usage_scope}</Tag>
                    <Tag>{forecastReviewPackage.dataset.data_mode}</Tag>
                    <Tag>{forecastReviewPackage.no_auto_trading ? "no automatic trading" : "check trading flag"}</Tag>
                    <Tag>
                      {forecastReviewPackage.recommendation_chain_isolated
                        ? "recommendation isolated"
                        : "check isolation"}
                    </Tag>
                  </Space>
                  <Descriptions
                    size="small"
                    column={{ xs: 1, md: 2 }}
                    data-testid="forecast-review-package-summary"
                  >
                    <Descriptions.Item label="Dataset">
                      <Typography.Text code style={{ wordBreak: "break-all" }}>
                        {forecastReviewPackage.dataset.dataset_id}
                      </Typography.Text>
                    </Descriptions.Item>
                    <Descriptions.Item label="Quality">
                      <Space wrap>
                        <Tag color={forecastReviewPackage.dataset.quality_status === "valid" ? "green" : "gold"}>
                          {forecastReviewPackage.dataset.quality_status}
                        </Tag>
                        <Typography.Text>
                          {forecastReviewPackage.quality_issue_summary.total_count} issues
                        </Typography.Text>
                      </Space>
                    </Descriptions.Item>
                    <Descriptions.Item label="Content sha256">
                      <Typography.Text code style={{ wordBreak: "break-all" }}>
                        {forecastReviewPackage.dataset.content_sha256 ?? "-"}
                      </Typography.Text>
                    </Descriptions.Item>
                    <Descriptions.Item label="Recent import">
                      {forecastReviewPackage.import_runs[0]?.status ?? "none"}
                    </Descriptions.Item>
                    <Descriptions.Item label="Issue codes">
                      {formatCounts(forecastReviewPackage.quality_issue_summary.issue_code_counts)}
                    </Descriptions.Item>
                    <Descriptions.Item label="Severities">
                      {formatCounts(forecastReviewPackage.quality_issue_summary.severity_counts)}
                    </Descriptions.Item>
                    <Descriptions.Item label="Candidate models">
                      {forecastReviewPackage.model_runs.length}
                    </Descriptions.Item>
                    <Descriptions.Item label="Generated">
                      {forecastReviewPackage.generated_at.slice(0, 19)}
                    </Descriptions.Item>
                  </Descriptions>
                  <Space wrap>
                    <Tag>{forecastReviewPackage.network_probe_performed ? "network probe" : "no network probe"}</Tag>
                    <Tag>{forecastReviewPackage.fetch_performed ? "fetch performed" : "no fetch"}</Tag>
                    <Tag>
                      displayed issues {forecastReviewPackage.quality_issue_summary.displayed_issue_count}
                    </Tag>
                    <Button
                      data-testid="forecast-review-package-download"
                      icon={<DownloadOutlined />}
                      onClick={() => downloadReviewPackage(forecastReviewPackage)}
                    >
                      Download review package JSON
                    </Button>
                  </Space>
                </Space>
              </section>
            )}
            {selectedForecastDatasetId ? (
              <Row gutter={[16, 16]}>
                <Col xs={24} xl={12}>
                  <Space orientation="vertical" className="full-width">
                    <Space wrap>
                      <Button
                        data-testid="forecast-run-seasonal_naive"
                        loading={runningBacktest === "seasonal_naive"}
                        onClick={() => void runBacktest("seasonal_naive")}
                      >
                        Run seasonal_naive
                      </Button>
                      <Button
                        data-testid="forecast-run-calendar_mean"
                        loading={runningBacktest === "calendar_mean"}
                        onClick={() => void runBacktest("calendar_mean")}
                      >
                        Run calendar_mean
                      </Button>
                      <Tag>evaluation_days=3</Tag>
                      <Tag>lag_days=7</Tag>
                      <Tag>lookback_days=7</Tag>
                    </Space>
                    <List
                      data-testid="forecast-import-runs"
                      size="small"
                      header="Recent import runs"
                      dataSource={forecastImportRuns}
                      locale={{ emptyText: "No import runs for the selected dataset." }}
                      renderItem={(run) => (
                        <List.Item>
                          <Space wrap>
                            <Typography.Text code>{run.status}</Typography.Text>
                            <Tag>{run.quality_status}</Tag>
                            <Typography.Text type="secondary">
                              {run.completed_at.slice(0, 10)} / {run.normalized_point_count} points
                            </Typography.Text>
                          </Space>
                        </List.Item>
                      )}
                    />
                    <List
                      data-testid="forecast-quality-issues"
                      size="small"
                      header="Quality issues"
                      dataSource={forecastQualityIssues}
                      locale={{ emptyText: "No quality issues for the selected dataset." }}
                      renderItem={(issue) => (
                        <List.Item>
                          <Space orientation="vertical" size={2}>
                            <Space wrap>
                              <Tag color={issue.severity === "error" ? "red" : "gold"}>{issue.issue_code}</Tag>
                              <Typography.Text>{issue.message}</Typography.Text>
                            </Space>
                            <Typography.Text type="secondary">{issue.data_mode}</Typography.Text>
                          </Space>
                        </List.Item>
                      )}
                    />
                  </Space>
                </Col>
                <Col xs={24} xl={12}>
                  <Space orientation="vertical" className="full-width">
                    <List
                      data-testid="forecast-model-runs"
                      size="small"
                      header="Candidate model runs"
                      dataSource={forecastModelRuns}
                      locale={{ emptyText: "No candidate model runs yet." }}
                      renderItem={(run) => (
                        <List.Item
                          actions={[
                            <Button
                              key={run.model_run_id}
                              size="small"
                              onClick={() => setSelectedModelRunId(run.model_run_id)}
                            >
                              Show predictions
                            </Button>,
                          ]}
                        >
                          <List.Item.Meta
                            title={<Space>{run.model_key}<Tag>{run.registry_status}</Tag><Tag>{run.usage_scope}</Tag></Space>}
                            description={(
                              <Space wrap>
                                <Typography.Text>MAE {metricValue(run.metrics, "mae")}</Typography.Text>
                                <Typography.Text>RMSE {metricValue(run.metrics, "rmse")}</Typography.Text>
                                <Typography.Text>sMAPE {metricValue(run.metrics, "smape")}</Typography.Text>
                              </Space>
                            )}
                          />
                        </List.Item>
                      )}
                    />
                    {selectedModelRunId ? (
                      <ReactEChartsCore
                        data-testid="forecast-prediction-chart"
                        echarts={echarts}
                        option={forecastChart}
                        style={{ height: 280 }}
                      />
                    ) : (
                      <Empty description="Select a candidate run to inspect predictions." />
                    )}
                  </Space>
                </Col>
              </Row>
            ) : (
              <Empty description="No forecast research dataset selected." />
            )}
          </Space>
        ) : (
          <Empty description="Loading forecast research status." />
        )}
      </Card>
    </Space>
  );
}
