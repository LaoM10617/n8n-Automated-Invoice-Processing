# Phase01 重构日志

## 2026-10-06：确认的目标与分工

用户确认：n8n 展示业务主线，Python LangChain Agent 负责带证据的文档理解，确定性后端负责业务判断与持久化。本轮仅执行基线固定、确定性后端收拢及精简画布验证；Agent/LangChain 接入另行实施，不把当前提取器改名为 Agent。

目标画布：Upload / Gmail → Prepare Attachments → Process Each Invoice → Archive & Read Document → Invoice Analysis Agent（本轮仍为现有提取器）→ Validate & Save Result → Route Outcome → Notify Reviewer / Record Exception → Return / Continue。

### 架构决策

- n8n 保留入口、循环、业务阶段、结果分流；移除 Capture 上下文搬运、重复缓存判断、逐项 Check 和零散 Record。
- 每阶段使用统一结果契约：source、receipt_id、invoice_id、run_id、stage、status/outcome、review_url、issue_codes、error_code、retryable、analysis_run_id、notification_status。
- Python 保存阶段进度和错误，后续请求只传 run_id，不信任客户端回传的业务状态。异常在发生阶段立即落库，Record Exception 不作为唯一错误落库点。
- 金额不一致、字段缺失和重复候选仍进入 pending 人工审核；损坏/不支持附件和技术故障单独区分。
- Python 封装通知领取、SMTP、结果登记，保留 sent/sending/unknown 不自动重发、明确失败可重试、不重建审核任务的语义。这替代原先 n8n 直接发 SMTP 的职责划分。
- 保留 OCR、现有 Schema、证据校验、金额/日期规则、查重及原件，不使用模型补平金额。

### 后续 Agent 设计（本轮不实施）

单一 Python LangChain Invoice Analysis Agent，工具只读：read_invoice_page、find_field_evidence、get_document_quality。返回字段草稿、证据、不确定项；不批准、不写最终业务状态、不发送邮件。不从历史发票补本张字段。

真实 Agent 必须有工具调用和结构化输出；单纯更换 SDK 或节点名称不算接入。初始考虑最多三次模型请求与有限工具调用，每次真实请求遵守至少60秒间隔、无自动 OpenAI 回退。缓存区分旧提取器结果、新 Agent 缓存和本次真实执行，并纳入分析/提示词/工具版本。

阶段状态和轨迹可恢复；不在数据库事务中等待模型/SMTP。多轮 Agent 可能需后台执行和状态查询，后续用最小联调决定，不提前搭建复杂任务平台。审核页未来增加 Analysis Trace，展示工具、证据、调用数、耗时、缓存和结束状态，不存模型内部思维过程。

### 实施顺序与验收

1. 固定完整工作区基线（当前未提交改动也必须包含）、SQLite一致性备份、原件与v5及既有验证结果。
2. 提取确定性阶段服务、统一契约，继续现有提取器，保留旧API/v5兼容。
3. 精简画布，真实回放已有Gmail多附件批次、上传/重放/来源冲突、失败即时登记、通知失败恢复和不重复发送。
4. 后续再接Agent、调用控制、执行轨迹与真实工具调用验证。

## 基线与比较口径

基线目录：`data/baselines/phase01-pre-refactor-20261006`（Git忽略；不包含.env或n8n凭据）。SQLite使用backup API，复制全部16份原件、backend/scripts/workflow/log目录和compose；manifest记录SHA-256及当前API结果。公开摘要：phase01_refactor_baseline.json。Git HEAD不是完整基线，工作区未提交文件已另行复制。

同源重跑比较receipt_id/invoice_id/review_id、字段、异常代码、证据、重复候选、处理attempt和通知记录；允许run_id及执行时间新增。新来源同文件仅允许新增receipt；不同文件业务重复保留不同invoice并显示候选。原件字节、历史v5和历史证据文件必须保持哈希不变。通知独立验证SMTP实际收到、review_url正确、失败恢复、重放不新增。

状态：基线已固定；实现与验证结果将在本日志追加。

## 实施结果：步骤1、2完成

### 已实施的拆分

- `backend/document_stages.py`：独立读取、分析、确定性校验保存服务。保持原 `step4-layout-v1` 输出语义、Gemini配置缓存和证据规则。新增 `document_reads` 保存独立读取缓存；分析草稿以 `processing_attempts.status=analyzed` 保存，校验后转 processed。
- `backend/intake_stages.py`：`ap-stage-v1` 统一契约与阶段接口。源信息/关联ID只保存在服务端；阶段推进仅使用run_id。新增 `intake_runs` 和 `intake_stage_events` 保存当前状态及历史事件。失败在原阶段立即保存，异常节点只是确认结果。
- 原 `/intakes`、`/process`、审核与通知API保留；旧process也委托相同文档阶段服务。v5原JSON字节不变，旧上传入口在新后端上真实执行成功。
- 通知服务封装原有claim/result函数并发送本地SMTP。只允许mailpit/localhost/127.0.0.1的1025端口，无外发配置。连接阶段失败可以重试；DATA发送期间不确定结果保留unknown，不自动重发；成功通知与审核任务幂等独立。
- 模型限流集中后端：精简阶段在缓存未命中时按现有本地冷却时间等待（最多65秒）；每次真实请求仍经过原请求门控。提供方429不自动重试。旧process保持原fail-fast门控行为。无后台队列或Agent循环，本轮仍是单worker同步服务。

### 精简画布

新 `01_AP_compact_intake_v6.json` / `APCompactIntakeV6`：14个执行节点＋2个说明节点；v5为34个执行节点＋3个说明。没有子工作流依赖。入口、准备附件、循环、Archive & Read Document、Extract Invoice Fields、Validate & Save Result、Route Outcome、Notify Reviewer、Record Exception、Return or Continue 保留可见。

本轮节点明确叫 Extract Invoice Fields，响应也标记 `direct_structured_extraction_not_agent`。未安装LangChain、未接Agent、未改变模型，不把SDK或缓存冒充Agent执行。

编辑器：http://localhost:5678/workflow/APCompactIntakeV6
上传：http://127.0.0.1:5678/form/ap-compact-intake-v6
Gmail：选择Run Gmail Batch，再Execute workflow；仍只读读取phase01-connect-001既有测试批次。新实例导入时绑定专用Gmail只读凭据；SMTP已在Python中，不需要为v6绑定n8n SMTP凭据。

### 分层验证与结果

1. JSON及连接检查通过；已导入并发布到实际实例；读取实例导出并确认节点/参数/连接与交付JSON一致。导出文件active=false仅用于安全迁移，实例active=true。
2. 凭据绑定：现有Gmail只读凭据真实执行成功。两次Gmail执行416、417均成功，每次5封/8项：4个待审核、2个损坏失败、2个跳过（无附件/不支持文本）。没有新外发测试邮件。
3. 生产上传413、414成功并重放；旧v5上传415成功；来源冲突418返回failed/HTTP_409，没有创建错误发票/任务。
4. 对16张发票GET结果做完整比较（含原文证据、字段、异常、重复候选、receipt和review ID），无差异。三个既有批次完整比较，仅忽略outcome更新时间，无差异。原件16份、v5与备份内全部文件SHA-256校验通过。
5. 主库业务表完全保持：16 invoices、159 receipts、84 processing_attempts、4 review_tasks、5 notification_attempts、123 email_outcomes。新增19个stage run与78个stage event用于追踪，不计作重复业务任务。真实模型调用新增0。
6. 独立数据库真实SMTP验证：复用基线中的真实提取缓存，不伪造字段且不调用模型；新建隔离审核任务。实际停止Mailpit使连接失败，恢复后发送成功，重放不新增发送/任务。Mailpit确认仅1封匹配消息、review_url正文一致且可打开。主库通知记录不变；Mailpit从115增至116封，新增的是明确的隔离通知探针。此项不是主库新发票全链模型测试。
7. 56项后端测试通过（2个原有依赖弃用警告）。新增测试覆盖阶段顺序、旧新结果一致、同源/新来源同文件、多附件隔离、模型错误即时落库、通知失败恢复/并发/不确定状态、有界冷却等待。测试中的模型与SMTP替身不作为真实提取或投递证据；真实SMTP证据单独保存。
8. 后端重建后阶段结果仍可读取，完整基线比较仍通过。没有删除邮件、原件、历史工作流或记录。

证据：phase01_refactor_baseline.json、phase01_refactor_comparison.json、phase01_refactor_acceptance.json、phase01_refactor_v6_executions.json、phase01_refactor_upload_verification.json、phase01_refactor_smtp_verification.json、phase01_refactor_v6_canvas.jpg。

### 比较、恢复与后续

执行 `.venv/Scripts/python.exe scripts/compare_refactor_baseline.py` 可重复比较当前业务结果和冻结基线；添加新的业务样本后数量差异需单独解释，不应覆盖基线。`scripts/build_compact_workflow.py`只生成v6，不自动导入或发布。

回退代码可从基线backend/scripts/compose恢复并重建后端；旧v5一直保留可用。新增数据库表为增量，不需要删除。若确实要恢复数据库，先停止后端、另存当前数据库和原件，再从基线SQLite备份及originals恢复；恢复会丢失基线后的数据，未经明确需要不要执行。n8n自身凭据/卷不在本次基线复制范围内，继续保留现有命名卷；v5 JSON与业务数据已单独固定。

本轮未新增后台队列/自动补偿、Agent/LangChain、审核写入或导出。模型输出算法保持原状；OCR11的Causeway遗漏仍在。读取阶段若进程被终止，可见未完成run；通过原来源重投可恢复，不能将所有非终态宣称为已完成。发送后结果落库前中断可能留下sending，仍需人工核对Mailpit，不提供exactly-once SMTP保证。同步阶段适合单worker受控演示，多路并发及真实模型吞吐未测试。

下一步按原分析接入真正的LangChain Agent、工具调用与执行轨迹，并升级分析缓存版本。当前提交未创建Git commit。


## 2026-10-06：步骤 3 — Python LangChain Agent

### 责任与实现

本轮按 karpathy-guidelines 保持阶段接口与确定性规则不变，仅替换文档分析。使用 langchain 1.4.3 create_agent、ToolStrategy(Extraction, handle_errors=False) 与 langchain-google-genai 4.4.0。原有 AP_LLM 配置继续选择 Gemini；原生适配器用于保留 Gemini 工具调用签名，未接入或自动回退 OpenAI。LangGraph 是 create_agent 的传递依赖，不另建业务编排层。

Agent 初始只获得页码清单，通过 read_invoice_page 读取当前文档，可选择 find_field_evidence、get_document_quality。工具只读且限定当前文档，没有文件路径、网络地址、邮件发送、SQL 或状态修改工具。原文视为不可信证据。原有 OCR、Extraction Schema、grounded_fields、金额校验、查重、审核任务与通知服务保持职责。

每次分析最多 3 次模型请求、6 次工具调用；关闭 SDK 重试和结构化输出自动重试。进程内请求使用单调时钟至少 60 秒限流（随后增加 0.1 秒余量，避免 UTC 墙钟采样产生毫秒级表观偏差）。同步单 worker 演示；不宣称多进程或跨重启全局限流。n8n 分析请求超时提高到 480 秒。完整业务吞吐不等于模型吞吐。

缓存键包含 pipeline、模型、端点及 prompt/schema/tools 的分析签名。旧提取缓存不冒充 Agent 执行；历史 attempts 不覆盖。每次模型请求、工具名/参数/输出摘要哈希、用量、完成/失败状态即时写入 processing_attempts.result_json.agent_trace；不保存模型推理。审核页可展开 Analysis agent execution。关闭 LangSmith 外传，轨迹只保存本地。

### 基线与质量检查

新增本地 SQLite/代码/工作流快照：data/baselines/phase01-pre-agent-20261006，原件继续保留原位置；之前包含原件哈希的完整重构基线也未修改。
首版 Agent 真实合成样本暴露字符串 null 和地址证据过度转义；证据校验拦截并保留原始草稿。修订提示明确 JSON null、真实换行及不为缺失值编造证据，升级 agent version/signature。没有放松校验规则。最终逐字段差异见 phase01_agent_verification.json；运行完成不等于提取准确。

### 官方接口依据

- https://docs.langchain.com/oss/python/langchain/structured-output
- https://docs.langchain.com/oss/python/langchain/middleware/custom
- https://reference.langchain.com/python/langchain-google-genai/chat_models/ChatGoogleGenerativeAI

本地已核实原生适配器 max_retries=0 被映射为 Google SDK 单次尝试；无隐式提供商重试。离线测试使用假模型驱动真实 LangChain 图，必须与真实 Gemini 执行证据分开解读。


### 实测发现与适配修正

v1 OCR 实测连续搜索证据触发 AGENT_MODEL_LIMIT，失败及时落库；v2 增加最后一次模型请求仅可提交 Extraction 的约束。v2 合成样本仍出现不合理的缺失字段补值。进一步离线检查 provider wire schema 发现 langchain-google-genai 4.4.0 的转换把 str|null 降为纯 STRING，遗漏 nullable，单改提示无法修复。v3 使用小型 InvoiceGemini.bind_tools 适配：从原有 Schema 生成 Gemini FunctionDeclaration.parameters_json_schema，保留 anyOf null，不更改业务 Schema 或金额规则。新增回归测试检查所有 13 个可空字段及 required 列表。原生 SDK 的 JSON Schema 接口依据：https://ai.google.dev/gemini-api/docs/function-calling 。这是真实适配缺陷修正，不把已出现的质量问题归咎于 OCR。

初轮失败/质量较差的 attempts 85–88 均保留用于追踪；它们不能作为最终提取准确性验收通过的依据。最终结果按最新分析签名比较，历史通知不因重新分析而重发。


### 最终验收层级

- JSON：v7 可解析，14 个执行节点与 2 个说明节点，全部连接目标存在。
- 实例：APAgentIntakeV7 已导入、发布并重启生效；只读导出与本地 nodes/connections 完全一致。
- 凭据：复用现有 Gmail readonly 凭据，未扩大权限。
- 测试：61 项通过，1 项既有 pypdf 弃用警告。5 项 Agent 专项测试是离线测试（真实 LangChain 图 + 假模型/Schema 检查），不冒充真实提供商调用。
- 实际调用：见 phase01_agent_executions.json、phase01_agent_upload_final.json、phase01_agent_verification.json。v3 合成样本 attempt89 使用真实 Gemini 两次请求，标准化字段与基线一致。

本次仅核验 v7 的 Agent 新流程；保留 v5/v6 不等于把旧运行栈隔离部署。旧工作流更短的超时不适合新的多轮分析，演示请使用 v7。没有外发新测试邮件；Gmail 查询原有五封邮件，未删除或修改邮箱。


### 最终结果（已完成）

v3 attempts89/90 均 processed，真实调用分别2/3次，共5次，最小请求间隔约60.096秒。包括v1/v2诊断在内共15次调用，6个有界分析attempt；没有自动失败重试、批量处理历史全库或提供商回退。v1预算失败完整保留。

n8n最终生产上传execution422成功；最终真实Gmail execution423成功：5封、8项，4 review_ready、2坏PDF失败、2跳过。n8n执行success只代表流程完成，不代表坏附件成功。Gmail四个有效来源仍对应两张原件/两个已有审核任务。全部原件及v5/v6工作流字节检查保持一致。主库invoice16、receipt159、review_task4、notification_attempt5（4 sent、1历史failed）均不增加；processing_attempt84→90来自六次有界分析。Mailpit仍116封；本轮未新增通知邮件，因为任务的已发送状态被复用。真实SMTP失败恢复依据上一阶段独立探针，不冒称本轮重新外发。

v3合成发票标准化字段与基线一致。OCR11原始草稿含完整“6479 Smith Causeway / East Camerontown, AS 38212 US”，但OCR文本顺序无法满足现有连续原文证据验证，supplier_address在最终字段为null并显示UNSUPPORTED_EXTRACTION；旧基线是不完整地址。其余标准化字段一致。完整地址证据与布局的衔接仍待改进，不把原始草稿当作已验证值。金额规则仍报告调整项需要显式等式审核。

后端重启后attempt89/90及轨迹持久化；两张发票process重放均复用attempt，真实v7上传重放analysis_cached=true，新模型调用0，新任务/通知0。61项测试通过，原有OCR和validation模块字节不变。证据：phase01_agent_instance.json、phase01_agent_executions.json、phase01_agent_verification.json、phase01_agent_upload_final.json、phase01_agent_restart_cache.json、phase01_agent_v7_canvas.jpg、phase01_agent_review.jpg。

后续：先改善OCR布局证据与地址验证的兼容性，再评估更多代表样本；不要降低证据规则或直接进入自动批准。本轮没有批准/拒绝、导出、提醒等下游扩展。


## 2026-10-06：步骤 4、5 — 调用控制补验与默认入口确认

按用户要求复用已经验证的内容，不生成 v8、不改 v7 画布、不重新导入或发布，不重跑真实 Gmail/付费模型。v7独立入口、14执行节点、发布/凭据绑定及实际上传/Gmail执行已有上节证据，本轮只读再次核对实例与文件。v5/v6及全部历史JSON保留。

### 补齐的缺口

已有启动恢复逻辑会把 processing attempt 标为 failed/PROCESS_INTERRUPTED，但内部 agent_trace 仍可能保持 running。本次仅修正这一状态不一致：重启时轨迹记为 interrupted，已完成模型调用和工具记录保留，未返回调用记为 unknown（不能判断提供商是否已完成/计费），不重试。仍为单worker启动恢复，不在正常请求途中判断其他进程是否存活。

### 8项新增离线控制测试

1. 真实 LangChain 图配假模型和虚拟时钟，连续两次分析的四轮请求严格经过同一限流器，间隔至少60秒；配置0也不能绕过下限。
2. 反复工具调用的假模型仅执行三次，第四次被硬限制；第三次可用工具仅Extraction。
3. 六次只读工具成功，第七次拒绝且不新增成功记录。
4–7. pipeline、分析签名、模型、端点分别变化时缓存失效；processing/failed不能作为缓存。
8. 在隔离子进程中写入真实SQLite attempt及部分轨迹后以os._exit(73)突然退出；父进程确认落库为processing/running，再重建应用确认failed/interrupted、completed调用保留、在途调用unknown；无模型重试、无审核任务或通知。再次启动不覆盖已保存的中断证据。该模型是故障注入替身，不是真实提供商故障或Docker强杀测试。

完整回归69项通过，1个既有pypdf弃用警告。测试报告phase01_step45_tests.xml；补验与部署核对phase01_step45_verification.json。

### 默认展示与边界

通过后将backend/README.md和handoff.md的默认展示明确为APAgentIntakeV7，URL不变；这不是改变n8n首页或覆盖旧入口。因只改启动恢复，不重新进行已经通过的有费用分析；部署后只做既有样本缓存上传冒烟。

限流仍为进程内单调时钟控制：不宣称跨进程/重启全局限流，重启后进行新分析前应等待配置间隔。n8n停止按钮不保证取消正在执行的后端/提供商请求。中断的intake run可能保留最后read检查点，应同时查看invoice attempt，不能把read当作分析成功；按原来源显式重投才会重新分析。此处没有新增自动重试、恢复队列或下游功能。OCR11地址证据限制保持原样。


部署后验收完成：v7实例仍published，nodes/connections与原JSON一致；本轮全部工作流文件SHA256不变。真实上传入口缓存冒烟返回review_ready、analysis_cached=true、attempt89、notification_status=sent。主库保持invoice16、receipt159、processing_attempt90、review_task4、notification_attempt5，Mailpit116；本轮新增提供商调用0、通知发送0。只新增一次上传执行/阶段审计记录，不改变已有业务实体。没有创建Git提交。
