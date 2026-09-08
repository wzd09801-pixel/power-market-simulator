import { ReloadOutlined } from "@ant-design/icons";
import { Alert, Button, Card, Col, Empty, Input, List, Row, Space, Statistic, Tag, Typography } from "antd";
import { useEffect, useRef, useState } from "react";

import { api } from "../api";
import { nextPollDelayMilliseconds } from "../operationPolling";
import type { BriefDetail, BriefReview, BriefSummary, OperationJob, PolicyWatchItem, WorkflowRun } from "../types";

const TERMINAL_RUN_STATUSES = new Set(["succeeded", "skipped", "failed"]);
const delay = (milliseconds: number) =>
  new Promise((resolve) => window.setTimeout(resolve, milliseconds));

function runColor(status: string) {
  if (status === "succeeded") return "green";
  if (status === "skipped") return "default";
  if (status === "failed") return "red";
  if (status === "retry_wait") return "gold";
  if (status === "running") return "blue";
  return "default";
}

function sourceRoleLabel(sourceRole: PolicyWatchItem["source_role"]) {
  if (sourceRole === "official_policy") return "官方政策";
  if (sourceRole === "official_market_notice") return "官方市场通知";
  return "公共研究补充";
}

function sourceRoleColor(sourceRole: PolicyWatchItem["source_role"]) {
  if (sourceRole === "official_policy") return "blue";
  if (sourceRole === "official_market_notice") return "cyan";
  return "default";
}

function policyWatchExcludedCount(facts: Record<string, unknown>) {
  const policyWatch = facts.policy_watch;
  if (!policyWatch || typeof policyWatch !== "object") return 0;
  const excluded = (policyWatch as { excluded_restricted_chunks?: unknown }).excluded_restricted_chunks;
  return Number(excluded ?? 0);
}

export function BriefDashboard(props: {
  targetBriefId?: string | null;
}) {
  const [brief, setBrief] = useState<BriefDetail | null>(null);
  const [briefHistory, setBriefHistory] = useState<BriefSummary[]>([]);
  const [jobs, setJobs] = useState<OperationJob[]>([]);
  const [runs, setRuns] = useState<WorkflowRun[]>([]);
  const [loading, setLoading] = useState(false);
  const [triggeringJob, setTriggeringJob] = useState<string | null>(null);
  const [reviewNote, setReviewNote] = useState("");
  const [reviewingStatus, setReviewingStatus] = useState<BriefReview["review_status"] | null>(null);
  const [reviewError, setReviewError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const mounted = useRef(true);

  const updateRun = (run: WorkflowRun) => {
    setRuns((current) => [run, ...current.filter((item) => item.workflow_run_id !== run.workflow_run_id)].slice(0, 8));
  };

  const load = async (targetBriefId?: string | null) => {
    try {
      const [jobItems, runItems, historyItems, latest] = await Promise.all([
        api.jobs(),
        api.runs(),
        api.briefs(),
        api.latestBrief(),
      ]);
      setJobs(jobItems);
      setRuns(runItems);
      setBriefHistory(historyItems);
      const briefId = targetBriefId ?? latest?.brief_id;
      setBrief(briefId ? await api.briefDetail(briefId) : null);
      setError(null);
    } catch {
      setError("本地 API 暂不可用，请检查数据库迁移和服务状态。");
    }
  };

  useEffect(() => {
    mounted.current = true;
    void load(props.targetBriefId);
    return () => {
      mounted.current = false;
    };
  }, [props.targetBriefId]);

  const generate = async () => {
    setLoading(true);
    try {
      const generated = await api.generateBrief();
      const [detail, historyItems] = await Promise.all([
        api.briefDetail(generated.brief_id),
        api.briefs(),
      ]);
      setBrief(detail);
      setBriefHistory(historyItems);
      setError(null);
    } catch {
      setError("简报生成失败，请检查本地 API 状态。");
    } finally {
      setLoading(false);
    }
  };

  const openBrief = async (briefId: string) => {
    try {
      setBrief(await api.briefDetail(briefId));
      setReviewError(null);
    } catch {
      setReviewError("简报详情暂不可用，请检查本地 API 状态。");
    }
  };

  const submitBriefReview = async (reviewStatus: BriefReview["review_status"]) => {
    if (!brief) return;
    const note = reviewNote.trim();
    if (!note) {
      setReviewError("请先填写复核说明。");
      return;
    }
    setReviewingStatus(reviewStatus);
    try {
      await api.reviewBrief(brief.brief_id, reviewStatus, note);
      const [detail, historyItems] = await Promise.all([
        api.briefDetail(brief.brief_id),
        api.briefs(),
      ]);
      setBrief(detail);
      setBriefHistory(historyItems);
      setReviewNote("");
      setReviewError(null);
    } catch {
      setReviewError("简报复核提交失败，请检查本地 API 状态。");
    } finally {
      setReviewingStatus(null);
    }
  };

  const triggerJob = async (jobKey: string) => {
    setTriggeringJob(jobKey);
    try {
      let run = await api.queueJob(jobKey);
      updateRun(run);
      while (
        mounted.current
        && !TERMINAL_RUN_STATUSES.has(run.status)
      ) {
        await delay(nextPollDelayMilliseconds(run));
        if (!mounted.current) return;
        run = await api.run(run.workflow_run_id);
        updateRun(run);
      }
      setError(null);
    } catch {
      setError("任务触发或状态轮询失败，请检查本地 worker 状态。");
    } finally {
      setTriggeringJob(null);
    }
  };

  const facts = brief?.deterministic_facts ?? {};
  const failures = Number(facts.workflow_failure_count ?? 0);
  const qualityIssues = Number(facts.market_quality_issue_count ?? 0);
  const excludedPolicyChunks = policyWatchExcludedCount(facts);

  return (
    <Space orientation="vertical" size={18} className="full-width" data-testid="brief-dashboard">
      <section className="hero">
        <div>
          <Typography.Text className="eyebrow">DAILY INTELLIGENCE</Typography.Text>
          <Typography.Title level={2}>今日变化与风险</Typography.Title>
          <Typography.Paragraph>
            事实、证据和人工审核优先。任何研究输出都不会自动执行交易。
          </Typography.Paragraph>
        </div>
        <Button
          data-testid="generate-brief"
          type="primary"
          icon={<ReloadOutlined />}
          loading={loading}
          onClick={generate}
        >
          重新生成简报
        </Button>
      </section>

      <Row gutter={[16, 16]}>
        <Col xs={24} md={8}><Card><Statistic title="风险级别" value={brief?.risk_level ?? "未生成"} /></Card></Col>
        <Col xs={24} md={8}><Card><Statistic title="数据质量问题" value={qualityIssues} /></Card></Col>
        <Col xs={24} md={8}><Card><Statistic title="失败工作流" value={failures} /></Card></Col>
      </Row>

      {error && <Alert type="warning" showIcon message={error} />}

      {brief ? (
        <Card title={`简报 ${brief.target_date}`} extra={<Tag color="gold">{brief.human_review_status}</Tag>}>
          <Typography.Paragraph>{String(brief.narrative.summary ?? "本地确定性简报")}</Typography.Paragraph>
          {brief.missing_information.length > 0 && (
            <Alert type="warning" showIcon message="缺失信息" description={brief.missing_information.join("；")} />
          )}
          <Space wrap className="card-footer">
            <Tag data-testid="brief-llm-mode" color={brief.llm_used ? "blue" : "default"}>
              {brief.llm_used ? "DeepSeek 已解释" : "确定性回退"}
            </Tag>
            <Tag color="green">禁止自动交易</Tag>
            <Tag>置信度 {brief.confidence_score.toFixed(2)}</Tag>
          </Space>
        </Card>
      ) : <Empty description="尚未生成简报" />}

      {brief && (
        <Card
          title="政策观察"
          data-testid="policy-watch-card"
          extra={<Tag color="green">本地只读检索</Tag>}
        >
          {excludedPolicyChunks > 0 && (
            <Alert
              type="info"
              showIcon
              message={`已排除 ${excludedPolicyChunks} 个未授权分块，不进入外部模型 prompt`}
            />
          )}
          {brief.policy_watch.length > 0 ? (
            <List
              dataSource={brief.policy_watch}
              renderItem={(item) => (
                <List.Item data-testid={`policy-watch-${item.watch_id}`}>
                  <Space orientation="vertical" size={4} className="full-width">
                    <Space wrap>
                      <Typography.Text strong>{item.title}</Typography.Text>
                      <Tag color={sourceRoleColor(item.source_role)}>
                        {sourceRoleLabel(item.source_role)}
                      </Tag>
                      <Tag color={item.external_processing_allowed ? "blue" : "gold"}>
                        {item.external_processing_allowed ? "外发已授权" : "本地引用"}
                      </Tag>
                    </Space>
                    <Typography.Text>{item.observation}</Typography.Text>
                    <Typography.Paragraph ellipsis={{ rows: 2 }}>
                      {item.excerpt}
                    </Typography.Paragraph>
                    <Space wrap>
                      <Tag>{item.citation.source_name}</Tag>
                      <Tag>{item.citation.document_layer}</Tag>
                      <Typography.Text type="secondary">
                        捕获时间 {new Date(item.captured_at).toLocaleString()}
                      </Typography.Text>
                    </Space>
                  </Space>
                </List.Item>
              )}
            />
          ) : (
            <Empty description="暂无本地政策观察" />
          )}
          <Typography.Text type="secondary">
            政策观察不进入自动交易，不改变示例甲省推荐证据链。
          </Typography.Text>
        </Card>
      )}

      {brief && (
        <Card title="人工复核" data-testid="brief-review-panel">
          {reviewError && <Alert type="warning" showIcon message={reviewError} />}
          <Space orientation="vertical" size={12} className="full-width">
            <Input.TextArea
              data-testid="brief-review-note"
              rows={3}
              value={reviewNote}
              onChange={(event) => setReviewNote(event.target.value)}
              placeholder="填写本次复核说明，例如：已核对政策观察与缺失信息。"
            />
            <Space wrap>
              <Button
                data-testid="review-brief-approved"
                type="primary"
                loading={reviewingStatus === "approved"}
                onClick={() => void submitBriefReview("approved")}
              >
                批准
              </Button>
              <Button
                data-testid="review-brief-needs_revision"
                danger
                loading={reviewingStatus === "needs_revision"}
                onClick={() => void submitBriefReview("needs_revision")}
              >
                需修订
              </Button>
              <Tag color="gold">{brief.human_review_status}</Tag>
              <Tag color="green">无自动交易</Tag>
            </Space>
            <List
              data-testid="brief-review-history"
              size="small"
              locale={{ emptyText: "暂无复核记录" }}
              dataSource={brief.reviews}
              renderItem={(review) => (
                <List.Item>
                  <Space orientation="vertical" size={2}>
                    <Space wrap>
                      <Tag color={review.review_status === "approved" ? "green" : "gold"}>
                        {review.review_status}
                      </Tag>
                      <Typography.Text>{review.actor}</Typography.Text>
                      <Typography.Text type="secondary">{review.created_at}</Typography.Text>
                    </Space>
                    <Typography.Text>{review.note}</Typography.Text>
                  </Space>
                </List.Item>
              )}
            />
          </Space>
        </Card>
      )}

      <Card title="简报历史" data-testid="brief-history">
        <List
          dataSource={briefHistory}
          locale={{ emptyText: "暂无简报历史" }}
          renderItem={(item) => (
            <List.Item
              actions={[
                <Button
                  key={item.brief_id}
                  data-testid={`open-brief-${item.brief_id}`}
                  onClick={() => void openBrief(item.brief_id)}
                >
                  查看
                </Button>,
              ]}
            >
              <List.Item.Meta
                title={<Space>{item.target_date}<Tag>{item.human_review_status}</Tag></Space>}
                description={`政策观察 ${item.policy_watch_count} · 缺失信息 ${item.missing_information_count} · 置信度 ${item.confidence_score.toFixed(2)}`}
              />
            </List.Item>
          )}
        />
      </Card>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={14}>
          <Card title="采集与生成任务">
            <List dataSource={jobs} renderItem={(job) => (
              <List.Item actions={[
                <Button
                  key={job.job_key}
                  data-testid={`trigger-${job.job_key}`}
                  loading={triggeringJob === job.job_key}
                  disabled={!job.manual_trigger_enabled}
                  onClick={() => void triggerJob(job.job_key)}
                >
                  人工触发
                </Button>,
              ]}>
                <List.Item.Meta
                  title={<Space>{job.description}{job.research_only && <Tag>research_only</Tag>}</Space>}
                  description={`${job.schedule} · ${job.timezone}`}
                />
              </List.Item>
            )} />
          </Card>
        </Col>
        <Col xs={24} lg={10}>
          <Card title="最近运行">
            <List dataSource={runs} locale={{ emptyText: "暂无运行记录" }} renderItem={(run) => (
              <List.Item>
                <Space orientation="vertical" size={2}>
                  <Space>
                    <Tag data-testid={`run-status-${run.workflow_run_id}`} color={runColor(run.status)}>
                      {run.status}
                    </Tag>
                    <Typography.Text>{run.workflow_key}</Typography.Text>
                    <Typography.Text type="secondary">尝试 {run.attempt_count}</Typography.Text>
                  </Space>
                  {run.error_code && <Typography.Text type="danger">{run.error_code}</Typography.Text>}
                  {run.completed_at && <Typography.Text type="secondary">完成于 {run.completed_at}</Typography.Text>}
                  <Typography.Text type="secondary">{String(run.summary.message ?? "")}</Typography.Text>
                </Space>
              </List.Item>
            )} />
          </Card>
        </Col>
      </Row>
    </Space>
  );
}
