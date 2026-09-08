export type Citation = {
  document_id: string;
  chunk_id: string;
  title: string;
  source_name: string;
  source_url: string | null;
  document_layer: string;
  data_mode: string;
};

export type PolicyWatchItem = {
  watch_id: string;
  title: string;
  observation: string;
  excerpt: string;
  citation: Citation;
  captured_at: string;
  source_role: "official_policy" | "official_market_notice" | "supplemental_research";
  external_processing_allowed: boolean;
  score: number;
};

export type PolicyWatchResponse = {
  generated_at: string;
  items: PolicyWatchItem[];
  missing_information: string[];
  excluded_restricted_chunks: number;
  local_only: boolean;
  no_auto_trading: boolean;
};

export type Brief = {
  brief_id: string;
  target_date: string;
  generated_at: string;
  status: string;
  human_review_status: string;
  risk_level: string;
  confidence_score: number;
  deterministic_facts: Record<string, unknown>;
  narrative: Record<string, unknown>;
  citations: Citation[];
  policy_watch: PolicyWatchItem[];
  missing_information: string[];
  llm_used: boolean;
  llm_model: string | null;
  no_auto_trading: boolean;
};

export type BriefSummary = {
  brief_id: string;
  target_date: string;
  generated_at: string;
  human_review_status: string;
  risk_level: string;
  confidence_score: number;
  policy_watch_count: number;
  missing_information_count: number;
  llm_used: boolean;
  no_auto_trading: boolean;
};

export type BriefReview = {
  review_id: string;
  brief_id: string;
  actor: string;
  review_status: "approved" | "needs_revision";
  note: string;
  created_at: string;
};

export type BriefDetail = Brief & {
  reviews: BriefReview[];
};

export type OperationJob = {
  job_key: string;
  description: string;
  schedule: string;
  timezone: string;
  research_only: boolean;
  manual_trigger_enabled: boolean;
};

export type OperationsStatus = "healthy" | "warning" | "critical";

export type WorkflowRun = {
  workflow_run_id: string;
  workflow_key: string;
  scheduled_for: string | null;
  status: string;
  started_at: string;
  available_at: string;
  claimed_at: string | null;
  lease_expires_at: string | null;
  worker_id: string | null;
  attempt_count: number;
  completed_at: string | null;
  summary: Record<string, unknown>;
  error_code: string | null;
  error_message: string | null;
};

export type HealthItem = {
  key: string;
  label: string;
  status: OperationsStatus;
  message: string;
  observed_at: string | null;
  details: Record<string, unknown>;
};

export type FreshnessItem = {
  key: string;
  label: string;
  status: OperationsStatus;
  message: string;
  latest_at: string | null;
  age_hours: number | null;
  data_mode: string | null;
  research_only: boolean;
  details: Record<string, unknown>;
};

export type ActionItem = {
  job_key: string;
  label: string;
  description: string;
  schedule: string;
  timezone: string;
  manual_trigger_enabled: boolean;
  research_only: boolean;
  recommended: boolean;
  reason: string;
};

export type WorkflowOverview = {
  counts: Record<string, number>;
  queued: number;
  running: number;
  retry_wait: number;
  failed: number;
  stale_lease_count: number;
  failed_last_24h: number;
  status: OperationsStatus;
};

export type OperationOverview = {
  generated_at: string;
  overall_status: OperationsStatus;
  workflow_overview: WorkflowOverview;
  freshness: FreshnessItem[];
  health: HealthItem[];
  actions: ActionItem[];
  recent_runs: WorkflowRun[];
  recent_incidents: WorkflowRun[];
  no_auto_trading: boolean;
};

export type OperationTodoCategory =
  | "workflow"
  | "brief_review"
  | "recommendation_review"
  | "decision_feedback"
  | "data_freshness"
  | "weather_feature_review"
  | "market_artifact_review"
  | "policy_document_review";

export type OperationTodoItem = {
  item_id: string;
  category: OperationTodoCategory;
  severity: OperationsStatus;
  title: string;
  message: string;
  target_type: string;
  target_id: string;
  navigation_target_type: string | null;
  navigation_target_id: string | null;
  created_at: string | null;
  latest_at: string | null;
  recommended_action: string;
  job_key: string | null;
  review_target_type: string | null;
  allowed_review_statuses: string[];
  default_review_note: string | null;
};

export type OperationTodoCounts = {
  total: number;
  critical: number;
  warning: number;
  by_category: Record<string, number>;
};

export type OperationActionCenter = {
  generated_at: string;
  status: OperationsStatus;
  counts: OperationTodoCounts;
  items: OperationTodoItem[];
  no_auto_trading: boolean;
};

export type OperationsReviewPackage = {
  package_version: string;
  generated_at: string;
  overview: OperationOverview;
  action_center: OperationActionCenter;
  system_readiness: SystemReadiness;
  recent_runs: WorkflowRun[];
  fixed_job_keys: string[];
  no_auto_trading: boolean;
  manual_job_keys_only: boolean;
  network_probe_performed: boolean;
  fetch_performed: boolean;
};

export type WeatherFeatureSnapshot = {
  feature_snapshot_id: string;
  ingestion_run_id: string;
  raw_payload_id: string;
  provider: string;
  location_id: string;
  generated_at: string;
  forecast_start: string | null;
  feature_version: string;
  quality_status: string;
  human_review_status: string;
  features: Record<string, number | null>;
  evidence: Record<string, unknown>[];
  missing_data_warnings: string[];
  data_mode: string;
};

export type WeatherQualityIssue = {
  quality_issue_id: string;
  ingestion_run_id: string;
  raw_payload_id: string;
  weather_record_id: string | null;
  provider: string;
  location_id: string;
  forecast_time: string | null;
  variable: string | null;
  issue_code: string;
  severity: string;
  message: string;
  details: Record<string, unknown>;
  data_mode: string;
};

export type WeatherFeatureReview = {
  review_id: string;
  feature_snapshot_id: string;
  created_at: string;
  actor: string;
  review_status: string;
  note: string;
};

export type WeatherQualityIssueSummary = {
  total_count: number;
  severity_counts: Record<string, number>;
  issue_code_counts: Record<string, number>;
  displayed_issue_count: number;
};

export type WeatherFeatureApprovalSummary = {
  can_approve: boolean;
  blockers: string[];
  required_features: string[];
};

export type WeatherFeatureReviewPackage = {
  package_version: string;
  generated_at: string;
  snapshot: WeatherFeatureSnapshot;
  quality_issue_summary: WeatherQualityIssueSummary;
  quality_issues: WeatherQualityIssue[];
  reviews: WeatherFeatureReview[];
  approval: WeatherFeatureApprovalSummary;
  no_auto_trading: boolean;
  recommendation_chain_requires_approved_snapshot: boolean;
  network_probe_performed: boolean;
  fetch_performed: boolean;
};

export type DemoSeedSummary = {
  seed_key: string;
  created: Record<string, boolean>;
  object_ids: Record<string, string>;
  data_modes: Record<string, string>;
  research_only: boolean;
  no_auto_trading: boolean;
};

export type SystemReadinessCheck = {
  key: string;
  label: string;
  status: OperationsStatus;
  message: string;
  details: Record<string, unknown>;
};

export type SystemReadiness = {
  generated_at: string;
  status: OperationsStatus;
  checks: SystemReadinessCheck[];
  demo_seed: DemoSeedSummary | null;
  table_counts: Record<string, number>;
  missing_demo_items: string[];
  recommended_actions: string[];
  no_auto_trading: boolean;
};

export type KnowledgeDocument = {
  document_id: string;
  title: string;
  document_layer: string;
  trust_tier: string;
  source_name: string;
  source_url: string | null;
  media_type: string;
  captured_at: string;
  external_processing_allowed: boolean;
  human_review_status: string;
  data_mode: string;
};

export type KnowledgeCorpusLayerSummary = {
  document_layer: string;
  document_count: number;
  chunk_count: number;
  embedded_chunk_count: number;
  embedding_coverage: number;
  external_processing_allowed_count: number;
  latest_captured_at: string | null;
};

export type KnowledgeCorpusOverview = {
  generated_at: string;
  status: OperationsStatus;
  message: string;
  document_count: number;
  version_count: number;
  chunk_count: number;
  embedded_chunk_count: number;
  embedding_coverage: number;
  external_processing_allowed_count: number;
  external_processing_blocked_count: number;
  artifact_provenance_count: number;
  layers: KnowledgeCorpusLayerSummary[];
  recent_documents: KnowledgeDocument[];
  network_probe_performed: boolean;
  fetch_performed: boolean;
  no_auto_trading: boolean;
};

export type KnowledgeDocumentVersionSummary = {
  version_id: string;
  version_number: number;
  content_sha256: string;
  parser_key: string;
  raw_object_id: string;
  parsed_character_count: number;
  created_at: string;
};

export type KnowledgeRawObjectSummary = {
  raw_object_id: string;
  content_sha256: string;
  storage_backend: string;
  bucket_name: string;
  object_key: string;
  media_type: string;
  byte_length: number;
  source_url: string | null;
  captured_at: string;
  data_mode: string;
};

export type KnowledgeArtifactProvenance = {
  artifact_id: string;
  artifact_content_sha256: string | null;
  artifact_captured_at: string | null;
  source_id: string | null;
  source_name: string | null;
  source_trust_tier: string | null;
  source_market_scope: string | null;
  endpoint_id: string | null;
  endpoint_name: string | null;
  endpoint_kind: string | null;
  endpoint_data_granularity: string | null;
  source_url: string | null;
};

export type KnowledgeDocumentDetail = KnowledgeDocument & {
  published_at: string | null;
  effective_at: string | null;
  external_processing_allowed_default: boolean;
  latest_version: KnowledgeDocumentVersionSummary | null;
  raw_object: KnowledgeRawObjectSummary | null;
  chunk_count: number;
  embedded_chunk_count: number;
  embedding_coverage: number;
  artifact_provenance: KnowledgeArtifactProvenance[];
  raw_download_available: boolean;
};

export type KnowledgeChunk = {
  chunk_id: string;
  ordinal: number;
  content: string;
  character_count: number;
  embedding_model: string | null;
};

export type KnowledgeDocumentReview = {
  review_id: string;
  document_id: string;
  created_at: string;
  actor: string;
  review_status: string;
  note: string;
};

export type KnowledgeDocumentReviewPackageChunkSummary = {
  total_count: number;
  embedded_count: number;
  embedding_coverage: number;
  displayed_chunk_count: number;
};

export type KnowledgeDocumentReviewPackageChunk = {
  chunk_id: string;
  ordinal: number;
  content_sha256: string;
  character_count: number;
  embedding_model: string | null;
  content_excerpt: string;
};

export type KnowledgeDocumentReviewPackage = {
  package_version: string;
  generated_at: string;
  document: KnowledgeDocumentDetail;
  chunk_summary: KnowledgeDocumentReviewPackageChunkSummary;
  displayed_chunks: KnowledgeDocumentReviewPackageChunk[];
  reviews: KnowledgeDocumentReview[];
  review_count: number;
  external_processing_allowed: boolean;
  external_processing_allowed_default: boolean;
  raw_payload_included: boolean;
  server_artifact_written: boolean;
  no_auto_trading: boolean;
  recommendation_chain_isolated: boolean;
  network_probe_performed: boolean;
  fetch_performed: boolean;
  external_model_call_performed: boolean;
};

export type MarketSource = {
  source_id: string;
  name: string;
  trust_tier: string;
  official_url: string;
  collection_permission_note: string;
};

export type MarketEndpoint = {
  endpoint_id: string;
  name: string;
  lifecycle_status: string;
  collection_enabled: boolean;
};

export type MarketIngestionRun = {
  ingestion_run_id: string;
  source_id: string;
  endpoint_id: string;
  trigger_mode: string;
  adapter_key: string | null;
  adapter_version: string | null;
  started_at: string;
  completed_at: string;
  status: string;
  items_received: number;
  items_inserted: number;
  duplicate_items: number;
  rejected_items: number;
  quality_status: string;
  quality_issue_count: number;
  error_code: string | null;
  error_message: string | null;
};

export type MarketRawArtifact = {
  artifact_id: string;
  source_id: string;
  endpoint_id: string;
  source_url: string;
  title: string | null;
  media_type: string;
  storage_backend: string;
  inline_text: string | null;
  object_key: string | null;
  content_sha256: string;
  byte_length: number;
  published_at: string | null;
  captured_at: string;
  ingestion_method: string;
  transport_security_status: string;
  human_review_status: string;
  data_mode: string;
};

export type MarketQualityIssue = {
  quality_issue_id: string;
  source_id: string;
  endpoint_id: string | null;
  ingestion_run_id: string | null;
  ingestion_run_item_id: string | null;
  parsing_run_id: string | null;
  endpoint_health_check_id: string | null;
  artifact_id: string | null;
  issue_scope: string;
  issue_code: string;
  severity: string;
  message: string;
  details: Record<string, unknown>;
  data_mode: string;
};

export type MarketQualityIssueSummary = {
  total_count: number;
  severity_counts: Record<string, number>;
  issue_code_counts: Record<string, number>;
  displayed_issue_count: number;
};

export type MarketArtifactReview = {
  review_id: string;
  artifact_id: string;
  created_at: string;
  actor: string;
  review_status: string;
  note: string;
};

export type MarketParsingRun = {
  parsing_run_id: string;
  artifact_id: string;
  parser_key: string;
  parser_version: string;
  started_at: string;
  completed_at: string;
  status: string;
  observations_parsed: number;
  observations_inserted: number;
  duplicate_observations: number;
  quality_status: string;
  quality_issue_count: number;
  error_code: string | null;
  error_message: string | null;
};

export type MarketArtifactReviewPackageArtifact = Omit<MarketRawArtifact, "inline_text"> & {
  inline_text_available: boolean;
};

export type MarketArtifactReviewPackage = {
  package_version: string;
  generated_at: string;
  artifact: MarketArtifactReviewPackageArtifact;
  source: (MarketSource & {
    operator_name?: string;
    market_scope?: string;
    data_mode?: string;
    attribution_text?: string;
  }) | null;
  endpoint: (MarketEndpoint & {
    source_id?: string;
    canonical_url?: string;
    access_mode?: string;
    lifecycle_status?: string;
    manual_submission_enabled?: boolean;
    collection_enabled?: boolean;
  }) | null;
  quality_issue_summary: MarketQualityIssueSummary;
  quality_issues: MarketQualityIssue[];
  reviews: MarketArtifactReview[];
  parsing_runs: MarketParsingRun[];
  no_auto_trading: boolean;
  recommendation_chain_isolated: boolean;
  network_probe_performed: boolean;
  fetch_performed: boolean;
  parse_performed: boolean;
};

export type QuestionAnswer = {
  answer: string;
  citations: Citation[];
  missing_information: string[];
  excluded_restricted_chunks: number;
  human_review_required: boolean;
  llm_used: boolean;
};

export type ForecastDataset = {
  dataset_id: string;
  name: string;
  source_name?: string;
  source_url?: string;
  region_code: string;
  region_name: string;
  market_scope: string;
  market_stage?: string;
  price_scope?: string;
  interval_minutes?: number;
  timezone?: string;
  currency?: string;
  price_unit?: string;
  data_mode: string;
  usage_scope: string;
  content_sha256?: string;
  imported_at: string;
  quality_status?: string;
  quality_issue_count?: number;
  normalized_point_count?: number;
  trade_date_count?: number;
  notes?: string;
};

export type ForecastPoint = {
  interval_start: string;
  trade_date?: string;
  interval_index?: number;
  price: string;
  data_mode?: string;
};

export type ForecastImportPointPayload = {
  interval_start: string;
  price: string;
};

export type ForecastImportPreviewPoint = ForecastImportPointPayload & {
  source_row?: number;
};

export type ManualForecastDatasetPayload = {
  name: string;
  source_name: string;
  source_url: string;
  region_code: string;
  region_name: string;
  market_scope: string;
  market_stage: "day_ahead" | "real_time" | "other";
  price_scope: string;
  interval_minutes: 15;
  timezone: string;
  currency: string;
  price_unit: string;
  data_mode: "public_observed" | "public_derived" | "scenario_simulated" | "user_uploaded";
  usage_scope: "research_only";
  notes: string;
  points: ForecastImportPointPayload[];
};

export type ManualForecastDatasetImportResult = {
  import_run_id: string;
  dataset_id: string;
  status: string;
  duplicate_dataset: boolean;
  quality_status: string;
  quality_issue_count: number;
  submitted_point_count: number;
  normalized_point_count: number;
  trade_date_count: number;
  content_sha256: string;
  data_mode: ManualForecastDatasetPayload["data_mode"];
  usage_scope: "research_only";
};

export type ForecastImportPreview = {
  file_name: string;
  point_count: number;
  date_count: number;
  date_range: string;
  duplicate_interval_count: number;
  incomplete_trade_date_count: number;
  timezone_issue_count: number;
  invalid_price_count: number;
  min_price: number | null;
  max_price: number | null;
  ignored_columns: string[];
  sample_points: ForecastImportPreviewPoint[];
  metadata: Partial<Omit<ManualForecastDatasetPayload, "points">>;
  points: ForecastImportPreviewPoint[];
  errors: string[];
  warnings: string[];
};

export type ForecastImportRun = {
  import_run_id: string;
  dataset_id: string;
  started_at: string;
  completed_at: string;
  status: string;
  submitted_point_count: number;
  normalized_point_count: number;
  quality_status: string;
  quality_issue_count: number;
  data_mode: string;
  error_code: string | null;
  error_message: string | null;
};

export type ForecastQualityIssue = {
  quality_issue_id: string;
  dataset_id: string;
  issue_code: string;
  severity: string;
  message: string;
  created_at?: string;
  details?: Record<string, unknown>;
  data_mode: string;
};

export type ForecastModelRun = {
  model_run_id: string;
  dataset_id: string;
  model_key: string;
  model_version?: string;
  feature_version?: string;
  started_at?: string;
  completed_at: string;
  status: string;
  registry_status: string;
  train_start?: string;
  train_end?: string;
  evaluation_start?: string;
  evaluation_end?: string;
  horizon_intervals?: number;
  parameters?: Record<string, unknown>;
  metrics: Record<string, unknown>;
  artifact_path?: string | null;
  usage_scope: string;
  data_mode: string;
  error_code?: string | null;
  error_message?: string | null;
};

export type ForecastPrediction = {
  prediction_id: string;
  model_run_id: string;
  target_interval_start: string;
  trade_date: string;
  interval_index: number;
  actual_price: string;
  predicted_price: string;
  data_mode: string;
};

export type ForecastResearchOverview = {
  generated_at: string;
  status: OperationsStatus;
  message: string;
  dataset_count: number;
  valid_dataset_count: number;
  invalid_dataset_count: number;
  research_only_dataset_count: number;
  candidate_model_run_count: number;
  succeeded_model_run_count: number;
  bench_expected_regions: string[];
  bench_available_regions: string[];
  bench_missing_regions: string[];
  bench_region_count: number;
  datasets: ForecastDataset[];
  recent_import_runs: ForecastImportRun[];
  recent_model_runs: ForecastModelRun[];
  recent_quality_issues: ForecastQualityIssue[];
  no_auto_trading: boolean;
  recommendation_chain_isolated: boolean;
  network_probe_performed: boolean;
  fetch_performed: boolean;
};

export type ForecastQualityIssueSummary = {
  total_count: number;
  severity_counts: Record<string, number>;
  issue_code_counts: Record<string, number>;
  displayed_issue_count: number;
};

export type ForecastReviewPackage = {
  package_version: string;
  generated_at: string;
  dataset: ForecastDataset;
  import_runs: ForecastImportRun[];
  quality_issue_summary: ForecastQualityIssueSummary;
  quality_issues: ForecastQualityIssue[];
  model_runs: ForecastModelRun[];
  no_auto_trading: boolean;
  recommendation_chain_isolated: boolean;
  network_probe_performed: boolean;
  fetch_performed: boolean;
};

export type Evidence = {
  source: string;
  source_type: string;
  data_mode: string;
  timestamp: string;
  field: string;
  value: string | number | boolean;
  unit: string | null;
  confidence: number;
  url: string | null;
  note: string | null;
};

export type HydroScenario = {
  scenario_id: string;
  asset_name: string;
  data_mode: string;
  installed_capacity_mw: number;
  firm_output_mw: number;
  current_water_level_m: number;
  available_energy_mwh: number;
  assumptions: string[];
  warning: string;
};

export type HydroOptimizationPricePoint = {
  interval_index: number;
  price: string;
};

export type HydroOptimizationPayload = {
  trade_date: string;
  asset_id?: string;
  scenario_id?: string;
  energy_budget_mwh?: number;
  min_output_mw?: number;
  max_output_mw?: number;
  price_signal?: HydroOptimizationPricePoint[];
};

export type HydroOptimizationInterval = {
  interval_index: number;
  interval_start: string;
  target_output_mw: number;
  energy_mwh: number;
  price_signal: string | null;
  priority_rank: number | null;
  binding_constraints: string[];
};

export type HydroOptimizationRun = {
  optimization_run_id: string;
  created_at: string;
  trade_date: string;
  asset_id: string;
  scenario_id: string;
  algorithm_key: "deterministic_priority_v1";
  data_mode: "scenario_simulated";
  energy_budget_mwh: number;
  min_output_mw: number;
  max_output_mw: number;
  price_signal_used: boolean;
  intervals: HydroOptimizationInterval[];
  top_priority_intervals: HydroOptimizationInterval[];
  missing_data_warnings: string[];
  constraint_explanation: string[];
  evidence: Evidence[];
  request_snapshot: Record<string, unknown>;
  constraints: Record<string, unknown>;
  human_review_required: boolean;
  no_auto_trading: boolean;
};

export type RecommendedWindow = {
  time: string;
  stance: string;
  reason: string;
};

export type RecommendationReview = {
  review_id: string;
  created_at: string;
  actor: string;
  review_status: string;
  note: string;
};

export type RecommendationAuditStatus = "healthy" | "warning" | "critical";

export type RecommendationAuditCheck = {
  key: string;
  label: string;
  status: RecommendationAuditStatus;
  message: string;
  details: Record<string, unknown>;
};

export type RecommendationEvidenceSummary = {
  evidence_count: number;
  missing_data_count: number;
  data_modes: Record<string, number>;
  source_types: Record<string, number>;
  weather_evidence_present: boolean;
  incomplete_evidence_count: number;
  research_only_evidence_count: number;
  bench_evidence_count: number;
  policy_watch_evidence_count: number;
};

export type Recommendation = {
  recommendation_id: string;
  input_snapshot_id: string;
  trade_date: string;
  created_at: string;
  data_mode: string;
  market_view: string;
  hydro_action: string;
  risk_level: string;
  confidence: number;
  review_status: string;
  recommended_windows: RecommendedWindow[];
  missing_data_warnings: string[];
  evidence: Evidence[];
  no_auto_trading: boolean;
};

export type RecommendationDetail = Recommendation & {
  reviews: RecommendationReview[];
};

export type RecommendationAudit = {
  recommendation_id: string;
  generated_at: string;
  audited_at: string;
  review_status: string;
  overall_status: RecommendationAuditStatus;
  evidence_summary: RecommendationEvidenceSummary;
  checks: RecommendationAuditCheck[];
  recommended_actions: string[];
  human_check_required: boolean;
  no_auto_trading: boolean;
};

export type RecommendationEvidenceExport = {
  recommendation_id: string;
  input_snapshot_id: string;
  trade_date: string;
  asset_id: string;
  scenario_id: string;
  generated_at: string;
  exported_at: string;
  review_status: string;
  audit_status: RecommendationAuditStatus;
  data_mode: string;
  risk_level: string;
  confidence: number;
  human_check_required: boolean;
  no_auto_trading: boolean;
  missing_data_warnings: string[];
  evidence_summary: RecommendationEvidenceSummary;
  checks: RecommendationAuditCheck[];
  recommended_actions: string[];
  evidence: Evidence[];
};

export type RecommendationDecisionFeedback = {
  feedback_id: string;
  decision_id: string;
  recommendation_id: string;
  created_at: string;
  actor: string;
  outcome_status: "pending_observation" | "useful" | "neutral" | "not_useful" | "uncertain";
  observed_at: string | null;
  note: string;
  data_mode: string;
};

export type RecommendationDecision = {
  decision_id: string;
  recommendation_id: string;
  created_at: string;
  actor: string;
  decision_status: "adopted" | "partially_adopted" | "not_adopted" | "deferred";
  selected_windows: string[];
  note: string;
  safety_boundary_acknowledged: boolean;
  no_auto_trading: boolean;
  audit_snapshot: Record<string, unknown>;
  feedback: RecommendationDecisionFeedback[];
};

export type RecommendationFeedbackAnalyticsSummary = {
  recommendation_count: number;
  decision_count: number;
  feedback_count: number;
  pending_observation_count: number;
  critical_audit_not_adopted_count: number;
  no_auto_trading_false_count: number;
  safety_boundary_unacknowledged_count: number;
  audit_status_counts: Record<string, number>;
  review_status_counts: Record<string, number>;
  decision_status_counts: Record<string, number>;
  outcome_status_counts: Record<string, number>;
  feedback_data_modes: Record<string, number>;
};

export type RecommendationFeedbackAnalyticsDecision = {
  decision_id: string;
  recommendation_id: string;
  created_at: string;
  actor: string;
  decision_status: RecommendationDecision["decision_status"];
  audit_status: RecommendationAuditStatus | null;
  selected_windows: string[];
  note: string;
  no_auto_trading: boolean;
  safety_boundary_acknowledged: boolean;
  feedback_count: number;
  latest_outcome_status: RecommendationDecisionFeedback["outcome_status"] | null;
  latest_feedback_at: string | null;
};

export type RecommendationFeedbackAnalyticsFeedback = {
  feedback_id: string;
  decision_id: string;
  recommendation_id: string;
  created_at: string;
  actor: string;
  decision_status: RecommendationDecision["decision_status"] | null;
  outcome_status: RecommendationDecisionFeedback["outcome_status"];
  observed_at: string | null;
  note: string;
  data_mode: string;
};

export type RecommendationFeedbackAnalytics = {
  generated_at: string;
  status: RecommendationAuditStatus;
  message: string;
  summary: RecommendationFeedbackAnalyticsSummary;
  recent_decisions: RecommendationFeedbackAnalyticsDecision[];
  recent_feedback: RecommendationFeedbackAnalyticsFeedback[];
  pending_observation_decisions: RecommendationFeedbackAnalyticsDecision[];
  critical_audit_not_adopted: RecommendationFeedbackAnalyticsDecision[];
  recommended_actions: string[];
  no_auto_trading: boolean;
};
