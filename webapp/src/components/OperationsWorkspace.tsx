import { DownloadOutlined } from "@ant-design/icons";
import { Alert, Button, Card, Col, Empty, Input, List, Row, Space, Statistic, Table, Tag, Typography } from "antd";
import { useEffect, useRef, useState } from "react";

import { api } from "../api";
import { nextPollDelayMilliseconds } from "../operationPolling";
import type {
  ActionItem,
  FreshnessItem,
  HealthItem,
  KnowledgeDocumentReviewPackage,
  MarketArtifactReviewPackage,
  MarketIngestionRun,
  OperationActionCenter,
  OperationOverview,
  OperationsReviewPackage,
  OperationTodoItem,
  OperationsStatus,
  SystemReadiness,
  WeatherFeatureReviewPackage,
  WorkflowRun,
} from "../types";

const TERMINAL_RUN_STATUSES = new Set(["succeeded", "skipped", "failed"]);
const DEFAULT_ACTION_CENTER_REVIEW_NOTE = "Reviewed from Action Center quick action.";

const delay = (milliseconds: number) =>
  new Promise((resolve) => window.setTimeout(resolve, milliseconds));

function statusColor(status: string) {
  if (status === "healthy" || status === "succeeded") return "green";
  if (status === "warning" || status === "retry_wait") return "gold";
  if (status === "critical" || status === "failed") return "red";
  if (status === "running") return "blue";
  return "default";
}

function formatTime(value: string | null | undefined) {
  if (!value) return "-";
  const timestamp = Date.parse(value);
  return Number.isNaN(timestamp) ? value : new Date(timestamp).toLocaleString();
}

function formatAge(value: number | null) {
  return value === null ? "-" : `${value.toFixed(1)} h`;
}

function statusWeight(status: OperationsStatus) {
  if (status === "critical") return 3;
  if (status === "warning") return 2;
  return 1;
}

function reviewLabel(status: string) {
  if (status === "approved") return "Approve";
  if (status === "needs_revision") return "Needs revision";
  if (status === "rejected") return "Reject";
  return status;
}

function downloadOperationsReviewPackage(reviewPackage: OperationsReviewPackage) {
  const blob = new Blob([JSON.stringify(reviewPackage, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `operations-review-package-${reviewPackage.generated_at.slice(0, 10)}.json`;
  anchor.click();
  URL.revokeObjectURL(url);
}

function downloadWeatherReviewPackage(reviewPackage: WeatherFeatureReviewPackage) {
  const blob = new Blob([JSON.stringify(reviewPackage, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `weather-review-package-${reviewPackage.snapshot.feature_snapshot_id}.json`;
  anchor.click();
  URL.revokeObjectURL(url);
}

function downloadMarketArtifactReviewPackage(reviewPackage: MarketArtifactReviewPackage) {
  const blob = new Blob([JSON.stringify(reviewPackage, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `market-artifact-review-package-${reviewPackage.artifact.artifact_id}.json`;
  anchor.click();
  URL.revokeObjectURL(url);
}

function downloadPolicyDocumentReviewPackage(reviewPackage: KnowledgeDocumentReviewPackage) {
  const blob = new Blob([JSON.stringify(reviewPackage, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${reviewPackage.document.document_id}-policy-document-review-package.json`;
  anchor.click();
  URL.revokeObjectURL(url);
}

function OperationsReviewPackageCard(props: {
  reviewPackage: OperationsReviewPackage | null;
  error: string | null;
}) {
  if (props.error) {
    return (
      <Card title="Review package" data-testid="operations-review-package">
        <Alert type="warning" showIcon message={props.error} />
      </Card>
    );
  }
  if (!props.reviewPackage) {
    return (
      <Card title="Review package" data-testid="operations-review-package">
        <Empty description="Operations review package is loading." />
      </Card>
    );
  }
  const { reviewPackage } = props;
  const recommendedActions = reviewPackage.overview.actions.filter((action) => action.recommended);
  return (
    <Card
      title="Review package"
      data-testid="operations-review-package"
      extra={(
        <Button
          icon={<DownloadOutlined />}
          data-testid="operations-review-package-download"
          onClick={() => downloadOperationsReviewPackage(reviewPackage)}
        >
          Download JSON
        </Button>
      )}
    >
      <Row gutter={[16, 16]}>
        <Col xs={12} lg={6}>
          <Statistic title="Overall" value={reviewPackage.overview.overall_status} />
        </Col>
        <Col xs={12} lg={6}>
          <Statistic title="Todos" value={reviewPackage.action_center.counts.total} />
        </Col>
        <Col xs={12} lg={6}>
          <Statistic title="Critical" value={reviewPackage.action_center.counts.critical} />
        </Col>
        <Col xs={12} lg={6}>
          <Statistic title="Recommended jobs" value={recommendedActions.length} />
        </Col>
      </Row>
      <Space className="card-footer" wrap data-testid="operations-review-package-flags">
        <Tag>{reviewPackage.package_version}</Tag>
        <Tag color={statusColor(reviewPackage.system_readiness.status)}>
          readiness {reviewPackage.system_readiness.status}
        </Tag>
        <Tag>{reviewPackage.no_auto_trading ? "no_auto_trading" : "auto_trading_flag_false"}</Tag>
        <Tag>{reviewPackage.manual_job_keys_only ? "fixed job keys only" : "dynamic job keys"}</Tag>
        <Tag>{reviewPackage.network_probe_performed ? "network probe performed" : "no network probe"}</Tag>
        <Tag>{reviewPackage.fetch_performed ? "fetch performed" : "no fetch"}</Tag>
      </Space>
      <List
        className="card-footer"
        size="small"
        data-testid="operations-review-package-categories"
        dataSource={Object.entries(reviewPackage.action_center.counts.by_category)}
        locale={{ emptyText: "No action categories." }}
        renderItem={([category, count]) => (
          <List.Item>
            <Typography.Text>{category}: {count}</Typography.Text>
          </List.Item>
        )}
      />
      <Typography.Text type="secondary">
        Fixed jobs: {reviewPackage.fixed_job_keys.join(", ")}. Recent runs included:
        {" "}{reviewPackage.recent_runs.length}. This package is generated locally from
        read-only endpoints and is not recommendation evidence.
      </Typography.Text>
    </Card>
  );
}

function WeatherReviewPackageCard(props: {
  reviewPackage: WeatherFeatureReviewPackage | null;
  error: string | null;
}) {
  if (props.error) {
    return (
      <Card title="Weather review package" data-testid="weather-review-package">
        <Alert type="warning" showIcon message={props.error} />
      </Card>
    );
  }
  if (!props.reviewPackage) return null;
  const { reviewPackage } = props;
  return (
    <Card
      title="Weather review package"
      data-testid="weather-review-package"
      extra={(
        <Button
          icon={<DownloadOutlined />}
          data-testid="weather-review-package-download"
          onClick={() => downloadWeatherReviewPackage(reviewPackage)}
        >
          Download JSON
        </Button>
      )}
    >
      <Row gutter={[16, 16]}>
        <Col xs={12} lg={6}>
          <Statistic title="Quality" value={reviewPackage.snapshot.quality_status} />
        </Col>
        <Col xs={12} lg={6}>
          <Statistic title="Review" value={reviewPackage.snapshot.human_review_status} />
        </Col>
        <Col xs={12} lg={6}>
          <Statistic title="Issues" value={reviewPackage.quality_issue_summary.total_count} suffix="issues" />
        </Col>
        <Col xs={12} lg={6}>
          <Statistic title="Blockers" value={reviewPackage.approval.blockers.length} />
        </Col>
      </Row>
      <Space className="card-footer" wrap>
        <Tag>{reviewPackage.package_version}</Tag>
        <Tag>{reviewPackage.snapshot.data_mode}</Tag>
        <Tag>{reviewPackage.snapshot.provider}</Tag>
        <Tag>{reviewPackage.no_auto_trading ? "no_auto_trading" : "auto_trading_flag_false"}</Tag>
        <Tag>
          {reviewPackage.recommendation_chain_requires_approved_snapshot
            ? "requires approved snapshot"
            : "recommendation link unchecked"}
        </Tag>
        <Tag>{reviewPackage.network_probe_performed ? "network probe performed" : "no network probe"}</Tag>
        <Tag>{reviewPackage.fetch_performed ? "fetch performed" : "no fetch"}</Tag>
      </Space>
      <List
        className="card-footer"
        size="small"
        data-testid="weather-review-package-blockers"
        dataSource={reviewPackage.approval.blockers}
        locale={{ emptyText: "No approval blockers." }}
        renderItem={(blocker) => (
          <List.Item>
            <Typography.Text>{blocker}</Typography.Text>
          </List.Item>
        )}
      />
      <Typography.Text type="secondary">
        {reviewPackage.snapshot.location_id} - {formatTime(reviewPackage.snapshot.forecast_start)}
        {" "} - reviews {reviewPackage.reviews.length}
      </Typography.Text>
    </Card>
  );
}

function MarketArtifactReviewPackageCard(props: {
  reviewPackage: MarketArtifactReviewPackage | null;
  error: string | null;
}) {
  if (props.error) {
    return (
      <Card title="Market artifact review package" data-testid="market-artifact-review-package">
        <Alert type="warning" showIcon message={props.error} />
      </Card>
    );
  }
  if (!props.reviewPackage) return null;
  const { reviewPackage } = props;
  return (
    <Card
      title="Market artifact review package"
      data-testid="market-artifact-review-package"
      extra={(
        <Button
          icon={<DownloadOutlined />}
          data-testid="market-artifact-review-package-download"
          onClick={() => downloadMarketArtifactReviewPackage(reviewPackage)}
        >
          Download JSON
        </Button>
      )}
    >
      <Row gutter={[16, 16]}>
        <Col xs={12} lg={6}>
          <Statistic title="Review" value={reviewPackage.artifact.human_review_status} />
        </Col>
        <Col xs={12} lg={6}>
          <Statistic title="Issues" value={reviewPackage.quality_issue_summary.total_count} />
        </Col>
        <Col xs={12} lg={6}>
          <Statistic title="Reviews" value={reviewPackage.reviews.length} />
        </Col>
        <Col xs={12} lg={6}>
          <Statistic title="Parse runs" value={reviewPackage.parsing_runs.length} />
        </Col>
      </Row>
      <Space className="card-footer" wrap>
        <Tag>{reviewPackage.package_version}</Tag>
        <Tag>{reviewPackage.artifact.data_mode}</Tag>
        <Tag>{reviewPackage.artifact.media_type}</Tag>
        <Tag>{reviewPackage.artifact.inline_text_available ? "raw text preserved" : "raw text external"}</Tag>
        <Tag>{reviewPackage.no_auto_trading ? "no_auto_trading" : "auto_trading_flag_false"}</Tag>
        <Tag>{reviewPackage.recommendation_chain_isolated ? "recommendation isolated" : "recommendation link unchecked"}</Tag>
        <Tag>{reviewPackage.network_probe_performed ? "network probe performed" : "no network probe"}</Tag>
        <Tag>{reviewPackage.fetch_performed ? "fetch performed" : "no fetch"}</Tag>
        <Tag>{reviewPackage.parse_performed ? "parse performed" : "no parse"}</Tag>
      </Space>
      <List
        className="card-footer"
        size="small"
        data-testid="market-artifact-review-package-issues"
        dataSource={reviewPackage.quality_issues}
        locale={{ emptyText: "No artifact quality issues." }}
        renderItem={(issue) => (
          <List.Item>
            <Space orientation="vertical" size={2}>
              <Space wrap>
                <Tag color={statusColor(issue.severity)}>{issue.severity}</Tag>
                <Typography.Text>{issue.issue_code}</Typography.Text>
              </Space>
              <Typography.Text type="secondary">{issue.message}</Typography.Text>
            </Space>
          </List.Item>
        )}
      />
      <Typography.Text type="secondary">
        {reviewPackage.source?.name ?? reviewPackage.artifact.source_id}
        {" - "}
        {reviewPackage.endpoint?.name ?? reviewPackage.artifact.endpoint_id}
      </Typography.Text>
    </Card>
  );
}

function PolicyDocumentReviewPackageCard(props: {
  reviewPackage: KnowledgeDocumentReviewPackage | null;
  error: string | null;
}) {
  if (props.error) {
    return (
      <Card title="Policy document review package" data-testid="policy-document-review-package">
        <Alert type="warning" showIcon message={props.error} />
      </Card>
    );
  }
  if (!props.reviewPackage) return null;
  const { reviewPackage } = props;
  const { document, chunk_summary } = reviewPackage;
  return (
    <Card
      title="Policy document review package"
      data-testid="policy-document-review-package"
      extra={(
        <Button
          icon={<DownloadOutlined />}
          data-testid="policy-document-review-package-download"
          onClick={() => downloadPolicyDocumentReviewPackage(reviewPackage)}
        >
          Download JSON
        </Button>
      )}
    >
      <Row gutter={[16, 16]}>
        <Col xs={12} lg={6}>
          <Statistic title="Chunks" value={chunk_summary.total_count} />
        </Col>
        <Col xs={12} lg={6}>
          <Statistic title="Embedded" value={chunk_summary.embedded_count} />
        </Col>
        <Col xs={12} lg={6}>
          <Statistic title="Reviews" value={reviewPackage.review_count} />
        </Col>
        <Col xs={12} lg={6}>
          <Statistic title="Displayed" value={chunk_summary.displayed_chunk_count} />
        </Col>
      </Row>
      <Space className="card-footer" wrap>
        <Tag>{reviewPackage.package_version}</Tag>
        <Tag>{document.document_layer}</Tag>
        <Tag>{document.data_mode}</Tag>
        <Tag>{document.human_review_status}</Tag>
        <Tag>{reviewPackage.no_auto_trading ? "no_auto_trading" : "trading flag disabled"}</Tag>
        <Tag>{reviewPackage.recommendation_chain_isolated ? "recommendation_chain_isolated" : "recommendation link unchecked"}</Tag>
        <Tag>external_processing_allowed={String(reviewPackage.external_processing_allowed)}</Tag>
        <Tag>raw_payload_included={String(reviewPackage.raw_payload_included)}</Tag>
        <Tag>server_artifact_written={String(reviewPackage.server_artifact_written)}</Tag>
        <Tag>{reviewPackage.external_model_call_performed ? "external model call" : "no external model call"}</Tag>
      </Space>
      <List
        className="card-footer"
        size="small"
        data-testid="policy-document-review-package-chunks"
        dataSource={reviewPackage.displayed_chunks}
        locale={{ emptyText: "No displayed chunks." }}
        renderItem={(chunk) => (
          <List.Item>
            <Space orientation="vertical" size={2}>
              <Typography.Text>Chunk {chunk.ordinal}: {chunk.content_sha256.slice(0, 12)}</Typography.Text>
              <Typography.Text type="secondary">{chunk.content_excerpt}</Typography.Text>
            </Space>
          </List.Item>
        )}
      />
    </Card>
  );
}

function OperationActionCenterCard(props: {
  actionCenter: OperationActionCenter | null;
  error: string | null;
  reviewError: string | null;
  allowedJobKeys: Set<string>;
  loadingJob: string | null;
  reviewingItem: string | null;
  reviewNotes: Record<string, string>;
  loadingWeatherPackageId: string | null;
  loadingMarketArtifactPackageId: string | null;
  loadingPolicyDocumentPackageId: string | null;
  onTriggerJob: (jobKey: string) => void;
  onOpenActionTarget?: (targetType: string, targetId: string) => void;
  onReviewNoteChange: (itemId: string, note: string) => void;
  onReviewAction: (item: OperationTodoItem, reviewStatus: string) => void;
  onShowWeatherPackage: (featureSnapshotId: string) => void;
  onShowMarketArtifactPackage: (artifactId: string) => void;
  onShowPolicyDocumentPackage: (documentId: string) => void;
}) {
  if (props.error) {
    return (
      <Card title="Action Center" data-testid="operation-action-center">
        <Alert type="warning" showIcon message={props.error} />
      </Card>
    );
  }
  if (!props.actionCenter) {
    return (
      <Card title="Action Center" data-testid="operation-action-center">
        <Empty description="Action center is loading." />
      </Card>
    );
  }
  const { actionCenter } = props;
  return (
    <Card
      title="Action Center"
      data-testid="operation-action-center"
      extra={<Tag color={statusColor(actionCenter.status)}>{actionCenter.status}</Tag>}
    >
      <Row gutter={[16, 16]}>
        <Col xs={8}>
          <Statistic title="Todo" value={actionCenter.counts.total} />
        </Col>
        <Col xs={8}>
          <Statistic title="Critical" value={actionCenter.counts.critical} />
        </Col>
        <Col xs={8}>
          <Statistic title="Warning" value={actionCenter.counts.warning} />
        </Col>
      </Row>
      {props.reviewError && (
        <Alert className="card-footer" type="warning" showIcon message={props.reviewError} />
      )}
      <List<OperationTodoItem>
        className="card-footer"
        data-testid="operation-action-items"
        dataSource={actionCenter.items}
        locale={{ emptyText: "No operator action items." }}
        renderItem={(item) => {
          const canTrigger = item.job_key !== null && props.allowedJobKeys.has(item.job_key);
          const canReview = Boolean(
            item.review_target_type && item.allowed_review_statuses.length > 0,
          );
          const canOpenTarget = Boolean(
            item.navigation_target_type
              && item.navigation_target_id
              && props.onOpenActionTarget,
          );
          const canShowWeatherPackage = item.review_target_type === "weather_feature";
          const canShowMarketArtifactPackage = item.review_target_type === "market_artifact";
          const canShowPolicyDocumentPackage = item.review_target_type === "policy_document";
          const actions = [
            ...(canShowWeatherPackage ? [
              <Button
                key={`${item.item_id}:weather-package`}
                data-testid={`todo-weather-package-${item.target_id}`}
                loading={props.loadingWeatherPackageId === item.target_id}
                onClick={() => props.onShowWeatherPackage(item.target_id)}
              >
                Review package
              </Button>,
            ] : []),
            ...(canShowMarketArtifactPackage ? [
              <Button
                key={`${item.item_id}:market-artifact-package`}
                data-testid={`todo-market-artifact-package-${item.target_id}`}
                loading={props.loadingMarketArtifactPackageId === item.target_id}
                onClick={() => props.onShowMarketArtifactPackage(item.target_id)}
              >
                Review package
              </Button>,
            ] : []),
            ...(canShowPolicyDocumentPackage ? [
              <Button
                key={`${item.item_id}:policy-document-package`}
                data-testid={`todo-policy-document-package-${item.target_id}`}
                loading={props.loadingPolicyDocumentPackageId === item.target_id}
                onClick={() => props.onShowPolicyDocumentPackage(item.target_id)}
              >
                Review package
              </Button>,
            ] : []),
            ...(canOpenTarget ? [
              <Button
                key={`${item.item_id}:open`}
                data-testid={`todo-open-${item.target_id}`}
                onClick={() => {
                  if (
                    item.navigation_target_type
                      && item.navigation_target_id
                      && props.onOpenActionTarget
                  ) {
                    props.onOpenActionTarget(
                      item.navigation_target_type,
                      item.navigation_target_id,
                    );
                  }
                }}
              >
                Open target
              </Button>,
            ] : []),
            ...(item.job_key ? [
              <Button
                key={`${item.item_id}:run`}
                data-testid={`todo-trigger-${item.target_id}`}
                disabled={!canTrigger}
                loading={props.loadingJob === item.job_key}
                onClick={() => {
                  if (canTrigger && item.job_key) props.onTriggerJob(item.job_key);
                }}
              >
                Run fixed job
              </Button>,
            ] : []),
          ];
          return (
            <List.Item
              actions={actions}
            >
              <Space orientation="vertical" size={2}>
                <Space wrap>
                  <Tag color={statusColor(item.severity)}>{item.severity}</Tag>
                  <Tag>{item.category}</Tag>
                  <Typography.Text strong>{item.title}</Typography.Text>
                </Space>
                <Typography.Text>{item.message}</Typography.Text>
                <Typography.Text type="secondary">
                  {item.recommended_action}
                </Typography.Text>
                <Typography.Text type="secondary">
                  {item.target_type}:{item.target_id} - {formatTime(item.latest_at ?? item.created_at)}
                </Typography.Text>
                {item.navigation_target_type && item.navigation_target_id && (
                  <Typography.Text type="secondary">
                    navigation target: {item.navigation_target_type}:{item.navigation_target_id}
                  </Typography.Text>
                )}
                {canReview && (
                  <Space wrap>
                    <Input
                      data-testid={`todo-review-note-${item.target_id}`}
                      placeholder={item.default_review_note ?? DEFAULT_ACTION_CENTER_REVIEW_NOTE}
                      value={props.reviewNotes[item.item_id] ?? ""}
                      onChange={(event) => props.onReviewNoteChange(
                        item.item_id,
                        event.target.value,
                      )}
                      style={{ minWidth: 280 }}
                    />
                    {item.allowed_review_statuses.map((reviewStatus) => (
                      <Button
                        key={`${item.item_id}:${reviewStatus}`}
                        data-testid={`todo-review-${reviewStatus}-${item.target_id}`}
                        loading={props.reviewingItem === `${item.item_id}:${reviewStatus}`}
                        onClick={() => props.onReviewAction(item, reviewStatus)}
                      >
                        {reviewLabel(reviewStatus)}
                      </Button>
                    ))}
                  </Space>
                )}
              </Space>
            </List.Item>
          );
        }}
      />
      <Typography.Text type="secondary">
        Read-only aggregation. No web probing, model call, recommendation mutation, or trade execution.
      </Typography.Text>
    </Card>
  );
}

function SystemReadinessCard(props: {
  readiness: SystemReadiness | null;
  error: string | null;
  allowedJobKeys: Set<string>;
  loadingJob: string | null;
  onTriggerJob: (jobKey: string) => void;
}) {
  if (props.error) {
    return (
      <Card title="RC Checklist" data-testid="system-readiness-card">
        <Alert type="warning" showIcon message={props.error} />
      </Card>
    );
  }
  if (!props.readiness) {
    return (
      <Card title="RC Checklist" data-testid="system-readiness-card">
        <Empty description="System readiness is loading." />
      </Card>
    );
  }
  const { readiness } = props;
  const canSeed = props.allowedJobKeys.has("demo_research_workspace_seed");
  const objectIds = readiness.demo_seed?.object_ids ?? {};
  return (
    <Card
      title="RC Checklist"
      data-testid="system-readiness-card"
      extra={<Tag color={statusColor(readiness.status)}>{readiness.status}</Tag>}
    >
      <Row gutter={[16, 16]}>
        <Col xs={12} lg={6}>
          <Statistic title="Checks" value={readiness.checks.length} />
        </Col>
        <Col xs={12} lg={6}>
          <Statistic
            title="Missing demo"
            value={readiness.missing_demo_items.length}
          />
        </Col>
        <Col xs={12} lg={6}>
          <Statistic
            title="Tables"
            value={Object.keys(readiness.table_counts).length}
          />
        </Col>
        <Col xs={12} lg={6}>
          <Statistic title="No auto trading" value={readiness.no_auto_trading ? "yes" : "no"} />
        </Col>
      </Row>
      <Space className="card-footer" wrap>
        <Button
          data-testid="system-readiness-seed-demo"
          disabled={!canSeed}
          loading={props.loadingJob === "demo_research_workspace_seed"}
          onClick={() => props.onTriggerJob("demo_research_workspace_seed")}
        >
          Seed local RC demo data
        </Button>
        <Tag>fixed job only</Tag>
        <Tag>local fixtures</Tag>
        <Tag>no external fetch</Tag>
      </Space>
      {readiness.missing_demo_items.length > 0 && (
        <Alert
          className="card-footer"
          type="warning"
          showIcon
          message={`Missing demo data: ${readiness.missing_demo_items.join(", ")}`}
        />
      )}
      {readiness.recommended_actions.length > 0 && (
        <Alert
          className="card-footer"
          type="info"
          showIcon
          message={`Recommended action: ${readiness.recommended_actions.join(" ")}`}
        />
      )}
      <List<SystemReadiness["checks"][number]>
        className="card-footer"
        size="small"
        dataSource={readiness.checks}
        renderItem={(check) => (
          <List.Item>
            <Space orientation="vertical" size={2}>
              <Space wrap>
                <Tag color={statusColor(check.status)}>{check.status}</Tag>
                <Typography.Text strong>{check.label}</Typography.Text>
              </Space>
              <Typography.Text>{check.message}</Typography.Text>
            </Space>
          </List.Item>
        )}
      />
      <Space direction="vertical" size={2}>
        <Typography.Text type="secondary">
          Demo seed: {readiness.demo_seed?.seed_key ?? "-"}; recommendation boundary:
          BENCH, research_only, and policy watch stay out of recommendation evidence.
        </Typography.Text>
        <Typography.Text type="secondary">
          Key objects: {Object.entries(objectIds).map(([key, value]) => `${key}=${value}`).join("; ") || "-"}
        </Typography.Text>
      </Space>
    </Card>
  );
}

export function OperationsWorkspace(props: {
  onOpenActionTarget?: (targetType: string, targetId: string) => void;
}) {
  const [overview, setOverview] = useState<OperationOverview | null>(null);
  const [readiness, setReadiness] = useState<SystemReadiness | null>(null);
  const [actionCenter, setActionCenter] = useState<OperationActionCenter | null>(null);
  const [reviewPackage, setReviewPackage] = useState<OperationsReviewPackage | null>(null);
  const [weatherReviewPackage, setWeatherReviewPackage] = useState<WeatherFeatureReviewPackage | null>(null);
  const [marketArtifactReviewPackage, setMarketArtifactReviewPackage] = useState<MarketArtifactReviewPackage | null>(null);
  const [policyDocumentReviewPackage, setPolicyDocumentReviewPackage] = useState<KnowledgeDocumentReviewPackage | null>(null);
  const [marketIngestionRuns, setMarketIngestionRuns] = useState<MarketIngestionRun[]>([]);
  const [trackedRuns, setTrackedRuns] = useState<WorkflowRun[]>([]);
  const [loadingJob, setLoadingJob] = useState<string | null>(null);
  const [reviewingItem, setReviewingItem] = useState<string | null>(null);
  const [loadingWeatherPackageId, setLoadingWeatherPackageId] = useState<string | null>(null);
  const [loadingMarketArtifactPackageId, setLoadingMarketArtifactPackageId] = useState<string | null>(null);
  const [loadingPolicyDocumentPackageId, setLoadingPolicyDocumentPackageId] = useState<string | null>(null);
  const [reviewNotes, setReviewNotes] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [readinessError, setReadinessError] = useState<string | null>(null);
  const [actionCenterError, setActionCenterError] = useState<string | null>(null);
  const [reviewPackageError, setReviewPackageError] = useState<string | null>(null);
  const [actionReviewError, setActionReviewError] = useState<string | null>(null);
  const [weatherReviewPackageError, setWeatherReviewPackageError] = useState<string | null>(null);
  const [marketArtifactReviewPackageError, setMarketArtifactReviewPackageError] = useState<string | null>(null);
  const [policyDocumentReviewPackageError, setPolicyDocumentReviewPackageError] = useState<string | null>(null);
  const mounted = useRef(true);

  const refresh = async () => {
    try {
      const [nextOverview, nextMarketIngestionRuns] = await Promise.all([
        api.operationsOverview(),
        api.marketIngestionRuns(),
      ]);
      setOverview(nextOverview);
      setMarketIngestionRuns(nextMarketIngestionRuns);
      setError(null);
    } catch {
      setError("运行状态 API 暂不可用，请检查本地服务和数据库迁移状态。");
    }
  };

  const refreshActionCenter = async () => {
    try {
      setActionCenter(await api.operationsActionCenter());
      setActionCenterError(null);
    } catch {
      setActionCenter(null);
      setActionCenterError("Operation action center API is unavailable.");
    }
  };

  const refreshReviewPackage = async () => {
    try {
      setReviewPackage(await api.operationsReviewPackage());
      setReviewPackageError(null);
    } catch {
      setReviewPackage(null);
      setReviewPackageError("Operations review package API is unavailable.");
    }
  };

  const refreshReadiness = async () => {
    try {
      setReadiness(await api.systemReadiness());
      setReadinessError(null);
    } catch {
      setReadiness(null);
      setReadinessError("System readiness API is unavailable.");
    }
  };

  useEffect(() => {
    mounted.current = true;
    void refresh();
    void refreshReadiness();
    void refreshActionCenter();
    void refreshReviewPackage();
    return () => {
      mounted.current = false;
    };
  }, []);

  const updateRun = (run: WorkflowRun) => {
    setTrackedRuns((current) => [
      run,
      ...current.filter((item) => item.workflow_run_id !== run.workflow_run_id),
    ].slice(0, 6));
  };

  const triggerJob = async (jobKey: string) => {
    setLoadingJob(jobKey);
    try {
      let run = await api.queueJob(jobKey);
      updateRun(run);
      while (mounted.current && !TERMINAL_RUN_STATUSES.has(run.status)) {
        await delay(nextPollDelayMilliseconds(run));
        if (!mounted.current) return;
        run = await api.run(run.workflow_run_id);
        updateRun(run);
      }
      await refresh();
      await refreshReadiness();
      await refreshActionCenter();
      await refreshReviewPackage();
    } catch {
      setError("固定任务入队或状态轮询失败，请检查本地 worker 状态。");
    } finally {
      setLoadingJob(null);
    }
  };

  const submitActionReview = async (item: OperationTodoItem, reviewStatus: string) => {
    if (!item.review_target_type) return;
    const note = reviewNotes[item.item_id]?.trim()
      || item.default_review_note
      || DEFAULT_ACTION_CENTER_REVIEW_NOTE;
    setReviewingItem(`${item.item_id}:${reviewStatus}`);
    try {
      if (item.review_target_type === "weather_feature") {
        await api.reviewWeatherFeature(item.target_id, reviewStatus, note);
      } else if (item.review_target_type === "market_artifact") {
        await api.reviewMarketArtifact(item.target_id, reviewStatus, note);
      } else if (item.review_target_type === "policy_document") {
        await api.reviewPolicyDocument(item.target_id, reviewStatus, note);
      } else {
        throw new Error(`Unsupported review target: ${item.review_target_type}`);
      }
      await refresh();
      await refreshReadiness();
      await refreshActionCenter();
      await refreshReviewPackage();
      setReviewNotes((current) => {
        const next = { ...current };
        delete next[item.item_id];
        return next;
      });
      setActionReviewError(null);
    } catch {
      setActionReviewError("Action Center review failed. Check the local API and review target.");
    } finally {
      setReviewingItem(null);
    }
  };

  const showWeatherReviewPackage = async (featureSnapshotId: string) => {
    setLoadingWeatherPackageId(featureSnapshotId);
    try {
      setWeatherReviewPackage(await api.weatherFeatureReviewPackage(featureSnapshotId));
      setWeatherReviewPackageError(null);
    } catch {
      setWeatherReviewPackage(null);
      setWeatherReviewPackageError("Weather review package API is unavailable.");
    } finally {
      setLoadingWeatherPackageId(null);
    }
  };

  const showMarketArtifactReviewPackage = async (artifactId: string) => {
    setLoadingMarketArtifactPackageId(artifactId);
    try {
      setMarketArtifactReviewPackage(await api.marketArtifactReviewPackage(artifactId));
      setMarketArtifactReviewPackageError(null);
    } catch {
      setMarketArtifactReviewPackage(null);
      setMarketArtifactReviewPackageError("Market artifact review package API is unavailable.");
    } finally {
      setLoadingMarketArtifactPackageId(null);
    }
  };

  const showPolicyDocumentReviewPackage = async (documentId: string) => {
    setLoadingPolicyDocumentPackageId(documentId);
    try {
      setPolicyDocumentReviewPackage(await api.policyDocumentReviewPackage(documentId));
      setPolicyDocumentReviewPackageError(null);
    } catch {
      setPolicyDocumentReviewPackage(null);
      setPolicyDocumentReviewPackageError("Policy document review package API is unavailable.");
    } finally {
      setLoadingPolicyDocumentPackageId(null);
    }
  };

  const allowedJobKeys = new Set(overview?.actions.map((action) => action.job_key) ?? []);
  const workflow = overview?.workflow_overview;
  const freshness = [...(overview?.freshness ?? [])].sort(
    (left, right) => statusWeight(right.status) - statusWeight(left.status),
  );

  return (
    <Space orientation="vertical" size={18} className="full-width" data-testid="operations-workspace">
      <section className="hero">
        <div>
          <Typography.Text className="eyebrow">OPERATIONS</Typography.Text>
          <Typography.Title level={2}>运行状态</Typography.Title>
          <Typography.Paragraph>
            只读聚合任务、数据新鲜度和来源健康；不执行网页探测，不改变推荐链路。
          </Typography.Paragraph>
        </div>
        {overview && (
          <Tag data-testid="operation-overall-status" color={statusColor(overview.overall_status)}>
            {overview.overall_status}
          </Tag>
        )}
      </section>

      {error && <Alert type="warning" showIcon message={error} />}

      <OperationActionCenterCard
        actionCenter={actionCenter}
        error={actionCenterError}
        reviewError={actionReviewError}
        allowedJobKeys={allowedJobKeys}
        loadingJob={loadingJob}
        reviewingItem={reviewingItem}
        reviewNotes={reviewNotes}
        loadingWeatherPackageId={loadingWeatherPackageId}
        loadingMarketArtifactPackageId={loadingMarketArtifactPackageId}
        loadingPolicyDocumentPackageId={loadingPolicyDocumentPackageId}
        onTriggerJob={(jobKey) => void triggerJob(jobKey)}
        onOpenActionTarget={props.onOpenActionTarget}
        onReviewNoteChange={(itemId, note) => {
          setReviewNotes((current) => ({ ...current, [itemId]: note }));
        }}
        onReviewAction={(item, reviewStatus) => void submitActionReview(item, reviewStatus)}
        onShowWeatherPackage={(featureSnapshotId) => void showWeatherReviewPackage(featureSnapshotId)}
        onShowMarketArtifactPackage={(artifactId) => void showMarketArtifactReviewPackage(artifactId)}
        onShowPolicyDocumentPackage={(documentId) => void showPolicyDocumentReviewPackage(documentId)}
      />

      <WeatherReviewPackageCard
        reviewPackage={weatherReviewPackage}
        error={weatherReviewPackageError}
      />

      <MarketArtifactReviewPackageCard
        reviewPackage={marketArtifactReviewPackage}
        error={marketArtifactReviewPackageError}
      />

      <PolicyDocumentReviewPackageCard
        reviewPackage={policyDocumentReviewPackage}
        error={policyDocumentReviewPackageError}
      />

      <SystemReadinessCard
        readiness={readiness}
        error={readinessError}
        allowedJobKeys={allowedJobKeys}
        loadingJob={loadingJob}
        onTriggerJob={(jobKey) => void triggerJob(jobKey)}
      />

      <OperationsReviewPackageCard
        reviewPackage={reviewPackage}
        error={reviewPackageError}
      />

      {overview ? (
        <>
          <Row gutter={[16, 16]}>
            <Col xs={12} lg={6}>
              <Card>
                <Statistic title="总体状态" value={overview.overall_status} />
              </Card>
            </Col>
            <Col xs={12} lg={6}>
              <Card>
                <Statistic title="运行中" value={workflow?.running ?? 0} />
              </Card>
            </Col>
            <Col xs={12} lg={6}>
              <Card>
                <Statistic title="重试等待" value={workflow?.retry_wait ?? 0} />
              </Card>
            </Col>
            <Col xs={12} lg={6}>
              <Card>
                <Statistic title="失败任务" value={workflow?.failed ?? 0} />
              </Card>
            </Col>
          </Row>

          <Card title="Registered Source Collection Runs" data-testid="operation-ingestion-runs">
            <Table<MarketIngestionRun>
              size="small"
              pagination={false}
              rowKey="ingestion_run_id"
              dataSource={marketIngestionRuns}
              locale={{ emptyText: "No registered source collection runs yet." }}
              columns={[
                {
                  title: "Status",
                  dataIndex: "status",
                  render: (status: string) => <Tag color={statusColor(status)}>{status}</Tag>,
                },
                { title: "Endpoint", dataIndex: "endpoint_id" },
                { title: "Trigger", dataIndex: "trigger_mode" },
                { title: "Adapter", dataIndex: "adapter_key", render: (value: string | null) => value ?? "-" },
                { title: "Inserted", dataIndex: "items_inserted" },
                { title: "Duplicate", dataIndex: "duplicate_items" },
                { title: "Rejected", dataIndex: "rejected_items" },
                {
                  title: "Completed",
                  dataIndex: "completed_at",
                  render: formatTime,
                },
                {
                  title: "Error",
                  dataIndex: "error_code",
                  render: (value: string | null) => value ?? "-",
                },
              ]}
            />
            <Typography.Text type="secondary">
              Chinese policy candidates remain disabled unless a registered endpoint is reviewed,
              verified, and collection_enabled=true.
            </Typography.Text>
          </Card>

          <Row gutter={[16, 16]}>
            <Col xs={24} xl={15}>
              <Card title="数据新鲜度" data-testid="operation-freshness">
                <Table<FreshnessItem>
                  size="small"
                  pagination={false}
                  rowKey="key"
                  dataSource={freshness}
                  columns={[
                    {
                      title: "状态",
                      dataIndex: "status",
                      render: (status: OperationsStatus) => <Tag color={statusColor(status)}>{status}</Tag>,
                    },
                    { title: "对象", dataIndex: "label" },
                    { title: "最近时间", dataIndex: "latest_at", render: formatTime },
                    { title: "年龄", dataIndex: "age_hours", render: formatAge },
                    {
                      title: "边界",
                      render: (_value: unknown, item) => (
                        <Space wrap>
                          {item.data_mode && <Tag>{item.data_mode}</Tag>}
                          {item.research_only && <Tag>research_only</Tag>}
                        </Space>
                      ),
                    },
                    { title: "说明", dataIndex: "message" },
                  ]}
                />
              </Card>
            </Col>
            <Col xs={24} xl={9}>
              <Card title="来源健康" data-testid="operation-source-health">
                <List<HealthItem>
                  dataSource={overview.health}
                  renderItem={(item) => (
                    <List.Item>
                      <Space orientation="vertical" size={2}>
                        <Space>
                          <Tag color={statusColor(item.status)}>{item.status}</Tag>
                          <Typography.Text strong>{item.label}</Typography.Text>
                        </Space>
                        <Typography.Text>{item.message}</Typography.Text>
                        <Typography.Text type="secondary">
                          {item.observed_at ? `最近记录 ${formatTime(item.observed_at)}` : "无主动探测"}
                        </Typography.Text>
                      </Space>
                    </List.Item>
                  )}
                />
              </Card>
            </Col>
          </Row>

          <Row gutter={[16, 16]}>
            <Col xs={24} xl={13}>
              <Card title="固定任务操作">
                <List<ActionItem>
                  dataSource={overview.actions}
                  renderItem={(action) => (
                    <List.Item actions={[
                      <Button
                        key={action.job_key}
                        data-testid={`operation-trigger-${action.job_key}`}
                        loading={loadingJob === action.job_key}
                        disabled={!action.manual_trigger_enabled}
                        onClick={() => void triggerJob(action.job_key)}
                      >
                        人工触发
                      </Button>,
                    ]}>
                      <List.Item.Meta
                        title={(
                          <Space wrap>
                            <Typography.Text>{action.label}</Typography.Text>
                            {action.recommended && <Tag color="gold">建议处理</Tag>}
                            {action.research_only && <Tag>research_only</Tag>}
                          </Space>
                        )}
                        description={`${action.description} · ${action.schedule} · ${action.timezone} · ${action.reason}`}
                      />
                    </List.Item>
                  )}
                />
              </Card>
            </Col>
            <Col xs={24} xl={11}>
              <Card title="失败与重试等待">
                <List<WorkflowRun>
                  dataSource={overview.recent_incidents}
                  locale={{ emptyText: "暂无失败或重试等待任务" }}
                  renderItem={(run) => (
                    <List.Item actions={[
                      <Button
                        key={run.workflow_run_id}
                        data-testid={`rerun-${run.workflow_run_id}`}
                        disabled={!allowedJobKeys.has(run.workflow_key)}
                        loading={loadingJob === run.workflow_key}
                        onClick={() => void triggerJob(run.workflow_key)}
                      >
                        重新入队同类任务
                      </Button>,
                    ]}>
                      <Space orientation="vertical" size={2}>
                        <Space wrap>
                          <Tag data-testid={`operation-run-status-${run.workflow_run_id}`} color={statusColor(run.status)}>
                            {run.status}
                          </Tag>
                          <Typography.Text>{run.workflow_key}</Typography.Text>
                          <Typography.Text type="secondary">尝试 {run.attempt_count}</Typography.Text>
                        </Space>
                        {run.error_code && <Typography.Text type="danger">{run.error_code}</Typography.Text>}
                        <Typography.Text type="secondary">
                          {run.completed_at ? `完成 ${formatTime(run.completed_at)}` : `可用 ${formatTime(run.available_at)}`}
                        </Typography.Text>
                        <Typography.Text type="secondary">{String(run.summary.message ?? "")}</Typography.Text>
                      </Space>
                    </List.Item>
                  )}
                />
              </Card>
            </Col>
          </Row>

          <Card title="本次手工触发状态">
            {trackedRuns.length > 0 ? (
              <List<WorkflowRun>
                dataSource={trackedRuns}
                renderItem={(run) => (
                  <List.Item>
                    <Space wrap>
                      <Tag data-testid={`tracked-run-status-${run.workflow_run_id}`} color={statusColor(run.status)}>
                        {run.status}
                      </Tag>
                      <Typography.Text>{run.workflow_key}</Typography.Text>
                      <Typography.Text type="secondary">尝试 {run.attempt_count}</Typography.Text>
                      {run.error_code && <Typography.Text type="danger">{run.error_code}</Typography.Text>}
                    </Space>
                  </List.Item>
                )}
              />
            ) : (
              <Empty description="暂无手工触发任务" />
            )}
          </Card>
        </>
      ) : (
        <Card>
          <Empty description="正在加载运行状态" />
        </Card>
      )}
    </Space>
  );
}
