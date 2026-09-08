// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { App } from "./App";
import { nextPollDelayMilliseconds } from "./operationPolling";
import type { OperationTodoItem } from "./types";

const policyJob = {
  job_key: "policy_research_refresh",
  description: "Refresh reviewed policy research sources",
  schedule: "0 */6 * * *",
  timezone: "Asia/Shanghai",
  research_only: false,
  manual_trigger_enabled: true,
};

const demoSeedJob = {
  job_key: "demo_research_workspace_seed",
  description: "Seed local deterministic demo data for the v0.1 RC checklist.",
  schedule: "manual",
  timezone: "Asia/Shanghai",
  research_only: false,
  manual_trigger_enabled: true,
};

const queuedRun = {
  workflow_run_id: "workflow_test",
  workflow_key: "policy_research_refresh",
  scheduled_for: null,
  status: "queued",
  started_at: "2026-06-02T08:00:00+08:00",
  available_at: "2026-06-02T08:00:00+08:00",
  claimed_at: null,
  lease_expires_at: null,
  worker_id: null,
  attempt_count: 0,
  completed_at: null,
  summary: {},
  error_code: null,
  error_message: null,
};

const failedRun = {
  ...queuedRun,
  workflow_run_id: "workflow_failed",
  status: "failed",
  attempt_count: 1,
  completed_at: "2026-06-02T08:02:00+08:00",
  summary: { message: "Adapter missing." },
  error_code: "policy_collection_adapter_not_registered",
  error_message: "adapter missing",
};

const marketIngestionRun = {
  ingestion_run_id: "market_ingest_test",
  source_id: "example_electricity_council",
  endpoint_id: "council_home",
  trigger_mode: "registered_collection",
  adapter_key: "registered_static_http:v1",
  adapter_version: "1",
  started_at: "2026-06-02T08:00:00+08:00",
  completed_at: "2026-06-02T08:00:01+08:00",
  status: "succeeded",
  items_received: 1,
  items_inserted: 1,
  duplicate_items: 0,
  rejected_items: 0,
  quality_status: "valid",
  quality_issue_count: 0,
  error_code: null,
  error_message: null,
};

const marketIngestionRunResponse = { items: [marketIngestionRun] };

const marketArtifact = {
  artifact_id: "market_artifact_policy",
  source_id: "southern_energy_regulator",
  endpoint_id: "southern_regulator_downloads",
  source_url: "https://policy.example.invalid/hdhy/zlxz/policy.html",
  title: "Official policy page",
  media_type: "text/html",
  storage_backend: "postgres_inline",
  inline_text: "<html><body>policy body</body></html>",
  object_key: null,
  content_sha256: "a".repeat(64),
  byte_length: 37,
  published_at: "2026-06-02T08:00:00+08:00",
  captured_at: "2026-06-02T08:00:00+08:00",
  ingestion_method: "registered_collection",
  transport_security_status: "tls_verified_source_url",
  human_review_status: "pending_review",
  data_mode: "public_observed",
};

const rejectedMarketArtifact = {
  ...marketArtifact,
  artifact_id: "market_artifact_rejected",
  title: "BENCH research benchmark",
  source_id: "bench_dispatch_research",
  endpoint_id: "bench_dispatch_archive",
  content_sha256: "b".repeat(64),
};

const importedKnowledgeDocument = {
  document_id: "knowledge_policy",
  title: "Official policy page",
  document_layer: "official_policy",
  trust_tier: "official",
  source_name: "Example Energy Regulator / Southern regulator public downloads",
  source_url: "https://policy.example.invalid/hdhy/zlxz/policy.html",
  media_type: "text/html",
  captured_at: "2026-06-02T08:00:00+08:00",
  external_processing_allowed: false,
  human_review_status: "pending_review",
  data_mode: "public_observed",
};

const policyCorpusOverview = {
  generated_at: "2026-06-02T08:05:00+08:00",
  status: "healthy",
  message: "Policy corpus is indexed with local chunks and embeddings.",
  document_count: 1,
  version_count: 1,
  chunk_count: 2,
  embedded_chunk_count: 2,
  embedding_coverage: 1,
  external_processing_allowed_count: 0,
  external_processing_blocked_count: 1,
  artifact_provenance_count: 1,
  layers: [
    {
      document_layer: "official_policy",
      document_count: 1,
      chunk_count: 2,
      embedded_chunk_count: 2,
      embedding_coverage: 1,
      external_processing_allowed_count: 0,
      latest_captured_at: "2026-06-02T08:00:00+08:00",
    },
  ],
  recent_documents: [importedKnowledgeDocument],
  network_probe_performed: false,
  fetch_performed: false,
  no_auto_trading: true,
};

const importedKnowledgeDocumentDetail = {
  ...importedKnowledgeDocument,
  published_at: null,
  effective_at: null,
  external_processing_allowed_default: false,
  latest_version: {
    version_id: "knowledge_version_policy",
    version_number: 1,
    content_sha256: "a".repeat(64),
    parser_key: "html_text",
    raw_object_id: "raw_policy",
    parsed_character_count: 24,
    created_at: "2026-06-02T08:00:01+08:00",
  },
  raw_object: {
    raw_object_id: "raw_policy",
    content_sha256: "a".repeat(64),
    storage_backend: "minio",
    bucket_name: "eee-research",
    object_key: "raw/aa/a",
    media_type: "text/html",
    byte_length: 37,
    source_url: "https://policy.example.invalid/hdhy/zlxz/policy.html",
    captured_at: "2026-06-02T08:00:00+08:00",
    data_mode: "public_observed",
  },
  chunk_count: 2,
  embedded_chunk_count: 2,
  embedding_coverage: 1,
  artifact_provenance: [
    {
      artifact_id: "market_artifact_policy",
      artifact_content_sha256: "a".repeat(64),
      artifact_captured_at: "2026-06-02T08:00:00+08:00",
      source_id: "southern_energy_regulator",
      source_name: "Example Energy Regulator",
      source_trust_tier: "official",
      source_market_scope: "southern_regional_policy",
      endpoint_id: "southern_regulator_downloads",
      endpoint_name: "Southern regulator public downloads",
      endpoint_kind: "html_listing",
      endpoint_data_granularity: "policy_documents",
      source_url: "https://policy.example.invalid/hdhy/zlxz/policy.html",
    },
  ],
  raw_download_available: false,
};

const questionAnswer = {
  question_run_id: "question_policy",
  answer: "Evidence-backed policy answer.",
  citations: [
    {
      document_id: "knowledge_policy",
      chunk_id: "chunk_1",
      title: "Official policy page",
      source_name: "Example Energy Regulator / Southern regulator public downloads",
      source_url: "https://policy.example.invalid/hdhy/zlxz/policy.html",
      document_layer: "official_policy",
      data_mode: "public_observed",
    },
  ],
  missing_information: [],
  retrieved_chunk_ids: ["chunk_1"],
  excluded_restricted_chunks: 1,
  confidence_score: 0.45,
  human_review_required: true,
  llm_used: true,
  llm_model: "deepseek-v4-flash",
};

const policyWatchItem = {
  watch_id: "chunk_policy_watch",
  title: "Official policy page",
  observation: "Official policy evidence for operator review.",
  excerpt: "policy body for local deterministic watch",
  citation: {
    document_id: "knowledge_policy",
    chunk_id: "chunk_policy_watch",
    title: "Official policy page",
    source_name: "Example Energy Regulator",
    source_url: "https://policy.example.invalid/hdhy/zlxz/policy.html",
    document_layer: "official_policy",
    data_mode: "public_observed",
  },
  captured_at: "2026-06-02T08:00:00+08:00",
  source_role: "official_policy",
  external_processing_allowed: false,
  score: 0.84,
};

const generatedBrief = {
  brief_id: "brief_policy_watch",
  target_date: "2026-06-02",
  generated_at: "2026-06-02T08:30:00+08:00",
  status: "draft",
  human_review_status: "pending_review",
  risk_level: "medium",
  confidence_score: 0.45,
  deterministic_facts: {
    workflow_failure_count: 0,
    market_quality_issue_count: 0,
    policy_watch: {
      item_count: 1,
      excluded_restricted_chunks: 1,
      items: [policyWatchItem],
      local_only: true,
    },
    bench_dispatch_benchmark: {
      usage_scope: "research_only",
      included_in_example_province_recommendations: false,
    },
  },
  narrative: {
    summary: "Deterministic local brief generated for operator review.",
    policy_watch: [],
  },
  citations: [policyWatchItem.citation],
  policy_watch: [policyWatchItem],
  missing_information: [],
  llm_used: false,
  llm_model: null,
  no_auto_trading: true,
};

const approvedBriefReview = {
  review_id: "brief_review_approved",
  brief_id: "brief_policy_watch",
  actor: "local_operator",
  review_status: "approved",
  note: "Reviewed policy watch and missing information.",
  created_at: "2026-06-02T08:40:00+08:00",
};

const generatedBriefDetail = {
  ...generatedBrief,
  reviews: [],
};

const reviewedBriefDetail = {
  ...generatedBrief,
  human_review_status: "approved",
  reviews: [approvedBriefReview],
};

const briefSummary = {
  brief_id: "brief_policy_watch",
  target_date: "2026-06-02",
  generated_at: "2026-06-02T08:30:00+08:00",
  human_review_status: "pending_review",
  risk_level: "medium",
  confidence_score: 0.45,
  policy_watch_count: 1,
  missing_information_count: 0,
  llm_used: false,
  no_auto_trading: true,
};

const forecastDataset = {
  dataset_id: "forecast_dataset_test",
  name: "Simulated 15-minute research curve",
  source_name: "Test scenario generator",
  source_url: "https://example.invalid/scenarios/interval-price-v1.json",
  region_code: "TEST",
  region_name: "Explicit simulated test region",
  market_scope: "research_fixture",
  market_stage: "day_ahead",
  price_scope: "regional_reference_price",
  interval_minutes: 15,
  timezone: "Asia/Shanghai",
  currency: "CNY",
  price_unit: "CNY_per_MWh",
  data_mode: "scenario_simulated",
  usage_scope: "research_only",
  content_sha256: "c".repeat(64),
  imported_at: "2026-06-02T08:00:00+08:00",
  quality_status: "valid",
  quality_issue_count: 0,
  normalized_point_count: 1440,
  trade_date_count: 15,
  notes: "Synthetic research fixture only.",
};

const forecastModelRun = {
  model_run_id: "forecast_model_seasonal",
  dataset_id: "forecast_dataset_test",
  model_key: "seasonal_naive",
  model_version: "v1",
  feature_version: "interval_price_v1",
  started_at: "2026-06-02T08:10:00+08:00",
  completed_at: "2026-06-02T08:10:01+08:00",
  status: "succeeded",
  registry_status: "candidate",
  train_start: "2026-01-01",
  train_end: "2026-01-12",
  evaluation_start: "2026-01-13",
  evaluation_end: "2026-01-15",
  horizon_intervals: 96,
  parameters: { evaluation_days: 3, lag_days: 7 },
  metrics: { mae: 1.25, rmse: 1.5, smape: 0.012, prediction_count: 288 },
  artifact_path: null,
  usage_scope: "research_only",
  data_mode: "public_derived",
  error_code: null,
  error_message: null,
};

const forecastOverview = {
  generated_at: "2026-06-02T08:12:00+08:00",
  status: "healthy",
  message: "Forecast research datasets and candidate model runs are available for review.",
  dataset_count: 1,
  valid_dataset_count: 1,
  invalid_dataset_count: 0,
  research_only_dataset_count: 1,
  candidate_model_run_count: 1,
  succeeded_model_run_count: 1,
  bench_expected_regions: ["NSW1", "QLD1", "SA1", "TAS1", "VIC1"],
  bench_available_regions: [],
  bench_missing_regions: [],
  bench_region_count: 0,
  datasets: [forecastDataset],
  recent_import_runs: [
    {
      import_run_id: "forecast_import_test",
      dataset_id: "forecast_dataset_test",
      started_at: "2026-06-02T08:00:00+08:00",
      completed_at: "2026-06-02T08:00:01+08:00",
      status: "accepted",
      submitted_point_count: 1440,
      normalized_point_count: 1440,
      quality_status: "valid",
      quality_issue_count: 0,
      data_mode: "scenario_simulated",
      error_code: null,
      error_message: null,
    },
  ],
  recent_model_runs: [forecastModelRun],
  recent_quality_issues: [],
  no_auto_trading: true,
  recommendation_chain_isolated: true,
  network_probe_performed: false,
  fetch_performed: false,
};

const forecastReviewPackage = {
  package_version: "forecast_research_review_package_v1",
  generated_at: "2026-06-02T08:12:30+08:00",
  dataset: forecastDataset,
  import_runs: forecastOverview.recent_import_runs,
  quality_issue_summary: {
    total_count: 0,
    severity_counts: {},
    issue_code_counts: {},
    displayed_issue_count: 0,
  },
  quality_issues: [],
  model_runs: [forecastModelRun],
  no_auto_trading: true,
  recommendation_chain_isolated: true,
  network_probe_performed: false,
  fetch_performed: false,
};

const uploadedForecastDataset = {
  ...forecastDataset,
  dataset_id: "forecast_dataset_uploaded",
  name: "operator_curve",
  data_mode: "user_uploaded",
  content_sha256: "d".repeat(64),
  normalized_point_count: 2,
  trade_date_count: 1,
};

const uploadedForecastReviewPackage = {
  ...forecastReviewPackage,
  generated_at: "2026-06-02T09:00:02+08:00",
  dataset: uploadedForecastDataset,
  import_runs: [
    {
      import_run_id: "forecast_import_uploaded",
      dataset_id: "forecast_dataset_uploaded",
      started_at: "2026-06-02T09:00:00+08:00",
      completed_at: "2026-06-02T09:00:01+08:00",
      status: "accepted",
      submitted_point_count: 2,
      normalized_point_count: 2,
      quality_status: "valid",
      quality_issue_count: 0,
      data_mode: "user_uploaded",
      error_code: null,
      error_message: null,
    },
  ],
  model_runs: [],
};

let marketArtifactsShouldFail = false;
let corpusOverviewShouldFail = false;
let documentDetailShouldFail = false;
let recommendationAuditShouldFail = false;
let recommendationEvidenceExportShouldFail = false;
let recommendationDecisionShouldFail = false;
let forecastBacktestShouldFail = false;
let briefGenerated = false;
let briefReviewed = false;
let recommendationGenerated = false;
let recommendationReviewed = false;
let recommendationDecisionCreated = false;
let recommendationFeedbackCreated = false;
let recommendationFeedbackAnalyticsShouldFail = false;
let hydroOptimizationCreated = false;
let hydroOptimizationUsedPriceSignal = false;
let operationActionCenterShouldFail = false;
let actionCenterReviewShouldFail = false;
let weatherFeatureReviewed = false;
let marketArtifactReviewed = false;
let policyDocumentReviewed = false;
let forecastManualImportShouldFail = false;

const recommendationEvidence = [
  {
    source: "Demo Hydro A scenario pack",
    source_type: "scenario_input",
    data_mode: "scenario_simulated",
    timestamp: "2026-06-02T08:00:00+08:00",
    field: "available_energy_mwh",
    value: 4200,
    unit: "MWh",
    confidence: 0.55,
    url: null,
    note: "Synthetic operator-lab scenario input.",
  },
];

const generatedRecommendation = {
  recommendation_id: "rec_sim",
  input_snapshot_id: "snapshot_sim",
  trade_date: "2026-06-02",
  created_at: "2026-06-02T09:00:00+08:00",
  asset_id: "demo_hydro_a",
  data_mode: "scenario_simulated",
  scenario_id: "demo_hydro_a_normal_storage_normal_inflow_v1",
  weather_feature_snapshot_id: null,
  horizon: "day_ahead",
  market_view: "Simulated spot volatility requires operator review.",
  hydro_action: "Hold flexible generation for evening intervals.",
  risk_level: "medium",
  confidence: 0.42,
  review_status: "pending_review",
  recommended_windows: [
    {
      time: "18:00-20:00",
      stance: "conserve",
      reason: "Synthetic reservoir and market assumptions are incomplete.",
    },
  ],
  missing_data_warnings: [
    "Internal reservoir telemetry is missing.",
    "Approved public-derived weather feature snapshot is not linked.",
  ],
  evidence: recommendationEvidence,
  human_check_required: true,
  no_auto_trading: true,
};

const hydroOptimizationRun = {
  optimization_run_id: "hydro_opt_sim",
  created_at: "2026-06-02T09:05:00+08:00",
  trade_date: "2026-06-02",
  asset_id: "demo_hydro_a",
  scenario_id: "demo_hydro_a_normal_storage_normal_inflow_v1",
  algorithm_key: "deterministic_priority_v1",
  data_mode: "scenario_simulated",
  energy_budget_mwh: 4200,
  min_output_mw: 120,
  max_output_mw: 600,
  price_signal_used: false,
  intervals: [
    {
      interval_index: 1,
      interval_start: "2026-06-02T00:00:00+08:00",
      target_output_mw: 175,
      energy_mwh: 43.75,
      price_signal: null,
      priority_rank: null,
      binding_constraints: ["constraint_only_balance"],
    },
  ],
  top_priority_intervals: [
    {
      interval_index: 1,
      interval_start: "2026-06-02T00:00:00+08:00",
      target_output_mw: 175,
      energy_mwh: 43.75,
      price_signal: null,
      priority_rank: null,
      binding_constraints: ["constraint_only_balance"],
    },
  ],
  missing_data_warnings: [
    "尚未接入经过核验的示例甲省现货 96 点价格曲线；本次按约束均衡分配。",
  ],
  constraint_explanation: [
    "No price signal supplied: the run used a constraint-only balanced allocation.",
    "This preview remains scenario_simulated, requires human review, and does not execute or submit trades.",
  ],
  evidence: recommendationEvidence,
  request_snapshot: {},
  constraints: { recommendation_chain_isolated: true },
  human_review_required: true,
  no_auto_trading: true,
};

const hydroOptimizationPriceRun = {
  ...hydroOptimizationRun,
  optimization_run_id: "hydro_opt_price",
  price_signal_used: true,
  top_priority_intervals: [
    {
      interval_index: 96,
      interval_start: "2026-06-02T23:45:00+08:00",
      target_output_mw: 600,
      energy_mwh: 150,
      price_signal: "196",
      priority_rank: 1,
      binding_constraints: ["installed_capacity_ceiling"],
    },
  ],
  missing_data_warnings: [
    "价格信号是本地预演输入，未被标记为核验后的示例甲省现货价格序列。",
  ],
  constraint_explanation: [
    "Price signal supplied: 96 user_uploaded interval prices were ranked from highest to lowest before assigning energy above the minimum output.",
    "This preview remains scenario_simulated, requires human review, and does not execute or submit trades.",
  ],
  evidence: [
    ...recommendationEvidence,
    {
      source: "local_hydro_price_signal_input",
      source_type: "operator_uploaded_price_curve",
      data_mode: "user_uploaded",
      timestamp: "2026-06-02T09:05:00+08:00",
      field: "price_signal_96_point_curve",
      value: "96 intervals supplied",
      unit: "CNY/MWh",
      confidence: 0.5,
      url: null,
      note: "Operator-supplied local preview curve.",
    },
  ],
};

const approvedRecommendationReview = {
  review_id: "rec_review_approved",
  recommendation_id: "rec_sim",
  actor: "local_operator",
  review_status: "approved",
  note: "Reviewed audit and scenario assumptions.",
  created_at: "2026-06-02T09:10:00+08:00",
};

const recommendationAudit = {
  recommendation_id: "rec_sim",
  generated_at: "2026-06-02T09:00:00+08:00",
  audited_at: "2026-06-02T09:00:02+08:00",
  review_status: "pending_review",
  overall_status: "warning",
  evidence_summary: {
    evidence_count: 1,
    missing_data_count: 2,
    data_modes: { scenario_simulated: 1 },
    source_types: { scenario_input: 1 },
    weather_evidence_present: false,
    incomplete_evidence_count: 0,
    research_only_evidence_count: 0,
    bench_evidence_count: 0,
    policy_watch_evidence_count: 0,
  },
  checks: [
    {
      key: "no_auto_trading",
      label: "No Automatic Trading",
      status: "healthy",
      message: "Recommendation explicitly disables automatic trading.",
      details: { no_auto_trading: true },
    },
    {
      key: "human_review_required",
      label: "Human Review Required",
      status: "healthy",
      message: "Recommendation requires human review.",
      details: { human_check_required: true },
    },
    {
      key: "recommendation_chain_isolation",
      label: "Recommendation Chain Isolation",
      status: "healthy",
      message: "Recommendation evidence is isolated from BENCH, research_only, and policy watch.",
      details: {
        research_only_evidence_count: 0,
        bench_evidence_count: 0,
        policy_watch_evidence_count: 0,
      },
    },
    {
      key: "weather_context",
      label: "Weather Context",
      status: "warning",
      message: "No approved public-derived weather feature evidence is linked.",
      details: {
        weather_feature_snapshot_id: null,
        weather_evidence_present: false,
      },
    },
  ],
  recommended_actions: [
    "Review missing internal reservoir, contract, and Example Province spot data warnings.",
    "Optionally link an approved public-derived weather feature snapshot.",
  ],
  human_check_required: true,
  no_auto_trading: true,
};

const recommendationEvidenceExport = {
  recommendation_id: "rec_sim",
  input_snapshot_id: "snapshot_sim",
  trade_date: "2026-06-02",
  asset_id: "demo_hydro_a",
  scenario_id: "demo_hydro_a_normal_storage_normal_inflow_v1",
  generated_at: "2026-06-02T09:00:00+08:00",
  exported_at: "2026-06-02T09:00:03+08:00",
  review_status: "pending_review",
  audit_status: "warning",
  data_mode: "scenario_simulated",
  risk_level: "medium",
  confidence: 0.42,
  human_check_required: true,
  no_auto_trading: true,
  missing_data_warnings: generatedRecommendation.missing_data_warnings,
  evidence_summary: recommendationAudit.evidence_summary,
  checks: recommendationAudit.checks,
  recommended_actions: recommendationAudit.recommended_actions,
  evidence: recommendationEvidence,
};

const recommendationDecisionFeedback = {
  feedback_id: "feedback_sim",
  decision_id: "decision_sim",
  recommendation_id: "rec_sim",
  created_at: "2026-06-02T09:20:00+08:00",
  actor: "local_operator",
  outcome_status: "useful",
  observed_at: "2026-06-03",
  note: "Follow-up observation was useful.",
  data_mode: "user_uploaded",
};

const recommendationDecision = {
  decision_id: "decision_sim",
  recommendation_id: "rec_sim",
  created_at: "2026-06-02T09:15:00+08:00",
  actor: "local_operator",
  decision_status: "deferred",
  selected_windows: ["18:00-20:00"],
  note: "Keep as local decision support only.",
  safety_boundary_acknowledged: true,
  no_auto_trading: true,
  audit_snapshot: recommendationAudit,
  feedback: [],
};

const recommendationFeedbackAnalyticsDecision = {
  decision_id: "decision_sim",
  recommendation_id: "rec_sim",
  created_at: "2026-06-02T09:15:00+08:00",
  actor: "local_operator",
  decision_status: "deferred",
  audit_status: "warning",
  selected_windows: ["18:00-20:00"],
  note: "Keep as local decision support only.",
  no_auto_trading: true,
  safety_boundary_acknowledged: true,
  feedback_count: recommendationFeedbackCreated ? 1 : 0,
  latest_outcome_status: recommendationFeedbackCreated ? "useful" : null,
  latest_feedback_at: recommendationFeedbackCreated ? "2026-06-02T09:20:00+08:00" : null,
};

function recommendationFeedbackAnalyticsResponse() {
  const decisionItems = recommendationDecisionCreated
    ? [{
      ...recommendationFeedbackAnalyticsDecision,
      feedback_count: recommendationFeedbackCreated ? 1 : 0,
      latest_outcome_status: recommendationFeedbackCreated ? "useful" : null,
      latest_feedback_at: recommendationFeedbackCreated ? "2026-06-02T09:20:00+08:00" : null,
    }]
    : [];
  return {
    generated_at: "2026-06-02T09:25:00+08:00",
    status: !recommendationDecisionCreated || !recommendationFeedbackCreated ? "warning" : "healthy",
    message: recommendationDecisionCreated
      ? "Recommendation feedback records have no pending analytics warnings."
      : "No local recommendation decisions have been recorded yet.",
    summary: {
      recommendation_count: recommendationGenerated ? 1 : 0,
      decision_count: recommendationDecisionCreated ? 1 : 0,
      feedback_count: recommendationFeedbackCreated ? 1 : 0,
      pending_observation_count: recommendationDecisionCreated && !recommendationFeedbackCreated ? 1 : 0,
      critical_audit_not_adopted_count: 0,
      no_auto_trading_false_count: 0,
      safety_boundary_unacknowledged_count: 0,
      audit_status_counts: recommendationGenerated ? { warning: 1 } : {},
      review_status_counts: recommendationGenerated
        ? { [recommendationReviewed ? "approved" : "pending_review"]: 1 }
        : {},
      decision_status_counts: recommendationDecisionCreated ? { deferred: 1 } : {},
      outcome_status_counts: recommendationFeedbackCreated ? { useful: 1 } : {},
      feedback_data_modes: recommendationFeedbackCreated ? { user_uploaded: 1 } : {},
    },
    recent_decisions: decisionItems,
    recent_feedback: recommendationFeedbackCreated ? [{
      feedback_id: "feedback_sim",
      decision_id: "decision_sim",
      recommendation_id: "rec_sim",
      created_at: "2026-06-02T09:20:00+08:00",
      actor: "local_operator",
      decision_status: "deferred",
      outcome_status: "useful",
      observed_at: "2026-06-03",
      note: "Follow-up observation was useful.",
      data_mode: "user_uploaded",
    }] : [],
    pending_observation_decisions: recommendationDecisionCreated && !recommendationFeedbackCreated
      ? decisionItems
      : [],
    critical_audit_not_adopted: [],
    recommended_actions: recommendationDecisionCreated && !recommendationFeedbackCreated
      ? ["Add follow-up feedback for decisions still pending observation."]
      : ["No feedback follow-up is required beyond normal operator review."],
    no_auto_trading: true,
  };
}

const operationsOverview = {
  generated_at: "2026-06-02T08:05:00+08:00",
  overall_status: "critical",
  workflow_overview: {
    counts: { queued: 0, running: 0, retry_wait: 0, succeeded: 0, skipped: 0, failed: 1 },
    queued: 0,
    running: 0,
    retry_wait: 0,
    failed: 1,
    stale_lease_count: 0,
    failed_last_24h: 1,
    status: "critical",
  },
  freshness: [
    {
      key: "weather_features",
      label: "Weather Features",
      status: "warning",
      message: "Weather feature snapshot is older than 18 hours.",
      latest_at: "2026-06-01T08:00:00+08:00",
      age_hours: 32,
      data_mode: "public_derived",
      research_only: false,
      details: {},
    },
    {
      key: "bench_dispatch_research",
      label: "BENCH Dispatch Research Benchmark",
      status: "healthy",
      message: "BENCH research benchmark has all five regions within 48 hours.",
      latest_at: "2026-06-02T09:30:00+08:00",
      age_hours: 6,
      data_mode: "public_observed",
      research_only: true,
      details: { usage_scope: "research_only", recommendation_chain_isolated: true },
    },
  ],
  health: [
    {
      key: "source_registry",
      label: "Source Registry",
      status: "healthy",
      message: "Registered source endpoints are present.",
      observed_at: null,
      details: { source_count: 4, disabled_count: 4, manual_only_count: 1 },
    },
    {
      key: "endpoint_health",
      label: "Endpoint Health Records",
      status: "healthy",
      message: "No endpoint health records are stored; overview did not run a probe.",
      observed_at: null,
      details: { network_probe_performed: false },
    },
  ],
  actions: [policyJob, demoSeedJob],
  recent_runs: [failedRun],
  recent_incidents: [failedRun],
  no_auto_trading: true,
};

let demoSeeded = false;

function systemReadinessResponse() {
  const missing = demoSeeded
    ? []
    : [
      "weather_snapshot",
      "market_artifact",
      "policy_document",
      "brief",
      "recommendation",
      "decision_feedback",
      "forecast_dataset",
      "forecast_model_run",
    ];
  return {
    generated_at: "2026-06-02T08:06:00+08:00",
    status: "warning",
    checks: [
      {
        key: "demo_seed",
        label: "Demo Seed Coverage",
        status: demoSeeded ? "healthy" : "warning",
        message: demoSeeded
          ? "Demo seed objects are present."
          : "Demo seed is incomplete; run the fixed demo seed job.",
        details: { missing },
      },
      {
        key: "recommendation_isolation",
        label: "Recommendation Evidence Isolation",
        status: "healthy",
        message: "Recommendation evidence is isolated from BENCH, research_only, and policy_watch.",
        details: { violating_recommendation_ids: [] },
      },
      {
        key: "forecast_research",
        label: "Forecast Research",
        status: "healthy",
        message: "Forecast research dataset and candidate model run are available.",
        details: { usage_scope: "research_only" },
      },
    ],
    demo_seed: {
      seed_key: "mvp_rc_demo_v1",
      created: {
        weather_snapshot: false,
        market_artifact: false,
        policy_document: false,
        brief: false,
        recommendation: false,
        forecast_dataset: false,
      },
      object_ids: demoSeeded
        ? {
          weather_feature_snapshot_id: "demo_rc_weather_features",
          policy_document_id: "demo_rc_policy_document",
          recommendation_id: "demo_rc_recommendation",
          forecast_dataset_id: "demo_rc_forecast_dataset",
        }
        : {},
      data_modes: {
        weather: "public_derived",
        market_artifact: "user_uploaded",
        policy_document: "user_uploaded",
        recommendation: "scenario_simulated",
        forecast_dataset: "scenario_simulated",
      },
      research_only: true,
      no_auto_trading: true,
    },
    table_counts: {
      weather_feature_snapshots: demoSeeded ? 1 : 0,
      knowledge_documents: demoSeeded ? 1 : 0,
      recommendation_runs: demoSeeded ? 1 : 0,
      forecast_research_datasets: demoSeeded ? 1 : 0,
    },
    missing_demo_items: missing,
    recommended_actions: missing.length
      ? ["Run fixed job demo_research_workspace_seed to populate local RC fixtures."]
      : ["Review Action Center items and complete normal human review steps."],
    no_auto_trading: true,
  };
}

const reviewTodoFields = {
  allowed_review_statuses: [],
  default_review_note: null,
  review_target_type: null,
};

function operationActionCenterResponse() {
  const baseItems: OperationTodoItem[] = [
    {
      item_id: "workflow:workflow_failed",
      category: "workflow",
      severity: "critical",
      title: "Workflow failed: policy_research_refresh",
      message: "adapter missing",
      target_type: "workflow_run",
      target_id: "workflow_failed",
      navigation_target_type: null,
      navigation_target_id: null,
      created_at: "2026-06-02T08:00:00+08:00",
      latest_at: "2026-06-02T08:02:00+08:00",
      recommended_action: "Review the run error, then rerun the fixed registered job if appropriate.",
      job_key: "policy_research_refresh",
      ...reviewTodoFields,
    },
    {
      item_id: "brief:brief_policy_watch",
      category: "brief_review",
      severity: "warning",
      title: "Brief review: pending_review",
      message: "Brief brief_policy_watch needs operator review.",
      target_type: "intelligence_brief",
      target_id: "brief_policy_watch",
      navigation_target_type: "intelligence_brief",
      navigation_target_id: "brief_policy_watch",
      created_at: "2026-06-02T08:30:00+08:00",
      latest_at: "2026-06-02T08:30:00+08:00",
      recommended_action: "Open the daily brief and review policy watch.",
      job_key: null,
      ...reviewTodoFields,
    },
    {
      item_id: "decision:decision_sim",
      category: "decision_feedback",
      severity: "warning",
      title: "Decision feedback pending",
      message: "Decision has no follow-up feedback yet. recommendation_id=rec_sim",
      target_type: "recommendation_decision",
      target_id: "decision_sim",
      navigation_target_type: "recommendation",
      navigation_target_id: "rec_sim",
      created_at: "2026-06-02T09:15:00+08:00",
      latest_at: "2026-06-02T09:15:00+08:00",
      recommended_action: "Add subjective follow-up feedback when observation is available.",
      job_key: null,
      ...reviewTodoFields,
    },
  ];
  const reviewItems: OperationTodoItem[] = [];
  if (!weatherFeatureReviewed) {
    reviewItems.push({
      item_id: "weather_feature:weather_feature_pending",
      category: "weather_feature_review",
      severity: "warning",
      title: "Weather feature review: pending_review",
      message: "Weather feature snapshot weather_feature_pending needs operator review.",
      target_type: "weather_feature_snapshot",
      target_id: "weather_feature_pending",
      navigation_target_type: null,
      navigation_target_id: null,
      created_at: "2026-06-02T07:00:00+08:00",
      latest_at: "2026-06-02T07:00:00+08:00",
      recommended_action: "Review public-derived weather quality.",
      job_key: null,
      review_target_type: "weather_feature",
      allowed_review_statuses: ["approved", "needs_revision", "rejected"],
      default_review_note: "Reviewed from Action Center quick action.",
    });
  }
  if (!marketArtifactReviewed) {
    reviewItems.push({
      item_id: "market_artifact:market_artifact_pending",
      category: "market_artifact_review",
      severity: "warning",
      title: "Market artifact review: pending_review",
      message: "Preserved artifact market_artifact_pending needs local review.",
      target_type: "market_raw_artifact",
      target_id: "market_artifact_pending",
      navigation_target_type: null,
      navigation_target_id: null,
      created_at: "2026-06-02T07:30:00+08:00",
      latest_at: "2026-06-02T07:30:00+08:00",
      recommended_action: "Review preserved source metadata.",
      job_key: null,
      review_target_type: "market_artifact",
      allowed_review_statuses: ["approved", "needs_revision", "rejected"],
      default_review_note: "Reviewed from Action Center quick action.",
    });
  }
  if (!policyDocumentReviewed) {
    reviewItems.push({
      item_id: "policy_document:knowledge_policy",
      category: "policy_document_review",
      severity: "warning",
      title: "Policy document review: pending_review",
      message: "Knowledge document knowledge_policy needs operator review.",
      target_type: "knowledge_document",
      target_id: "knowledge_policy",
      navigation_target_type: null,
      navigation_target_id: null,
      created_at: "2026-06-02T08:00:00+08:00",
      latest_at: "2026-06-02T08:00:00+08:00",
      recommended_action: "Review document provenance and chunks.",
      job_key: null,
      review_target_type: "policy_document",
      allowed_review_statuses: ["approved", "needs_revision", "rejected"],
      default_review_note: "Reviewed from Action Center quick action.",
    });
  }
  const items = [...baseItems, ...reviewItems];
  const byCategory = items.reduce<Record<string, number>>((counts, item) => {
    counts[item.category] = (counts[item.category] ?? 0) + 1;
    return counts;
  }, {});
  return {
    generated_at: "2026-06-02T08:05:00+08:00",
    status: "critical",
    counts: {
      total: items.length,
      critical: 1,
      warning: items.length - 1,
      by_category: byCategory,
    },
    items,
    no_auto_trading: true,
  };
}

function operationsReviewPackageResponse() {
  return {
    package_version: "operations_review_package_v1",
    generated_at: "2026-06-02T08:07:00+08:00",
    overview: operationsOverview,
    action_center: operationActionCenterResponse(),
    system_readiness: systemReadinessResponse(),
    recent_runs: [failedRun],
    fixed_job_keys: [
      "weather_refresh",
      "policy_research_refresh",
      "bench_dispatch_research",
      "daily_intelligence_brief",
      "demo_research_workspace_seed",
    ],
    no_auto_trading: true,
    manual_job_keys_only: true,
    network_probe_performed: false,
    fetch_performed: false,
  };
}

const weatherFeatureReviewPackage = {
  package_version: "weather_feature_review_package_v1",
  generated_at: "2026-06-02T08:09:00+08:00",
  snapshot: {
    feature_snapshot_id: "weather_feature_pending",
    ingestion_run_id: "weather_ingest_test",
    raw_payload_id: "weather_raw_test",
    provider: "open_meteo",
    location_id: "demo_hydro_a_reference",
    generated_at: "2026-06-02T07:00:00+08:00",
    forecast_start: "2026-06-02T00:00:00+08:00",
    feature_version: "hydro_weather_v1",
    quality_status: "warning",
    human_review_status: "pending_review",
    features: {
      precipitation_24h_mm: null,
      precipitation_72h_mm: null,
    },
    evidence: [],
    missing_data_warnings: ["precipitation_24h_mm missing"],
    data_mode: "public_derived",
  },
  quality_issue_summary: {
    total_count: 2,
    severity_counts: { warning: 2 },
    issue_code_counts: { missing_value: 2 },
    displayed_issue_count: 2,
  },
  quality_issues: [],
  reviews: [],
  approval: {
    can_approve: false,
    blockers: ["required derived features are missing: precipitation_24h_mm"],
    required_features: ["precipitation_24h_mm"],
  },
  no_auto_trading: true,
  recommendation_chain_requires_approved_snapshot: true,
  network_probe_performed: false,
  fetch_performed: false,
};

const marketArtifactReviewPackage = {
  package_version: "market_artifact_review_package_v1",
  generated_at: "2026-06-02T08:09:00+08:00",
  artifact: {
    artifact_id: "market_artifact_pending",
    source_id: "example_region_power_exchange_center",
    endpoint_id: "reports_market_research",
    source_url: "http://reports.market.example.invalid/news/scyj/example.html",
    title: "Pending preserved market artifact",
    media_type: "text/html",
    storage_backend: "postgres_inline",
    inline_text_available: true,
    object_key: null,
    content_sha256: "a".repeat(64),
    byte_length: 120,
    published_at: null,
    captured_at: "2026-06-02T07:10:00+08:00",
    ingestion_method: "manual_submission",
    transport_security_status: "insecure_http_source",
    human_review_status: "pending_review",
    data_mode: "public_observed",
  },
  source: {
    source_id: "example_region_power_exchange_center",
    name: "Example Regional Exchange",
    trust_tier: "official_public",
    official_url: "http://reports.market.example.invalid/",
    collection_permission_note: "Manual preservation only.",
    operator_name: "Example Regional Exchange",
    market_scope: "southern_regional_market_disclosure",
    data_mode: "public_derived",
    attribution_text: "REPORTS",
  },
  endpoint: {
    endpoint_id: "reports_market_research",
    name: "REPORTS market research column",
    lifecycle_status: "blocked_tls",
    collection_enabled: false,
    source_id: "example_region_power_exchange_center",
    canonical_url: "http://reports.market.example.invalid/news/scyj/",
    access_mode: "anonymous_http_only",
    manual_submission_enabled: true,
  },
  quality_issue_summary: {
    total_count: 2,
    severity_counts: { warning: 2 },
    issue_code_counts: {
      endpoint_candidate_unverified: 1,
      insecure_transport_source: 1,
    },
    displayed_issue_count: 2,
  },
  quality_issues: [{
    quality_issue_id: "market_quality_1",
    source_id: "example_region_power_exchange_center",
    endpoint_id: "reports_market_research",
    ingestion_run_id: "market_ingest_1",
    ingestion_run_item_id: "market_item_1",
    parsing_run_id: null,
    endpoint_health_check_id: null,
    artifact_id: "market_artifact_pending",
    issue_scope: "artifact",
    issue_code: "insecure_transport_source",
    severity: "warning",
    message: "The submitted public source URL uses HTTP because trusted HTTPS is unavailable.",
    details: {},
    data_mode: "public_derived",
  }],
  reviews: [],
  parsing_runs: [],
  no_auto_trading: true,
  recommendation_chain_isolated: true,
  network_probe_performed: false,
  fetch_performed: false,
  parse_performed: false,
};

const policyDocumentReviewPackage = {
  package_version: "policy_document_review_package_v1",
  generated_at: "2026-06-02T08:09:00+08:00",
  document: importedKnowledgeDocumentDetail,
  chunk_summary: {
    total_count: 2,
    embedded_count: 2,
    embedding_coverage: 1,
    displayed_chunk_count: 2,
  },
  displayed_chunks: [
    {
      chunk_id: "chunk_1",
      ordinal: 0,
      content_sha256: "b".repeat(64),
      character_count: 120,
      embedding_model: "bge-m3",
      content_excerpt: "Policy evidence excerpt.",
    },
  ],
  reviews: [],
  review_count: 0,
  external_processing_allowed: false,
  external_processing_allowed_default: false,
  raw_payload_included: false,
  server_artifact_written: false,
  no_auto_trading: true,
  recommendation_chain_isolated: true,
  network_probe_performed: false,
  fetch_performed: false,
  external_model_call_performed: false,
};

beforeEach(() => {
  marketArtifactsShouldFail = false;
  corpusOverviewShouldFail = false;
  documentDetailShouldFail = false;
  recommendationAuditShouldFail = false;
  recommendationEvidenceExportShouldFail = false;
  recommendationDecisionShouldFail = false;
  forecastBacktestShouldFail = false;
  briefGenerated = false;
  briefReviewed = false;
  recommendationGenerated = false;
  recommendationReviewed = false;
  recommendationDecisionCreated = false;
  recommendationFeedbackCreated = false;
  recommendationFeedbackAnalyticsShouldFail = false;
  hydroOptimizationCreated = false;
  hydroOptimizationUsedPriceSignal = false;
  operationActionCenterShouldFail = false;
  actionCenterReviewShouldFail = false;
  weatherFeatureReviewed = false;
  marketArtifactReviewed = false;
  policyDocumentReviewed = false;
  forecastManualImportShouldFail = false;
  demoSeeded = false;
  vi.stubGlobal("ResizeObserver", class {
    observe() {}
    unobserve() {}
    disconnect() {}
  });
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({
    arc: vi.fn(),
    beginPath: vi.fn(),
    bezierCurveTo: vi.fn(),
    clearRect: vi.fn(),
    clip: vi.fn(),
    closePath: vi.fn(),
    createLinearGradient: vi.fn(() => ({ addColorStop: vi.fn() })),
    createRadialGradient: vi.fn(() => ({ addColorStop: vi.fn() })),
    drawImage: vi.fn(),
    fill: vi.fn(),
    fillRect: vi.fn(),
    fillText: vi.fn(),
    lineTo: vi.fn(),
    measureText: vi.fn(() => ({ width: 100 })),
    moveTo: vi.fn(),
    quadraticCurveTo: vi.fn(),
    rect: vi.fn(),
    restore: vi.fn(),
    rotate: vi.fn(),
    save: vi.fn(),
    scale: vi.fn(),
    setLineDash: vi.fn(),
    setTransform: vi.fn(),
    stroke: vi.fn(),
    strokeRect: vi.fn(),
    translate: vi.fn(),
  } as unknown as CanvasRenderingContext2D);
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input);
    if (path.endsWith("/v1/operations/jobs")) {
      return new Response(JSON.stringify({ items: [policyJob, demoSeedJob] }), { status: 200 });
    }
    if (path.endsWith("/v1/system/readiness")) {
      return new Response(JSON.stringify(systemReadinessResponse()), { status: 200 });
    }
    if (path.endsWith("/v1/operations/overview")) {
      return new Response(JSON.stringify(operationsOverview), { status: 200 });
    }
    if (path.endsWith("/v1/operations/review-package")) {
      return new Response(JSON.stringify(operationsReviewPackageResponse()), { status: 200 });
    }
    if (path.endsWith("/v1/operations/action-center")) {
      if (operationActionCenterShouldFail) {
        return new Response(JSON.stringify({ error: { code: "action_center_unavailable" } }), { status: 500 });
      }
      return new Response(JSON.stringify(operationActionCenterResponse()), { status: 200 });
    }
    if (path.endsWith("/v1/weather/features/weather_feature_pending/review-package")) {
      return new Response(JSON.stringify(weatherFeatureReviewPackage), { status: 200 });
    }
    if (path.endsWith("/v1/market/artifacts/market_artifact_pending/review-package")) {
      return new Response(JSON.stringify(marketArtifactReviewPackage), { status: 200 });
    }
    if (path.endsWith("/v1/policy/documents/knowledge_policy/review-package")) {
      return new Response(JSON.stringify(policyDocumentReviewPackage), { status: 200 });
    }
    if (path.endsWith("/v1/weather/features/weather_feature_pending/reviews")) {
      if (actionCenterReviewShouldFail) {
        return new Response(JSON.stringify({ error: { code: "weather_review_failed" } }), { status: 500 });
      }
      weatherFeatureReviewed = true;
      return new Response(JSON.stringify({
        review_id: "weather_review_action",
        feature_snapshot_id: "weather_feature_pending",
        created_at: "2026-06-02T08:06:00+08:00",
        actor: "local_operator",
        review_status: "approved",
        note: "Reviewed from Action Center quick action.",
      }), { status: 200 });
    }
    if (path.endsWith("/v1/market/artifacts/market_artifact_pending/reviews")) {
      if (actionCenterReviewShouldFail) {
        return new Response(JSON.stringify({ error: { code: "market_review_failed" } }), { status: 500 });
      }
      marketArtifactReviewed = true;
      return new Response(JSON.stringify({
        review_id: "market_review_action",
        artifact_id: "market_artifact_pending",
        created_at: "2026-06-02T08:07:00+08:00",
        actor: "local_operator",
        review_status: "needs_revision",
        note: "Check artifact provenance before approval.",
      }), { status: 200 });
    }
    if (path.endsWith("/v1/policy/documents/knowledge_policy/reviews")) {
      if (actionCenterReviewShouldFail) {
        return new Response(JSON.stringify({ error: { code: "policy_review_failed" } }), { status: 500 });
      }
      policyDocumentReviewed = true;
      return new Response(JSON.stringify({
        review_id: "knowledge_review_action",
        document_id: "knowledge_policy",
        created_at: "2026-06-02T08:08:00+08:00",
        actor: "local_operator",
        review_status: "rejected",
        note: "Reviewed from Action Center quick action.",
      }), { status: 200 });
    }
    if (path.endsWith("/v1/market/ingestion/runs?limit=5")) {
      return new Response(JSON.stringify(marketIngestionRunResponse), { status: 200 });
    }
    if (path.endsWith("/v1/market/artifacts?limit=10")) {
      if (marketArtifactsShouldFail) {
        return new Response(JSON.stringify({ error: { code: "market_artifacts_unavailable" } }), { status: 500 });
      }
      return new Response(JSON.stringify({ items: [marketArtifact, rejectedMarketArtifact] }), { status: 200 });
    }
    if (path.endsWith("/v1/policy/corpus/overview")) {
      if (corpusOverviewShouldFail) {
        return new Response(JSON.stringify({ error: { code: "policy_corpus_unavailable" } }), { status: 500 });
      }
      return new Response(JSON.stringify(policyCorpusOverview), { status: 200 });
    }
    if (path.endsWith("/v1/policy/documents")) {
      return new Response(JSON.stringify({ items: [importedKnowledgeDocument] }), { status: 200 });
    }
    if (path.endsWith("/v1/policy/documents/from-market-artifact/market_artifact_policy")) {
      return new Response(JSON.stringify(importedKnowledgeDocument), { status: 200 });
    }
    if (path.endsWith("/v1/policy/documents/knowledge_policy/chunks")) {
      return new Response(JSON.stringify({
        items: [
          {
            chunk_id: "chunk_1",
            ordinal: 0,
            content: "policy body",
            character_count: 11,
            embedding_model: "bge-m3",
          },
          {
            chunk_id: "chunk_2",
            ordinal: 1,
            content: "policy appendix",
            character_count: 15,
            embedding_model: "bge-m3",
          },
        ],
      }), { status: 200 });
    }
    if (path.endsWith("/v1/policy/documents/knowledge_policy")) {
      if (documentDetailShouldFail) {
        return new Response(JSON.stringify({ error: { code: "policy_document_detail_unavailable" } }), { status: 500 });
      }
      return new Response(JSON.stringify(importedKnowledgeDocumentDetail), { status: 200 });
    }
    if (path.endsWith("/v1/policy/documents/from-market-artifact/market_artifact_rejected")) {
      return new Response(JSON.stringify({ error: { code: "market_artifact_not_usable" } }), { status: 409 });
    }
    if (path.endsWith("/v1/forecasting/research/overview")) {
      return new Response(JSON.stringify(forecastOverview), { status: 200 });
    }
    if (path.endsWith("/v1/forecasting/research/datasets/manual")) {
      if (forecastManualImportShouldFail) {
        return new Response(JSON.stringify({ error: { code: "forecast_research_dataset_quality_failed" } }), { status: 409 });
      }
      const body = JSON.parse(String(init?.body));
      return new Response(JSON.stringify({
        import_run_id: "forecast_import_uploaded",
        dataset_id: "forecast_dataset_uploaded",
        status: "accepted",
        duplicate_dataset: false,
        quality_status: "valid",
        quality_issue_count: 0,
        submitted_point_count: body.points.length,
        normalized_point_count: body.points.length,
        trade_date_count: 1,
        content_sha256: "d".repeat(64),
        data_mode: body.data_mode,
        usage_scope: "research_only",
      }), { status: 200 });
    }
    if (path.endsWith("/v1/forecasting/research/datasets")) {
      return new Response(JSON.stringify({ items: [forecastDataset] }), { status: 200 });
    }
    if (path.endsWith("/v1/forecasting/research/import-runs?dataset_id=forecast_dataset_test&limit=5")) {
      return new Response(JSON.stringify({ items: forecastOverview.recent_import_runs }), { status: 200 });
    }
    if (path.endsWith("/v1/forecasting/research/import-runs?dataset_id=forecast_dataset_uploaded&limit=5")) {
      return new Response(JSON.stringify({
        items: [
          {
            import_run_id: "forecast_import_uploaded",
            dataset_id: "forecast_dataset_uploaded",
            started_at: "2026-06-02T09:00:00+08:00",
            completed_at: "2026-06-02T09:00:01+08:00",
            status: "accepted",
            submitted_point_count: 2,
            normalized_point_count: 2,
            quality_status: "valid",
            quality_issue_count: 0,
            data_mode: "user_uploaded",
            error_code: null,
            error_message: null,
          },
        ],
      }), { status: 200 });
    }
    if (path.endsWith("/v1/forecasting/research/quality/issues?dataset_id=forecast_dataset_test&limit=5")) {
      return new Response(JSON.stringify({ items: forecastOverview.recent_quality_issues }), { status: 200 });
    }
    if (path.endsWith("/v1/forecasting/research/quality/issues?dataset_id=forecast_dataset_uploaded&limit=5")) {
      return new Response(JSON.stringify({ items: [] }), { status: 200 });
    }
    if (path.endsWith("/v1/forecasting/research/datasets/forecast_dataset_test/review-package")) {
      return new Response(JSON.stringify(forecastReviewPackage), { status: 200 });
    }
    if (path.endsWith("/v1/forecasting/research/datasets/forecast_dataset_uploaded/review-package")) {
      return new Response(JSON.stringify(uploadedForecastReviewPackage), { status: 200 });
    }
    if (path.endsWith("/v1/forecasting/research/model-runs?dataset_id=forecast_dataset_test&limit=8")) {
      return new Response(JSON.stringify({ items: [forecastModelRun] }), { status: 200 });
    }
    if (path.endsWith("/v1/forecasting/research/model-runs?dataset_id=forecast_dataset_uploaded&limit=8")) {
      return new Response(JSON.stringify({ items: [] }), { status: 200 });
    }
    if (path.endsWith("/v1/forecasting/research/model-runs/forecast_model_seasonal/predictions?limit=500")) {
      return new Response(JSON.stringify({
        items: [
          {
            prediction_id: "prediction_1",
            model_run_id: "forecast_model_seasonal",
            target_interval_start: "2026-01-15T00:00:00+08:00",
            trade_date: "2026-01-15",
            interval_index: 1,
            actual_price: "105.0",
            predicted_price: "104.0",
            data_mode: "public_derived",
          },
          {
            prediction_id: "prediction_2",
            model_run_id: "forecast_model_seasonal",
            target_interval_start: "2026-01-15T00:15:00+08:00",
            trade_date: "2026-01-15",
            interval_index: 2,
            actual_price: "106.0",
            predicted_price: "105.5",
            data_mode: "public_derived",
          },
        ],
      }), { status: 200 });
    }
    if (path.endsWith("/v1/forecasting/research/datasets/forecast_dataset_test/points?limit=192")) {
      return new Response(JSON.stringify({
        items: [
          {
            point_id: "point_1",
            dataset_id: "forecast_dataset_test",
            interval_start: "2026-01-15T00:00:00+08:00",
            trade_date: "2026-01-15",
            interval_index: 1,
            price: "105.0",
            data_mode: "scenario_simulated",
          },
          {
            point_id: "point_2",
            dataset_id: "forecast_dataset_test",
            interval_start: "2026-01-15T00:15:00+08:00",
            trade_date: "2026-01-15",
            interval_index: 2,
            price: "106.0",
            data_mode: "scenario_simulated",
          },
        ],
      }), { status: 200 });
    }
    if (path.endsWith("/v1/forecasting/research/datasets/forecast_dataset_test/backtests")) {
      if (forecastBacktestShouldFail) {
        return new Response(JSON.stringify({ error: { code: "forecast_research_dataset_not_usable" } }), { status: 409 });
      }
      return new Response(JSON.stringify(forecastModelRun), { status: 200 });
    }
    if (path.endsWith("/v1/intelligence/questions")) {
      return new Response(JSON.stringify(questionAnswer), { status: 200 });
    }
    if (path.endsWith("/v1/intelligence/briefs/generate")) {
      briefGenerated = true;
      return new Response(JSON.stringify(generatedBrief), { status: 200 });
    }
    if (path.endsWith("/v1/intelligence/briefs/brief_policy_watch/reviews")) {
      briefReviewed = true;
      return new Response(JSON.stringify(approvedBriefReview), { status: 200 });
    }
    if (path.endsWith("/v1/intelligence/briefs/brief_policy_watch")) {
      return new Response(
        JSON.stringify(briefReviewed ? reviewedBriefDetail : generatedBriefDetail),
        { status: 200 },
      );
    }
    if (path.endsWith("/v1/intelligence/briefs?limit=20")) {
      if (!briefGenerated) {
        return new Response(JSON.stringify({ items: [] }), { status: 200 });
      }
      return new Response(JSON.stringify({
        items: [
          {
            ...briefSummary,
            human_review_status: briefReviewed ? "approved" : "pending_review",
          },
        ],
      }), { status: 200 });
    }
    if (path.endsWith("/v1/operations/jobs/policy_research_refresh/run")) {
      return new Response(JSON.stringify(queuedRun), { status: 200 });
    }
    if (path.endsWith("/v1/operations/jobs/demo_research_workspace_seed/run")) {
      demoSeeded = true;
      return new Response(JSON.stringify({
        ...queuedRun,
        workflow_run_id: "workflow_demo_seed",
        workflow_key: "demo_research_workspace_seed",
        summary: { seed_key: "mvp_rc_demo_v1" },
      }), { status: 200 });
    }
    if (path.endsWith("/v1/operations/runs/workflow_demo_seed")) {
      return new Response(JSON.stringify({
        ...queuedRun,
        workflow_run_id: "workflow_demo_seed",
        workflow_key: "demo_research_workspace_seed",
        status: "succeeded",
        attempt_count: 1,
        completed_at: "2026-06-02T08:00:01+08:00",
        summary: {
          message: "Seeded local deterministic v0.1 RC demo data.",
          seed_key: "mvp_rc_demo_v1",
        },
      }), { status: 200 });
    }
    if (path.endsWith("/v1/operations/runs/workflow_test")) {
      return new Response(JSON.stringify({
        ...queuedRun,
        status: "skipped",
        attempt_count: 1,
        completed_at: "2026-06-02T08:00:01+08:00",
        summary: { reason: "no_collection_enabled_sources" },
      }), { status: 200 });
    }
    if (path.includes("/v1/operations/runs?")) {
      return new Response(JSON.stringify({ items: [] }), { status: 200 });
    }
    if (path.includes("/v1/intelligence/briefs/latest")) return new Response("{}", { status: 404 });
    if (path.includes("/v1/scenarios/demo_hydro/default")) {
      return new Response(JSON.stringify({
        scenario_id: "demo_hydro_a_normal_storage_normal_inflow_v1",
        asset_name: "Demo Hydro A Hydropower Station",
        data_mode: "scenario_simulated",
        installed_capacity_mw: 1200,
        firm_output_mw: 300.0,
        current_water_level_m: 760,
        available_energy_mwh: 4200,
        assumptions: ["Synthetic input for testing."],
        warning: "This is simulated scenario data.",
      }), { status: 200 });
    }
    if (path.endsWith("/v1/scenarios/demo_hydro/optimization-runs/recent?limit=5")) {
      return new Response(
        JSON.stringify({
          items: hydroOptimizationCreated
            ? [hydroOptimizationUsedPriceSignal ? hydroOptimizationPriceRun : hydroOptimizationRun]
            : [],
        }),
        { status: 200 },
      );
    }
    if (path.endsWith("/v1/scenarios/demo_hydro/optimization-runs")) {
      const body = JSON.parse(String(init?.body ?? "{}"));
      hydroOptimizationCreated = true;
      hydroOptimizationUsedPriceSignal = Array.isArray(body.price_signal);
      return new Response(
        JSON.stringify(hydroOptimizationUsedPriceSignal ? hydroOptimizationPriceRun : hydroOptimizationRun),
        { status: 200 },
      );
    }
    if (path.endsWith("/v1/recommendations/run")) {
      recommendationGenerated = true;
      return new Response(JSON.stringify(generatedRecommendation), { status: 200 });
    }
    if (path.endsWith("/v1/recommendations/feedback/overview?limit=10")) {
      if (recommendationFeedbackAnalyticsShouldFail) {
        return new Response(JSON.stringify({ error: { code: "feedback_analytics_unavailable" } }), { status: 500 });
      }
      return new Response(JSON.stringify(recommendationFeedbackAnalyticsResponse()), { status: 200 });
    }
    if (path.endsWith("/v1/recommendations/rec_sim/reviews")) {
      recommendationReviewed = true;
      return new Response(JSON.stringify(approvedRecommendationReview), { status: 200 });
    }
    if (path.endsWith("/v1/recommendations/rec_sim/audit")) {
      if (recommendationAuditShouldFail) {
        return new Response(JSON.stringify({ error: { code: "recommendation_audit_unavailable" } }), { status: 500 });
      }
      return new Response(JSON.stringify({
        ...recommendationAudit,
        review_status: recommendationReviewed ? "approved" : "pending_review",
      }), { status: 200 });
    }
    if (path.endsWith("/v1/recommendations/rec_sim/evidence-export")) {
      if (recommendationEvidenceExportShouldFail) {
        return new Response(JSON.stringify({ error: { code: "evidence_export_unavailable" } }), { status: 500 });
      }
      return new Response(JSON.stringify({
        ...recommendationEvidenceExport,
        review_status: recommendationReviewed ? "approved" : "pending_review",
      }), { status: 200 });
    }
    if (path.endsWith("/v1/recommendations/rec_sim/decisions")) {
      const method = init?.method ?? (input instanceof Request ? input.method : "GET");
      if (method === "POST") {
        if (recommendationDecisionShouldFail) {
          return new Response(JSON.stringify({ error: { code: "recommendation_audit_not_adoptable" } }), { status: 409 });
        }
        recommendationDecisionCreated = true;
        return new Response(JSON.stringify(recommendationDecision), { status: 200 });
      }
      return new Response(JSON.stringify({
        items: recommendationDecisionCreated
          ? [{
            ...recommendationDecision,
            feedback: recommendationFeedbackCreated ? [recommendationDecisionFeedback] : [],
          }]
          : [],
      }), { status: 200 });
    }
    if (path.endsWith("/v1/recommendations/decisions/decision_sim/feedback")) {
      recommendationFeedbackCreated = true;
      return new Response(JSON.stringify(recommendationDecisionFeedback), { status: 200 });
    }
    if (path.endsWith("/v1/recommendations/rec_sim")) {
      return new Response(JSON.stringify({
        ...generatedRecommendation,
        review_status: recommendationReviewed ? "approved" : "pending_review",
        reviews: recommendationReviewed ? [approvedRecommendationReview] : [],
      }), { status: 200 });
    }
    if (path.includes("/v1/recommendations/recent")) {
      return new Response(JSON.stringify({
        items: recommendationGenerated
          ? [{ ...generatedRecommendation, review_status: recommendationReviewed ? "approved" : "pending_review" }]
          : [],
      }), { status: 200 });
    }
    return new Response(JSON.stringify({ items: [] }), { status: 200 });
  }));
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function requestJsonBody(pathSuffix: string) {
  const call = vi.mocked(fetch).mock.calls.find(([path]) => String(path).endsWith(pathSuffix));
  expect(call).toBeDefined();
  return JSON.parse(String(call?.[1]?.body));
}

async function openResearchWorkspace() {
  fireEvent.click(screen.getAllByTestId("nav-research")[0]);
  await screen.findByTestId("research-workspace", {}, { timeout: 15_000 });
}

test("renders the daily intelligence workspace with safety boundary", async () => {
  render(<App />);
  expect(screen.getAllByTestId("nav-brief")[0]).toHaveTextContent("今日简报");
  expect(screen.getAllByTestId("nav-research")[0]).toHaveTextContent("证据与研究");
  expect(screen.getByText("示例甲省电力研究台")).toBeInTheDocument();
  expect(screen.getByText("个人研究工作站")).toBeInTheDocument();
  expect(screen.getByText("今日变化与风险")).toBeInTheDocument();
  expect(screen.getByText("Human-in-the-loop")).toBeInTheDocument();
  expect(document.body).not.toHaveTextContent(/骞夸笢|鐢靛姏|浠婃棩|绂佹/);
  expect(await screen.findByText("尚未生成简报")).toBeInTheDocument();
});

test("renders deterministic policy watch inside the daily brief", async () => {
  render(<App />);
  fireEvent.click(await screen.findByTestId("generate-brief"));

  expect(await screen.findByTestId("policy-watch-card")).toHaveTextContent("政策观察");
  expect(screen.getByTestId("policy-watch-chunk_policy_watch")).toHaveTextContent("Official policy page");
  expect(screen.getByTestId("policy-watch-chunk_policy_watch")).toHaveTextContent("官方政策");
  expect(screen.getByTestId("policy-watch-chunk_policy_watch")).toHaveTextContent("本地引用");
  expect(screen.getByTestId("policy-watch-card")).toHaveTextContent("已排除 1 个未授权分块");
  expect(screen.getByTestId("policy-watch-card")).toHaveTextContent("Example Energy Regulator");
});

test("submits a brief review and refreshes review history", async () => {
  render(<App />);
  fireEvent.click(await screen.findByTestId("generate-brief"));

  expect(await screen.findByTestId("brief-review-panel")).toHaveTextContent("pending_review");
  fireEvent.change(screen.getByTestId("brief-review-note"), {
    target: { value: "Reviewed policy watch and missing information." },
  });
  fireEvent.click(screen.getByTestId("review-brief-approved"));

  await waitFor(() => {
    expect(screen.getByTestId("brief-review-panel")).toHaveTextContent("approved");
  });
  expect(screen.getByTestId("brief-review-history")).toHaveTextContent("Reviewed policy watch and missing information.");
  expect(screen.getByTestId("brief-history")).toHaveTextContent("approved");
  expect(fetch).toHaveBeenCalledWith(
    "/v1/intelligence/briefs/brief_policy_watch/reviews",
    expect.objectContaining({ method: "POST" }),
  );
});

test("opens the human-reviewed simulated scenario workspace from mobile navigation", async () => {
  render(<App />);
  fireEvent.click(screen.getAllByRole("menuitem", { name: "experiment 场景建议" })[0]);
  expect(await screen.findByText("场景建议与人工审核")).toBeInTheDocument();
  expect(await screen.findByTestId("hydro-optimization-preview")).toHaveTextContent("scenario_simulated");
  expect(screen.getByText("建议模块保持独立")).toBeInTheDocument();
});

test("runs a local hydro constraint preview without entering the recommendation chain", async () => {
  render(<App />);
  fireEvent.click(screen.getAllByTestId("nav-recommendation")[0]);

  const preview = await screen.findByTestId("hydro-optimization-preview");
  expect(preview).toHaveTextContent("水电约束预演");
  fireEvent.change(screen.getByTestId("hydro-energy-budget"), { target: { value: "4200" } });
  fireEvent.change(screen.getByTestId("hydro-min-output"), { target: { value: "120" } });
  fireEvent.change(screen.getByTestId("hydro-max-output"), { target: { value: "600" } });
  fireEvent.click(screen.getByTestId("run-hydro-optimization"));

  expect(await screen.findByText("水电约束预演已保存为本地审计记录。")).toBeInTheDocument();
  expect(screen.getByTestId("hydro-optimization-preview")).toHaveTextContent("no_auto_trading=true");
  expect(screen.getByTestId("hydro-optimization-preview")).toHaveTextContent("scenario_simulated");
  expect(screen.getByTestId("hydro-optimization-warnings")).toHaveTextContent("96 点价格曲线");
  expect(screen.getByTestId("hydro-optimization-recent")).toHaveTextContent("hydro_opt_sim");
  expect(screen.getByTestId("hydro-constraint-explanation")).toHaveTextContent("No price signal supplied");
  expect(screen.getByTestId("hydro-optimization-comparison")).toHaveTextContent("未使用");
  expect(document.body).not.toHaveTextContent(/骞夸笢|鐢靛姏|浠婃棩|绂佹/);
  const body = requestJsonBody("/v1/scenarios/demo_hydro/optimization-runs");
  expect(body).toMatchObject({
    trade_date: expect.any(String),
    energy_budget_mwh: 4200,
    min_output_mw: 120,
    max_output_mw: 600,
  });
  expect(body).not.toHaveProperty("price_signal");
});

test("submits a pasted 96 point hydro price curve as user uploaded preview input", async () => {
  render(<App />);
  fireEvent.click(screen.getAllByTestId("nav-recommendation")[0]);

  await screen.findByTestId("hydro-optimization-preview");
  const priceSignal = Array.from({ length: 96 }, (_, index) => String(index + 101)).join("\n");
  fireEvent.change(screen.getByTestId("hydro-price-signal"), {
    target: { value: priceSignal },
  });
  fireEvent.click(screen.getByTestId("run-hydro-optimization"));

  expect(await screen.findByText("水电约束预演已保存为本地审计记录。")).toBeInTheDocument();
  expect(screen.getByTestId("hydro-optimization-preview")).toHaveTextContent("price_signal=user_uploaded");
  expect(screen.getByTestId("hydro-constraint-explanation")).toHaveTextContent("Price signal supplied");
  expect(screen.getByTestId("hydro-top-intervals")).toHaveTextContent("96");
  expect(screen.getByTestId("hydro-optimization-comparison")).toHaveTextContent("已使用");
  expect(screen.getByTestId("hydro-optimization-recent")).toHaveTextContent("hydro_opt_price");

  const body = requestJsonBody("/v1/scenarios/demo_hydro/optimization-runs");
  expect(body.price_signal).toHaveLength(96);
  expect(body.price_signal[0]).toEqual({ interval_index: 1, price: "101" });
  expect(body.price_signal[95]).toEqual({ interval_index: 96, price: "196" });
});

test("renders recommendation evidence audit after generating a draft", async () => {
  render(<App />);
  fireEvent.click(screen.getAllByTestId("nav-recommendation")[0]);
  fireEvent.click(await screen.findByTestId("generate-recommendation"));

  const auditCard = await screen.findByTestId("recommendation-audit");
  expect(auditCard).toHaveTextContent("warning");
  expect(auditCard).toHaveTextContent("no_auto_trading=true");
  expect(auditCard).toHaveTextContent("human_check_required=true");
  expect(auditCard).toHaveTextContent("BENCH");
  expect(auditCard).toHaveTextContent("research_only");
  expect(auditCard).toHaveTextContent("No approved public-derived weather feature evidence is linked.");
  const reviewPackage = await screen.findByTestId("recommendation-review-package");
  expect(reviewPackage).toHaveTextContent("只读证据导出包");
  expect(reviewPackage).toHaveTextContent("scenario_simulated");
  expect(reviewPackage).toHaveTextContent("no_auto_trading=true");
  expect(reviewPackage).toHaveTextContent("human_check_required=true");
  const exportJson = screen.getByTestId("recommendation-evidence-export-json") as HTMLTextAreaElement;
  expect(exportJson.value).toContain('"recommendation_id": "rec_sim"');
  expect(fetch).toHaveBeenCalledWith("/v1/recommendations/rec_sim/audit", undefined);
  expect(fetch).toHaveBeenCalledWith("/v1/recommendations/rec_sim/evidence-export", undefined);
  expect(document.body).not.toHaveTextContent(/骞夸笢|鐢靛姏|浠婃棩|绂佹/);
});

test("keeps recommendation detail usable when audit API fails", async () => {
  recommendationAuditShouldFail = true;
  render(<App />);
  fireEvent.click(screen.getAllByTestId("nav-recommendation")[0]);
  fireEvent.click(await screen.findByTestId("generate-recommendation"));

  expect(await screen.findByTestId("recommendation-card")).toBeInTheDocument();
  expect(await screen.findByTestId("recommendation-audit")).toHaveTextContent("API");
  expect(screen.getByTestId("submit-review")).toBeInTheDocument();
});

test("keeps recommendation review usable when evidence export API fails", async () => {
  recommendationEvidenceExportShouldFail = true;
  render(<App />);
  fireEvent.click(screen.getAllByTestId("nav-recommendation")[0]);
  fireEvent.click(await screen.findByTestId("generate-recommendation"));

  expect(await screen.findByTestId("recommendation-card")).toBeInTheDocument();
  expect(await screen.findByTestId("recommendation-review-package")).toHaveTextContent("证据导出包暂不可用");
  expect(screen.getByTestId("recommendation-audit")).toBeInTheDocument();
  expect(screen.getByTestId("submit-review")).toBeInTheDocument();
});

test("refreshes recommendation audit after manual review", async () => {
  render(<App />);
  fireEvent.click(screen.getAllByTestId("nav-recommendation")[0]);
  fireEvent.click(await screen.findByTestId("generate-recommendation"));

  fireEvent.change(await screen.findByTestId("review-note"), {
    target: { value: "Reviewed audit and scenario assumptions." },
  });
  fireEvent.click(screen.getByTestId("submit-review"));

  await waitFor(() => {
    expect(screen.getByTestId("recommendation-audit")).toHaveTextContent("review=approved");
  });
  expect(screen.getByTestId("review-history")).toHaveTextContent("Reviewed audit and scenario assumptions.");
});

test("records recommendation decisions and follow-up feedback", async () => {
  render(<App />);
  fireEvent.click(screen.getAllByTestId("nav-recommendation")[0]);
  fireEvent.click(await screen.findByTestId("generate-recommendation"));

  expect(await screen.findByTestId("decision-log-card")).toHaveTextContent("暂无人工决策日志");
  fireEvent.click(screen.getByText("18:00-20:00 · conserve"));
  fireEvent.change(screen.getByTestId("decision-note"), {
    target: { value: "Keep as local decision support only." },
  });
  fireEvent.click(screen.getByTestId("decision-safety-ack"));
  fireEvent.click(screen.getByTestId("submit-decision"));

  await waitFor(() => {
    expect(screen.getByTestId("decision-history")).toHaveTextContent("Keep as local decision support only.");
  });
  fireEvent.change(screen.getByTestId("feedback-note-decision_sim"), {
    target: { value: "Follow-up observation was useful." },
  });
  fireEvent.click(screen.getByTestId("submit-feedback-decision_sim"));

  await waitFor(() => {
    expect(screen.getByTestId("decision-history")).toHaveTextContent("useful");
  });
  expect(screen.getByTestId("decision-history")).toHaveTextContent("user_uploaded");
});

test("renders recommendation feedback analytics and refreshes after feedback", async () => {
  render(<App />);
  fireEvent.click(screen.getAllByTestId("nav-recommendation")[0]);
  fireEvent.click(await screen.findByTestId("generate-recommendation"));

  expect(await screen.findByTestId("recommendation-feedback-analytics")).toHaveTextContent("No local recommendation decisions");
  expect(screen.getByTestId("recommendation-feedback-analytics")).toHaveTextContent("audit_warning=1");
  expect(screen.getByTestId("recommendation-feedback-analytics")).toHaveTextContent("review_pending_review=1");
  expect(await screen.findByTestId("decision-log-card")).toBeInTheDocument();
  const firstWindow = screen.getByTestId("decision-windows").querySelector("input");
  expect(firstWindow).not.toBeNull();
  fireEvent.click(firstWindow as Element);
  fireEvent.change(screen.getByTestId("decision-note"), {
    target: { value: "Keep as local decision support only." },
  });
  fireEvent.click(screen.getByTestId("decision-safety-ack"));
  fireEvent.click(screen.getByTestId("submit-decision"));

  await waitFor(() => {
    expect(screen.getByTestId("recommendation-feedback-analytics")).toHaveTextContent("Pending observation");
  });
  fireEvent.change(screen.getByTestId("feedback-note-decision_sim"), {
    target: { value: "Follow-up observation was useful." },
  });
  fireEvent.click(screen.getByTestId("submit-feedback-decision_sim"));

  await waitFor(() => {
    expect(screen.getByTestId("recommendation-feedback-analytics")).toHaveTextContent("useful=1");
  });
  expect(screen.getByTestId("recommendation-feedback-analytics")).toHaveTextContent("Follow-up observation was useful.");
});

test("keeps recommendation detail usable when feedback analytics fails", async () => {
  recommendationFeedbackAnalyticsShouldFail = true;
  render(<App />);
  fireEvent.click(screen.getAllByTestId("nav-recommendation")[0]);
  fireEvent.click(await screen.findByTestId("generate-recommendation"));

  expect(await screen.findByTestId("recommendation-card")).toBeInTheDocument();
  expect(screen.getByTestId("recommendation-feedback-analytics")).toHaveTextContent("analytics API is unavailable");
  expect(screen.getByTestId("recommendation-audit")).toBeInTheDocument();
  expect(screen.getByTestId("submit-review")).toBeInTheDocument();
});

test("keeps recommendation review usable when decision logging fails", async () => {
  recommendationDecisionShouldFail = true;
  render(<App />);
  fireEvent.click(screen.getAllByTestId("nav-recommendation")[0]);
  fireEvent.click(await screen.findByTestId("generate-recommendation"));

  fireEvent.change(await screen.findByTestId("decision-note"), {
    target: { value: "Try to adopt a critical draft." },
  });
  fireEvent.click(screen.getByTestId("decision-safety-ack"));
  fireEvent.click(screen.getByTestId("submit-decision"));

  expect(await screen.findByText("人工决策日志保存失败，请检查审计状态、安全确认或本地 API 状态。")).toBeInTheDocument();
  expect(screen.getByTestId("recommendation-audit")).toBeInTheDocument();
  expect(screen.getByTestId("submit-review")).toBeInTheDocument();
});

test("polls an audited operation until the worker reports a terminal state", async () => {
  render(<App />);
  fireEvent.click(await screen.findByTestId("trigger-policy_research_refresh"));
  await waitFor(() => {
    expect(screen.getByTestId("run-status-workflow_test")).toHaveTextContent("skipped");
  }, { timeout: 2_500 });
});

test("renders operations overview and reruns a fixed failed job", async () => {
  render(<App />);
  fireEvent.click(screen.getAllByTestId("nav-operations")[0]);

  expect(await screen.findByTestId("operations-workspace")).toBeInTheDocument();
  expect(await screen.findByTestId("operation-action-center")).toHaveTextContent("Action Center");
  expect(screen.getByTestId("operation-action-center")).toHaveTextContent("Workflow failed: policy_research_refresh");
  expect(screen.getByTestId("operation-action-center")).toHaveTextContent("decision_feedback");
  expect(await screen.findByTestId("operation-overall-status")).toHaveTextContent("critical");
  expect(screen.getByTestId("operation-freshness")).toHaveTextContent("BENCH Dispatch Research Benchmark");
  expect(screen.getByTestId("operation-source-health")).toHaveTextContent("Source Registry");
  expect(screen.getByTestId("operation-ingestion-runs")).toHaveTextContent("council_home");
  expect(screen.getByTestId("operation-ingestion-runs")).toHaveTextContent("registered_static_http:v1");
  expect(await screen.findByTestId("operations-review-package")).toHaveTextContent("operations_review_package_v1");
  expect(screen.getByTestId("operations-review-package")).toHaveTextContent("no_auto_trading");
  expect(screen.getByTestId("operations-review-package")).toHaveTextContent("fixed job keys only");
  expect(screen.getByTestId("operations-review-package-download")).toBeInTheDocument();

  fireEvent.click(await screen.findByTestId("todo-trigger-workflow_failed"));
  await waitFor(() => {
    expect(screen.getByTestId("tracked-run-status-workflow_test")).toHaveTextContent("skipped");
  }, { timeout: 2_500 });
  expect(fetch).toHaveBeenCalledWith("/v1/operations/jobs/policy_research_refresh/run", { method: "POST" });
});

test("renders RC readiness checklist and seeds local demo data with a fixed job", async () => {
  render(<App />);
  fireEvent.click(screen.getAllByTestId("nav-operations")[0]);

  expect(await screen.findByTestId("system-readiness-card")).toHaveTextContent("Missing demo data");
  expect(screen.getByTestId("system-readiness-card")).toHaveTextContent("demo_research_workspace_seed");
  expect(screen.getByTestId("system-readiness-card")).toHaveTextContent("no external fetch");

  fireEvent.click(screen.getByTestId("system-readiness-seed-demo"));

  await waitFor(() => {
    expect(screen.getByTestId("tracked-run-status-workflow_demo_seed")).toHaveTextContent("succeeded");
  }, { timeout: 2_500 });
  await waitFor(() => {
    expect(screen.getByTestId("system-readiness-card")).toHaveTextContent("demo_rc_policy_document");
  });
  expect(fetch).toHaveBeenCalledWith(
    "/v1/operations/jobs/demo_research_workspace_seed/run",
    { method: "POST" },
  );
});

test("reviews action center data items with default and custom notes", async () => {
  render(<App />);
  fireEvent.click(screen.getAllByTestId("nav-operations")[0]);

  expect(await screen.findByTestId("operation-action-center")).toHaveTextContent("weather_feature_review");
  expect(screen.getByTestId("operation-action-center")).toHaveTextContent("market_artifact_review");
  expect(screen.getByTestId("operation-action-center")).toHaveTextContent("policy_document_review");

  fireEvent.click(await screen.findByTestId("todo-weather-package-weather_feature_pending"));
  expect(await screen.findByTestId("weather-review-package")).toHaveTextContent("weather_feature_review_package_v1");
  expect(screen.getByTestId("weather-review-package")).toHaveTextContent("public_derived");
  expect(screen.getByTestId("weather-review-package")).toHaveTextContent("2issues");
  expect(screen.getByTestId("weather-review-package")).toHaveTextContent("requires approved snapshot");
  expect(screen.getByTestId("weather-review-package-download")).toBeInTheDocument();

  fireEvent.click(await screen.findByTestId("todo-market-artifact-package-market_artifact_pending"));
  expect(await screen.findByTestId("market-artifact-review-package")).toHaveTextContent("market_artifact_review_package_v1");
  expect(screen.getByTestId("market-artifact-review-package")).toHaveTextContent("public_observed");
  expect(screen.getByTestId("market-artifact-review-package")).toHaveTextContent("raw text preserved");
  expect(screen.getByTestId("market-artifact-review-package")).toHaveTextContent("no_auto_trading");
  expect(screen.getByTestId("market-artifact-review-package")).toHaveTextContent("no parse");
  expect(screen.getByTestId("market-artifact-review-package-download")).toBeInTheDocument();

  fireEvent.click(await screen.findByTestId("todo-policy-document-package-knowledge_policy"));
  const policyPackage = await screen.findByTestId("policy-document-review-package");
  expect(policyPackage).toHaveTextContent("policy_document_review_package_v1");
  expect(policyPackage).toHaveTextContent("official_policy");
  expect(policyPackage).toHaveTextContent("public_observed");
  expect(policyPackage).toHaveTextContent("external_processing_allowed=false");
  expect(policyPackage).toHaveTextContent("raw_payload_included=false");
  expect(policyPackage).toHaveTextContent("recommendation_chain_isolated");
  expect(screen.getByTestId("policy-document-review-package-download")).toBeInTheDocument();

  fireEvent.click(await screen.findByTestId("todo-review-approved-weather_feature_pending"));
  await waitFor(() => {
    expect(weatherFeatureReviewed).toBe(true);
  });
  const weatherReview = requestJsonBody("/v1/weather/features/weather_feature_pending/reviews");
  expect(weatherReview).toEqual({
    review_status: "approved",
    note: "Reviewed from Action Center quick action.",
  });

  fireEvent.change(await screen.findByTestId("todo-review-note-market_artifact_pending"), {
    target: { value: "Check artifact provenance before approval." },
  });
  fireEvent.click(screen.getByTestId("todo-review-needs_revision-market_artifact_pending"));
  await waitFor(() => {
    expect(marketArtifactReviewed).toBe(true);
  });
  const artifactReview = requestJsonBody("/v1/market/artifacts/market_artifact_pending/reviews");
  expect(artifactReview).toEqual({
    review_status: "needs_revision",
    note: "Check artifact provenance before approval.",
  });

  fireEvent.click(await screen.findByTestId("todo-review-rejected-knowledge_policy"));
  await waitFor(() => {
    expect(policyDocumentReviewed).toBe(true);
  });
  expect(requestJsonBody("/v1/policy/documents/knowledge_policy/reviews")).toEqual({
    review_status: "rejected",
    note: "Reviewed from Action Center quick action.",
  });
});

test("keeps action center usable when a quick review fails", async () => {
  actionCenterReviewShouldFail = true;
  render(<App />);
  fireEvent.click(screen.getAllByTestId("nav-operations")[0]);

  fireEvent.click(await screen.findByTestId("todo-review-approved-weather_feature_pending"));
  expect(await screen.findByTestId("operation-action-center")).toHaveTextContent("review failed");
  expect(screen.getByTestId("operation-action-center")).toHaveTextContent("Workflow failed");
  expect(weatherFeatureReviewed).toBe(false);
});

test("opens action center targets without running jobs", async () => {
  render(<App />);
  fireEvent.click(screen.getAllByTestId("nav-operations")[0]);

  fireEvent.click(await screen.findByTestId("todo-open-brief_policy_watch"));
  expect(await screen.findByTestId("brief-dashboard")).toBeInTheDocument();
  expect(await screen.findByTestId("policy-watch-card")).toHaveTextContent("Example Energy Regulator");
  expect(fetch).toHaveBeenCalledWith("/v1/intelligence/briefs/brief_policy_watch", undefined);

  fireEvent.click(screen.getAllByTestId("nav-operations")[0]);
  fireEvent.click(await screen.findByTestId("todo-open-decision_sim"));
  expect(await screen.findByTestId("recommendation-workspace")).toBeInTheDocument();
  expect(await screen.findByTestId("recommendation-card")).toHaveTextContent("Simulated spot volatility");
  expect(fetch).toHaveBeenCalledWith("/v1/recommendations/rec_sim", undefined);
}, 30_000);

test("keeps operations overview usable when action center is unavailable", async () => {
  operationActionCenterShouldFail = true;
  render(<App />);
  fireEvent.click(screen.getAllByTestId("nav-operations")[0]);

  expect(await screen.findByTestId("operations-workspace")).toBeInTheDocument();
  expect(await screen.findByTestId("operation-overall-status")).toHaveTextContent("critical");
  expect(screen.getByTestId("operation-action-center")).toHaveTextContent("action center API is unavailable");
  expect(screen.getByTestId("operation-freshness")).toHaveTextContent("BENCH Dispatch Research Benchmark");
});

test("imports a preserved market artifact into the policy knowledge library", async () => {
  render(<App />);
  await openResearchWorkspace();

  await waitFor(() => {
    expect(screen.getByTestId("policy-corpus-overview")).toHaveTextContent("Embedding 覆盖");
  });
  expect(await screen.findByTestId("import-artifact-market_artifact_policy")).toBeInTheDocument();
  expect(screen.getByTestId("preserved-artifacts")).toHaveTextContent("Official policy page");
  fireEvent.click(await screen.findByTestId("import-artifact-market_artifact_policy"));

  await waitFor(() => {
    expect(screen.getByText(/已转入知识库：knowledge_policy，2 个分块，外部处理默认禁用/)).toBeInTheDocument();
  });
  expect(await screen.findByTestId("policy-document-detail")).toHaveTextContent("raw_policy");
  expect(screen.getByTestId("policy-document-provenance")).toHaveTextContent("market_artifact_policy");
  expect(screen.getByTestId("policy-document-provenance")).toHaveTextContent("southern_energy_regulator");
  expect(fetch).toHaveBeenCalledWith(
    "/v1/policy/documents/from-market-artifact/market_artifact_policy",
    { method: "POST" },
  );
}, 30_000);

test("renders policy corpus detail and evidence citations with provenance labels", async () => {
  render(<App />);
  await openResearchWorkspace();

  fireEvent.click(await screen.findByTestId("document-detail-knowledge_policy"));
  expect(await screen.findByTestId("policy-document-detail")).toHaveTextContent("official_policy");
  expect(screen.getByTestId("policy-document-detail")).toHaveTextContent("外发禁用");
  expect(screen.getByTestId("policy-document-provenance")).toHaveTextContent("southern_regulator_downloads");

  fireEvent.change(screen.getByPlaceholderText("询问政策变化、风险或证据来源"), {
    target: { value: "政策影响是什么" },
  });
  fireEvent.click(screen.getByRole("button", { name: /提交问题/ }));

  expect(await screen.findByText("Evidence-backed policy answer.")).toBeInTheDocument();
  expect(screen.getByText(/Official policy page · official_policy · Example Energy Regulator/)).toBeInTheDocument();
  expect(screen.getByText("已排除 1 个未授权分块")).toBeInTheDocument();
}, 15_000);

test("keeps research workspace usable when preserved artifact list is unavailable", async () => {
  marketArtifactsShouldFail = true;
  render(<App />);
  await openResearchWorkspace();

  expect(await screen.findByTestId("research-workspace")).toBeInTheDocument();
  expect(await screen.findByText("证据问答")).toBeInTheDocument();
  expect(await screen.findByText("已保全原文列表暂不可用；资料库、来源健康和 BENCH 研究视图不受影响。")).toBeInTheDocument();
});

test("keeps research workspace usable when corpus overview or detail is unavailable", async () => {
  corpusOverviewShouldFail = true;
  documentDetailShouldFail = true;
  render(<App />);
  await openResearchWorkspace();

  expect(await screen.findByTestId("research-workspace")).toBeInTheDocument();
  expect(await screen.findByText("语料库健康状态暂不可用；资料列表、来源健康和 BENCH 研究视图不受影响。")).toBeInTheDocument();
  fireEvent.click(await screen.findByTestId("document-detail-knowledge_policy"));
  expect(await screen.findByText("文档详情暂不可用，请检查本地 API 状态。")).toBeInTheDocument();
  expect(screen.getByTestId("source-health")).toBeInTheDocument();
});

test("renders forecast research observability and triggers fixed baseline backtests", async () => {
  render(<App />);
  await openResearchWorkspace();

  expect(await screen.findByTestId("forecast-research-dashboard")).toHaveTextContent("Forecast Research");
  expect(await screen.findByTestId("forecast-overview-status")).toHaveTextContent("candidate model runs");
  expect(await screen.findByTestId("forecast-import-runs")).toHaveTextContent("accepted");
  expect(await screen.findByTestId("forecast-model-runs")).toHaveTextContent("seasonal_naive");
  expect(screen.getByTestId("forecast-research-dashboard")).toHaveTextContent("recommendation isolated");
  expect(screen.getByTestId("forecast-research-dashboard")).toHaveTextContent("research_only");
  expect(await screen.findByTestId("forecast-review-package")).toHaveTextContent("Review package");
  expect(screen.getByTestId("forecast-review-package")).toHaveTextContent("forecast_research_review_package_v1");
  expect(screen.getByTestId("forecast-review-package")).toHaveTextContent("scenario_simulated");
  expect(screen.getByTestId("forecast-review-package-summary")).toHaveTextContent("0 issues");
  expect(screen.getByTestId("forecast-review-package-download")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /Show predictions/ }));
  expect(await screen.findByTestId("forecast-prediction-chart")).toBeInTheDocument();

  fireEvent.click(await screen.findByTestId("forecast-run-seasonal_naive"));

  await waitFor(() => {
    expect(requestJsonBody("/v1/forecasting/research/datasets/forecast_dataset_test/backtests")).toEqual({
      model_key: "seasonal_naive",
      evaluation_days: 3,
      lag_days: 7,
      lookback_days: 7,
    });
  });
}, 15_000);

test("imports a local forecast CSV into the research-only manual endpoint", async () => {
  render(<App />);
  await openResearchWorkspace();

  const file = new File(
    [
      [
        "interval_start,price,source_note",
        "2026-01-01T00:00:00+08:00,100.5,local row",
        "2026-01-01T00:15:00+08:00,101.0,local row",
      ].join("\n"),
    ],
    "operator_curve.csv",
    { type: "text/csv" },
  );

  fireEvent.change(await screen.findByTestId("forecast-import-file-input"), {
    target: { files: [file] },
  });

  expect(await screen.findByTestId("forecast-import-preview")).toHaveTextContent("operator_curve.csv");
  expect(screen.getByTestId("forecast-import-workbench")).toHaveTextContent("research_only");
  expect(screen.getByTestId("forecast-import-warnings")).toHaveTextContent("Ignored CSV columns");

  fireEvent.click(screen.getByTestId("forecast-import-submit"));

  await waitFor(() => {
    expect(requestJsonBody("/v1/forecasting/research/datasets/manual")).toMatchObject({
      name: "operator_curve",
      data_mode: "user_uploaded",
      usage_scope: "research_only",
      interval_minutes: 15,
      points: [
        { interval_start: "2026-01-01T00:00:00+08:00", price: "100.5" },
        { interval_start: "2026-01-01T00:15:00+08:00", price: "101.0" },
      ],
    });
  });
  expect(await screen.findByTestId("forecast-import-success")).toHaveTextContent("forecast_dataset_uploaded");
  expect(await screen.findByTestId("forecast-import-runs")).toHaveTextContent("accepted");
}, 15_000);

test("does not submit forecast import files that fail local preview validation", async () => {
  render(<App />);
  await openResearchWorkspace();

  const file = new File(
    ["interval_start,price\n2026-01-01T00:00:00,not-a-price"],
    "bad_curve.csv",
    { type: "text/csv" },
  );

  fireEvent.change(await screen.findByTestId("forecast-import-file-input"), {
    target: { files: [file] },
  });

  expect(await screen.findByTestId("forecast-import-error")).toHaveTextContent("timezone offset");
  expect(screen.getByTestId("forecast-import-submit")).toBeDisabled();
  expect(vi.mocked(fetch).mock.calls.some(([path]) =>
    String(path).endsWith("/v1/forecasting/research/datasets/manual"),
  )).toBe(false);
});

test("keeps forecast research dashboard usable when manual import fails", async () => {
  forecastManualImportShouldFail = true;
  render(<App />);
  await openResearchWorkspace();

  const file = new File(
    ["interval_start,price\n2026-01-01T00:00:00+08:00,100"],
    "quality_failed.csv",
    { type: "text/csv" },
  );

  fireEvent.change(await screen.findByTestId("forecast-import-file-input"), {
    target: { files: [file] },
  });
  fireEvent.click(await screen.findByTestId("forecast-import-submit"));

  expect(await screen.findByTestId("forecast-import-error")).toHaveTextContent("Forecast dataset import failed");
  expect(screen.getByTestId("forecast-model-runs")).toHaveTextContent("seasonal_naive");
});

test("keeps forecast research dashboard usable when a baseline backtest fails", async () => {
  forecastBacktestShouldFail = true;
  render(<App />);
  await openResearchWorkspace();

  fireEvent.click(await screen.findByTestId("forecast-run-calendar_mean"));

  expect(await screen.findByTestId("forecast-backtest-error")).toHaveTextContent("Baseline backtest failed");
  expect(screen.getByTestId("forecast-model-runs")).toHaveTextContent("seasonal_naive");
});

test("reports artifact-to-knowledge import failures", async () => {
  render(<App />);
  await openResearchWorkspace();

  fireEvent.click(await screen.findByTestId("import-artifact-market_artifact_rejected"));

  expect(await screen.findByText("保全原文转入知识库失败，请检查媒体类型、正文内容或 research_only 限制。")).toBeInTheDocument();
});

test("keeps polling retry_wait runs across the backend retry delay", () => {
  const retryWaitRun = {
    ...queuedRun,
    status: "retry_wait",
    available_at: "2026-06-02T08:01:00+08:00",
  };
  const now = Date.parse("2026-06-02T08:00:00+08:00");

  expect(nextPollDelayMilliseconds(retryWaitRun, now)).toBe(5_000);
  expect(nextPollDelayMilliseconds({ ...retryWaitRun, available_at: "invalid" }, now)).toBe(750);
  expect(nextPollDelayMilliseconds(queuedRun, now)).toBe(750);
});
