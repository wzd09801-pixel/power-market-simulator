# First-Data-Day 操作员使用手册

本手册给本地研究工作站操作员使用。它覆盖从“目前没有任何数据”到“以后拿到一包本地文件后先验收、再人工导入和审查”的最小流程。

这不是生产部署说明，也不是数据源接入方案。当前系统目标是数据就绪和 RAG 就绪的人审决策支持框架。

## 1. 安全边界

操作员必须保持以下边界：

- 不接入新的真实外部数据源，不接示例甲省匿名官方 96 点价格适配器。
- 不把本地上传文档默认发送给外部模型，`external_processing_allowed=false` 是 RAG 默认值。
- 不启动自动交易、自动下单或交易平台登录自动化，所有报告和推荐草稿都必须保留 `no_auto_trading=true`。
- 不做模型自动晋级，训练和回测结果只能作为 `research_only` 和 candidate 级材料。
- 不把 `research_only` 预测、BENCH 研究材料或 policy-watch 结果直接放进推荐执行链。
- 不把模拟公司数据称为真实运营数据；没有验证内部数据前，公司侧输入只能是 `scenario_simulated` 或未来明确上传的 `user_uploaded`。

## 2. 空状态闭环：无数据是合法状态

没有文件时不要造数据，也不要为了让校验通过而填假值。系统应该稳定告诉你缺什么：

- RAG 不能回答无证据问题，`rag_answering_enabled=false`。
- Forecast training 和 backtest 不能启动，`forecast_training_enabled=false`，`backtest_enabled=false`。
- Recommendation 只能保持 `scenario_simulated_only`，并且继续要求人工审查。
- External model call、production model promotion、database write、file upload 都不能由 dry-run 触发。
- 页面或校验报告如果显示缺项，先补 contract 和 metadata，再考虑导入。

## 3. 契约和模板：总体操作顺序

每次准备首日数据包时按这个顺序执行：

```powershell
.\scripts\validate_framework_readiness.ps1
.\scripts\scaffold_first_data_day_package.ps1 --output-dir <local-first-data-day-folder> --json
.\scripts\validate_first_data_day_package.ps1 --package-dir <local-first-data-day-folder> --json
```

这一步是 dry-run 校验入口。如果 dry-run 报告 `ok=false` 和 `status=missing_required_inputs`，这是空目录或未补齐文件时的正常结果。先读 `missing_items`、`workflow_readiness` 和 `next_actions`，不要跳过验收直接导入。

只有 dry-run 变成 `status=ready_for_manual_review` 后，才进入现有人工入口：

- RAG 文档：使用现有 policy document upload API 或前端上传工作流，之后检查 document review package、citation 和 human review。
- Forecast：使用现有 manual research dataset import 或本地导入工作台，之后检查 dataset review package，再考虑 `seasonal_naive` 或 `calendar_mean` baseline backtest。
- Market artifact：只做 manual preservation 和 review package，不从 manifest 的 URL 自动抓取。
- Weather：只把本地 weather reference metadata 作为人工审查材料，不自动影响推荐。
- Recommendation：只生成 scenario-simulated 草稿和人工审查上下文，不执行交易。

## 4. 本地包目录

脚手架会创建：

```text
<local-first-data-day-folder>/
  first_data_day_package.json
  README.md
  forecast/
  rag/
  market/
  weather/
  recommendation/
```

目录用途：

- `forecast/`：未来 15 分钟价格曲线 CSV 和 forecast dataset JSON。CSV 至少包含 `interval_start`、`price`，一日有效曲线应是 96 个 15 分钟点。用途保持 `research_only`。
- `rag/`：未来 PDF、DOCX、HTML、TXT 或 Markdown 文档。每个文档都要有 title、source、timestamp、permission 和 `human_review_required=true`。
- `market/`：人工保存的公开市场网页或文件快照。这里是证据保存，不是 crawler 队列。
- `weather/`：本地准备的 weather reference JSON metadata。它只能进入 review package，不能自动触发推荐。
- `recommendation/`：推荐审查上下文 JSON。默认 `evidence_ready=false`，`recommendation_mode=scenario_simulated_only`。

不要放入：

- API key、cookie、账号、密码、交易平台导出、私有公司交易数据。
- 为了通过 dry-run 临时编造的 CSV/JSON/PDF/DOCX/HTML。
- 会暗示自动下单、生产模型晋级或外部模型调用的配置。

## 5. Manifest 字段填写

每个 `files[]` 条目至少要把路径、类型、目标 workflow 和 metadata 填清楚。常用字段含义如下：

| 字段 | 怎么填 |
| --- | --- |
| `relative_path` | 文件在本地包内的相对路径，不能用绝对路径，不能包含 `..`。 |
| `file_type` | 只能使用 dry-run 支持的类型：`csv`、`json`、`pdf`、`docx`、`html`、`txt`、`md`。 |
| `target_workflow` | 指向用途，例如 `forecast_research_curve`、`rag_document_upload`、`market_artifact_manual_preservation`。 |
| `data_mode` | `public_observed`、`public_derived`、`scenario_simulated`、`user_uploaded` 之一；没有验证内部数据前不要写成真实运营数据。 |
| `source_name` | 操作员能审查的来源名称，例如“本地上传政策 PDF”或“人工保存市场公告”。 |
| `source_url` | 只作为 provenance；dry-run 不 fetch，不 probe。未知就保留 `null`。 |
| `source_timestamp` | 来源发布时间或文件生成时间；未知就保留 `null`，不要猜。 |
| `timezone` | 示例甲省电力场景默认 `Asia/Shanghai`，forecast/weather JSON 也应保持一致。 |
| `unit` | 价格用 `CNY_per_MWh`，天气可用 `weather_reference`，文档类可为 `null`。 |
| `permission` | 说明为什么可以本地使用，例如 `local_operator_upload` 或 `manual_preservation_only`。 |
| `visibility_scope` | 默认 `local_only`。 |
| `human_review_required` | 必须为 `true`。 |

Workflow 额外要求：

- RAG：`external_processing_allowed=false`，`cited_evidence_required=true`。
- Forecast：`usage_scope=research_only`，`interval_minutes=15`，`price_unit=CNY_per_MWh`。
- Market/weather：`manual_submission_only=true`，`fetch_performed=false`，`network_probe_performed=false`。
- Recommendation：`recommendation_mode=scenario_simulated_only`，`no_auto_recommendation_execution=true`，`no_auto_trading=true`。

## 6. Dry-Run 输出解读

`validate_first_data_day_package.ps1 --json` 的关键字段：

- `ok`：整体是否通过。空目录通常是 `false`。
- `status`：
  - `missing_required_inputs`：目录、manifest 或声明文件缺失；按 `missing_items` 补齐。
  - `invalid_manifest`：manifest 语法、字段、安全默认值或本地文件轻量形状不合格。
  - `ready_for_manual_review`：只表示本地包通过 dry-run，可以进入人工导入和审查，不表示数据已被导入。
- `workflow_readiness`：RAG、forecast、backtest、market/weather、recommendation 分别显示 `disabled`、`missing_required_inputs` 或 `ready_for_manual_review`。
- `missing_items`：缺少的相对路径或 manifest。
- `disabled_capabilities`：当前保持禁用的能力，例如 RAG answering、forecast training、backtest、external model call、production model promotion。
- `simulated_only_capabilities`：只能模拟的能力，例如 recommendation generation 和 hydro optimization preview。
- `next_actions`：下一步人工动作。严格按这里补文件和 metadata，再重新 dry-run。

## 7. 常见失败处理

| 失败现象 | 处理 |
| --- | --- |
| 空目录返回 `missing_required_inputs` | 正常。先运行 scaffold，再按 `missing_items` 补真实未来文件。 |
| 缺少 `first_data_day_package.json` | 从 `docs/import_contracts/first_data_day_package.example.json` 复制，或重新运行 scaffold。 |
| Manifest 是空文件或 JSON 解析失败 | 修复 JSON 语法，不要直接进入导入。 |
| CSV header 缺 `interval_start` 或 `price` | 修正 CSV header；不要在 manifest 里假装字段存在。 |
| Forecast JSON 缺 `points` 或 `usage_scope` 不是 `research_only` | 修正 JSON shape 和用途边界。 |
| Weather JSON 缺 `location_id`、`timezone` 或 `hourly_variables` | 补齐 reference metadata；不要从 dry-run 发起 fetch。 |
| Recommendation review context 的 `evidence_ready` 不是 `false` | 首日包阶段先保持未就绪，等人工证据审查后再进入后续流程。 |
| Unsupported extension | 改用支持类型，或等后续明确增加 contract。 |
| 路径包含绝对路径或 `..` | 把文件放回本地包目录内，使用安全相对路径。 |
| `external_processing_allowed` 不是 `false` | 恢复本地 RAG 默认边界，除非后续有单独授权流程。 |
| `no_auto_trading` 不是 `true` | 立即修正；该包不能进入导入或推荐审查。 |

## 8. 通过后怎么交给人工审查

Dry-run 通过后仍然不代表可以自动使用。按 workflow 分别进入人工审查：

- RAG：上传后检查 chunk、citation、review package 和 human review 记录；没有 cited evidence 时不能回答。
- Forecast/backtest：确认 96 点、timezone、unit、data mode 和 quality issues；只运行 baseline candidate backtest，不 promotion。
- Market/weather：检查 manual artifact 和 weather feature review package；它们是证据材料，不自动生成交易建议。
- Recommendation：只有在 required scenario inputs、evidence entries、missing data warnings、risk level、confidence score 和 human review status 都可审查时，才生成草稿。

每一步都保留人工审查记录。任何缺证据、缺 metadata、权限不清或 data mode 不确定的文件，都停在 dry-run 或 review package 阶段。
