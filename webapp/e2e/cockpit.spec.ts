import { expect, test } from "@playwright/test";

const BENCH_REGIONS = [
  ["NSW1", "New South Wales"],
  ["QLD1", "Queensland"],
  ["SA1", "South Australia"],
  ["TAS1", "Tasmania"],
  ["VIC1", "Victoria"],
];

test("generates a deterministic brief when DeepSeek is unavailable", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveTitle("示例甲省电力智能研究台");
  await expect(page.getByTestId("nav-brief").first()).toHaveText("今日简报");
  await expect(page.getByTestId("nav-research").first()).toHaveText("证据与研究");
  await expect(page.getByTestId("nav-operations").first()).toHaveText("运行状态");
  await expect(page.getByTestId("nav-recommendation").first()).toHaveText("场景建议");
  await expect(page.locator("body")).not.toContainText(/骞夸笢|鐢靛姏|浠婃棩|绂佹/);
  await page.getByTestId("generate-brief").click();
  await expect(page.getByTestId("brief-llm-mode")).toHaveText("确定性回退");
  await expect(page.getByText("禁止自动交易")).toBeVisible();
});

test("keeps mobile navigation and simulated recommendation boundaries visible", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.locator('[data-testid="nav-recommendation"]:visible').click();
  await expect(page.getByTestId("recommendation-workspace")).toBeVisible();
  await expect(page.getByText("scenario_simulated")).toBeVisible();
  await expect(page.getByTestId("recommendation-isolation")).toContainText("不会提交交易");
  await expect(page.getByTestId("hydro-optimization-preview")).toContainText("水电约束预演");
  await expect(page.getByTestId("hydro-optimization-preview")).toContainText("不是调度指令或交易建议");
  await expect(page.getByTestId("hydro-price-signal")).toBeVisible();
  await expect(page.getByTestId("hydro-optimization-comparison")).toBeVisible();
});

test("shows operator overview and reruns a fixed failed job from mobile navigation", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  let demoSeeded = false;
  await page.route("**/v1/system/readiness", async (route) => {
    const missing = demoSeeded ? [] : ["weather_snapshot", "policy_document", "recommendation"];
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        generated_at: "2026-06-03T09:00:00+08:00",
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
        ],
        demo_seed: {
          seed_key: "mvp_rc_demo_v1",
          created: {},
          object_ids: demoSeeded ? { policy_document_id: "demo_rc_policy_document" } : {},
          data_modes: { recommendation: "scenario_simulated", forecast_dataset: "scenario_simulated" },
          research_only: true,
          no_auto_trading: true,
        },
        table_counts: { knowledge_documents: demoSeeded ? 1 : 0 },
        missing_demo_items: missing,
        recommended_actions: missing.length
          ? ["Run fixed job demo_research_workspace_seed to populate local RC fixtures."]
          : ["Review Action Center items and complete normal human review steps."],
        no_auto_trading: true,
      }),
    });
  });
  await page.route("**/v1/operations/overview", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        generated_at: "2026-06-03T09:00:00+08:00",
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
          {
            key: "policy_documents",
            label: "Policy Knowledge Library",
            status: "healthy",
            message: "Policy library is local/manual-only.",
            latest_at: null,
            age_hours: null,
            data_mode: null,
            research_only: false,
            details: { document_count: 0, manual_only: true },
          },
        ],
        health: [
          {
            key: "source_registry",
            label: "Source Registry",
            status: "healthy",
            message: "Registered source endpoints are present.",
            observed_at: null,
            details: { source_count: 4, disabled_count: 4 },
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
        actions: [{
          job_key: "policy_research_refresh",
          label: "Check Policy Research Sources",
          description: "Refresh enabled allowlisted policy sources.",
          schedule: "0 1,7,13,19 * * *",
          timezone: "Asia/Shanghai",
          manual_trigger_enabled: true,
          research_only: false,
          recommended: true,
          reason: "Recent failed or retry-wait run exists for this fixed job.",
        },
        {
          job_key: "demo_research_workspace_seed",
          label: "Seed Local RC Demo Data",
          description: "Seed local deterministic demo data for the v0.1 RC checklist.",
          schedule: "manual",
          timezone: "Asia/Shanghai",
          manual_trigger_enabled: true,
          research_only: false,
          recommended: false,
          reason: "Available for manual operator-triggered rerun.",
        }],
        recent_runs: [],
        recent_incidents: [{
          workflow_run_id: "workflow_ops_failed",
          workflow_key: "policy_research_refresh",
          trigger_mode: "prefect_schedule",
          prefect_flow_run_id: null,
          scheduled_for: "2026-06-03T07:00:00+08:00",
          status: "failed",
          started_at: "2026-06-03T07:00:00+08:00",
          available_at: "2026-06-03T07:01:00+08:00",
          claimed_at: "2026-06-03T07:00:01+08:00",
          lease_expires_at: null,
          worker_id: "worker-smoke",
          attempt_count: 1,
          completed_at: "2026-06-03T07:01:00+08:00",
          summary: { message: "adapter missing" },
          error_code: "policy_collection_adapter_not_registered",
          error_message: "adapter missing",
        }],
        no_auto_trading: true,
      }),
    });
  });
  await page.route("**/v1/operations/review-package", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        package_version: "operations_review_package_v1",
        generated_at: "2026-06-03T09:01:00+08:00",
        overview: {
          generated_at: "2026-06-03T09:00:00+08:00",
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
          freshness: [],
          health: [],
          actions: [{
            job_key: "policy_research_refresh",
            label: "Check Policy Research Sources",
            description: "Refresh enabled allowlisted policy sources.",
            schedule: "0 1,7,13,19 * * *",
            timezone: "Asia/Shanghai",
            manual_trigger_enabled: true,
            research_only: false,
            recommended: true,
            reason: "Recent failed or retry-wait run exists for this fixed job.",
          }],
          recent_runs: [],
          recent_incidents: [],
          no_auto_trading: true,
        },
        action_center: {
          generated_at: "2026-06-03T09:00:00+08:00",
          status: "critical",
          counts: {
            total: 2,
            critical: 1,
            warning: 1,
            by_category: { workflow: 1, data_freshness: 1 },
          },
          items: [],
          no_auto_trading: true,
        },
        system_readiness: {
          generated_at: "2026-06-03T09:00:00+08:00",
          status: "warning",
          checks: [],
          demo_seed: null,
          table_counts: {},
          missing_demo_items: [],
          recommended_actions: [],
          no_auto_trading: true,
        },
        recent_runs: [{
          workflow_run_id: "workflow_ops_failed",
          workflow_key: "policy_research_refresh",
          trigger_mode: "prefect_schedule",
          prefect_flow_run_id: null,
          scheduled_for: "2026-06-03T07:00:00+08:00",
          status: "failed",
          started_at: "2026-06-03T07:00:00+08:00",
          available_at: "2026-06-03T07:01:00+08:00",
          claimed_at: "2026-06-03T07:00:01+08:00",
          lease_expires_at: null,
          worker_id: "worker-smoke",
          attempt_count: 1,
          completed_at: "2026-06-03T07:01:00+08:00",
          summary: { message: "adapter missing" },
          error_code: "policy_collection_adapter_not_registered",
          error_message: "adapter missing",
        }],
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
      }),
    });
  });
  await page.route("**/v1/operations/action-center", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        generated_at: "2026-06-03T09:00:00+08:00",
        status: "critical",
        counts: {
          total: 4,
          critical: 1,
          warning: 3,
          by_category: {
            workflow: 1,
            weather_feature_review: 1,
            market_artifact_review: 1,
            policy_document_review: 1,
          },
        },
        items: [
          {
            item_id: "workflow:workflow_ops_failed",
            category: "workflow",
            severity: "critical",
            title: "Workflow failed: policy_research_refresh",
            message: "adapter missing",
            target_type: "workflow_run",
            target_id: "workflow_ops_failed",
            navigation_target_type: null,
            navigation_target_id: null,
            created_at: "2026-06-03T07:00:00+08:00",
            latest_at: "2026-06-03T07:01:00+08:00",
            recommended_action: "Review the run error, then rerun the fixed registered job if appropriate.",
            job_key: "policy_research_refresh",
            review_target_type: null,
            allowed_review_statuses: [],
            default_review_note: null,
          },
          {
            item_id: "weather_feature:weather_feature_pending",
            category: "weather_feature_review",
            severity: "warning",
            title: "Weather feature review: pending_review",
            message: "Weather feature snapshot weather_feature_pending needs operator review.",
            target_type: "weather_feature_snapshot",
            target_id: "weather_feature_pending",
            navigation_target_type: null,
            navigation_target_id: null,
            created_at: "2026-06-03T06:30:00+08:00",
            latest_at: "2026-06-03T06:30:00+08:00",
            recommended_action: "Review public-derived weather quality.",
            job_key: null,
            review_target_type: "weather_feature",
            allowed_review_statuses: ["approved", "needs_revision", "rejected"],
            default_review_note: "Reviewed from Action Center quick action.",
          },
          {
            item_id: "market_artifact:market_artifact_pending",
            category: "market_artifact_review",
            severity: "warning",
            title: "Market artifact review: pending_review",
            message: "Preserved artifact market_artifact_pending needs local review.",
            target_type: "market_raw_artifact",
            target_id: "market_artifact_pending",
            navigation_target_type: null,
            navigation_target_id: null,
            created_at: "2026-06-03T06:30:00+08:00",
            latest_at: "2026-06-03T06:30:00+08:00",
            recommended_action: "Review preserved public artifact provenance.",
            job_key: null,
            review_target_type: "market_artifact",
            allowed_review_statuses: ["approved", "needs_revision", "rejected"],
            default_review_note: "Reviewed from Action Center quick action.",
          },
          {
            item_id: "policy_document:demo_rc_policy_document",
            category: "policy_document_review",
            severity: "warning",
            title: "Policy document review: pending_review",
            message: "Knowledge document demo_rc_policy_document needs operator review.",
            target_type: "knowledge_document",
            target_id: "demo_rc_policy_document",
            navigation_target_type: null,
            navigation_target_id: null,
            created_at: "2026-06-03T08:00:00+08:00",
            latest_at: "2026-06-03T08:00:00+08:00",
            recommended_action: "Review document provenance and chunks.",
            job_key: null,
            review_target_type: "policy_document",
            allowed_review_statuses: ["approved", "needs_revision", "rejected"],
            default_review_note: "Reviewed from Action Center quick action.",
          },
        ],
        no_auto_trading: true,
      }),
    });
  });
  await page.route("**/v1/weather/features/weather_feature_pending/review-package", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        package_version: "weather_feature_review_package_v1",
        generated_at: "2026-06-03T09:01:00+08:00",
        snapshot: {
          feature_snapshot_id: "weather_feature_pending",
          ingestion_run_id: "weather_ingest_ops",
          raw_payload_id: "weather_raw_ops",
          provider: "open_meteo",
          location_id: "demo_hydro_a_reference",
          generated_at: "2026-06-03T06:30:00+08:00",
          forecast_start: "2026-06-03T00:00:00+08:00",
          feature_version: "hydro_weather_v1",
          quality_status: "warning",
          human_review_status: "pending_review",
          features: { precipitation_24h_mm: null },
          evidence: [],
          missing_data_warnings: ["precipitation_24h_mm missing"],
          data_mode: "public_derived",
        },
        quality_issue_summary: {
          total_count: 1,
          severity_counts: { warning: 1 },
          issue_code_counts: { missing_value: 1 },
          displayed_issue_count: 1,
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
      }),
    });
  });
  await page.route("**/v1/market/artifacts/market_artifact_pending/review-package", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        package_version: "market_artifact_review_package_v1",
        generated_at: "2026-06-03T09:01:00+08:00",
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
          captured_at: "2026-06-03T06:30:00+08:00",
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
        },
        endpoint: {
          endpoint_id: "reports_market_research",
          name: "REPORTS market research column",
          lifecycle_status: "blocked_tls",
          collection_enabled: false,
        },
        quality_issue_summary: {
          total_count: 1,
          severity_counts: { warning: 1 },
          issue_code_counts: { insecure_transport_source: 1 },
          displayed_issue_count: 1,
        },
        quality_issues: [{
          quality_issue_id: "market_quality_e2e",
          source_id: "example_region_power_exchange_center",
          endpoint_id: "reports_market_research",
          ingestion_run_id: "market_ingest_e2e",
          ingestion_run_item_id: "market_item_e2e",
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
      }),
    });
  });
  await page.route("**/v1/policy/documents/demo_rc_policy_document/review-package", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        package_version: "policy_document_review_package_v1",
        generated_at: "2026-06-03T09:01:00+08:00",
        document: {
          document_id: "demo_rc_policy_document",
          title: "Demo RC policy document",
          document_layer: "user_uploaded",
          trust_tier: "user_uploaded",
          source_name: "Local RC seed",
          source_url: null,
          media_type: "text/plain",
          published_at: null,
          effective_at: null,
          captured_at: "2026-06-03T08:00:00+08:00",
          data_mode: "user_uploaded",
          external_processing_allowed: false,
          external_processing_allowed_default: false,
          human_review_status: "pending_review",
          latest_version: {
            version_id: "demo_policy_version",
            version_number: 1,
            content_sha256: "b".repeat(64),
            parser_key: "plain_text",
            raw_object_id: "demo_policy_raw",
            parsed_character_count: 80,
            created_at: "2026-06-03T08:00:01+08:00",
          },
          raw_object: null,
          chunk_count: 1,
          embedded_chunk_count: 1,
          embedding_coverage: 1,
          artifact_provenance: [],
          raw_download_available: false,
        },
        chunk_summary: {
          total_count: 1,
          embedded_count: 1,
          embedding_coverage: 1,
          displayed_chunk_count: 1,
        },
        displayed_chunks: [{
          chunk_id: "demo_policy_chunk",
          ordinal: 0,
          content_sha256: "c".repeat(64),
          character_count: 80,
          embedding_model: "bge-m3",
          content_excerpt: "Demo local policy text.",
        }],
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
      }),
    });
  });
  await page.route("**/v1/operations/jobs/demo_research_workspace_seed/run", async (route) => {
    demoSeeded = true;
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        workflow_run_id: "workflow_demo_seed",
        workflow_key: "demo_research_workspace_seed",
        trigger_mode: "manual_request",
        prefect_flow_run_id: null,
        scheduled_for: null,
        status: "queued",
        started_at: "2026-06-03T09:00:00+08:00",
        available_at: "2026-06-03T09:00:00+08:00",
        claimed_at: null,
        lease_expires_at: null,
        worker_id: null,
        attempt_count: 0,
        completed_at: null,
        summary: { seed_key: "mvp_rc_demo_v1" },
        error_code: null,
        error_message: null,
      }),
    });
  });
  await page.route("**/v1/operations/runs/workflow_demo_seed", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        workflow_run_id: "workflow_demo_seed",
        workflow_key: "demo_research_workspace_seed",
        trigger_mode: "manual_request",
        prefect_flow_run_id: null,
        scheduled_for: null,
        status: "succeeded",
        started_at: "2026-06-03T09:00:00+08:00",
        available_at: "2026-06-03T09:00:00+08:00",
        claimed_at: "2026-06-03T09:00:01+08:00",
        lease_expires_at: null,
        worker_id: "worker-smoke",
        attempt_count: 1,
        completed_at: "2026-06-03T09:00:02+08:00",
        summary: { message: "Seeded local deterministic v0.1 RC demo data." },
        error_code: null,
        error_message: null,
      }),
    });
  });
  await page.route("**/v1/market/ingestion/runs?limit=5", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        items: [{
          ingestion_run_id: "market_ingest_ops",
          source_id: "example_electricity_council",
          endpoint_id: "council_home",
          trigger_mode: "registered_collection",
          adapter_key: "registered_static_http:v1",
          adapter_version: "1",
          started_at: "2026-06-03T07:00:00+08:00",
          completed_at: "2026-06-03T07:00:01+08:00",
          status: "succeeded",
          items_received: 1,
          items_inserted: 1,
          duplicate_items: 0,
          rejected_items: 0,
          quality_status: "valid",
          quality_issue_count: 0,
          error_code: null,
          error_message: null,
        }],
      }),
    });
  });

  await page.goto("/");
  await page.locator('[data-testid="nav-operations"]:visible').click();
  await expect(page.getByTestId("operations-workspace")).toBeVisible();
  await expect(page.getByTestId("operation-overall-status")).toHaveText("critical");
  await expect(page.getByTestId("operation-freshness")).toContainText("research_only");
  await expect(page.getByTestId("operation-source-health")).toContainText("Endpoint Health Records");
  await expect(page.getByTestId("operation-ingestion-runs")).toContainText("council_home");
  await expect(page.getByTestId("system-readiness-card")).toContainText("RC Checklist");
  await expect(page.getByTestId("system-readiness-card")).toContainText("demo_research_workspace_seed");
  await expect(page.getByTestId("operations-review-package")).toContainText("operations_review_package_v1");
  await expect(page.getByTestId("operations-review-package")).toContainText("no_auto_trading");
  await expect(page.getByTestId("operations-review-package-download")).toBeVisible();
  await expect(page.getByTestId("operation-action-center")).toContainText("weather_feature_review");
  await page.getByTestId("todo-weather-package-weather_feature_pending").click();
  await expect(page.getByTestId("weather-review-package")).toContainText("weather_feature_review_package_v1");
  await expect(page.getByTestId("weather-review-package")).toContainText("requires approved snapshot");
  await expect(page.getByTestId("weather-review-package-download")).toBeVisible();
  await expect(page.getByTestId("operation-action-center")).toContainText("market_artifact_review");
  await page.getByTestId("todo-market-artifact-package-market_artifact_pending").click();
  await expect(page.getByTestId("market-artifact-review-package")).toContainText("market_artifact_review_package_v1");
  await expect(page.getByTestId("market-artifact-review-package")).toContainText("no_auto_trading");
  await expect(page.getByTestId("market-artifact-review-package-download")).toBeVisible();
  await expect(page.getByTestId("operation-action-center")).toContainText("policy_document_review");
  await page.getByTestId("todo-policy-document-package-demo_rc_policy_document").click();
  await expect(page.getByTestId("policy-document-review-package")).toContainText("policy_document_review_package_v1");
  await expect(page.getByTestId("policy-document-review-package")).toContainText("user_uploaded");
  await expect(page.getByTestId("policy-document-review-package-download")).toBeVisible();
  await page.getByTestId("system-readiness-seed-demo").click();
  await expect(page.getByTestId("system-readiness-card")).toContainText("demo_rc_policy_document");
  await page.getByTestId("rerun-workflow_ops_failed").click();
  await expect(page.locator('[data-testid^="tracked-run-status-"]').first()).toHaveText(
    /succeeded|skipped|failed/,
    { timeout: 20_000 },
  );
});

test("shows source status and all five isolated BENCH research regions", async ({ page }) => {
  let pointRequestCount = 0;
  let backtestPayload: unknown = null;
  const forecastModelRun = {
    model_run_id: "forecast_model_e2e",
    dataset_id: "bench_nsw1",
    model_key: "seasonal_naive",
    model_version: "v1",
    feature_version: "interval_price_v1",
    started_at: "2026-06-02T09:40:00+08:00",
    completed_at: "2026-06-02T09:40:01+08:00",
    status: "succeeded",
    registry_status: "candidate",
    train_start: "2026-05-20",
    train_end: "2026-05-28",
    evaluation_start: "2026-05-29",
    evaluation_end: "2026-05-31",
    horizon_intervals: 96,
    parameters: { evaluation_days: 3, lag_days: 7 },
    metrics: { mae: 1.2, rmse: 1.5, smape: 0.01, prediction_count: 288 },
    artifact_path: null,
    usage_scope: "research_only",
    data_mode: "public_derived",
    error_code: null,
    error_message: null,
  };
  await page.route("**/v1/operations/jobs", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ items: [] }),
    });
  });
  await page.route("**/v1/operations/runs?limit=8", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ items: [] }),
    });
  });
  await page.route("**/v1/intelligence/briefs?limit=20", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ items: [] }),
    });
  });
  await page.route("**/v1/intelligence/briefs/latest", async (route) => {
    await route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ error: { code: "brief_not_found" } }),
    });
  });
  await page.route("**/v1/policy/documents", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ items: [] }),
    });
  });
  await page.route("**/v1/policy/corpus/overview", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        generated_at: "2026-06-02T09:45:00+08:00",
        status: "healthy",
        message: "Policy corpus is available for local review.",
        document_count: 0,
        version_count: 0,
        chunk_count: 0,
        embedded_chunk_count: 0,
        embedding_coverage: 0,
        external_processing_allowed_count: 0,
        external_processing_blocked_count: 0,
        artifact_provenance_count: 0,
        layers: [],
        recent_documents: [],
        network_probe_performed: false,
        fetch_performed: false,
        no_auto_trading: true,
      }),
    });
  });
  await page.route("**/v1/market/sources", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        items: [{
          source_id: "institute_public",
          name: "INSTITUTE public website",
          trust_tier: "official_public",
          official_url: "https://institute.example.invalid/",
          collection_permission_note: "Registered public source; no login automation.",
        }],
      }),
    });
  });
  await page.route("**/v1/market/endpoints", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        items: [{
          endpoint_id: "institute_news",
          name: "INSTITUTE public announcements",
          lifecycle_status: "enabled",
          collection_enabled: true,
        }],
      }),
    });
  });
  await page.route("**/v1/market/artifacts?limit=10", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ items: [] }),
    });
  });
  await page.route("**/v1/forecasting/research/overview", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        generated_at: "2026-06-02T09:45:00+08:00",
        status: "healthy",
        message: "Forecast research datasets and candidate model runs are available for review.",
        dataset_count: 5,
        valid_dataset_count: 5,
        invalid_dataset_count: 0,
        research_only_dataset_count: 5,
        candidate_model_run_count: 1,
        succeeded_model_run_count: 1,
        bench_expected_regions: BENCH_REGIONS.map(([regionCode]) => regionCode),
        bench_available_regions: BENCH_REGIONS.map(([regionCode]) => regionCode),
        bench_missing_regions: [],
        bench_region_count: 5,
        datasets: [],
        recent_import_runs: [],
        recent_model_runs: [forecastModelRun],
        recent_quality_issues: [],
        no_auto_trading: true,
        recommendation_chain_isolated: true,
        network_probe_performed: false,
        fetch_performed: false,
      }),
    });
  });
  await page.route("**/v1/forecasting/research/datasets", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        items: [
          ...BENCH_REGIONS.map(([regionCode, regionName]) => ({
          dataset_id: `bench_${regionCode.toLowerCase()}`,
          name: `BENCH Dispatch ${regionCode}`,
          region_code: regionCode,
          region_name: regionName,
          market_scope: "bench_nem_dispatch_benchmark",
          data_mode: "public_derived",
          usage_scope: "research_only",
          imported_at: "2026-06-02T09:30:00+08:00",
          })),
          {
            dataset_id: "bench_nsw1_old",
            name: "BENCH Dispatch NSW1 old",
            region_code: "NSW1",
            region_name: "New South Wales",
            market_scope: "bench_nem_dispatch_benchmark",
            data_mode: "public_derived",
            usage_scope: "research_only",
            imported_at: "2026-06-01T09:30:00+08:00",
          },
        ],
      }),
    });
  });
  await page.route("**/v1/forecasting/research/import-runs**", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        items: [{
          import_run_id: "forecast_import_e2e",
          dataset_id: "bench_nsw1",
          started_at: "2026-06-02T09:30:00+08:00",
          completed_at: "2026-06-02T09:30:01+08:00",
          status: "accepted",
          submitted_point_count: 96,
          normalized_point_count: 96,
          quality_status: "valid",
          quality_issue_count: 0,
          data_mode: "public_derived",
          error_code: null,
          error_message: null,
        }],
      }),
    });
  });
  await page.route("**/v1/forecasting/research/quality/issues**", async (route) => {
    await route.fulfill({ contentType: "application/json", body: JSON.stringify({ items: [] }) });
  });
  await page.route("**/v1/forecasting/research/datasets/*/review-package", async (route) => {
    const datasetId = route.request().url().split("/datasets/")[1].split("/")[0];
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        package_version: "forecast_research_review_package_v1",
        generated_at: "2026-06-02T09:46:00+08:00",
        dataset: {
          dataset_id: datasetId,
          name: "BENCH Dispatch NSW1",
          source_name: "Australian Energy Market Operator (BENCH) NEM DispatchIS",
          source_url: "https://archive.benchmark.example.invalid/Reports/Current/DispatchIS_Reports/",
          region_code: "NSW1",
          region_name: "New South Wales",
          market_scope: "bench_nem_dispatch_benchmark",
          market_stage: "real_time",
          price_scope: "regional_reference_price_15_minute_arithmetic_mean",
          interval_minutes: 15,
          timezone: "Australia/Brisbane",
          currency: "AUD",
          price_unit: "AUD_per_MWh",
          data_mode: "public_derived",
          usage_scope: "research_only",
          content_sha256: "e".repeat(64),
          imported_at: "2026-06-02T09:30:00+08:00",
          quality_status: "valid",
          quality_issue_count: 0,
          normalized_point_count: 96,
          trade_date_count: 1,
          notes: "BENCH public benchmark fixture only; research_only and isolated.",
        },
        import_runs: [{
          import_run_id: "forecast_import_e2e",
          dataset_id: datasetId,
          started_at: "2026-06-02T09:30:00+08:00",
          completed_at: "2026-06-02T09:30:01+08:00",
          status: "accepted",
          submitted_point_count: 96,
          normalized_point_count: 96,
          quality_status: "valid",
          quality_issue_count: 0,
          data_mode: "public_derived",
          error_code: null,
          error_message: null,
        }],
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
      }),
    });
  });
  await page.route("**/v1/forecasting/research/model-runs?**", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ items: [forecastModelRun] }),
    });
  });
  await page.route("**/v1/forecasting/research/model-runs/forecast_model_e2e/predictions?limit=500", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        items: [{
          prediction_id: "prediction_e2e_1",
          model_run_id: "forecast_model_e2e",
          target_interval_start: "2026-05-31T00:00:00+10:00",
          trade_date: "2026-05-31",
          interval_index: 1,
          actual_price: "91.25",
          predicted_price: "90.00",
          data_mode: "public_derived",
        }],
      }),
    });
  });
  await page.route("**/v1/forecasting/research/datasets/bench_nsw1/backtests", async (route) => {
    backtestPayload = route.request().postDataJSON();
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(forecastModelRun),
    });
  });
  await page.route("**/v1/forecasting/research/datasets/*/points?limit=192", async (route) => {
    pointRequestCount += 1;
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        items: [
          { interval_start: "2026-05-31T00:00:00+10:00", price: "91.25" },
          { interval_start: "2026-05-31T00:15:00+10:00", price: "88.50" },
        ],
      }),
    });
  });
  await page.route("**/v1/policy/documents", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ items: [] }),
    });
  });
  await page.route("**/v1/market/sources", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        items: [{
          source_id: "institute_public",
          name: "INSTITUTE public website",
          trust_tier: "official_public",
          official_url: "https://institute.example.invalid/",
          collection_permission_note: "Registered public source; no login automation.",
        }],
      }),
    });
  });
  await page.route("**/v1/market/endpoints", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        items: [{
          endpoint_id: "institute_news",
          name: "INSTITUTE public announcements",
          lifecycle_status: "enabled",
          collection_enabled: true,
        }],
      }),
    });
  });
  await page.route("**/v1/market/artifacts?limit=10", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ items: [] }),
    });
  });
  const endpointsLoaded = page.waitForResponse((response) =>
    response.url().includes("/v1/market/endpoints") && response.status() === 200,
  );
  await page.goto("/");
  await page.locator('[data-testid="nav-research"]:visible').click();
  await endpointsLoaded;
  const sourceHealth = page.getByTestId("source-health");
  await expect(sourceHealth).toBeVisible();
  await expect(sourceHealth).toContainText("INSTITUTE public website", { timeout: 15_000 });
  for (const [regionCode] of BENCH_REGIONS) {
    await expect(page.getByTestId(`bench-region-${regionCode}`)).toBeVisible();
  }
  await expect(page.getByTestId("bench-region-NSW1")).toHaveCount(1);
  expect(pointRequestCount).toBe(1);
  await page.getByTestId("bench-region-select").click();
  await page.getByText("Queensland · 2026-06-02").click();
  await expect.poll(() => pointRequestCount).toBe(2);
  await expect(page.getByTestId("forecast-research-dashboard")).toContainText("Forecast Research");
  await expect(page.getByTestId("forecast-research-dashboard")).toContainText("research_only");
  await expect(page.getByTestId("forecast-review-package")).toContainText("Review package");
  await expect(page.getByTestId("forecast-review-package")).toContainText("public_derived");
  await expect(page.getByTestId("forecast-review-package-download")).toBeVisible();
  await expect(page.getByTestId("forecast-model-runs")).toContainText("seasonal_naive");
  await page.getByTestId("forecast-run-seasonal_naive").click();
  await expect.poll(() => backtestPayload).toEqual({
    model_key: "seasonal_naive",
    evaluation_days: 3,
    lag_days: 7,
    lookback_days: 7,
  });
  await expect(page.getByTestId("forecast-prediction-chart")).toBeVisible();
  await expect(page.getByTestId("bench-isolation")).toContainText("不属于示例甲省市场数据");
  await expect(page.getByTestId("bench-isolation")).toContainText("不会进入推荐链路");
});

test("generates a simulated recommendation and records human review audit", async ({ page }) => {
  await page.goto("/");
  await page.locator('[data-testid="nav-recommendation"]:visible').click();
  await page.getByTestId("generate-recommendation").click();
  await expect(page.getByTestId("recommendation-card")).toContainText("scenario_simulated");
  await expect(page.getByTestId("recommendation-audit")).toBeVisible();
  await expect(page.getByTestId("decision-log-card")).toBeVisible();
  await page.getByTestId("review-note").fill("Playwright 人工复核记录");
  await page.getByTestId("submit-review").click();
  await expect(page.getByText("复核结果已保存，并写入审计记录。")).toBeVisible();
  await expect(page.getByTestId("review-history")).toContainText("Playwright 人工复核记录");
  await page.getByTestId("decision-note").fill("Playwright 人工决策日志");
  await page.getByTestId("decision-safety-ack").click();
  await page.getByTestId("submit-decision").click();
  await expect(page.getByTestId("decision-history")).toContainText("Playwright 人工决策日志");
  await page.locator('[data-testid^="feedback-note-"]').first().fill("Playwright 复盘反馈");
  await page.locator('[data-testid^="submit-feedback-"]').first().click();
  await expect(page.getByTestId("decision-history")).toContainText("Playwright 复盘反馈");
});

test("reports failed external-processing authorization updates", async ({ page }) => {
  await page.route("**/v1/policy/documents", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        items: [{
          document_id: "document_local_only",
          title: "Local only research note",
          document_layer: "user_uploaded",
          trust_tier: "user_uploaded",
          source_name: "Local upload",
          source_url: null,
          captured_at: "2026-06-03T08:00:00+08:00",
          external_processing_allowed: false,
        }],
      }),
    });
  });
  await page.route("**/v1/policy/documents/document_local_only/external-processing-authorization", async (route) => {
    await route.fulfill({ status: 500, contentType: "application/json", body: "{}" });
  });
  await page.goto("/");
  await page.locator('[data-testid="nav-research"]:visible').click();
  await page.getByRole("switch").click();
  await expect(page.getByText("资料外发授权更新失败，请检查本地 API 状态。")).toBeVisible();
});

test("queues a fixed policy job and renders the worker terminal status", async ({ page }) => {
  await page.goto("/");
  const trigger = page.getByTestId("trigger-policy_research_refresh");
  await trigger.click();
  await expect(page.locator('[data-testid^="run-status-"]').first()).toHaveText("skipped", {
    timeout: 20_000,
  });
});
