# Phase02 第一步：固定基线与数据迁移

日期：2026-10-07。状态：本地业务库迁移完成，容器未启动／重建。审批、事件投递和 Excel 生成尚未实现。

## 当前范围与决策

按用户最新确认，Phase02 必须同时实现自动批准、人工审核和真实 Excel 导出。本次仅执行指南第4节及第9节第一步。保留 v7 和所有历史工作流；不修改画布、不调用模型、不发送通知、不创建 Git 提交。

- 版本通过 SQLite `PRAGMA user_version` 管理：0 为无版本的 Phase01，1 为 Phase02 数据基础。未来版本高于代码支持范围时拒绝迁移。
- `review_tasks` 替换原 pending-only CHECK，允许 pending/approved/rejected；保留旧列、任务 ID 和外键。新增 current_revision、extraction_attempt_id、决策人／时间、approval_method、policy_version、规则输入快照与分流理由。
- 旧任务 current_revision=0，extraction_attempt_id=created_attempt_id。不把最新处理结果默认为已审核版本，不制造历史人工操作；后续审核服务首次明确保存时生成 revision 1。新任务暂由旧 Phase01 接口创建，extraction_attempt_id 可以为空，后续审核服务须显式绑定并检查 processing attempt。
- `review_revisions` 保存字段、差异、校验、重复处理、证据处理、actor 和备注，引用原 processing attempt；禁止 UPDATE/DELETE。原始 processing_result/raw_extraction 原样保留。
- `review_events` 同时承担最终决定标识和 outbox：每个 review_id 最多一个终态事件，包含 revision、请求标识／哈希、投递次数、错误与时间；accepted 与 processed 分开。决定与事件同事务须由下一步服务实现。
- `exports` 的业务唯一键为 invoice_id + review_revision + target；target 只允许 excel。mapping_version 不进入去重键。event_id、文件相对路径、哈希和失败状态另存。审批授权及快照一致性仍须由导出服务检查，当前表结构不宣称已实现审批门禁。
- 新建独立 `result_notifications` 与 `result_notification_attempts`，逻辑通知按 event_id + category 去重，投递尝试逐条留存。旧 notification_attempts 保持不变。
- 自动批准政策沿用指南：EUR 含税总额以 Decimal 判断，0 < total < 10000.00 且全部门禁通过；等于阈值、非 EUR 或异常均转人工。拟用 policy_version=`eur-gross-under-10000-v1`，导出 mapping_version=`excel-v1`，后续服务实现时固定并保存规则输入。此步未启用政策，未自动处理历史 pending。

## 基线

忽略目录：`data/baselines/phase02-start-20261007-073157Z/`（目录时间为 UTC）。Git 基线为 e77ddcc，用户已有 AGENTS.md、handoff.md 和 Phase02 指南变更保留。

使用 sqlite3.Connection.backup，从只读连接生成一致性 SQLite 备份；另外备份全部原件、所有 n8n JSON、迁移前 backend、compose.yaml 和 AGENTS.md。manifest.json 保存文件 SHA-256 和旧表计数。未额外复制 .env、密钥文件、n8n 凭据或邮件正文文件；业务库备份仅保存在忽略目录，不在公开日志展开记录内容。

迁移前后：invoices=16、receipts=159、processing_attempts=90、review_tasks=4、notification_attempts=5、email_outcomes=123、document_reads=0、intake_runs=48、intake_stage_events=202。旧列逐行一致；全部原件与历史工作流哈希一致。

## 迁移和验证

迁移使用 BEGIN IMMEDIATE，按 SQLite 表重建方式临时关闭连接外键执行检查，保留旧父表名称的引用；新表复制完成后删除旧表并将新表改为 review_tasks。所有 DDL、数据复制和 user_version 写入同事务，提交前执行 foreign_key_check / integrity_check；失败 rollback，finally 恢复原 foreign_keys 设置。未使用会隐式提交的 executescript 执行迁移。

1. 三个 Compose 容器均已退出，迁移全程不启动服务。
2. 基线库复制到 `tmp/phase02-rehearsal.sqlite3`，执行迁移并重复执行，旧数据和约束检查通过。
3. 74 项离线测试通过：原有69项未删改，新增5项覆盖旧任务／通知外键保留、幂等、后段 DDL 失败回滚、未知版本拒绝、修订不可变、事件／导出去重以及活动事务拒绝。保留1个既有 pypdf 弃用警告。初次沙箱 pytest 临时目录访问失败，提升权限后离线测试完成；没有真实服务故障注入。
4. 隔离验证通过后迁移 `data/ap/invoices.sqlite3`，重复迁移通过。integrity_check=ok、foreign_key_check为空；5张新增业务表均为空。旧 processing_result 包括原始草稿与轨迹逐行保持一致。
5. app.py 在原表初始化后调用迁移，确保新环境和重启使用同一版本逻辑；Dockerfile补充复制 SQL 文件。尚未构建新镜像或做容器运行验证。

证据：`phase02_migration_verification.json`、`phase02_migration_tests.xml`。没有新增或修改 n8n JSON，因而不宣称本次完成导入、发布、凭据绑定或真实工作流执行。

## 文件与运行步骤

- `scripts/phase02_baseline.py`：在服务停止且无其他写入者时执行，创建独立基线，拒绝覆盖同名目录。
- `backend/migrations.py`、`backend/phase02_schema.sql`：版本化迁移。
- `backend/test_migrations.py`：隔离测试。
- `scripts/verify_phase02_migration.py`：本次基线演练、旧数据比对与本地迁移；保留演练库，再次完整演练需使用新的演练路径，不能删除历史证据来重跑。
- `backend/app.py`、`backend/Dockerfile`：启动迁移和 SQL 打包接入。

从根目录执行已备份数据库的幂等迁移：

```powershell
.venv/Scripts/python.exe -m backend.migrations data/ap/invoices.sqlite3
```

完整回归（使用新的临时目录名，避免覆盖现有证据）：

```powershell
.venv/Scripts/python.exe -m pytest backend -q -p no:cacheprovider --basetemp=tmp/phase02-next-tests
```

未提供破坏性降级命令。若确需回退，先停止写入并另存当前数据库，再协调恢复基线数据库与对应代码；后续新增业务记录不能通过直接恢复旧库保留。

## 下一步

实现审核后端与英语 Web 操作：独立修订、版本冲突、确定性重新校验、异常处理和批准／拒绝。随后实现确定性自动批准与同事务 outbox、Excel 服务及精简独立02画布。两条批准分支及故障恢复仍是 Phase02 最终必验收项，本次完成不代表整个 Phase02 完成。
