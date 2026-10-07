# 原生 Agent B0–B2 实施交接

日期：2026-10-07。用户在 B0 差距报告后明确同意增加模型请求代理，本轮据此继续实施。此前 B0 报告保留为历史检查证据；其中“未实现代理”的状态已由本记录取代。

## 最新验收：本地代理认证通过（2026-10-07）

用户明确授权从项目根目录 local_key.txt 读取代理 key 并代为配置。已通过 n8n 官方 CLI 更新两个既有凭据的内容，保留 ID、名称和归属；Gemini Host 为内部代理，Header Name 为 X-AP-Native。未输出 key，容器临时导入文件已清理，local_key.txt 已加入 .gitignore；用户原文件保留。

直接本地认证返回 HTTP 200；独立 n8n 探针 LwT5i5GzfPXdzXDO 顺序运行两个真实 HTTP 节点，编辑器显示 Workflow executed successfully，后端元数据请求返回 200。证据：AP_native_credential_probe_success.jpg；探针导出：n8n_workflows/AP_native_gateway_credential_recheck.json。探针已归档，执行留存仍为 none。CLI 独立执行尝试因端口冲突未启动，随后使用运行中的 n8n 服务验证成功。

候选 J4xPbnTCAgYFVNzJ 的四个凭据绑定读回正确，版本仍为 87c61b94-95eb-4fc7-8131-4ca8019e020c，保持未发布。阶段 A 版本 fe01bad5-6a5d-46c6-8013-ccf3f846b565 仍已发布。业务表计数与此前一致，native_analysis=0。此次为凭据配置及认证验证，没有重新运行代码回归；此前 59 项测试结果仍是代码验证依据。

B0/B1 隔离控制验证及 B2 候选构建、凭据认证已完成；完整原生 Agent、真实 Google 工具轮次与字段质量仍待 B3，不能据此宣称迁移已通过端到端验收。B4 切换尚未进行。

## 历史检查：凭据已绑定，但认证仍需修正（已解决）

用户已创建并绑定 Gemini 凭据 `9MPrYnkVhS6ONXzd`（Google Gemini(PaLM) Api account）及三个工具共用的 Header Auth 凭据 `uCjC6LA0eyVAylWt`（Header Auth account）。用户确认 Gemini Host 指向内部代理。只读探针在 n8n 中分别先检查 Header 和先检查 Gemini；两者访问本地模型列表均返回 HTTP 401，因此“已绑定”不等于“认证通过”。请将两份凭据的 key 都更新为说明中复制的本地代理 key，Header 的 Name 必须为 X-AP-Native。不要更改旧 event credential。没有调用真实模型。

临时探针 `z96BqJFhNt4mVjkF` 已归档，原始 JSON 保存在 n8n_workflows/AP_native_gateway_credential_probe.json。执行 479/481 的数据按 none 留存设置未保存，不能通过 MCP 重新取回；认证失败由实时编辑器及后端 401 日志确认。截图 AP_native_credential_probe_pending.jpg 为 Header 检查失败证据。没有为了取证放宽数据留存设置。

另外，编辑器发现三个工具的嵌套 JSON 表达式相邻右花括号被模板解释器提前截断。旧表达式在实例内复现 invalid syntax；增加括号间空格后，三个表达式均通过真实解释器的固定输入检查。SDK 校验此前未捕获这一问题。已更新实例、构建器和候选 JSON，连接未变。

## 当前状态

- B0：已选定并实现 Gemini 协议代理；使用隔离测试验证控制边界，并用实例内实际安装的 n8n Agent sequence 与 Gemini SDK 做假传输验证。真实 Google 请求和字段质量不在这些结果中。
- B1：分析开始、严格原生缓存、三类文档工具、确定性提交、失败关闭、中断恢复接口已实现并部署。59 项受影响回归通过，其中 16 项为新增 native/gateway 契约测试。
- B2：独立实例 `J4xPbnTCAgYFVNzJ` / `AP Invoices — Native Agent Candidate B2` 已创建；36 个节点，4 个组；SDK 校验、实例连线读回和两个凭据的真实本地认证通过。候选构建完成；完整 Agent 端到端运行与提供商质量待 B3。
- 阶段 A `7xXB2pjXOE1EQ2bY` 仍为已发布的推荐入口。未发布 B2、未切换后端事件目标、未执行历史邮件批次、未调用真实提供商。B3/B4 尚未开始。

## 设计与实现

### 模型请求控制

`backend/model_gate.py` 使用 SQLite 原子事务持久化下一次允许发出请求的时间。现有 Python Agent 通过 ContextVar 接入同一个门禁，候选网关也使用该门禁；两条路径不会各自独立计时。间隔下限为 60.1 秒。正常调用在本地等待，不向提供商发送重试请求；争用时拒绝未取得时间槽的请求。

`backend/native_analysis.py` 提供固定 Google 域名、固定当前模型的非流式 Gemini 入口。n8n 原生 Agent 继续承担工具选择与多轮编排，没有嵌套调用旧 Python Agent。每个 attempt 最多 3 个提供商请求、6 次文档工具调用。模型请求开始前保存请求摘要和 running 轨迹；失败/不确定结果关闭作用域，后续隐式客户端重试不再转发。重复 payload 也关闭作用域。不存在 OpenAI fallback、自动模型修复或 provider retry。

每个新 attempt 有随机作用域引用，系统提示中的作用域由后端校验并在发往 Google 前移除；提示正文须与后端签名版本完全相同。工具 URL、scope 和当前 invoice 由工作流/后端固定，模型只能选择页码、检索短语和读取质量指示，不获得路径、SQL、目标 URL 或 invoice_id 输入。

### 身份与权限

开始/提交/中止使用已有 event credential；模型代理和只读工具使用独立 HMAC 派生的 native key。native key 不能通过已有审批/导出/event 写接口鉴权；真实 Google key 保留在 Python 环境。n8n credential-test 使用 query key，因此对 native URL 的 uvicorn access log 移除整个 query；模型常规调用使用认证头。

凭据创建按技能要求由用户在 UI 完成，具体步骤在 `AP_native_agent_credential_setup.md`。本轮没有程序化创建凭据，也没有将 key 写入日志、工作流参数或 JSON。候选保持不发布，避免绑定未完成时作为演示入口。

### 数据与状态

新增 `model_request_gate` 与 `native_analysis` 两个附加表，沿用现有阶段服务的幂等建表方式；原审批/导出 Schema 版本仍为 5。native attempt 仍追加到 `processing_attempts`，不覆盖 Python 分析、人工修订或批准快照。

分析签名包含执行器版本、提示词、Extraction Schema 和工具版本；缓存同时检查当前模型及 `native_provider_analysis` 来源。不复用旧 Python 或 synthetic 分析冒充 native 结果。命中缓存走独立 `Reuse Verified Analysis` 分支。

Agent 返回 JSON 文本，由后端 Pydantic 严格解析，要求与最后一次提供商最终文本的解析结果一致、所有页均被工具读取、finishReason 为 STOP 且不存在待处理工具调用。支持 JSON null；仅允许去除明确的 JSON Markdown fence，不修正事实。随后才进入既有证据、金额、查重与审批规则。输出失败不会进入自动批准。

已完成草稿的重复提交不可覆盖内容或把 validate/notify 阶段倒退为 analyze。工具失败、预算耗尽和网关错误保存失败；n8n Agent/提交节点 error output 调用中止接口。应用重启时沿用 existing processing recovery，running 模型请求标为 unknown。若 n8n 被强制取消且中止请求未送达，20 分钟 lease 在下次 attempt 访问时关闭；应用重启也会将该分析标记中断。没有声称后台存在实时取消监听器。

## 验证证据与边界

| 验证 | 结果与限制 |
| --- | --- |
| Python 契约及回归 | 59 passed；`AP_native_agent_B1_tests.xml` |
| 时间门禁 | 假时钟验证两次实际转发间隔至少 60 秒、数据库重建对象后保留门禁、并发只准一个申请者通过；未进行真实提供商墙钟计时 |
| 预算/重试 | 第四次模型请求和第七次工具请求被拒绝；模拟超时后重复七次请求只转发一次 |
| 数据隔离 | 两份不同文档作用域返回各自内容，工具不接受额外 invoice_id；native key 无法调用 commit |
| 提交/失败 | null、非法字段类型、缺页、草稿篡改、重复请求、错误模型、外部工具、过期和重启中断均覆盖 |
| 已安装 SDK wire probe | 精确代理路径、认证头、无认证 query、工具声明和 null 文本通过；实际提供商请求 0 |
| 已安装 n8n Agent sequence | 实际 createAgentSequence / prepareMessages / preparePrompt，通过两轮假模型请求和一次假工具调用得到最终 null JSON；非流式且 system scope 保持完整。不是 n8n 引擎或真实 Google 测试 |
| 工作流 | SDK valid，36 节点；读回 Agent→提交/失败、3 条 ai_tool、1 条 ai_languageModel、缓存/循环等连接正确 |
| 可视检查 | 真实编辑器中原生 Agent、模型和三工具可见，三条业务入口保持分区；截图 `AP_native_agent_B2_canvas.jpg` |
| 部署 | `/health` ok，认证后的本地 models 列表返回当前模型；数据库 integrity ok、FK violation 0 |

MCP 提示折叠后 25 个顶层盒子高于其建议 7 个。保留新分析/缓存、原生 Agent、批准/审核/失败和独立业务入口的可见性；没有为满足固定数量把整条链压成黑盒。分组只使用合法的单入口/出口片段。候选仍比阶段 A 增加了分析控制节点，最终演示精简可在功能验收后继续调整。

部署后计数仍为：24 invoices、98 processing_attempts、12 review_tasks、13 review_revisions、8 review_events、4 export_batches、12 outcome_notifications；native_analysis 为 0。上述生产数据没有加入假模型样本。测试数据均位于隔离的 `data/test-runs/`。

## 文件与恢复

- 新增后端：`backend/model_gate.py`、`backend/native_analysis.py`、`backend/test_native_analysis.py`。
- 局部接入：`backend/extraction.py`、`backend/document_stages.py`、`backend/intake_stages.py`。未修改审批/导出算法，也未修改 compose 事件路由。
- 候选 SDK/构建器：`scripts/AP_unified_canvas_native_agent_v2.ts`、`scripts/build_native_candidate.py`；基于保留的 A4 export 生成。
- 候选导出：`n8n_workflows/AP_unified_canvas_native_agent_v2.json`；凭据绑定完成后须再次读回更新，以实例为准。
- 离线探针：`scripts/probe_native_gemini_b0.cjs`、`scripts/probe_native_gemini_wire.cjs`、`scripts/probe_native_agent_sequence.cjs`。
- 实施前一致性备份：被忽略目录 `data/baselines/native-agent-b0-b2-20261007/`，包括旧后端、工作流、业务库、原件和既有 Excel。

阶段 A 无需回退工作流，因为本轮未切换它。若代理附加代码需要撤回，使用该 baseline 中本轮涉及的三个既有后端文件恢复对应接入并重建 python-api；保留新增表和分析审计，不删除或回滚业务数据库，不覆盖其他用户未提交改动。没有 Git commit/push。

## 下一步

两个 native credential 已配置、绑定且认证通过。下一步 B3 使用明确标记的新样本验证候选 Agent 引擎、实际工具调用、当前 Gemini 的字段/证据质量、真实请求间隔与失败行为；不将本地元数据认证或 mock 测试当成真实 Agent 调用。B4 再验收完整业务路径、更新 candidate webhook 隐私 hook 并受控切换事件目标。
