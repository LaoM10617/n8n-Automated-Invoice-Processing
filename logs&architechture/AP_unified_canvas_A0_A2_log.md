# A0–A2 统一业务画布实施记录

日期：2026-10-07  
状态：**A0、A1、A2 完成；候选草稿已保存并读回，尚未发布、执行或进行端到端验收。**  
依据：[实施指南](AP_unified_canvas_native_agent_implementation_guide_zh.md)。本轮保留 Python Agent；A3/A4、原生 Agent 迁移及 Phase03 未实施。

## 1. 交付与当前运行状态

- 实例候选：[Process AP Invoices — Review & Excel Export](http://localhost:5678/workflow/7xXB2pjXOE1EQ2bY)，ID `7xXB2pjXOE1EQ2bY`。
- 保存位置：当前用户的 n8n Personal project 根目录，无 folder；不是新建团队项目。
- 导入文件：`n8n_workflows/AP_unified_canvas_python_agent_v1.json`。23 个执行节点、4 个 Sticky Notes、25 条连接、4 个有效节点组。
- SDK 来源：`scripts/AP_unified_canvas_python_agent_v1.ts`。最终 JSON 含实例读回的设置；单独用 SDK 重建时必须按文件顶部说明补设隐私保存策略。
- 验证证据：[AP_unified_canvas_A0_A2_verification.json](AP_unified_canvas_A0_A2_verification.json)。
- 当前运行入口仍是旧 01、02。候选 `active=false`、`activeVersionId=null`。没有调用 publish、execute、test 工具；没有切换后端配置、重启服务、生成新审批、邮件或 Excel。

## 2. A0：固定基线

执行前读取了项目规则、最新交接、计划与相关业务文档、实际代码和 compose 配置，并先通过 MCP 读取实例用户偏好（无保存偏好）。Git 中已有大量未提交改动，均作为基线保留，不归为本轮实现。

| 原流程 | 草稿 versionId | 发布 activeVersionId | 启用 |
| --- | --- | --- | --- |
| APApprovalIntakeV9 | bebacb60-3ec1-4569-af1f-df9b5b6d1ec2 | 0ed7c114-27ff-4704-822c-053243669104 | 是 |
| APReviewExportV1 | a48ef5ce-0339-495a-8661-1aaf4b2fa2fb | a48ef5ce-0339-495a-8661-1aaf4b2fa2fb | 是 |

01 草稿与发布版本只存在位置差异；02 一致。保存完整 MCP 快照（包含 draft 与 activeVersion，不是直接导入格式）：

- `n8n_workflows/baseline_APApprovalIntakeV9_20261007-120021Z.json`
- `n8n_workflows/baseline_APReviewExportV1_20261007-120021Z.json`

一致性备份目录：`data/baselines/unified-canvas-a0-20261007-120021Z/`（已验证被 Git 忽略）。
备份脚本：`scripts/snapshot_unified_canvas.py`；固定目录且拒绝覆盖，不能直接重跑覆盖本次基线。

备份包含：

- SQLite online backup，integrity_check 与 foreign_key_check 通过。
- 167 个工作区文件的副本／SHA-256，Git HEAD 与未提交状态。
- 21 个原件、5 个既有导出文件的副本、大小与 SHA-256。
- manifest 表行数；包括 invoices=21、review_events=5、export_batches=3、outcome_notifications=8。
- compose、原节点凭据**引用**、表单／Webhook 路径、启用状态。没有复制 .env、密钥值或 n8n 凭据数据库。

只读检查实际 Docker：n8n 2.42.3、python-api、Mailpit 均运行，后两者 healthy。实际事件配置：

| 配置 | A0 与 A2 当前值 |
| --- | --- |
| AP_REVIEW_EVENT_URL | http://n8n:5678/webhook/ap-review-export-v1 |
| AP_BATCH_EVENT_URL | http://n8n:5678/webhook/ap-batch-export-v1 |
| AP_OUTCOME_AUTODISPATCH | 1 |
| AP_DATA_DIR | /data/ap |

恢复基线时先停止业务写入，核对 manifest，再恢复 SQLite／原件／导出配套快照；不要在运行中的 SQLite 上直接覆盖文件或遗留旧 WAL。工作流恢复优先既有版本，须区分 draft 与 activeVersion。A2 没有切换运行入口，因此当前不需要恢复数据库或旧流程；放弃候选只需保持未发布。本轮未演练恢复，备份完整性不等同恢复演练。

## 3. A1：逐节点业务映射

| 来源 | 原节点 | 候选节点 | 处理与业务意义 |
| --- | --- | --- | --- |
| 01 | Run Gmail Batch | Run Demo Email Batch | 重命名；手动启动既有演示邮件查询，不是定时收件。 |
| 01 | Gmail | Fetch Invoice Emails | 重命名；保留只读查询、附件下载和现有凭据，不标记或发送邮件。 |
| 01 | Upload Invoice | Upload Invoice | 保留；仅表单 path 改为候选独有值。 |
| 01 | Prepare Attachments | Prepare Invoice Files | 重命名、单节点技术分组；代码原样保留，显式声明 runOnceForAllItems。 |
| 01 | Process Each Invoice | Process One Invoice | 重命名；显式 batchSize=1，保留逐附件顺序处理。 |
| 01 | Batch Complete | Email Batch Complete | 重命名；邮件批次循环完成出口。 |
| 01 | Archive & Read Document | Save Invoice & Read Text | 重命名；与提取节点分组，保存原件并读取文本／OCR。 |
| 01 | Invoice Analysis Agent | Extract Invoice Details | 重命名；同组，仍调用 Python LangChain Agent，说明中明确实际实现。 |
| 01 | Validate & Apply Approval Policy | Check Invoice & Apply Approval Rules | 重命名；保留后端校验、查重、审批事务与异常门禁，主画布可见。 |
| 01 | Decision Saved? | Route Invoice Result | 与 Route Outcome 合并为 Switch；只路由已保存结果。 |
| 01 | Route Outcome | Route Invoice Result | 同上；自动批准、已有决定、待审核、跳过、失败分别展示。 |
| 01 | Dispatch Review Outcome | Forward Saved Decision | 重命名；派发已持久化事件，不再次批准，也不生成 Excel。 |
| 01 | Notify Reviewer | Request Invoice Review | 重命名；本地 Mailpit 审核链接及异常说明。 |
| 01 | Record Exception | Read Skipped or Failed Result | 纠正名称；当前 API 读取已保存的 skipped/failed，不是创建新的异常记录。 |
| 01 | Return or Continue | Continue Email Batch? | 重命名；邮件回到循环，上传进入响应，保留 source 关联。 |
| 01 | Upload Result | Show Upload Result | 重命名；原响应表达式保留，返回真实结果与审核／导出入口。 |
| 01 | Business Overview | Start Here | 替换说明；概括接收、AI 提取和确定性批准门禁。 |
| 01 | Current Scope | Candidate Status | 替换说明；草稿边界及 A3 前置条件。 |
| 02 | Review Decision Received | Approval Decision Received | 重命名、唯一 path；接收自动及人工决定，不能叫 Human Review Completed。 |
| 02 | Load Current Decision | Verify Saved Approval Decision | 重命名、与 Approved? 分组；重新读取权威事件与当前状态。 |
| 02 | Approved or Rejected? | Approved? | 重命名；保留 category 判断，批准／拒绝通知分别可见。 |
| 02 | Notify Approval and Register | Send Approval Confirmation | 重命名；清单记录已存在，只发送本地批准通知。 |
| 02 | Notify Rejection | Send Rejection Notice | 重命名；保留拒绝通知，拒绝记录不进入批准清单。 |
| 02 | Excel Batch Ready | Excel File Ready | 重命名、唯一 path；文件完成事件，不能叫 Export Excel。 |
| 02 | Verify Saved Excel Batch | Check Export File | 重命名、与下载通知分组；读取既有批次和文件。 |
| 02 | Notify Excel Download | Send Excel Download Link | 重命名；通知已生成文件的下载地址。 |
| 02 | Decision and Export Contract | Reviewer Actions | 替换说明；说明审核操作、Mailpit 链接和独立决定入口。 |
| 02 | Recovery and Local Scope | Excel Actions | 替换说明；用户选择清单并下载，导出不是支付或外部记账。 |

审批政策未改：低于 10,000 EUR 只是门禁之一，仍要求正数金额、完整字段、校验证据与重复处理等全部符合既有规则。AI 不能批准；批准不等于付款。

`Route Invoice Result` 按首次匹配分流：

1. `decision_ready + review_status=approved + approval_method=automatic` → Automatically Approved。
2. 其余 `decision_ready` → Existing Decision（可包含重投的人工批准或拒绝，不伪称自动批准）。
3. `review_ready` → Needs Human Review。
4. `skipped` → Skipped File。
5. fallback → Failed or Unexpected。后端 exception 接口只接受相应既有结果；不以成功结果吞掉未知状态。

前两路共用已有 handoff；待审核走已有通知；跳过／失败读取持久化结果。所有有效处理结果汇合后，邮件返回顺序循环，单文件上传返回表单。技术传输故障仍按既有服务／恢复机制处理，不能将本次静态检查写成故障隔离运行验收。

客户操作入口：

- 审核：打开 [Mailpit](http://127.0.0.1:8025) 内对应发票的 `/reviews/{invoice_id}` 链接，对照原件、保存修改、批准或拒绝。没有虚构通用审核列表页。
- 导出：打开 [Export Portal](http://127.0.0.1:8000/exports)，筛选／勾选已批准记录并下载合并 Excel。仍由用户选择时机，文件先生成，随后进入 Excel File Ready 通知链。
- 新表单目前未发布，不能作为可用生产入口提供给客户。

## 4. A2：独立候选实现

统一画布分三个业务区域：接收与检查、审批结果通知、Excel 文件交付。四个入口是手动 Gmail、上传表单、审批事件、Excel 完成事件；同一画布不代表同一次执行，不加入 Wait，不用假连线串接人工等待。

| 入口 | 候选 path | 状态 |
| --- | --- | --- |
| Upload Invoice | ap-unified-intake-a2-v1 | 草稿 |
| Approval Decision Received | ap-unified-review-a2-v1 | 草稿 |
| Excel File Ready | ap-unified-excel-a2-v1 | 草稿 |

所有新 path 与原 01／02 不冲突。来源 namespace、source_id、attachment_id、pairedItem、binary、run_id 与事件 ID 契约保持原样；未按新画布名称更换去重 namespace。

有效节点组：

- Prepare Invoice Files：保留一段附件处理代码的折叠入口。
- Read & Understand Invoice：保存／读文本与 Python Agent 提取。
- Check Saved Decision：重新读取决定与批准／拒绝路由。
- Deliver Excel Download：检查既有文件与发送下载通知。

系统有一条展示建议：`TOP_LEVEL_ITEMS_OVER_CEILING`，折叠后 20 个顶层框，高于建议的 7；不是配置或连接错误，没有被丢弃的组。保留原因逐项如下：

| 未分组节点 | 保留原因 |
| --- | --- |
| Fetch Invoice Emails | 后面的准备节点还接上传入口；合组会形成多个外部入口成员。 |
| Process One Invoice、Email Batch Complete | 循环入口及完成出口；只包完成死端不符合组规则，包整个循环则隐藏审批／审核主线。 |
| Check Invoice & Apply Approval Rules、Route Invoice Result | 确定性审批与结果分支必须可见，不能与 AI 提取折叠为一个不透明动作。 |
| Forward Saved Decision、Request Invoice Review、Read Skipped or Failed Result | 三种不同业务副作用／结果，收拢到一组会失去独立入口结构和结果含义。 |
| Continue Email Batch?、Show Upload Result | 一个出口回循环，另一个终止并响应表单；只分组条件和响应死端不满足组边界。 |
| Send Approval Confirmation、Send Rejection Notice | 两个重要可见业务结局；与上游一起折叠会隐藏批准／拒绝分流。 |

所有触发器按 n8n 规则不得放进节点组。画布位置已分为独立区域并避开说明框；本轮仅核对坐标与保存结果，未做浏览器渲染／缩放可读性验收，留待 A3。

其他配置差异：

- 明确既有默认值：Gmail resource=message、Code mode=runOnceForAllItems、batchSize=1。
- Webhook v2 响应码改为 `responseCode=customCode, customCode=202`，符合当前 schema，仍是 202 接收语义。
- 凭据复用既有 Gmail 与本地 header auth 引用。创建工具的 HTTP 自动分配提示是通用提示；已逐节点读回核实需要认证的 HTTP 和 Webhook 均保留原引用，其余内部 API 沿用原认证方式。没有新建或输出凭据值。
- 统一候选采用 02 的保守执行保存策略：成功／失败 none，manual/progress false；timezone=Europe/Berlin，executionOrder=v1。这降低 n8n 历史明细可用性，但后端按 ID 的持久化轨迹保留。该设置不能替代请求头隐私钩子。
- 未发现当前阶段需要合并的重复后端请求；没有拆改已有审批事务，也没有新加后端服务或子工作流。

## 5. 验证层级与结果

| 验证层级 | 结果 |
| --- | --- |
| 本地 JSON | 可解析；最终文件来源于实例草稿读回 |
| 节点 schema | 27/27 通过 |
| SDK 工作流 | valid=true；参数修正后无 schema 警告 |
| 实例创建与读回 | 成功；27 节点、25 条预期连接、4 个组；保留上述展示建议 |
| 参数／凭据 | 每个节点与候选设计逐项相等；复用引用与原基线相同 |
| 分流／循环／响应 | 静态核对所有预期边、Switch 5 路、循环回边、上传响应 |
| 原 01／02 | 再次读取；版本、启用、draft、activeVersion、参数、连接、设置均未变 |
| 后端与业务数据 | 写日志前 167 个基线工作区文件未变；SQLite schema 及所有业务行相等；原件和导出哈希相等 |
| 发布／真实执行／新入口隐私 | 未进行，不能声称候选端到端已通过 |

未跑全量后端测试：没有修改后端代码，本轮验收边界是 A2 的静态检查与实例草稿读回。Phase02 历史验收范围与 mock 限制继续以 phase02_final_log.md 为准。

## 6. A3 前置事项与下一步

1. **先扩展隐私钩子**：`scripts/n8n_review_header_privacy.cjs` 当前只识别旧路径。为候选两条事件路径增加 production/test 覆盖，并运行既有隐私检查，再按实际挂载方式加载。不要在此前试执行新 Webhook；n8n 即使关闭保存也可能持久化初始请求头。本轮没有修改钩子。
2. 现有 `AP_REVIEW_EVENT_URL`／`AP_BATCH_EVENT_URL` 已是显式单目标切换开关，无需新双投代码。隔离测试／受控启用时按计划切换对应单一目标，保留旧值用于回退；同一事件不能同时向旧、新接收器投递。
3. A3 才进行可视验收、样板执行、实际 202 语义、逐附件关联、重复投递、人工批准／拒绝、文件通知和失败恢复验收。新草稿的手动执行会产生真实后端写入及本地通知，不能视作无副作用的画布预览。
4. A4 验收后再将候选设为展示默认入口。原生 Agent 迁移按 B 阶段另行推进，不替换当前 Python Agent。

## 7. 本轮文件边界

新增：两个 baseline JSON、候选 JSON、SDK 来源文件、A0 快照脚本、本记录、验证 JSON。更新：实施计划的进度、handoff、workflow_map 与架构摘要的当前候选状态。没有修改 AGENTS.md、backend、compose、隐私钩子、旧工作流 JSON 或历史 Phase02 final log，也没有 Git 提交。

