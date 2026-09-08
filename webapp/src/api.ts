import type {
  Brief,
  BriefDetail,
  BriefSummary,
  ForecastDataset,
  ForecastImportRun,
  ForecastModelRun,
  ForecastPoint,
  ForecastPrediction,
  ForecastQualityIssue,
  ForecastReviewPackage,
  ForecastResearchOverview,
  HydroOptimizationPayload,
  HydroOptimizationRun,
  KnowledgeChunk,
  KnowledgeCorpusOverview,
  KnowledgeDocumentDetail,
  KnowledgeDocument,
  KnowledgeDocumentReviewPackage,
  ManualForecastDatasetImportResult,
  ManualForecastDatasetPayload,
  MarketArtifactReviewPackage,
  MarketEndpoint,
  MarketIngestionRun,
  MarketRawArtifact,
  MarketSource,
  OperationJob,
  OperationActionCenter,
  OperationOverview,
  OperationsReviewPackage,
  PolicyWatchResponse,
  QuestionAnswer,
  HydroScenario,
  Recommendation,
  RecommendationAudit,
  RecommendationDecision,
  RecommendationDetail,
  RecommendationEvidenceExport,
  RecommendationFeedbackAnalytics,
  SystemReadiness,
  WeatherFeatureReviewPackage,
  WorkflowRun,
} from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) {
    throw new Error(`API request failed: ${response.status}`);
  }
  return (await response.json()) as T;
}

async function requestOptional<T>(path: string): Promise<T | null> {
  const response = await fetch(path);
  if (response.status === 404) {
    return null;
  }
  if (!response.ok) {
    throw new Error(`API request failed: ${response.status}`);
  }
  return (await response.json()) as T;
}

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
  latestBrief: () => requestOptional<Brief>("/v1/intelligence/briefs/latest"),
  briefs: async (limit = 20) =>
    (await request<{ items: BriefSummary[] }>(`/v1/intelligence/briefs?limit=${limit}`)).items,
  briefDetail: (briefId: string) => request<BriefDetail>(`/v1/intelligence/briefs/${briefId}`),
  generateBrief: () => request<Brief>("/v1/intelligence/briefs/generate", json({})),
  policyWatch: (limit = 5) =>
    request<PolicyWatchResponse>(`/v1/intelligence/policy-watch?limit=${limit}`),
  operationsOverview: () => request<OperationOverview>("/v1/operations/overview"),
  operationsReviewPackage: () =>
    request<OperationsReviewPackage>("/v1/operations/review-package"),
  systemReadiness: () => request<SystemReadiness>("/v1/system/readiness"),
  operationsActionCenter: () => request<OperationActionCenter>("/v1/operations/action-center"),
  jobs: async () => (await request<{ items: OperationJob[] }>("/v1/operations/jobs")).items,
  runs: async () => (await request<{ items: WorkflowRun[] }>("/v1/operations/runs?limit=8")).items,
  run: (workflowRunId: string) => request<WorkflowRun>(`/v1/operations/runs/${workflowRunId}`),
  queueJob: (jobKey: string) =>
    request<WorkflowRun>(`/v1/operations/jobs/${jobKey}/run`, { method: "POST" }),
  documents: async () => (await request<{ items: KnowledgeDocument[] }>("/v1/policy/documents")).items,
  policyCorpusOverview: () =>
    request<KnowledgeCorpusOverview>("/v1/policy/corpus/overview"),
  documentDetail: (documentId: string) =>
    request<KnowledgeDocumentDetail>(`/v1/policy/documents/${documentId}`),
  policyDocumentReviewPackage: (documentId: string) =>
    request<KnowledgeDocumentReviewPackage>(
      `/v1/policy/documents/${documentId}/review-package`,
    ),
  documentChunks: async (documentId: string) =>
    (await request<{ items: KnowledgeChunk[] }>(`/v1/policy/documents/${documentId}/chunks`)).items,
  sources: async () => (await request<{ items: MarketSource[] }>("/v1/market/sources")).items,
  endpoints: async () => (await request<{ items: MarketEndpoint[] }>("/v1/market/endpoints")).items,
  marketArtifacts: async () =>
    (await request<{ items: MarketRawArtifact[] }>("/v1/market/artifacts?limit=10")).items,
  marketArtifactReviewPackage: (artifactId: string) =>
    request<MarketArtifactReviewPackage>(
      `/v1/market/artifacts/${encodeURIComponent(artifactId)}/review-package`,
    ),
  marketIngestionRuns: async () =>
    (await request<{ items: MarketIngestionRun[] }>("/v1/market/ingestion/runs?limit=5")).items,
  importMarketArtifactToKnowledge: (artifactId: string) =>
    request<KnowledgeDocument>(`/v1/policy/documents/from-market-artifact/${artifactId}`, {
      method: "POST",
    }),
  reviewWeatherFeature: (featureSnapshotId: string, reviewStatus: string, note: string) =>
    request(`/v1/weather/features/${featureSnapshotId}/reviews`, json({
      review_status: reviewStatus,
      note,
    })),
  weatherFeatureReviewPackage: (featureSnapshotId: string) =>
    request<WeatherFeatureReviewPackage>(
      `/v1/weather/features/${encodeURIComponent(featureSnapshotId)}/review-package`,
    ),
  reviewMarketArtifact: (artifactId: string, reviewStatus: string, note: string) =>
    request(`/v1/market/artifacts/${artifactId}/reviews`, json({
      review_status: reviewStatus,
      note,
    })),
  reviewPolicyDocument: (documentId: string, reviewStatus: string, note: string) =>
    request(`/v1/policy/documents/${documentId}/reviews`, json({
      review_status: reviewStatus,
      note,
    })),
  authorizeDocument: (documentId: string, allowed: boolean) =>
    request(`/v1/policy/documents/${documentId}/external-processing-authorization`, json({
      external_processing_allowed: allowed,
      note: allowed ? "Authorized by local operator." : "Returned to local-only processing.",
    })),
  ask: (question: string, deep: boolean) =>
    request<QuestionAnswer>("/v1/intelligence/questions", json({
      question,
      analysis_mode: deep ? "deep" : "simple",
    })),
  upload: (form: FormData) => request<KnowledgeDocument>("/v1/policy/documents/upload", {
    method: "POST",
    body: form,
  }),
  datasets: async () =>
    (await request<{ items: ForecastDataset[] }>("/v1/forecasting/research/datasets")).items,
  createManualForecastDataset: (payload: ManualForecastDatasetPayload) =>
    request<ManualForecastDatasetImportResult>(
      "/v1/forecasting/research/datasets/manual",
      json(payload),
    ),
  forecastOverview: () =>
    request<ForecastResearchOverview>("/v1/forecasting/research/overview"),
  forecastImportRuns: async (datasetId?: string) => {
    const query = datasetId ? `?dataset_id=${encodeURIComponent(datasetId)}&limit=5` : "?limit=5";
    return (await request<{ items: ForecastImportRun[] }>(
      `/v1/forecasting/research/import-runs${query}`,
    )).items;
  },
  forecastQualityIssues: async (datasetId?: string) => {
    const query = datasetId ? `?dataset_id=${encodeURIComponent(datasetId)}&limit=5` : "?limit=5";
    return (await request<{ items: ForecastQualityIssue[] }>(
      `/v1/forecasting/research/quality/issues${query}`,
    )).items;
  },
  forecastReviewPackage: (datasetId: string) =>
    request<ForecastReviewPackage>(
      `/v1/forecasting/research/datasets/${encodeURIComponent(datasetId)}/review-package`,
    ),
  forecastModelRuns: async (datasetId?: string) => {
    const query = datasetId ? `?dataset_id=${encodeURIComponent(datasetId)}&limit=8` : "?limit=8";
    return (await request<{ items: ForecastModelRun[] }>(
      `/v1/forecasting/research/model-runs${query}`,
    )).items;
  },
  forecastPredictions: async (modelRunId: string) =>
    (await request<{ items: ForecastPrediction[] }>(
      `/v1/forecasting/research/model-runs/${modelRunId}/predictions?limit=500`,
    )).items,
  runForecastBacktest: (
    datasetId: string,
    modelKey: "seasonal_naive" | "calendar_mean",
  ) => request<ForecastModelRun>(
    `/v1/forecasting/research/datasets/${datasetId}/backtests`,
    json({
      model_key: modelKey,
      evaluation_days: 3,
      lag_days: 7,
      lookback_days: 7,
    }),
  ),
  points: async (datasetId: string) =>
    (await request<{ items: ForecastPoint[] }>(`/v1/forecasting/research/datasets/${datasetId}/points?limit=192`)).items,
  scenario: () => request<HydroScenario>("/v1/scenarios/demo_hydro/default"),
  runHydroOptimization: (payload: HydroOptimizationPayload) =>
    request<HydroOptimizationRun>("/v1/scenarios/demo_hydro/optimization-runs", json(payload)),
  recentHydroOptimizations: async () =>
    (await request<{ items: HydroOptimizationRun[] }>(
      "/v1/scenarios/demo_hydro/optimization-runs/recent?limit=5",
    )).items,
  recentRecommendations: async () =>
    (await request<{ items: Recommendation[] }>("/v1/recommendations/recent?limit=12")).items,
  recommendation: (recommendationId: string) =>
    request<RecommendationDetail>(`/v1/recommendations/${recommendationId}`),
  recommendationAudit: (recommendationId: string) =>
    request<RecommendationAudit>(`/v1/recommendations/${recommendationId}/audit`),
  recommendationEvidenceExport: (recommendationId: string) =>
    request<RecommendationEvidenceExport>(
      `/v1/recommendations/${recommendationId}/evidence-export`,
    ),
  recommendationDecisions: async (recommendationId: string) =>
    (await request<{ items: RecommendationDecision[] }>(
      `/v1/recommendations/${recommendationId}/decisions`,
    )).items,
  recommendationFeedbackAnalytics: (limit = 10) =>
    request<RecommendationFeedbackAnalytics>(`/v1/recommendations/feedback/overview?limit=${limit}`),
  createRecommendationDecision: (
    recommendationId: string,
    payload: {
      decision_status: RecommendationDecision["decision_status"];
      selected_windows: string[];
      note: string;
      safety_boundary_acknowledged: boolean;
    },
  ) => request<RecommendationDecision>(`/v1/recommendations/${recommendationId}/decisions`, json(payload)),
  createRecommendationDecisionFeedback: (
    decisionId: string,
    payload: {
      outcome_status: RecommendationDecision["feedback"][number]["outcome_status"];
      observed_at: string | null;
      note: string;
    },
  ) => request(`/v1/recommendations/decisions/${decisionId}/feedback`, json(payload)),
  runRecommendation: (tradeDate: string) =>
    request<Recommendation>("/v1/recommendations/run", json({ trade_date: tradeDate })),
  reviewRecommendation: (recommendationId: string, reviewStatus: string, note: string) =>
    request(`/v1/recommendations/${recommendationId}/reviews`, json({
      review_status: reviewStatus,
      note,
    })),
  reviewBrief: (briefId: string, reviewStatus: "approved" | "needs_revision", note: string) =>
    request(`/v1/intelligence/briefs/${briefId}/reviews`, json({
      review_status: reviewStatus,
      note,
    })),
};
