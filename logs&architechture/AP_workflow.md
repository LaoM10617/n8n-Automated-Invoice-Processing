## Phase02 final integration — 2026-10-07 (current)

The recommended intake is `APApprovalIntakeV9` (`/form/ap-approval-intake-v9`), followed by independent `APReviewExportV1`. Both are imported and published in the local instance; existing v7/v8 and historical workflows remain intact. Approval snapshots enter `/exports` immediately. The user selects a combined Excel download; 02 sends local Mailpit approval/rejection and completed-batch notifications without generating a workbook on every approval.

Schema 5 adds a separate outcome notification ledger. Final acceptance, recovery instructions, evidence and precise mock limitations are in `phase02_final_log.md` and `phase02_final_verification.json`. Earlier sections below are historical snapshots where they conflict with this update.

Current update (2026-10-06): Phase01 analysis now uses a real Python LangChain Agent through APAgentIntakeV7. OCR, evidence grounding, amount rules and state changes stay deterministic. v5/v6 files are historical; see phase01_refactor_log.md and phase01_agent_verification.json for runtime evidence and quality limits.

Current implementation update (2026-10-06): Phase 01 steps 6–8 are verified. Upload v4 and manual readonly Gmail intake share the backend, attachment child and persistent Mailpit notification status. Five real external test emails, local representative/100-message cached batches, replay and container persistence passed. Review remains pending/read-only. See log_2026-10-06_step06_08_acceptance.md; older unimplemented statements below are historical.

> 最新进度（2026-10-06）：**第五步／第8节已完成**。真实待审核任务、只读原件/字段/异常/重复候选页面、n8n v3及重启持久化已验证。49项测试通过，本轮模型调用0。当前停在pending；下一步为**第六步／第9节：Mailpit审核通知与单张happy path**。详见 `log_2026-10-06_step05_review.md`。下文较早状态为历史记录。

> 2026-10-06 第四步最新状态：真实本地 OCR、OpenAI 结构化提取、确定性校验和业务重复候选已接入；n8n v2 已导入发布并实际执行。详情与限制见 `decision_2026-10-06_step04_processing.md`，字段评估见 `step_04_field_evaluation.json`。下文旧的未实现/501 说明为历史状态；审核任务和通知仍待第五、六步。

> 2026-10-06 当前补充：接收支持 PDF/JPEG/PNG；第一轮含文本 PDF 和无文本层图像 PDF，真实 OCR 为第一阶段验收必需。Python 接收登记接口已开始实现，OCR、结构化提取及审核仍待接入。具体来源幂等字段、状态和 501 占位接口见 `decision_2026-10-06_intake_ocr.md`，实际验证见 `handoff.md`。以下保留原始骨架讨论，冲突处以最新决策为准。

你的摘要把职责划分得很清楚。**建议先画出三条业务工作流：AP 接收处理、审核后导出、AP／AR 到期检查，再留一个共用错误处理入口。** 先把节点之间的数据和分支接通，具体实现可以逐段替换成模板或 Python 服务。

以下是供讨论和搭建的初版骨架，尚未生成 workflow 文件。

**一、AP 接收与处理：主工作流**

```text
邮件触发／模拟上传
  → 获取并拆分附件
  → 统一输入字段，标记 direction=AP
  → 保存原件、登记接收记录
  → 是否重复？
      ├─ 是：关联已有记录，结束本次处理
      └─ 否：调用提取与校验
               → 按结果分流
                   ├─ 需要人工检查：创建审核任务 → 发送审核链接
                   ├─ 满足自动批准条件：保存批准结果 → 进入导出
                   └─ 处理失败：记录原因 → 通知处理人员
```

对应到 n8n，先考虑这些节点：

- **邮件入口**：Gmail／Outlook／IMAP 中选实际使用的一种；开发初期用 Form Trigger 上传样板文件替代。
- **附件处理**：将一封邮件的多个附件拆成独立处理项，同时保留邮件与附件的关联。不要把拆附件和拆多页 PDF 混为一件事。
- **Edit Fields／短 Code 节点**：统一来源、文件名、业务方向、关联 ID。
- **HTTP Request**：调用 Python 的登记、提取、校验接口。
- **IF／Switch**：根据后端返回的重复标记和处理结果分流。
- **通知节点**：发送审核链接或错误通知。

这里有两个值得提前约定的细节：

**重复检查分两层。** 接收时识别同一邮件附件的重复投递；提取后再识别“同一供应商、同一发票编号”的业务重复。两种结果都不应简单删除原始接收记录。

**第一轮 happy path 可以全部走人工批准。** 自动批准先留分支，默认关闭，等字段校验和演示规则确定后再开启。这样主线可以更快跑通。

**二、人工审核结果与导出：独立工作流**

```text
审核人员打开 Web 页面
  → 修改字段／批准／拒绝
  → Python 重新校验并保存结果
  → 向 n8n 发出审核事件

n8n Webhook 接收事件
  → 从 Python 重新读取当前发票状态
  → 按审核结果分流
      ├─ 已批准：请求导出 → 保存导出结果 → 完成通知
      ├─ 已拒绝：记录处理结果 → 结束
      └─ 仍待审核：不导出
```

节点骨架是：

**Webhook → HTTP Request → Switch → HTTP Request（导出）→ 通知。**

我倾向于这种“审核后重新触发”的方式：原始收票执行不需要一直等着人，审核页面也有独立入口。Webhook 是事件通知，**最终是否允许导出，以数据库当前状态为准**；重复收到批准事件时，也不能重复导出。

社区模板里经常会用 **Wait + 审批回调**，这种方式也可以。如果找到简洁、可用的模板，可以采用；第一版只选一种审核恢复机制。

AP 的自动批准分支和人工批准分支，最终应进入**同一段导出逻辑**。这部分适合后续抽成子工作流；n8n 支持通过 Execute Sub-workflow 调用并传递输入。[官方说明](https://github.com/n8n-io/n8n-docs/blob/main/docs/integrations/builtin/core-nodes/n8n-nodes-base.executeworkflow.md)

**三、AP／AR 到期检查：薄共享流程**

```text
Schedule Trigger／Manual Trigger
  → 设置检查日期
  → 查询未结清且符合提醒条件的记录
  → Switch：AP 或 AR
      ├─ AP：生成内部付款提醒
      └─ AR：生成客户催款草稿
  → 保存提醒／草稿记录
  → 通知内部人员
```

这里先留两个明确接口：

- **查询接口**：返回发票 ID、方向、币种、到期日、未结清金额、往来单位等。
- **提醒登记接口**：记录本次提醒对象和类型，避免每次定时执行都生成相同提醒。

AR 预制发票直接进入业务数据库，**不经过 AP 的 OCR 流程**。可以另留一段标注清楚的初始化示例：

**Manual Trigger → 加载 AR 样板记录 → 调用预制数据导入接口。**

它属于演示数据初始化，不接在日常定时任务上。

**四、共用错误处理：先留简单入口**

**Error Trigger → 整理工作流／执行信息 → 记录技术故障 → 内部通知。**

注意区分：

- 缺少发票编号、金额不一致、供应商未知：属于业务异常，进入审核分支。
- OCR 服务不可用、请求超时、数据库连接失败：属于技术故障。

被节点捕获并转为普通输出的错误，需要显式接到错误分支，不能假设 Error Trigger 会兜住所有情况。重试次数、补偿和故障恢复细节留到主线跑通后集中处理。

**五、LangChain 和 MCP 在骨架中的位置**

**LangChain 暂时包含在“调用提取与校验”的 Python 服务里。** n8n 画布可以把这个节点命名为“提取发票字段”，说明中注明实现包含 OCR／LangChain，避免画布充满底层模型步骤。

**MCP 保持独立的只读查询入口，共用业务数据库。** 它不需要成为每张发票必经的节点。演示时可以在 AP 处理完成后，查询该发票的异常、审批记录，或者汇总 AP／AR 的未结清金额。

这样工作流运行和对话查询各有用途，也与我们已经确定的架构一致。

**六、按模块找模板，比搜索“完整财务系统”更有效**

你在 GitHub 模板库里可以先搜这些词；如果没有结果，再组合搜索：

- **收票与附件**  
  `invoice email attachment`、`Gmail invoice PDF`、`Outlook invoice`、`IMAP attachment`、`invoice intake`
- **提取与结构化结果**  
  `invoice extraction`、`invoice OCR`、`structured output`、`invoice line items`、`document processing`
- **人工审核与恢复执行**  
  `invoice approval`、`human in the loop`、`approval webhook`、`wait approval`、`review form`
- **重复识别与存储**  
  `duplicate invoice`、`deduplication`、`idempotency`、`invoice database`
- **到期与提醒**  
  `accounts payable reminder`、`accounts receivable`、`overdue invoice`、`payment reminder`、`invoice due date`
- **导出与系统交接**  
  `invoice CSV export`、`accounting export`、`invoice Xero`、`invoice QuickBooks`

最后一组可以借鉴“批准后交接”的节点模式，不意味着我们需要改用对应会计软件。

优先使用以下入口：

- [你选的 awesome-n8n-templates](https://github.com/enescingoz/awesome-n8n-templates)：先在 README 中搜关键词，再看对应 JSON。
- [n8n 官方模板库：Invoice Processing](https://n8n.io/workflows/categories/invoice-processing/)：集中找收票、提取和审批模板。
- [n8n 官方社区](https://community.n8n.io/)：查模板作者的演示、配置说明，以及审批回调和附件处理的实际问题。
- [GitHub 搜索](https://github.com/search?q=n8n+invoice+approval&type=repositories)：补充查找带工作流 JSON、说明和样例的项目。

目前有两项可以直接作为定向参考：

- [邮件发票归档与数据提取](https://n8n.io/workflows/10923-automatic-email-invoice-archiving-and-data-extraction-with-gmail-drive-and-ai/)：重点看邮件附件的接收、归档和提取衔接；其中 Drive／Sheets 可替换为我们的存储接口。
- [发票上传与 Slack 审批的双工作流示例](https://community.n8n.io/t/invoice-approval-via-slack-in-n8n-one-button-instead-of-four-emails-workflow-template/282981)：重点看审批请求与审批结果如何分开处理，不必跟随它选用 Slack 或 OCR 供应商。

这些目前是**结构参考，尚未验证 JSON 和运行效果**。

建议每次只针对一个缺口挑一两个模板，判断三件事：**能替换哪一段、需要哪些账号与依赖、是否比自己搭这一段更省时。** 找到合适片段就回到骨架继续推进。第一轮只完成“样板发票进入 → 提取 → 人工审核 → 模拟导出”，AR 和自动批准先保留清楚的分支与输入约定。
