> Current policy update (2026-10-07): the gross EUR automatic-approval ceiling is operator-configurable and deployed at 1,500.00. Amounts at or above the ceiling require human review. See [configuration and verification](AP_configurable_approval_limit.md). Historical 10,000 EUR values below describe the earlier policy.

# Phase02：AP 自动／人工批准与 Excel 导出实施指南

> 2026-10-07 后续重构决策：用户已确认将 01、02 合并到同一业务画布，保留独立事件入口、持久化状态与现有清单／Excel规则；先整理画布，再迁移原生 Agent。后续实施以 [统一画布与原生 Agent 迁移指南](AP_unified_canvas_native_agent_implementation_guide_zh.md) 为准，替代本文“不把 02 嵌入 01 的画布”的旧要求。此重构尚未实施，本文其余内容仍记录 Phase02 已验收基线。

日期：2026-10-07  
状态：当前实施指南；2026-10-07按用户确认改为“批准后自动进入导出清单 → 筛选预览 → 用户下载合并Excel”。此决定替代原第7节“一张批准快照一份文件”和“审批事件自动生成Excel”的主流程。旧单票导出保留兼容。Phase02集中验收已完成，当前结果见phase02_final_log.md与phase02_final_verification.json；此前分步日志保留为历史。推荐入口为APApprovalIntakeV9，独立02为APReviewExportV1；v7及历史入口保留。
基线提交：`e77ddcc` — `Unified Workflow Canvas, added LangChain and Agent`

## 1. 目标与边界

完成真实闭环：提取校验后的发票 → 确定性自动批准规则／人工审核分流 → 自动批准或 Web 修改、重新校验、人工批准／拒绝 → Python 保存决策、不可变快照与待发送事件；批准快照立即进入数据库导出清单 → 用户在Web筛选预览、勾选 → 生成并下载一份合并Excel（.xlsx），持久化本次文件及成员版本。独立n8n `02_AP_Review_Export` 处理审核结果及本地通知，不因审批事件自动生成每票文件，也不阻塞清单可见性。

金额自动批准和人工审核两条分支均为必做、必验收项。实现时可先跑通人工分支，但不能以此结束阶段。批准不等于导出，导出不等于付款。Excel 文件生成、事件传输、状态保存和下载均真实运行；文件标注未提交记账系统。

本轮不实现：DATEV／Lexoffice 或其他外部记账平台集成、实际付款、AP／AR 到期提醒、AR 开票、完整 MCP、多用户权限平台、批准后的撤销／重开；不实现持续更新的latest.xlsx或用户本地Excel路径同步。批准／拒绝保持终态；同一批准版本可由用户明确选入不同汇总批次，历史批次内容不变，这不表示再次批准或再次记账。后续更正需求另定版本和冲销语义。

中文交流与开发日志；代码注释、页面文案、n8n 节点及说明使用英语。遵循根目录 AGENTS.md 与 karpathy-guidelines。

## 2. 开始前必读与当前事实

按顺序阅读：

1. 根目录 `AGENTS.md`。
2. `logs&architechture/workflow_map.md`、`Architechture_rough_summary.txt`。
3. 本指南、`manualReview_workflow.md`、`handoff.md`、`phase01_refactor_log.md`。
4. `phase01_step45_verification.json`、`phase01_agent_verification.json`；需要追踪执行时再读对应 execution 文件。
5. 实际 `backend/`、`compose.yaml`、`n8n_workflows/01_AP_agent_intake_v7.json` 与当前容器状态。

Phase01开始时的历史基线（非当前实现状态）：

- Phase01 默认画布 `APAgentIntakeV7`，14 个执行节点、2 个说明节点，独立上传／只读 Gmail 入口，共用 Python 阶段服务；已导入、发布、绑定凭据并真实运行。
- 本地 Tesseract／Poppler OCR；Python LangChain Agent 使用 Gemini `gemini-3.5-flash-lite`。证据校验、Decimal 金额规则、两层查重、幂等任务和通知均在确定性后端。
- 69 项测试通过。主库验收时有 16 张原件、159 条接收记录、90 次分析 attempt、4 个 pending 任务、5 条通知尝试（4 sent、1 历史 failed）；这些是交接快照，不应硬编码到产品。
- 模型每轮至少间隔 60 秒，最多 3 次请求／6 次只读工具调用，版本化缓存；重启会标记中断轨迹，未知提供商结果不自动重试。限流仍是单进程；重启后新分析需等待配置间隔。
- `review_tasks.status` 当前有 `CHECK(status='pending')`，`get_invoice()` 从最新 processing attempt 获取字段；不能只新增按钮而不改状态及字段读取模型。
- 目前没有审核写入、批准／拒绝、审核完成事件或导出表／接口。
- OCR11 的原始 Agent 草稿包含 Causeway，但完整地址未通过连续文本证据校验，最终地址为 null 并显示异常。不能把无规则异常当作提取完全正确。

入口：

- n8n 编辑器：`http://localhost:5678/workflow/APAgentIntakeV7`
- 上传：`http://127.0.0.1:5678/form/ap-agent-intake-v7`
- 后端：`http://127.0.0.1:8000`
- 本地 Mailpit：`http://127.0.0.1:8025`

历史文档中的“未实现”、旧计数及“No commit made”按日期解读；Phase01 已提交为上述基线。启动新阶段先查看 Git 状态，保留后续用户变更。

## 3. 架构与精简画布

```text
Intake → Deterministic Approval Policy
           ├─ Eligible low-value invoice → Auto Approve
           └─ Otherwise → Pending Review → Web: Edit / Approve / Reject
                                      ↓
Python: decision + immutable snapshot + outbox event (one transaction)
           ├─ Approved → Export register (database-backed)
           │                → Web: Filter / Preview / Select
           │                → Download combined Excel → Saved batch + membership
           └─ Review event → Independent 02 → Load Current State → Notify Outcome
```

批准快照本身构成导出清单，不复制另一份可修改字段；清单可见性不依赖n8n回调。生成Excel由用户选择触发，02不得在审核事件重放时再次生成文件。通知区分“已批准、可在清单导出”和“合并文件已生成”，后者按batch/export_id去重，不把每票审批事件等同于一份Excel。

自动批准判断位于接收校验完成之后、待审核通知之前，由 Python 规则服务执行。符合条件时不发送“请人工审核”邮件，直接保存自动批准决定并发出同类事件；不符合条件才保持 pending 并通知审核人。保留已验证 v7 文件和入口，新分流通过独立的新01版本接入，验收后再切换默认入口。不要在启动时批量自动批准历史 pending 任务；历史记录只有显式重新评估才走新规则。

01、02 是独立入口，不让 01 Wait 等待人工，不把 02 嵌入 01 的画布。采用审核事件恢复机制，不同时加入 Wait 回调机制。

n8n 仅保留明显业务节点。字段版本、审批门禁、事件投递记录、文件落盘、导出幂等和通知状态由 Python 承担；不要为每个数据库检查再建一串 check／record 节点。复用现有通知模式，但使用独立通知类别，不能与 Phase01 的“待审核通知”共用同一个发送去重键。

Agent 不参与批准、金额纠错、最终导出决策。人工修改不自动重新调用模型，不用模型生成或“修复”会计金额。

## 4. 固定基线与数据迁移

先备份当前 SQLite、原件及 v7 文件／哈希，写入忽略目录 `data/baselines/phase02-start-<date>/`；日志只保存清单与摘要，不复制 .env、令牌或邮件正文。SQLite 使用一致性备份，不在写入时直接复制数据库文件。保留 e77ddcc 及所有历史工作流。

为 SQLite 编写可重复执行的迁移与 schema version。现有 pending-only CHECK 需要表迁移，不能靠新增 API 绕过。保留 review_id、invoice_id、created_attempt_id 及 notification_attempts 的外键关系。迁移先对隔离数据库演练，检查外键、行数、唯一约束及重复执行；失败时回滚，禁止删库重建演示数据。

最小逻辑数据模型如下；表名可调整，语义不可缺失：

- **review_tasks**：审核状态 pending／approved／rejected、当前 revision、关联 extraction attempt、决策人和时间、approval_method=automatic/manual、policy_version、规则输入快照和分流理由。
- **review_revisions**：不可变审核版本（自动批准也保存快照）；字段快照、原始提取引用、修改前后差异、重新校验结果、重复候选／处理理由、actor、时间及备注。revision 随保存递增。
- **review_events / outbox**：event_id、invoice_id、review_id、approved/rejected revision、类型、投递状态、尝试次数及错误。决策与事件在同一数据库事务提交。
- **导出清单**：查询已批准的review_tasks＋review_events＋不可变review_revisions；invoice_id＋批准revision唯一，自动／人工批准共用，拒绝／待审核不入列。
- **export_batches / export_batch_items**：批次export_id、选择集合哈希、mapping_version、状态、尝试次数、文件相对路径／哈希、失败原因和时间；成员保存event_id、invoice_id、批准revision和固定行序。每批一份合并.xlsx，不另导出CSV／JSON；保留旧exports表及已生成单票文件。
- **result notification ledger**：schema 5新增outcome_notifications与outcome_notification_attempts，分别唯一关联review_events.event_id或export_batches.export_id，记录类别、SMTP状态、Message-ID、投递状态与尝试记录。保留旧result_notifications与单票exports外键。已实现批准、拒绝及合并批次完成通知。

分别保存 processing、review、export、notification 状态。不要把 approved 写成 processing 状态，也不要用 n8n execution success 代替导出成功。

## 5. Web 审核与批准规则

保留原件分页图片、字段、异常、重复候选和 Agent 轨迹；增加英语操作：`Save changes`、`Approve`、`Reject`，以及清晰的保存／冲突／失败提示。

### 5.1 修改与版本

- 原始 processing_result.raw_extraction 与机器证据不可覆盖。
- 单独保存人工修订；页面展示机器原稿、当前人工值及修改来源，不把人工填写值伪装成模型提取。
- 每次保存传 expected_revision 与所依据的 processing_attempt_id；后台在事务内检查，过期页面返回 409，提示刷新比较，不覆盖另一人的修改。
- 修改关键字段后重新执行确定性标准化、金额校验和查重。审批时再次检查，不能复用早期页面上的绿灯。
- 人工核对原件可以纠正 OCR 未识别的地址；保存页码和说明，不要求新值必须出现在错误 OCR 文本中。机器原始证据问题仍保留历史，人工处理结果另存，不能删除原始异常。
- Phase01 的重新分析／任务重放不得清空人工修订或把终态任务重置为 pending。终态发票本阶段禁止重新分析；pending 下出现新 attempt 时必须显式标记版本冲突，不能默默换掉待批准字段。

### 5.2 金额自动批准：必做分支

用户提供的官网截图表达的是：金额 < €10,000 自动批准，金额 > €10,000 发给 CFO 人工批准。也就是符合低金额分支的发票不必等待人工点击批准；它仍须经过提取、校验、查重和可追踪的批准记录。截图未规定等于阈值、税前／含税或其他币种，以下为本项目的实施默认值，不冒称官网原文：

- 比较明确识别的 EUR 发票含税总额 total_amount，以 Decimal 比较；阈值为 EUR 10,000.00，配置及 policy_version 一起持久化。
- 仅 `0 < total_amount < 10000.00` 且所有自动批准门禁通过时自动批准。
- `total_amount >= 10000.00`（包含恰好 €10,000）转人工；非 EUR、零／负金额、金额不明确也转人工，不做汇率换算。
- 自动批准须满足必填字段完整、金额等式成立、无未解决校验／证据／OCR质量／提取不确定异常、重复检查可执行且无候选、没有人工修订或已有决策。任何一项不满足即 pending，不因金额低而忽略异常。
- 人工修改后继续由人工批准，不因改低金额自动转换为自动批准。自动与人工决策并发时使用同一事务／版本检查，最多一个终态和一个决定事件。
- 自动 actor 明确为 system，保存规则版本、金额／币种、检查结果和理由。Agent 不决定是否批准；规则无异常仍不是绝对提取正确性的证明，自动批准是本 Demo 的明确业务策略。
- 两条批准分支共用批准快照、事件、导出清单和合并Excel服务，不复制两套导出代码。高金额审批通知本阶段仍发本地 Mailpit 的演示审核人，不真实发送给 CFO。

### 5.3 共用审批门禁与人工处理

自动规则与人工决定都只作用于已完成处理、尚未决定的任务。审批使用最新、已保存的审核版本；提交未保存修改时应明确拒绝并提示先保存。

- 现有必填字段、明确币种、合法日期、可解析金额、金额矛盾等必须有确定性检查；不因“人工点了批准”跳过。
- 本阶段先使用供应商、发票号、开票日、到期日、币种和总额均完整，净额＋税额校验成立的普通发票作为 happy path。沿用当前 MISSING_FIELD 的要求；不擅自推断到期日、税额或币种。
- 金额不匹配、未解析币种／金额、未支持负数单据、未处理的关键缺失项阻止批准。
- 复杂折扣／运费／税式和 TOTAL_CHECK_INCOMPLETE／TOTAL_EQUATION_REVIEW 不靠通用勾选绕过。若本阶段尚未实现有证据的确定性公式，则保持 pending 或拒绝，并明确原因。
- OCR／提取不确定项可由人工逐项核对并记录处理理由；这不修改机器原稿。重复候选必须显式说明“确属重复并拒绝”或“不是重复／有理由继续”，记录候选 ID 和理由，不自动批准疑似重复。
- 保存验证结果和允许／禁止批准的解释；异常分类应由明确映射决定，不能依据 message 文本模糊匹配。
- Reject 必填理由；已拒绝不导出。默认 approved／rejected 是终态；相同决策请求重放返回原结果，相反决策返回冲突。

本地单人 Demo 可以记录明确的 demo reviewer 身份，但必须标为演示身份，不能宣称已实现可信多用户认证。写接口只绑定本地，采用合适的 CSRF／Origin 防护；不得用 GET 链接执行批准。

## 6. 审核事件与失败恢复

批准事务必须一起保存终态、不可变批准快照、审计记录与 outbox 事件。事务提交后再进行网络投递；n8n 不可用时审核结果仍然存在，事件保留待重试状态，页面显示“Approved; in export register”，并独立显示事件投递状态。

事件只传标识与版本，例如 event_id、invoice_id、review_id、review_revision、event_type。不要把事件携带的金额或 approved 字符串当作导出授权。02 必须从后端读取该事件及当前状态；Python 的导出接口也必须再次核验状态和批准快照，不能信任仅由 n8n 做门禁。

第一版采用持久化 outbox＋显式本地重试入口／命令，不必先上消息队列。重试使用同一 event_id、有限次数和可见错误，禁止无节制循环。演示至少要能在 n8n 停止／恢复后重新投递待发事件。

区分“HTTP 已接收”与“业务已处理”：Webhook 返回 2xx 不能直接代表导出完成。若 n8n 接收后执行失败，事件仍须可以重新驱动；保留 accepted/delivered 与 processed 的区别，或等业务确认再置完成。清单和用户下载不依赖事件消费；processed只说明对应审核结果处理完成，不能代表用户已生成或下载Excel。

本地 Webhook 使用最小凭据校验，凭据在 .env／n8n credential 中保存，不进 JSON／日志。绑定方式以实际实例能力核实；新凭据或真实账户确实需要用户操作时再请求。

## 7. 导出清单、合并Excel契约与幂等

采用数据库作为真实数据源，Excel作为用户下载的快照文件。不逐条append修改物理.xlsx，不要求用户配置本地路径，不提供latest.xlsx同步。标准.xlsx标注 `Invoice export — not submitted to an accounting system`；不接入外部记账平台。

### 7.1 清单与选择

- 自动或人工批准后立即进入清单；审批事务保存的不可变快照是唯一字段来源。无需额外模型调用、n8n在线或定时刷新文件，重复批准不重复入列。
- Web `/exports` 显示发票号、供应商、发票日期、币种、含税总额、批准方式、批准revision及导出状态，可返回审核页查看原件。
- 支持发票日期起止（含边界）、供应商名称包含匹配、币种，以及“尚未导出／全部已批准”筛选。展示条数与按币种分别汇总的Decimal金额，不跨币种加总。
- 用户勾选当前预览记录后点击Download Excel；一次最多500条，超过则要求缩小选择，不静默截断。修改筛选后先重新应用，避免旧选择与新条件混淆。
- 请求传确切event_id集合，服务端重新核验当前批准状态和版本；预览之后新增的批准记录不自动塞进本次文件，下次刷新可见。
- “已导出”表示已成功生成单票或合并文件，不代表用户已下载、已记账或已付款。failed不标为已导出；completed但文件损坏／丢失时从历史按原编号恢复，不退回新业务导出。
- “尚未导出”在创建事务内检查；预览后其他批次已导出或占用所选记录则返回409，要求刷新／恢复历史。全部已批准模式允许用户明确将同一批准快照纳入不同集合的汇总文件。

### 7.2 文件和持久化

- 每个合并批次保存不可变成员集合与顺序：event_id、invoice_id、批准revision。文件仅读取这些快照，不能读取“最新提取字段”替换批准内容。
- 最小字段：invoice_id、review_revision、supplier_name/address/tax_id、invoice_number、invoice_date、due_date、currency、net/tax/total、discount/shipping（存在时）、approved_at、export_id、mapping_version、approval_method、policy_version。合并文件每行export_id为同一批次ID。
- 金额由Decimal计算，写数值单元格并保留币种精度；日期统一格式，缺失值空白不改0。生成后逐行读取复核与批准快照一致，超出Excel可靠数值精度时报错，不静默舍入。
- 文本强制字符串，防止=、+、-、@开头内容变公式；发票号、税号保留前导零。不含宏、外部链接或自动执行内容。英语表头、冻结首行、筛选和合理列宽。
- 将排序去重后的event_id集合计算selection_hash并施加数据库唯一约束；相同集合（无论请求顺序、模式或新mapping版本）返回原export_id和文件。不同集合为新的汇总批次；不再使用“一张发票只允许一份文件”的旧主流程约束。
- 下载GET仅读取、核验已有文件，不生成；显式POST生成／重试。有并发写入时返回409，60秒租期后可恢复，最多5次尝试。
- 文件写入受控exports/batches目录，临时文件fsync后原子替换，保存哈希；用户文件名或路径不能控制位置。
- 文件落盘和数据库提交非同一事务：写完文件但未提交时校验并复用孤立文件；已提交但文件缺失／损坏时使用原成员、原ID恢复且核对哈希；进程中断保留writing状态和租期。不能用新批次掩盖失败。
- 失败不撤销批准，历史显示错误与尝试次数并提供显式重试。后续通知失败只重试通知，不重建Excel；unknown先核对Mailpit，不盲目重发。
- 保留已有单票exports、文件和兼容接口。审核页改以Open export register为主入口，并保留历史单票下载链接。旧记录无需重导出即可计入已导出筛选。

按2026-10-07用户确认，此流程替代原第7节的逐票文件主流程；外部记账平台集成仍不在计划内。

## 8. 接口契约（实现状态以OpenAPI与交接日志为准）

| 操作 | 建议接口与关键语义 |
| --- | --- |
| 审核读取 | GET /api/ap/invoices/{invoice_id}/review：机器稿、人工版本、校验、状态及 revision |
| 保存修改 | PATCH /api/ap/invoices/{invoice_id}/review：expected_revision、processing_attempt_id、changes、理由 |
| 审核决定 | POST /api/ap/invoices/{invoice_id}/review/decision：approve/reject、expected_revision、request_id、理由 |
| 事件读取 | GET /api/ap/review-events/{event_id}：当前任务状态、批准快照引用、是否可导出 |
| 事件投递 | 后端服务＋显式重试入口或命令；不向浏览器暴露凭据 |
| 清单预览 | GET /api/ap/export-register：date_from/date_to/supplier/currency/only_unexported |
| 合并导出 | POST /api/ap/export-batches：event_ids、only_unexported；核验并冻结成员，返回原有或新export_id |
| 导出历史／查询 | GET /api/ap/export-batches；GET /api/ap/export-batches/{export_id} |
| 显式恢复 | POST /api/ap/export-batches/{export_id}/retry；保持原成员与编号 |
| 文件下载 | GET /api/ap/export-batches/{export_id}/files/xlsx；只读校验 |
| 历史单票兼容 | POST /api/ap/exports；GET /api/ap/exports/{export_id}及/files/xlsx；不再是页面主入口 |
| 完成通知 | GET /api/ap/outcomes/{review或batch}/{id}与POST其/notify供02认证调用；本地GET /api/ap/result-notifications/{kind}/{id}，POST其/retry或/check独立恢复 |

接口数量以实际复用为准，不为了这张表增加无用端点。审核接口使用乐观并发；request_id 重用但请求内容不同返回冲突。404／409／422／服务失败语义明确。审批重放返回原决策，即使新 request_id 也不能再造事件。

## 9. 实施顺序与每步验收

1. **固定基线与迁移。** 保存备份和哈希，设计并记录审核状态、revision、自动批准阈值与门禁及导出幂等键。隔离旧库迁移通过；Phase01 任务／通知外键与原件不丢失。
2. **审核后端和 Web。** 实现保存、重新校验、版本冲突、批准／拒绝；保留原件和提取初稿。先跑通修改错误字段后批准、拒绝和非法批准阻断。审核过程不新增模型调用。
3. **自动批准与事件可靠交接。** 实现第5.2节的确定性分流及新01版本：低金额且无异常自动批准，其余转人工；两条分支共用决定事务。 决策和 outbox 同事务，真实向本地 Webhook 投递；模拟 n8n 不可用、响应丢失和接受后失败，显式重试不产生重复决策。
4. **确定性 Excel 导出服务。** 实现数据库清单、筛选、按币种汇总、明确选择的合并.xlsx和历史下载；验证集合幂等、增量可见性、并发、写文件／落库中断、失败恢复与批准版本一致性。
5. **精简独立画布。** 新文件建议 `n8n_workflows/02_AP_review_export_v1.json`，实例 ID 建议 `APReviewExportV1`。保留01/v7入口，节点英语。导入、发布、凭据绑定和真实执行分别核验；不能以JSON存在宣称闭环完成。
6. **通知与集中验收。** 本地Mailpit收到对应审核结果／批次文件完成通知，链接正确；批次通知已通过schema 5独立账本关联，核对审核事件、批次、成员、文件和通知数量。新样本只需少量，优先使用已有提取缓存和明确标注的模拟输入。
7. **收尾。** 保存日志、验证结果、字段映射、导入／运行步骤及交接。默认入口是否切换仅在验收通过后决定；未经用户要求不自动 Git commit／push。

## 10. 必测场景与验收证据

- 已有待审核记录经迁移仍能打开；旧01任务重放不会重置终态或人工字段。
- EUR 9,999.99、10,000.00、10,000.01边界：前者在其余条件全部通过时自动批准，后两者必须人工；保存自动／人工决策来源。
- 低金额但有缺失、金额矛盾、OCR／证据异常、重复候选、无法查重或人工修订的发票均转人工；非EUR不自动换算或批准。
- 自动批准不产生待人工审核通知；自动与人工分支均进入清单，可选择两者生成同一份可下载.xlsx；相同集合重放返回原批次。
- 用全新、无重复的合成样本验证自动分支；现有低金额重复样本应转人工，不能为了演示删除查重记录。
- 自动决策与人工决策并发仅产生一个终态／事件；重启不自动批准历史pending记录。
- 日期边界、供应商与币种筛选、全部／尚未导出模式、混合币种分别汇总；预览后新批准不进入旧选择，下次可见。旧单票记录和文件不变并计入已导出。
- 修改错误字段、重新校验、批准，Excel内容等于批准快照，原稿不变；核对日期、金额类型、前导零、空值和公式注入样本。
- OCR11人工核对并修正地址，来源为manual；不能伪造原始OCR证据。若其他金额公式仍未支持，批准仍须阻止。
- 缺失必填项、错误日期／金额、未处理重复候选阻止批准；带理由拒绝后无导出。
- pending／rejected／旧版本／伪造事件，即使直接调用导出API也不导出。
- 两个过期页面或并发批准仅一份终态／事件；重复批准和事件重放不重复入列；同一选择集合的并发下载生成仅一个批次。
- 审核完成后改变提取结果／来源重放不会更改已批准快照或文件。
- n8n停止再恢复、事件接收后执行失败、返回响应丢失均可通过原event_id恢复。
- 导出目录不可写／文件中断／文件丢失可诊断并恢复，同一export_id不产生重复业务记录。
- 通知失败不重导出；通知不确定时保留需核对状态。
- 重建后端／n8n后审核、事件、文件和通知仍存在，下载哈希一致。
- Phase01既有69项回归作为基线：状态扩展需要更新旧测试期望时记录理由，不能删除有价值的幂等／限流测试来通过。

每批记录预期与实得：输入发票数、审核决定数、待投递／已处理事件数、成功／失败／跳过数、唯一批次export_id数、成员数、文件数和通知数。分别统计自动批准／人工批准／转人工原因；一个逻辑导出对应一份.xlsx，不混淆邮件吞吐和模型吞吐。

交付日志必须分别列出：JSON解析、节点连线、实例导入、发布、凭据绑定、真实执行、Mock部分及未验证部分。单元测试故障注入不冒称实际服务故障；真实Excel导出不冒称第三方记账成功。

## 11. 停止条件与交接

低金额无异常自动批准→导出清单，以及高金额／异常转人工→修改／批准→导出清单，两条分支都必须真实成功，并通过筛选、选择与合并Excel下载闭环；独立02完成对应审核结果通知，不要求审批事件自动生成单票文件；拒绝／pending不导出、幂等、故障恢复和重启持久化通过，即可结束Phase02。金额自动批准不得留作可选或以后实现；复杂税务／调整公式保持转人工，外部记账平台不在计划内。

本指南保存到 `logs&architechture/`；后续开发日志／验证／交接同目录，全部n8n JSON保存在 `n8n_workflows/`。更新 `handoff.md` 指向最新验收。若实际接口／默认审批策略变化，记录新决策与理由，不把建议接口当作既成实现。
