# 统一画布与原生 Agent：最终交付 — 2026-10-07

## 交付结论与边界

当前默认入口仍是已发布的原生画布 [Process AP Invoices — Native Agent, Review & Excel](http://localhost:5678/workflow/J4xPbnTCAgYFVNzJ)。本轮完成回退、数据保护和交付整理，**新增模型调用为 0**。Stage A、旧 01/02 都保留；没有删除数据、覆盖历史 Phase02 验收或提交 Git。

原生 Agent 已有真实 Gemini 与当前文档工具调用证据，不是空候选配置。三份同输入新旧对照 39 字段一致，累计 18 次真实请求。不过第三份草稿经后端恢复，最终表达式修复仅进行了真实闭合草稿回放与缓存入口回归；**最终修复后全新样本的一次完整付费端到端运行仍未补测**。本交付保留这一验收限制，不把恢复后的结果写成首次运行无故障，也不声称 OCR11 历史问题已解决。

## 分层验收

| 层级 | 结果与证据 |
|---|---|
| 文件解析 | 四个当前实例交付 JSON 可解析；保留旧 JSON，不覆盖原导出 |
| 节点/连接 | 原生 36 节点、3 分组；SDK 验证通过，连接目标存在，临时样本节点已移除 |
| 实例导入/读回 | 四个工作流均通过 MCP 读取；交付导出与实际 nodes/connections/settings 一致 |
| 凭据 | 既有 Gemini gateway、当前文档工具、事件 Header Auth 引用保留；真实调用已验证，不复制密钥 |
| 发布 | 原生 `ec9b355d-a4bf-433f-895b-4ab76119af20`；Stage A `fe01bad5-6a5d-46c6-8013-ccf3f846b565`；原 01/02 仍发布 |
| 真实执行 | 自动批准、人工修订批准、拒绝、Excel、Mailpit、缓存、重复事件和重启通过；第三份保存恢复及最终新样本限制见上文 |
| 视觉 | 实际编辑器画布、业务英语命名、Agent 与三个真实工具、独立事件入口已检查；截图见 B4 canvas。顶层框数量仍有既有建议警告，未为压缩框数隐藏业务分支 |
| 模型质量 | 小样本 39 字段匹配；原生与 Python 草稿/证据分开保存。未知结果不自动重试，故障模拟测试不冒充真实提供商故障 |
| 回退 | 本轮实际运行原生→Stage A→旧 01/02→原生；每阶段只设置一个 review 和一个 batch 接收目标 |
| 数据保护 | 所有业务表逐行摘要及 27 原件、7 Excel 哈希在整次回退演练前后完全一致；未产生新模型/审批/导出/通知 |

## 回退与恢复验证

`scripts/rehearse_ap_rollback.py` 在切换前确认无 processing 分析，创建一致性备份；每阶段通过实际运行环境验证目标配置，并向当阶段唯一接收方重放三个已有 event_id 和一个已有 export_id。12 次 HTTP 202 后再次检查完整业务状态不变。脚本 finally 恢复原 compose 内容和原生运行配置。202 仅代表接收；此处业务完成状态来自原有 processed/sent 记录及不变性检查，不将 202 本身当作新业务处理成功。

数据库回退没有在在线环境执行。对最新备份的独立副本进行了恢复读取、完整性/FK 检查及两次迁移，所有行保持不变。本次没有新增 schema；之后如需字段/表变化，继续使用增量可重复迁移，不删除原生表以适配旧执行入口。

隔离恢复测试 **5 passed**：合并 Excel 丢失/损坏时沿用原 export_id、成员和文件哈希；两种进程中断恢复；重复迁移保留原导出。真实原件和 Excel 没有被删除来制造演示故障。

事件恢复复用 event_id，Excel 恢复复用 export_id；不重新批准或换新批次掩盖失败。原生失败 attempts 101/102、成功/恢复 attempts 99/100/103 和 Python 对照历史均保留。

## 备份与保护范围

- 备份：`data/baselines/final-delivery-20261007-145502Z/`，已被 Git 忽略。
- 包含 SQLite 一致性快照、27 原件、7 导出、代码/日志/工作流快照、compose、Git 状态及哈希 manifest。
- `restore-rehearsal.sqlite3` 仅为隔离恢复检查副本，未替换在线数据库。
- 工作流交付只含凭据引用；本地 `.env`、`local_key.txt`、n8n 凭据库和解密密钥不进入公开交付。该备份**不是整机灾备包**；n8n 命名卷与原凭据需要另外保留在受保护环境，不能执行 `docker compose down -v`。
- 默认切换执行版本而非数据库。若确需整库恢复，先停止写入并对当时最新状态再备份，逐项评估备份时间以后新增的数据；未经明确决定不覆盖在线库。
- 最终隐私检查：21 条相关 n8n 执行载荷中未发现事件凭据。

## 入口与回退矩阵

| 模式 | 推荐上传入口 | Review 目标 | Excel 目标 |
|---|---|---|---|
| 当前 Native | `/form/ap-native-intake-b2-v2` | `ap-native-review-b2-v2` | `ap-native-excel-b2-v2` |
| 阶段 B 回退到 Stage A | `/form/ap-unified-intake-a2-v1` | `ap-unified-review-a2-v1` | `ap-unified-excel-a2-v1` |
| 阶段 A 回退到原 01/02 | `/form/ap-approval-intake-v9` | `ap-review-export-v1` | `ap-batch-export-v1` |

目标在 compose 中使用 `http://n8n:5678/webhook/` 前缀。两项一起切换，重建 python-api，再选择对应上传/手动邮件入口。工作流保持发布不代表它们会自动同时消费；本项目邮件入口是手动触发。只运行所选版本，禁止对同一邮件批次重复执行旧/新入口。回退不会自动重新分析已完成发票，native/Python 的缓存和分析历史不可混标。

## 交付索引

- [English operations, two demo paths and recovery](AP_native_agent_demo_operations.md)
- [B3–B4 implementation and limitations](AP_native_agent_B3_B4_log.md)
- [Rollback/data verification](AP_final_delivery_rollback_verification.json)
- [Isolated recovery tests](AP_final_delivery_recovery_tests.xml)
- [Final artifact hashes and acceptance](AP_final_delivery_manifest.json)
- [Native published canvas screenshot](AP_native_agent_B4_canvas.jpg)
- `n8n_workflows/delivery_J4xPbnTCAgYFVNzJ_20261007.json` — native
- `n8n_workflows/delivery_7xXB2pjXOE1EQ2bY_20261007.json` — Stage A Python Agent
- `n8n_workflows/delivery_APApprovalIntakeV9_20261007.json` — original 01
- `n8n_workflows/delivery_APReviewExportV1_20261007.json` — original 02

未实现：Phase03 定时只读检查/汇总、外部会计平台、真实付款、真实 CFO 邮件、持续同步到固定 Excel 文件。当前 Excel 是用户选择已批准快照后生成的批次文件，通知留在本地 Mailpit。
