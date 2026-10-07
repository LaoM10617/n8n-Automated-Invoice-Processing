# A3–A4 统一画布验收与展示入口切换

日期：2026-10-07。状态：**A3、A4 完成；统一画布已发布并成为推荐演示入口。**
本轮沿用 Python LangChain Agent，没有实施原生 Agent 迁移或 Phase03。A0–A2 历史记录保留，当前运行状态以本记录为准。

## 1. 入口与版本

- [统一画布](http://127.0.0.1:5678/workflow/7xXB2pjXOE1EQ2bY)：`Process AP Invoices — Review & Excel Export`。
- [上传表单](http://127.0.0.1:5678/form/ap-unified-intake-a2-v1)。路径中的 a2 是既有唯一标识，不表示仍处于草稿阶段。
- [导出清单](http://127.0.0.1:8000/exports)；[本地 Mailpit](http://127.0.0.1:8025)。审核链接在具体发票通知中。
- 实例 ID：`7xXB2pjXOE1EQ2bY`；最终 draft 和 activeVersion 均为 `fe01bad5-6a5d-46c6-8013-ccf3f846b565`，active=true，Personal project 根目录。
- 最终导入文件：`n8n_workflows/AP_unified_canvas_python_agent_v1_A4.json`。A2 JSON 与 SDK 来源文件原样保留，不将其误当作最新发布版本。
- 23 个执行节点、4 个说明节点、25 条连接、4 个节点组。所有执行节点的参数、凭据引用与 A2 已验证候选逐项相同；更新了展示说明与状态。

## 2. A3 保护与受控切换

新增起点备份 `data/baselines/unified-canvas-a3-start-20261007/`：SQLite online backup、170 个工作区文件摘要及副本、21 原件和 5 既有导出文件。integrity 与外键检查通过，目录被 Git 忽略。此前未提交修改作为基线保留。

`scripts/n8n_review_header_privacy.cjs` 增加新 review/excel 的 production 和 test 路径，保留认证访问但阻止令牌序列化。扩展已有测试并通过；重启 n8n 加载。`check_review_event_privacy.py` 的只读扫描加入统一工作流 ID。最终扫描 32 条相关 payload，credential_found=false；没有运行清理旧数据选项。

模拟路由测试通过后，为真实本地验收发布候选；A3 受控测试期间将 compose 的两个单一事件目标切到候选，未向旧、新双投。A3 通过后 A4 保留该配置并更新推荐入口：

| 配置 | 当前值 |
| --- | --- |
| AP_REVIEW_EVENT_URL | http://n8n:5678/webhook/ap-unified-review-a2-v1 |
| AP_BATCH_EVENT_URL | http://n8n:5678/webhook/ap-unified-excel-a2-v1 |
| AP_OUTCOME_AUTODISPATCH | 1 |

只重建运行容器以加载环境配置，未修改后端业务代码或 schema。Gmail 和 Header Auth 复用已有引用；认证的真实成功由审批／批次通知及 202/403 探测证明。没有再次读取外部 Gmail 或调用模型。

## 3. 分层验证与证据范围

| 层级 | 本轮完成的验证 | 结果与限制 |
| --- | --- | --- |
| 静态 | 参数 schema、25 条连接、凭据、循环、上传响应、独立事件入口 | 27 节点通过；最终执行参数与 A2 相同 |
| 编辑器 | 真实 n8n 编辑器打开、分组、五路结果标签、三个业务区域、发布状态 | 无遮挡关键节点；缩小适合全局介绍，讲解节点时需放大 |
| 模拟路由 | 自动批准、已有人工决定、待审核、跳过、失败五例 | test_workflow 均 success，执行 ID 449–453；Gmail 和全部 HTTP 输出固定，不是后端运行证据 |
| 模拟多附件 | 一封三附件邮件加一封无附件邮件 | 执行 461 success；Code／循环真实执行，触发器、Gmail、HTTP 为固定输出，不能据此宣称真实 Gmail 多附件端到端验收 |
| 真实上传 | 三个标注合成提取缓存的 PDF 经候选生产表单提交 | 自动批准、待人工修订、待拒绝三路正确；实际运行缓存读取、确定性校验、持久化和通知 |
| 人工审核 | 在真实审核网页对照原件修正地址、保存、批准 | revision 2，人工结果与机器初稿并存；网页显示 processed 与通知 sent |
| 拒绝及故障恢复 | 保存审核后拒绝；受控停止 Mailpit 制造失败，恢复后仅重试通知 | SMTP_CONNECTION_FAILED → sent，attempts=2；拒绝不进入 Excel |
| 多附件隔离 | 同一合成邮件的正常 PDF、损坏 PDF、txt、错误后的正常 PDF 调用真实后端阶段接口 | source/attachment 关联保留；decision_ready、failed、skipped、decision_ready；另外损坏／不支持文件经过真实 n8n 表单，明确返回 failed/skipped |
| Excel | 两个批准事件合并为一批；API 下载及浏览器下载 | 2 成员，attempts=1，下载哈希一致；文件通知 sent |
| 幂等 | 三份原件重复上传，三个决定事件和一个批次事件直接重放，重复选择同一导出集合 | 没有增加决定、Excel 批次／文件或结果通知；允许生成新的 intake run 审计记录 |
| 重启 | Python、n8n、Mailpit 重启后重放并比较快照 | 决定、事件、通知、成员、批次 ID、文件哈希及计数完全一致 |
| 授权与隐私 | 两种事件入口无凭据／有凭据，扫描落盘数据 | 403／202；未发现令牌；202 仅表示接受 |
| 专项回归 | 复用 test_intake_stages、test_outcomes、test_review_decisions | 44 passed；多附件隔离、并发决定、幂等、通知失败／unknown／中断恢复等 |

本轮不是新增 OCR／模型质量验收：三个缓存均明确 `synthetic_saved_analysis_no_model`，analysis_cached=true。processing_attempts 从 95 增至 98，仅新增三条显式合成缓存，真实路径没有额外分析尝试。原 Phase01 的真实 Gmail、OCR 和 Agent 验收仍是历史依据。

n8n 不保存手动／成功／失败执行明细，五例模拟测试返回成功后不能通过 get_workflow_execution 读回；没有将它们描述为已检查逐节点输出。尝试临时启用手动执行保存被自动审批审查拒绝，原因是可能持续留存后续敏感发票数据。该设置未改变；改用后端持久化结果、真实表单响应、独立 HTTP 探测、工具返回状态和既有专项回归形成证据，没有绕过限制。

环境性问题：首次 pytest 临时目录父目录不存在，之后受限环境出现 Windows ACL 错误；换用项目内新隔离目录并经工具权限审查运行，44 项全部通过。首次重启后的请求早于 n8n 就绪而断开，服务就绪后重放通过。它们没有导致业务代码修改。

编辑器保存说明时会省略节点默认参数。最终已重新明确 Gmail resource、Code mode、batchSize、Switch mode、GET 方法与 onReceived，并与 A2 参数逐项比对；UI 添加的 binaryMode=separate 保留。执行保存策略仍是 success/error none、manual/progress false。

## 4. 合成样本与持久化结果

| 样本 | invoice_id | 结果 |
| --- | --- | --- |
| 自动批准 | 81a9bcfc-ff58-43fe-90ef-8ec128962694 | EUR 9,999.99，automatic，1 个最终决定 |
| 人工修订 | 6870f4df-b874-4786-af20-82590ca9e409 | EUR 10,000.00，地址从未提取修正为 Example Street 1，manual，1 个最终决定 |
| 拒绝 | 0d06e690-7cfd-4741-917e-33ecee70bcdc | 金额不匹配，rejected，不导出 |

批次：`66dc78c7-dd03-4e2f-a211-a38c8f210426`；两个批准成员；SHA-256：
`6bdb2616ca49dec757a7a632805d3f7a43974731b8ee5c491c7e640a352be42d`。

浏览器实际下载 `C:/Users/13020/Downloads/invoices-66dc78c7-dd03-4e2f-a211-a38c8f210426.xlsx` 与服务器哈希一致。三个审批结果通知和一个批次通知逐一按 Message-ID 检查，Mailpit 中各恰好一封。SMTP 失败属于独立通知尝试，没有重做拒绝或生成文件。

全部 A3 前业务行逐行相等；全部既有原件、Excel、历史工作流 JSON 的 SHA-256 保持不变。后端业务代码未改。新增记录仅来自标注的合成样本与验证；没有为通过计数检查删除业务数据。

自调用没有递归：接收审批事件后只读取决定与调用通知；接收批次事件后只读取文件与通知。这两条链均不连接 handoff、不写批准、不调用文件生成。直接重放后的完整业务快照相等，既有事件／文件不重复创建。

## 5. A4 启用、保留与回退

| 工作流／入口 | 当前状态 | 使用方式 |
| --- | --- | --- |
| 统一工作流 7xXB2pjXOE1EQ2bY | 已发布、推荐 | 上传表单；手动 Gmail 演示批次；两个独立事件入口 |
| APApprovalIntakeV9 | 仍已发布，原版本未变 | 保留回退；不再推荐，不与统一工作流同时手动读取同一邮件批次 |
| APReviewExportV1 | 仍已发布，原版本未变 | 保留回退；后端单目标配置已不指向它 |
| 历史 v1–v8、旧 receiver 等 | 启用状态均未批量修改 | 仅历史／回退用途，不能当作当前入口 |
| APGmailIntakeV1 与模板 | 原本未启用，保持不变 | 不启用额外轮询／模板 |

没有停用任何原工作流，也没有新增 Gmail 定时轮询。本轮没有运行旧 01 或新流程的真实 Gmail 手动入口，避免同批次双消费。演示时只使用统一工作流的 **Run Demo Email Batch**；其原有限定查询保持不变，不能以普通新邮件已自动接入来讲解。

回退操作（仅文档，未执行）：

1. 停止发起新的演示上传／手动邮件批次，等待当前执行结束。
2. 将 compose 中 review/batch 目标分别恢复为 `http://n8n:5678/webhook/ap-review-export-v1` 与 `http://n8n:5678/webhook/ap-batch-export-v1`，运行 `docker compose up -d python-api` 并读取容器实际值确认。
3. 将推荐上传切回 `/form/ap-approval-intake-v9`；旧 01、02 本轮没有更改，仍可用。不同时使用两个版本跑邮件。
4. 保留数据库、审批和现有 Excel；UI 回退不需要回滚数据库，否则会丢失本轮合法演示记录。仅在明确数据恢复场景才使用一致性备份，并先停止写入。
5. 新路径隐私保护可以保留；不要通过删除保护来回退。需要停止统一入口时可取消发布该单一工作流，不批量停用历史版本。

## 6. English demo walkthrough

1. Open the unified canvas. Explain **Receive & Check Invoices**, **Review & Approval Results**, and **Excel Export & Delivery** as separate event paths on one canvas.
2. Open **Upload Invoice**. Upload one invoice and use a unique Upload ID; reuse the same ID only when retrying the same file. The manual email entry reads the configured demo batch only.
3. Show the deterministic approval rules. For exceptions, open the invoice link in Mailpit, compare the original, save corrections, and approve or reject. The AI extracts information; it does not approve invoices.
4. Open the export portal, select approved records, and download combined Excel. A review notification confirms a decision; the Excel notification confirms an existing downloadable file.
5. If a notification fails, use its recovery controls. Do not approve again or regenerate Excel to retry an email. Approval and export do not mean payment or accounting submission.
6. Expand **Read & Understand Invoice** when explaining the Python Agent. Native n8n Agent migration is a later phase.

## 7. 文件与证据

- 最终实例校验：`AP_unified_canvas_A4_instance_verification.json`。
- 业务、重放、重启、通知、文件摘要：`AP_unified_canvas_A3_A4_verification.json`。
- 专项测试：`AP_unified_canvas_A3_tests.xml`。
- 截图：`AP_unified_canvas_A4_canvas.jpg`、`AP_unified_canvas_A3_review.jpg`、`AP_unified_canvas_A3_export.jpg`。
- 可重用验收辅助：`scripts/unified_canvas_a3_probe.py`、`scripts/unified_canvas_a3_checks.py`。upload/decide/batch/mixed/replay 有本地副作用，不是只读检查；snapshot/verify/preserve 用于当前固定验收基准，新增业务数据后应另建基准。
- 修改范围：compose 两个目标、隐私钩子与其测试／扫描范围、候选展示说明、日志与入口说明；新增 A4 导出和验收辅助。没有修改审批／导出服务、AGENTS.md、旧工作流或历史 Phase02 final log，没有 Git commit/push。

后续从 B0 原生 Agent 可行性核对继续；当前阶段 A 已可独立演示。
