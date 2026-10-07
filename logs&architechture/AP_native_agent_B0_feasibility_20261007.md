# 原生 Agent B0 可行性检查与 B1–B2 阻塞记录

日期：2026-10-07。目标：执行统一画布实施计划 B0–B2。

## 结论与实际完成范围

B0 的实例、源码和离线探针检查已完成，但**迁移可行性门禁尚未通过**。当前原生 Gemini 直连不能等价保留逐请求间隔、精确预算及故障中途审计。最小代理具备接入点，但尚未实现或验收；本轮建议先保留阶段 A，讨论维护成本后再继续代理实现。

B1 仅在本文固定了建议契约，**未实现接口、未做接口验收**。B2 **未创建工作流 JSON 或实例候选、未绑定凭据、未发布、未执行**。不能把本次检查称为原生 Agent 迁移完成。

这遵循用户要求的实施计划 B0：“若所需复杂度明显超过收益，保留阶段 A，报告具体差距后再讨论取舍。”这里的成本判断是工程判断，不是已证明原生 Agent 不可实现。原生画布展示的收益真实存在，但必须新增并维护模型请求控制边界，不能仅用 Max Iterations、批次延时和成功输出替代。

## 已检查的事实

| 项目 | 证据与状态 |
| --- | --- |
| 实例 | compose 固定 n8n 2.42.3；实时 MCP 提供 Agent 3.1、Gemini Chat Model 1.2 |
| 当前模型 | 运行中 Python 容器为 `gemini-3.5-flash-lite`，配置间隔 60 秒；未读取或输出 API key |
| 凭据 | MCP `list_credentials(type=googlePalmApi)` 返回 0；表示当前 MCP 可访问范围内没有相应凭据，不代表后端缺少密钥 |
| 原生模型初始化 | 已安装 `LmChatGoogleGemini.node.js` 向 ChatGoogleGenerativeAI 传入模型、API key、`baseUrl: credentials.host`、生成参数及 n8n tracing/failed-attempt 回调；不传 `maxRetries` |
| 重试 | 已安装 @langchain/google-genai 2.1.24 / @langchain/core 1.2.8；离线实例化的 `model.caller.maxRetries` 为 6。具体错误是否重试还受 failed-attempt handler 影响；不能断言每次错误都会重试六次 |
| 调用间隔 | 同一实际客户端 caller 连续调用两次假函数，起始间隔约 0.60 ms；说明该调用器自身没有 60 秒门禁。没有向 Google 发出请求 |
| 代理接入 | GooglePalmApi 凭据包含 Host，且运行模型确实使用此 Host。可以研究 Gemini 协议代理，不必改成 OpenAI 模型；端到端代理兼容仍待验证 |
| 精确预算 | Agent maxIterations 控制迭代，不覆盖底层重试，也不等于工具调用总数。当前节点参数不能直接表达最多 3 次实际提供商请求、6 次只读工具调用 |
| nullable Schema | JS 转换源码移除 additionalProperties 等字段并保留其余结构；仅源码检查，尚未验证完整本项目 Schema 的 Google 接受度及输出质量。不能据此宣布兼容，也不能直接假设 Python 适配缺陷在 JS 中同样存在 |
| 发票隔离 | 无 Memory 可以减少串话，但服务端仍需把 run/attempt 固定到当前文档；工具参数不能允许模型指定 invoice_id、任意 URL、路径或 SQL |
| 审计 | returnIntermediateSteps 不等价于持久化每次请求开始、失败和中断状态；本轮未验证原生失败时完整轨迹。没有更改 n8n 执行数据留存设置 |

## 最小代理方案：可研究，但不是已实现能力

候选结构：原生 AI Agent → 原生 Gemini Chat Model → 同一 Python 应用中的 Gemini 请求适配入口 → 当前 Google 模型。三种只读工具也由 Python 提供。代理只负责请求控制，不调用现有 Python Agent，不接管 n8n 的工具选择或多轮编排。

最低必要工作：

1. 独立 Gemini 凭据指向内部代理 Host；提供商密钥留在后端，工作流不包含密钥。代理须验证客户端身份和受限 attempt 作用域。
2. 固定提供商域名与模型；逐次实际请求共享至少 60 秒间隔、每 attempt 最多 3 次请求，并在发出请求前持久化预算。阶段 A 与候选并存时也不能各自独立计时。
3. 下游请求结果不确定或失败后关闭该 attempt 的转发能力。原生客户端隐式重试不得产生第二次提供商请求。需要隔离验证返回错误、自动重试和流式/非流式行为；HTTP 错误码本身不作为完整保障。
4. 每次只读工具调用在服务端计数，最多 6 次；固定文档、校验输入、保存结果摘要。请求控制与工具接口共用 attempt 状态。
5. 逐请求开始/成功/失败记录、工具摘要、最终提交与中断恢复；处理代理完成但 Agent 未提交、n8n 取消、应用重启等情况。
6. 完整 Extraction Schema 的确定性验证；缺失值保留 null。不引入输出修复模型、备用提供商或未计数的额外调用。

这不是增加一个普通 HTTP 节点即可完成。凭据 Host 只有静态目标；受信任的 attempt 如何绑定每次内部模型请求、如何避免敏感作用域信息进入上游提示、以及重试去重都需要协议设计和故障验证。此时先大规模改造现有服务，会在迁移门禁未通过时增加维护负担。

## B1 建议契约（仅设计，待上述方案确认后实现）

- 开始分析：由已有 intake run 解析当前 invoice；创建独立 native attempt，记录执行器、当前模型、prompt/schema/tool 版本签名。重复 begin 不重复创建活跃 attempt。
- 缓存：只有匹配签名和明确来源的成功结果才能复用；返回 `cache_hit` 与来源。Python、native、synthetic 分开，不能静默把旧 Python 提取视为本次原生模型结果。
- 上下文：返回受限 attempt 引用、页码清单和读取说明；原件/OCR 仍由后端保存。拒绝跨 attempt、过期、失败或已完成的工具访问。
- `Read Invoice Page`：仅输入当前文档页码集合，返回页文字与必要布局。服务端记录已读页，提交时检查必需阅读范围。
- `Find Field Evidence`：仅输入长度受限的检索文字；只在当前文档中返回 literal snippets。
- `Check Document Quality`：返回当前文档 OCR/布局质量，不接受文件路径或外部资源。
- 成功提交：后端按 Extraction Schema 解析字段、evidence、uncertainties，检查 attempt 状态和预算、保存新的原始草稿；再进入现有 finalize / deterministic policy 阶段。重复提交不能覆盖既有成功结果或重触发审批。
- 失败/中断：关闭 attempt，保存阶段和错误类别；不得推进到自动批准。旧分析、人工修订、已批准快照都不覆盖。

B1 验收仍需固定输入验证：正常提交、null、非法 Schema、跨发票、重复提交、工具超额、请求超额、失败后提交、缓存来源和重启中断。本文不代替这些测试。

## 验证、改动和后续

新增可复跑离线探针 `scripts/probe_native_gemini_b0.cjs`，通过 Docker stdin 在已安装的 n8n Node 环境执行。使用固定非凭据字符串，不访问网络、不执行工作流、不写业务库。

复跑命令（项目根目录 PowerShell）：

```powershell
Get-Content scripts/probe_native_gemini_b0.cjs -Raw | docker compose exec -T n8n node -
```

本轮真实提供商请求 0；无工作流写操作，无运行配置或数据库变更。只新增探针、本文、证据 JSON，并更新计划和交接入口。

阶段 A 实例 `7xXB2pjXOE1EQ2bY` 仍 active；草稿和发布版本均为 `fe01bad5-6a5d-46c6-8013-ccf3f846b565`。模型、后端路由、既有审批与 Excel 交付保持原状态。

建议下一步先决定是否承担上述代理与审计适配工作。若继续，应先在隔离环境以假提供商验证请求控制与故障边界，再实现 B1 并创建 B2 独立候选；真实字段质量和默认切换仍属于 B3/B4。
