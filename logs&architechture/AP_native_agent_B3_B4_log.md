# Native Agent B3–B4 实施记录 — 2026-10-07

## 当前状态

原生画布 `J4xPbnTCAgYFVNzJ` 已发布为本地默认演示入口，名称为 `Process AP Invoices — Native Agent, Review & Excel`。发布版本：`ec9b355d-a4bf-433f-895b-4ab76119af20`。36 个节点、3 个分组；临时样本节点已移除，手动邮件入口已恢复。阶段 A 和旧 01/02 保留，不同时读取同一邮件批次。

本轮完成三份真实原生分析及旧 Python Agent 对照、故障回归、真实审核/导出/本地通知、缓存与重启检查。验收采用分层证据：第三份原生模型已成功返回，但保存节点失败，随后通过正常后端接口恢复原样草稿。最终表达式修复使用三份真实闭合草稿在 n8n 中顺序回放验证；**没有在最终修复之后再额外运行一份全新的付费端到端样本**。不得把这条恢复路径描述成第三份首次运行完全成功。

## B3 样本与预算

数据均为新建、明确标记为 `SYNTHETIC DEMO INVOICE - NOT PAYABLE` 的样本，不重跑历史发票库。样本及人工预期保存在被 Git 忽略的 `data/native-b3-samples/`。

| 样本 | 原生成功 attempt | 金额 | 分析结果 | 旧 Python 对照 |
|---|---:|---:|---|---|
| 清晰文本 PDF | 99 | EUR 119.00 | 13 字段匹配，自动批准 | 13 字段一致 |
| 图像型扫描 PDF | 100 | EUR 11,900.00 | 13 字段匹配，金额规则要求人工审核 | 13 字段一致 |
| 缺少到期日 PDF | 103 | EUR 238.00 | 到期日保持 null，人工审核 | 13 字段一致，同样报 MISSING_FIELD |

- 用户将本轮预算从 12 提高至 18 次；实际为 **18 次**：原生 12 次（成功样本 6 次、两个故障定位尝试共 6 次），旧 Python 对照 6 次。每个成功样本两次模型请求、一次页面读取。
- 两套实现均使用明确配置的 Gemini `gemini-3.5-flash-lite`，没有替换模型或回落到 OpenAI。全局实测最短调用间隔 **60.0804 秒**。
- 39 个原始/最终字段与人工预期吻合，原生和 Python 最终字段无差异；证据通过现有 grounding 检查。具体草稿、最终值、证据、异常、请求起止时间、用量均分别保存于 JSON 报告。
- 旧 Python 对照直接使用原生样本相同的持久化页面，结果单独保存，不覆盖原生或历史 processing_attempts。
- 这三份是小样本，不代表一般准确率提升。历史 OCR11 地址证据限制未重验、未放宽、未宣称解决。

## 多附件缺陷与修复

1. 初始工具跨节点 `.item` 引用在多次循环/分组组合下拿到此前附件 scope。attempt 101 的工具请求被后端以 409 拒绝，未跨票读取，三次模型请求后失败。
2. 将引用改成 `.last(0, -1)` 后，真实执行出现 JSON Body 解析失败（attempt 102）。离线表达式测试及编辑器预览正常，不能作为运行通过的替代证据。故障轨迹保留，101/102 显式 abort，未产生批准或通知。
3. 工具改用当前 Agent 单张输入 `$json.scope`；移除读取/准备阶段的分组，保持顺序 batch size 1。attempt 103 的真实工具与两轮模型成功，正确读到缺失字段样本。
4. 103 的下游 commit 仍受 `.last(0, -1)` 影响，未到达后端。通过受保护的 commit 与 validate-policy 接口提交后端已保存的原样 `last_output`，没有补写发票事实或重新请求模型。
5. 最终 commit 使用对象请求体及配对项 `$("Prepare Invoice Analysis").item.json.scope`；abort 使用读取节点的配对项 run_id。独立 n8n 回放画布以三个真实闭合草稿逐项执行：新写法连续通过三项，旧 `.last` 写法复现失败，恢复新写法后再次通过。回放不是一次新的 Agent 推理。临时回放画布 `cFC02r2ToaROa5Ps` 已归档。
6. 完整候选对扫描/无效 PDF/缺字段三个附件成功走完缓存与隔离分支；10 条历史演示投递结果中保留 3 条无效附件、2 条失败分析，未抹去失败记录。测试使用合成邮件形状的附件输入，不声称重新验收 Gmail 拉取。

## 故障与持久化验证

- 30 项针对性测试通过，另 1 项真实子进程中断恢复测试通过。覆盖 provider HTTP 错误/超时、非法输出、请求/工具预算、scope 隔离、缓存、未知结果不自动重试及失败不进入审批；提供商故障由隔离测试模拟，非主动制造真实 Gemini 故障。
- 子进程测试确实终止执行进程并通过重新创建应用恢复；使用隔离数据库及假提供商。
- 实际 python-api 与 n8n 服务重启后，审核、版本、事件、Excel 哈希、通知状态不变。
- 重启后通过已发布原生上传表单回放三份原件，均报告 `analysis_cached=true`、`analysis_source=native_provider_analysis`，未新增分析、审核决定、导出或通知。
- 一致性备份：`data/baselines/native-agent-b3-b4-20261007/`。基线全部历史业务行以及 30 个既有原件/导出文件保持不变；共享 model_request_gate 的时间推进属于预期变化。

## B4 业务结果与切换

- 清晰文本样本自动批准；扫描件人工将地址按原件重新排为两行并批准（展示人工修订，不是假装修复模型提取错误）；缺少到期日样本拒绝，不补造到期日。
- 人工决定前确认两份 pending 不在导出清单；拒绝后仍不在清单与 Excel。
- 用户选择式批次导出仅含 text/scan 两张发票，合计 **EUR 12,019.00**。下载校验文件哈希、发票 ID/号码、批准方式、修订版本及原始提取未覆盖。批准事件本身不生成 Excel。
- 三个审核结果及一个 Excel 文件结果通知均由本地 Mailpit 确认 sent；事件 processed。既有自动批准事件只向切换后的原生入口顺序重放一次，未重复通知。
- compose 的 review/batch 两个目标现在分别为 `ap-native-review-b2-v2` 与 `ap-native-excel-b2-v2`。每类事件只有一个目标。路径保留 B2 标识以维持接口稳定，并不表示仍是 B2 未验证状态。
- 更新并重启加载了请求头隐私 hook；最终读取 16 条相关执行载荷，未发现事件凭据。没有开启执行数据保留。
- Stage A `7xXB2pjXOE1EQ2bY` 与旧 01/02 仍发布保留；没有新增邮件定时触发器，没有自动运行旧/新邮件入口，无外部邮件、付款或外部会计接入。

## 文件与证据

- `n8n_workflows/AP_unified_canvas_native_agent_v2_B4.json`：实际发布实例读回；旧 B2 JSON 保留。
- `AP_native_agent_B3_verification.json`：原生样本、证据、失败尝试与请求间隔。
- `AP_native_agent_B3_comparison.json`：三份旧实现同输入结果及总预算。
- `AP_native_agent_B3_fault_tests.xml` / `AP_native_agent_B3_abrupt_tests.xml`：隔离故障结果。
- `AP_native_agent_B3_baseline_preservation.json`：历史行和文件保留检查。
- `AP_native_agent_B4_verification.json` / `AP_native_agent_B4_upload_replay.json`：真实业务、重启、缓存回放。
- `AP_native_agent_B3_cache.jpg` / `AP_native_agent_B3_commit_replay.jpg` / `AP_native_agent_B4_canvas.jpg`：编辑器证据。
- `AP_native_agent_demo_operations.md`：English demo and explicit rollback instructions。

展示上保留明确审批/失败/缓存分流。实例的顶层节点数建议仍有既有警告；不为追求 7 个框而隐藏核心业务，也不重新引入已影响循环引用的准备分组。Phase03 仍未实施。未提交 Git。
