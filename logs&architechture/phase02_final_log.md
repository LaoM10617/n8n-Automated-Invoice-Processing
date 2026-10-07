# Phase02 衔接、集中验收与收尾 — 2026-10-07

状态：本地 Demo 的 Phase02 闭环已验收。最新依据是本记录和 `phase02_final_verification.json`，此前分步日志保留为历史。未执行 Git commit/push。

## 当前设计与入口

批准快照立即进入数据库导出清单，用户筛选、选择后生成合并 Excel。审核事件负责结果通知，不能自动为每票生成文件；合并批次完成再独立通知。这延续用户确认的清单方案，替代早期逐票自动导出方案。

- 推荐上传：`http://127.0.0.1:5678/form/ap-approval-intake-v9`。
- 01 画布：`http://127.0.0.1:5678/workflow/APApprovalIntakeV9`。
- 02 画布：`http://127.0.0.1:5678/workflow/APReviewExportV1`。
- 导出清单：`http://127.0.0.1:8000/exports`。
- 本地邮件：`http://127.0.0.1:8025`。

仅在验收后将文档推荐入口改为 v9；v7、v8 和其他历史工作流保留，未覆盖或停用。e77ddcc 基线仍保留。Gmail 的既有凭据引用不变；不要同时手动开启多个版本去消费同一批邮件。

## 实现

01 v9 复用 v8 的上传/Gmail公共处理线，增加一个 Dispatch Review Outcome 节点，共16个执行节点及2个说明节点。Python 完成确定性分流；自动决定保存后交接02，人工任务按原机制通知。人工页面决定在事务提交后交接02。

02 使用两个独立入口，共8个执行节点及2个说明节点：审核事件→重新读取状态→批准/拒绝通知；已完成批次→核验现存Excel→下载通知。没有复制两套导出实现，没有将幂等、SQL、重试编排拆成大量画布节点。

Schema 5 新增 outcome_notifications / outcome_notification_attempts，分别关联审核事件或合并批次，保留旧单票通知表及外键。SMTP前持久化 Message-ID 和尝试记录；网络在事务后进行。HTTP accepted 与业务 processed 分开；审核结果邮件确认成功后才标记事件 processed，不意味着已生成Excel或实际记账。

通知面板支持 Refresh notification、Retry notification、Check Mailpit。发送失败独立重试，不改批准、不重建文件。unknown 或崩溃遗留 sending 至少等待60秒后按 Message-ID 查询 Mailpit；找不到保持 unknown，禁止盲目重发。SMTP及Webhook投递分别最多5次，无自动无限循环。SMTP只允许本地Mailpit。

主要文件：backend/outcomes.py、outcome_notifications.js、phase02_outcome_schema.sql、migrations.py；reviews.py、intake_stages.py、export_register.py、app.py 接入事务后交接；review.js/review_page.py/export_register_page.py 显示通知；compose.yaml切换新Webhook并启用交接。n8n_workflows保存新01/02；scripts保存画布生成、凭据隐私检查及集中验收脚本。

## 验收证据

- SQLite online backup：`data/baselines/phase02-final-20261007-100832Z/`（忽略目录），包含库、原件、Excel与工作流备份；隔离库重复迁移两次通过。日志只记清单、摘要和哈希。
- JSON解析、连接核对、目标实例导入、发布及实际凭据认证均完成。实例导出与新JSON节点/连线一致，旧实例工作流节点/连接/启用状态保持不变。无凭据的两个新Webhook实际返回403。
- 两个新合成样本通过真实v9上传：EUR9,999.99无异常自动批准；EUR10,000.00且地址提取异常转人工，网页核对原件、修订、保存再批准。机器稿与异常未被人工修订覆盖。两者均实际触发02并收到结果通知。
- 新样本的提取缓存明确标为 synthetic_saved_analysis_no_model。实际执行了上传、缓存读取、校验、决定、事件、通知及Excel服务；不是本轮新增的真实OCR/模型验收。Phase01真实OCR/Agent/Gmail证据沿用其历史验收，本轮未重新调用外部Gmail或模型，无OpenAI回退。
- 新自动/人工快照共同组成批次 `6b0a081c-97af-483f-86d0-099f02b17d68`，2成员，attempts=1，SHA256 `ee44b704f47f75220149a118bbf9e12dc86534a80a4932bf1c494ffbe2aaeb6d`。重启后重复选择返回原ID及哈希；下载API读取有效XLSX。此前清单页面浏览器下载、筛选及格式验收见 phase02_export_register_log.md。
- 复用既有拒绝事件实际停止Mailpit，得到 SMTP_CONNECTION_FAILED；启动后同通知成功，attempts=2。已拒绝发票没有导出。
- SMTP响应丢失使用受控故障注入：先真实发送至Mailpit，再返回unknown；等待后用Message-ID找回，仍只有1次发送。这不是物理网络断线测试。相应证据在JSON中。
- 重建Python并重启Python/n8n/Mailpit，决定、通知、批次、成员和下载哈希保持不变。已处理事件重放不再发送，合并选择重放不再生成文件或发送邮件。旧库业务行（除预期推进的事件投递字段）、原件、已有Excel及历史工作流哈希保持不变。
- 最终计数：21原件、164接收记录、95分析attempt、9审核任务、8审核版本、5审核事件全部processed、2历史单票导出、3合并批次/6成员、8结果通知全部sent/9发送尝试。新增仅2个缓存合成样本；另有1条新的待审核通知。8封结果邮件逐条按Message-ID验证恰好一封，邮件中本地链接均实际返回成功。
- 全量187项通过；最后补充确认状态不能被迟到结果降级的修复后，通知专项13项通过，共188个不同测试。XML：phase02_final_tests.xml、phase02_final_notification_tests.xml。仅已有pypdf弃用警告。
- Header隐私测试通过；实际n8n保存的相关执行数据扫描未发现事件凭据。未将邮件正文、令牌或.env写入交接。
- 截图：phase02_final_canvas01.png、phase02_final_canvas02.png、phase02_final_intake.png、phase02_final_review.png。

## 运行与恢复

本实例已部署。重建使用 `docker compose up -d --build python-api`；新实例导入和绑定说明见 backend/README.md。现有Header Auth凭据必须与忽略的.env一致，不把凭据写进工作流JSON。导入与发布是两个操作，发布后重启n8n让Webhook生效。

审核事件显式重投：`docker compose exec -T python-api python -m backend.review_events EVENT_ID`。审核/批次通知优先用页面的恢复按钮；API为 GET `/api/ap/result-notifications/{review|batch}/{id}`，POST其 `/retry` 或 `/check`，遵守本地Origin与X-AP-Review保护。文件失败用批次自己的retry；通知失败仅重试通知。

只读复核：`python scripts/verify_phase02_final.py`。该脚本针对本次验收快照比较，不适合新增业务数据后仍要求计数完全相等；届时应保存新的验收基准，不能删除业务数据来通过检查。`python scripts/check_review_event_privacy.py`扫描凭据落盘风险。

Mailpit Message-ID查询依据：[API](https://mailpit.axllent.org/docs/api-v1/)与[搜索过滤器](https://mailpit.axllent.org/docs/usage/search-filters/)。

## 交付边界

Phase02本地闭环完成，未扩展Phase03、外部记账、付款或真实CFO邮件。人工身份仍明确标为本地演示身份。复杂金额公式继续阻止批准；SMTP unknown 未找到邮件时保留需调查状态。没有新增消息队列、无限重试或自动修复历史pending任务。后续如需提交代码，等待用户明确要求。
