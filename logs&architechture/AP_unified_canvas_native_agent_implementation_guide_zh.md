## Final delivery and rollback — 2026-10-07

See [final delivery index](AP_unified_refactor_final_delivery.md) for layered acceptance, two English demo paths, recovery commands and remaining limits. Native → Stage A → original 01/02 → native receiver rollback passed with every business row and all 34 original/export files unchanged. Five isolated file-recovery/migration tests passed. Current native entry is restored; no new model calls. The final fresh paid end-to-end validation gap remains explicit. Earlier records below are historical.

## Native Agent B3–B4 — 2026-10-07 (current runtime)

Native canvas `J4xPbnTCAgYFVNzJ` is published and is now the recommended local demo entry. Upload: http://127.0.0.1:5678/form/ap-native-intake-b2-v2. Both backend event targets point only to its unique review and Excel receivers. Three real native/Python comparisons matched 39 fields within the user-approved 18-request budget. Review, Excel, local notices, replay and restart checks passed. The third native draft required explicit recovery; final commit wiring was verified with closed real drafts, not an additional fresh paid run. Stage A and old 01/02 remain explicit rollback choices. See [B3–B4 evidence and limits](AP_native_agent_B3_B4_log.md) and [demo/rollback instructions](AP_native_agent_demo_operations.md). All earlier runtime claims below are historical.

# AP 统一业务画布与 n8n 原生 Agent 迁移实施指南

日期：2026-10-07  
状态：阶段 A（A0–A4）已完成，仍为推荐演示入口。B0/B1 的代理与分析契约已实现并通过隔离验证；B2 原生 Agent 候选已构建，凭据绑定与真实 n8n 本地认证通过。候选保持未发布，完整 Agent 运行、真实模型质量及入口切换待 B3/B4。详见 [B0–B2 实施记录](AP_native_agent_B0_B2_log.md)。  
范围：现有 01、02 的统一画布、业务可读性与原生 AI Agent 迁移；Phase03 暂缓。

## 1. 目标、依据与决策优先级

面试 Demo 模拟官网截图中的发票接收、提取、规则分流、人工审核和导出。交付需要兼顾实际运行与客户培训：客户能够理解业务步骤、识别需要自己的操作，并找到审核和 Excel 下载入口。

本轮确认的目标：

1. 将当前 01、02 合并到同一个实际 n8n 工作流画布，方便 Live 展示。
2. 节点名称、分支和说明对应业务；隐藏或封装客户不需要操作的技术细节。
3. 将文档分析逐步迁移为真正的 n8n AI Agent 节点，展示模型及只读工具；不在 Python Agent 外再套一层装饰性 Agent。
4. 保留后端持久化、确定性审批、审计、幂等及恢复能力。

依据：根目录 AGENTS.md、phase_01_AP_implementation_guide_zh.md、phase_02_AP_review_export_implementation_guide_zh.md、phase02_final_log.md、phase01_refactor_log.md、Architechture_rough_summary.txt，以及本对话通过 MCP 读取的实时工作流。

**新决策替代范围：** 原 Phase02 指南要求“不把 02 嵌入 01 的画布”。用户本轮明确要求统一画布，后续实施以本指南为准；保留独立事件入口、不使用 Wait 等待人工、数据库为权威状态源的原则。统一画布已发布，后端事件目标已单一切换；原 01、02 保留用于回退。

交流与规划文档使用中文；节点名称、n8n 说明、代码注释及客户界面使用英语。实施代码时应用 karpathy-guidelines，先做最小可验证改动。

## 2. 当前基线与业务边界

### 2.1 已知实现

| 项目 | 当前状态与依据 |
| --- | --- |
| 01 | APApprovalIntakeV9 / 01_AP_Approval_Intake_v9；16 个执行节点、2 个说明节点、18 条连接 |
| 02 | APReviewExportV1 / 02_AP_Review_Export_v1；8 个执行节点、2 个说明节点、6 条连接 |
| 实时状态 | 前次 MCP 只读检查显示两者已启用并开放 MCP，连接目标均存在 |
| 草稿与发布版本 | 前次读取中，01 仅节点位置不同；02 完全一致。实施前重新读取，不能用此快照覆盖后续用户改动 |
| 分析 | Python LangChain Agent + Gemini；本地 Tesseract/Poppler OCR；有只读工具、缓存及持久化轨迹 |
| 审核与导出 | 自动／人工批准、修订、拒绝、导出清单、合并 Excel、本地结果通知已验收 |
| 验证限制 | Phase02 最终新样本使用明确标记的合成提取缓存；真实 OCR/模型/Gmail 证据来自 Phase01，不能当作原生 Agent 的验收 |
| MCP | 已可实际读取工作流；原生 Agent、Gemini Chat Model、节点分组定义可查询。未试写或试运行新方案 |

### 2.2 必须保留的业务规则

- 自动批准仅适用于 EUR 含税总额满足 `0 < total < 10000.00`，并且字段、金额、证据、OCR 质量和查重等门禁全部通过的记录；恰好 10,000 EUR、其他币种及异常转人工。
- 人工修改后重新校验，继续人工批准；模型不批准、不补平金额、不执行导出或发送通知。
- 保留机器原稿、人工修订、不可变批准快照及来源关联；重放不得清空人工修改或重置终态。
- 批准后立即进入数据库导出清单；用户筛选、预览、选择后生成合并 Excel。历史文件和批次成员不变。
- “更新 Excel”在本计划中指清单更新及按选择生成文件，不新增固定 `latest.xlsx` 持续追加／覆盖或用户本地文件同步。如需该行为，单独确认业务设计。
- 02 的审核入口通知审批结果；批次入口核验已生成文件并通知下载。不得将现有通知节点改名为 `Generate Excel`。
- 通知失败只恢复通知；审核事件、文件生成、邮件投递分别记录状态。HTTP 202 不等于业务完成。
- 不接 DATEV/Lexoffice，不实际付款，不扩展 Phase03，不新增真实对外邮件。Gmail 保持现有只读、手动测试批次语义。

## 3. 目标画布与客户操作

建议工作流名称：`Process AP Invoices — Review & Excel Export`。下列命名为计划，实施时确认实例中不重名。

| 业务区域 | 可见内容 | 独立入口及客户操作 |
| --- | --- | --- |
| Receive & Check Invoices | 接收、保存与读取、AI 提取、检查与审批分流 | 手动 Gmail 批次、上传表单；保留多附件逐张处理 |
| Review & Approval Results | 请求人工审核、读取已保存决定、批准／拒绝通知 | 审批决定事件，包括自动与人工决定；客户在 Review Portal 修改、批准或拒绝 |
| Excel Export & Delivery | 导出门户说明、已生成文件检查、下载通知 | Excel 批次完成事件；客户在 Export Portal 筛选、勾选、下载 |

统一画布不等于一次连续执行。审核和 Excel 完成事件分别产生新的执行记录；不得承诺一次运行中所有区域都变绿。人工操作用清楚的说明和真实门户链接表达，不添加没有实际作用的执行节点或伪连线。不同入口的共享业务关系由说明解释，实际线条只表示真实执行连接。

### 3.1 节点表达建议

| 当前表达 | 目标表达／处理 |
| --- | --- |
| Run Gmail Batch / Gmail | `Run Demo Email Batch` / `Fetch Invoice Emails`，注明受控手动读取 |
| Prepare Attachments | `Prepare Invoice Files`；保持每个附件与来源一一关联 |
| Archive & Read Document | `Save Invoice & Read Text`；说明文本 PDF 与 OCR 路径 |
| Invoice Analysis Agent | `Extract Invoice Details`；阶段 A 说明 Python Agent，阶段 B 使用真实原生 Agent |
| Validate & Apply Approval Policy | `Check Invoice & Apply Approval Rules` |
| Decision Saved? / Route Outcome | 优先合并为明确的结果分流：已批准、需要审核、跳过／异常；真实失败与业务待审核不可混为成功 |
| Notify Reviewer | `Request Invoice Review`，说明审核链接与需要处理的原因 |
| Dispatch Review Outcome | 若保留独立节点，命名 `Forward Saved Decision`；合并进阶段服务时保持既有事件与投递语义 |
| Load Current Decision | `Verify Saved Approval Decision` |
| Notify Approval and Register | `Send Approval Confirmation`，说明发票已在清单中，不由通知创建清单记录 |
| Notify Rejection | `Send Rejection Notice` |
| Verify Saved Excel Batch | `Check Export File` |
| Notify Excel Download | `Send Excel Download Link` |

自动批准目前发生在确定性规则服务内。结果分支可以标为 `Automatically Approved`；若单独显示 `Auto Approve Invoice` 执行节点，该节点必须真正承担审批动作，不能用空节点或通知节点充当审批。

### 3.2 布局和说明标准

- 同一区域统一从左到右阅读，分支紧邻决策点；批准、需审核和异常结果有清楚文字标签，不只靠颜色。
- 业务动作默认可见；准备、循环、返回响应等按实际连接条件使用 Node Groups 收拢。不要为了减少节点数增加无实际复用价值的子工作流。
- MCP 分组规则：触发器不能入组；节点组须满足连通性及入口／出口限制；Agent 与其模型、工具、解析器不能被组边界拆开。不能任意把多个事件入口打包。
- AI 区域演示时展开模型和少量只读工具；日常业务总览可以折叠。
- 节点短名称说明动作；可见短说明解释业务意义；内部 notes 保存接口、恢复和维护细节。
- Sticky Notes 只承担少量补充说明：操作入口、审批规则概要、模拟边界。长篇恢复说明放文档，不铺满画布。
- 必须在真实编辑器检查缩放后的可读性、遮挡和连线；MCP 保存可能自动布局，不能把 JSON 坐标当作最终视觉验收。

## 4. 阶段 A：先统一画布，保留已验证的 Python Agent

### 步骤 A0：重新读取并固定基线

1. 阅读本指南和最新交接，查看 Git 状态及实际 compose.yaml，不覆盖用户未提交改动。
2. 通过 MCP 获取当前 01、02 的完整草稿与发布信息；先读取实例用户偏好，再进行任何创建或修改。
3. 将原工作流导出保存到 n8n_workflows/，新文件明确标记来源和日期；保留现有 JSON。
4. 保存数据库一致性备份、原件／既有 Excel 摘要、Webhook 路径、凭据引用和启用状态。备份目录使用被忽略的 data/baselines/；不复制密钥进公开记录。

验收：能定位原始文件、实例 ID、版本、节点／连接及恢复配置；基线能区分用户改动与本轮改动。

### 步骤 A1：形成准确的业务映射

1. 逐节点标记保留、重命名、分组或合并，并说明客户看到的业务动作。
2. 确认自动批准、人工审核、拒绝、跳过与技术失败如何呈现；审核完成事件不能被误标成仅人工来源。
3. 明确 Web 审核和导出门户在画布中的说明与链接，不改变用户选择导出的时机。
4. 仅对确实重复的后端请求提出合并；不为画布更短拆开已有审批事务。

验收：每个可见节点名称与实际副作用一致；客户能找到“在哪里审核”和“在哪里下载”。

### 步骤 A2：创建独立的统一画布候选

1. 新建候选工作流，保留旧 01、02；建议 JSON 为 n8n_workflows/AP_unified_canvas_python_agent_v1.json。
2. 迁入上传、手动邮件、审批事件和 Excel 完成事件入口；暂不使用原生 Agent。
3. 落实业务命名、结果分流、短说明和合法节点分组。保留逐附件关联、循环和上传响应。
4. 候选使用唯一的表单／Webhook 路径；不要与已发布旧入口抢占同一路径。
5. 若需修改后端事件目标，设计显式切换配置；同一事件只选一个接收目标，不同时向旧、新工作流双投。
6. 凭据仅复用正确的已有引用，不写入工作流参数或文档。后端改动限于确实必要的阶段封装与路由配置。

验收：新 JSON 可解析、节点参数与连接核对通过；实例草稿可读回；旧节点、路径和运行配置尚未被替换。

### 步骤 A3：分层验证与展示检查

1. 先做静态参数／连接检查及真实编辑器视觉检查；不以画布美观代替功能验证。
2. 完成候选凭据绑定和受控入口切换后，使用隔离数据或明确标记的演示批次验证真实路径。
3. 验证自动批准、人工修改后批准、拒绝、Excel 合并下载及两类通知；优先复用已有提取缓存，明确本阶段没有重新验收模型。
4. 复核多附件、无效附件隔离、重复投递、重复事件、通知失败恢复、重启后的持久化。仅运行受影响的必要回归，不重复建设大测试套件。
5. 检查自调用事件不会回到接收入口形成递归；审核事件不生成 Excel，批次事件不重新审批。

验收：新画布与旧流程的业务结果一致；批准／拒绝／清单／文件／通知状态可解释；没有新增重复决定、文件或通知。记录 JSON、导入、凭据、发布、执行各自验证层级。

### 步骤 A4：统一画布作为展示入口

通过 A3 后才切换推荐入口及后端事件目标。旧流程保留用于回退；不得同时消费同一邮件批次。精确记录哪些入口启用、停用或仅保留，不默认批量停用历史工作流。

阶段 A 完成后，应已有一张能独立演示的完整业务画布，即使阶段 B 仍在验证，也不影响已完成的展示改进。

## 5. 阶段 B：原生 Agent 迁移

### 步骤 B0：先验证迁移可行性

只读核对当前实例节点定义、现有模型与凭据能力，再做隔离验证。前次查询返回 Agent 3.1 和 Gemini Chat Model 1.2，但可用参数不等于运行已验证。

必须确认：

- 能否继续使用当前明确配置的 Gemini 模型；不得静默换模型或回退 OpenAI。
- 每次提供商请求至少 60 秒的控制如何落实，包括 Agent 内部多轮、输出解析和隐式重试。批次间隔不是内部模型调用间隔。
- 现有最多 3 次模型请求、6 次只读工具调用如何落实；Max Iterations 不能直接当作等价限制。
- nullable Schema、工具返回、结构化输出和 Gemini 适配是否兼容；不能假设 Python 的自定义修复已在 n8n 生效。
- 每张发票上下文是否隔离；工具只能读当前文档，不得允许模型自行指定任意路径、URL、SQL 或跨发票查询。
- 能否保留模型调用、工具摘要、完成／失败／中断状态；仅成功结束时保存 intermediate steps 不足以覆盖中途故障。

验收：形成已验证／待验证的能力表及选定方案。若原生直连不能维持关键约束，先研究最小模型请求适配或代理方案；不能通过删除限流、预算或审计要求宣布迁移完成。若所需复杂度明显超过收益，保留阶段 A，报告具体差距后再讨论取舍。

### 步骤 B1：固定分析阶段契约

1. 保留后端原件保存与 OCR；为当前 run/attempt 提供受限的分析上下文。
2. 将现有只读能力以最小接口供工具调用，计划工具名称为 `Read Invoice Page`、`Find Field Evidence`、`Check Document Quality`。
3. 原生 Agent 输出字段草稿、页码／证据引用和不确定项；由后端解析、核验、保存，再执行已有金额、查重与审批规则。
4. 明确开始分析、缓存命中、成功提交、失败及中断的记录方式；新分析签名区分执行器、模型、提示词、Schema 和工具版本。
5. 旧 Python 分析历史不可覆盖；缓存来源要区分旧分析、原生 Agent 和合成样本。

验收：使用固定的非模型输入先验证接口和状态语义；失败输出不能进入自动批准，旧审核记录不受影响。

### 步骤 B2：构建真实原生 AI Agent 候选

1. 在独立候选版本中替换分析环节；建议文件 n8n_workflows/AP_unified_canvas_native_agent_v2.json，名称仅表示候选顺序。
2. 配置 `Extract Invoice Details` AI Agent、当前 Gemini 模型及必要的只读工具；不调用原 Python Agent 作为嵌套 Agent。
3. 使用明确的字段 Schema 和证据要求；缺失值保留 null，不从历史发票或常识补值，不为金额平衡修改数字。
4. 不添加跨发票聊天 Memory；保持逐张分析，核实子节点表达式与 item 绑定，防止读取上一张或首张发票。
5. 输出解析优先采用确定性校验；不得未经设计启用额外 LLM auto-fix、自动重试或备用提供商。即便修复格式，也不得改变发票事实，且必须纳入预算和轨迹。
6. 缓存命中走明确的复用路径；不能让界面或日志声称本次调用了模型。
7. 继续由后端执行审批、导出和通知；Agent 工具不获得这些写权限。

验收：节点参数、工具范围、结构化输出及状态提交均通过；业务控制不依赖模型遵守提示词。

### 步骤 B3：小样本对照与故障验证

先用少量代表样本：一份清晰文本 PDF、一份扫描 PDF、一份缺字段或证据异常样本；再验证多附件逐项隔离。真实模型调用使用明确的样本和预算，不对历史全库批量重分析。

逐字段对照人工标准及旧实现，分别记录原始草稿、最终验证值、证据、异常、请求数与耗时。模型完成不等于字段正确；OCR11 的地址证据限制须如实报告，不能为通过验收放宽规则。

另外验证：超时、提供商错误、输出非法、预算耗尽、缓存重放、中断后重启；不确定的提供商结果不得自动重试。部分轨迹应可追踪，失败不得生成批准或重复通知。

验收：代表样本达到预先约定的字段／证据标准，调用预算与间隔有实测记录；缓存重放不新增模型调用。原生 Agent 的证据单独保存，不能沿用 Phase01 Python Agent 的验收替代。

### 步骤 B4：完整业务回归与切换

1. 原生 Agent 成功后验证自动批准和人工审核两条真实链路；新样本避免因已有查重记录误解为流程失败，不删除历史数据凑演示结果。
2. 核对清单、批准版本、Excel 内容及通知；拒绝和 pending 不导出。
3. 新入口验收通过后才设为默认演示入口；保留阶段 A 和旧 Python Agent 作为明确的回退选择。
4. 回退为人工选择的版本／配置切换，不是模型失败时静默调用另一套 Agent。

## 6. 回退和数据保护

- 阶段 A 回退：恢复原推荐入口及审核／批次事件目标，避免旧新接收方同时工作；已生成业务记录继续保留。
- 阶段 B 回退：使用已验证的统一画布 Python Agent 版本；保留原生 Agent 已产生的分析记录和失败证据。
- 恢复事件必须复用原 event_id，恢复文件复用原 export_id，不通过重新审批或生成新批次掩盖失败。
- 默认不回滚数据库、不删除原件或历史 Excel。若确需数据恢复，先保存当前一致性备份并单独评估新增数据损失。
- 新表或字段确有必要时采用增量、可重复迁移；回退旧分析路径不能要求删掉新数据。

## 7. 最终交付与完成标准

交付物统一放置：工作流 JSON 在 n8n_workflows/；设计更新、开发日志、截图及验证摘要在 logs&architechture/。优先新建统一重构日志并从 handoff.md 链接，不覆盖 phase02_final_log.md 的历史验收证据。

完成时需要：

- 一张实际可运行的统一画布，明确接收、人工审核、批准／拒绝及 Excel 交付关系。
- 英语业务名称、简短说明、真实门户链接和可展开的技术细节；在实际编辑器检查展示效果。
- 原生 Agent 真实调用模型和当前发票只读工具，后端继续执行确定性校验和状态变更。
- 自动批准、人工修订批准、拒绝、多附件、重放、失败恢复及持久化的必要验证通过。
- 审核轨迹能区分机器原稿、人工修订、缓存与真实调用；Excel 与批准快照一致。
- 简短英语操作说明：如何开始演示、如何审核、如何选取和下载、失败时从哪里查看状态。
- 两段演示路径：正常自动批准；异常／高金额转人工修正后批准。演示时说明异步执行边界，不用伪节点或伪执行效果连接故事。
- 明确未实现部分：Phase03、外部会计软件、真实付款、真实 CFO 邮件、持续同步固定 Excel。

最终验收分别报告：文件可解析、节点／连接正确、实例导入、凭据绑定、发布、真实执行、视觉验收、模型质量与剩余限制。未完成原生 Agent 实测时只报告阶段 A 完成，不把候选配置视为迁移完成。

## 8. 当前进度与下一步

2026-10-07：阶段 A 已完成，统一画布 Python Agent 版本是当前推荐演示入口。旧 01、02 保留用于回退。

2026-10-07 B0 初次检查发现原生直连缺少逐请求门禁和精确预算，曾按 B0 停止条件暂停。用户随后明确同意增加代理；现已实现并部署代理与 B1 接口，59 项隔离回归通过。B2 独立原生 Agent 候选 `J4xPbnTCAgYFVNzJ` 已导入，节点和连线读回通过，凭据绑定及引擎端到端验证尚未完成；未发布、未调用真实提供商。当前进度以 [B0–B2 实施交接](AP_native_agent_B0_B2_log.md) 为准；[初次可行性报告](AP_native_agent_B0_feasibility_20261007.md) 保留为历史证据。阶段 A 仍是当前入口，B3/B4 待后续。本计划不授权扩展 Phase03 或外部财务操作。

参考：
- n8n Agent 官方说明：https://docs.n8n.io/integrations/builtin/cluster-nodes/root-nodes/n8n-nodes-langchain.agent/tools-agent/
- 本实例 MCP 只读返回的 get_node_types 与 get_workflow_sdk_reference(section=groups)；实施时再次核对版本，优先使用实时定义。
