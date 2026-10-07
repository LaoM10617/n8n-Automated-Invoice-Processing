# Phase02 导出清单与合并Excel修订

日期：2026-10-07。用户明确授权修改代码和原指南；本次覆盖第7节主流程设计，不扩展记账、付款或Phase03。

## 决策与实现

批准后自动进入数据库导出清单，用户预览、筛选、勾选后下载一份合并Excel。数据库是权威数据源，不逐条append物理工作簿，不新增latest.xlsx或用户本地路径同步。此决定替代此前“一张批准快照对应一份文件”和“审核事件触发逐票生成”的主流程；此前第7节验收日志和单票文件保留为历史。

- 清单直接查询已批准任务、事件和不可变审核版本，没有另一份可变字段副本或异步入列窗口。自动与人工批准共享；pending／rejected不入列；n8n离线不影响清单。
- `/exports`支持发票日期起止（含边界）、供应商包含匹配、币种和All approved／Not yet exported筛选。表格链接回审核页，显示revision、批准方式、导出状态；金额按币种独立汇总，后端Decimal、页面整数缩放计算。
- 修改筛选即清空并禁用旧选择，应用后重新勾选；每批上限500条。POST只提交确切event_id集合，服务端重新核验当前终态与批准版本，预览后的新批准不会进入旧选择。
- Schema 4新增export_batches及export_batch_items，成员和身份不可修改；排序event_id集合哈希施加唯一约束。相同集合返回同一ID，不因顺序、模式或mapping部署变化创建重复批次。不同集合可明确复用先前导出的批准版本。
- 未导出模式在事务内检查历史完成及活动批次占用，冲突409。旧单票成功记录也算已导出；曾成功的文件在修复中／修复失败时仍算历史导出，避免错误地重新入选。首次生成失败则保留未导出状态。
- 每批生成`exports/batches/<export_id>.xlsx`，19列沿用invoice-excel-v1，每行Export ID为批次ID；保存确切invoice_id、review_revision和固定行序。文字强制字符串、日期类型、数值金额与币种精度、空白可选字段、英语表头及演示声明均保留。
- 复用单票服务的写入租期、五次有界尝试、临时文件／fsync／原子替换、快照回读、哈希校验和故障恢复。GET不生成；历史中的Open saved export提供已验证下载或显式Retry this export。
- 审核页主操作改为Open export register，仍保留旧单票下载。旧API和两份历史单票文件继续兼容。固定ZIP create_system=3以匹配已部署Linux文件，Windows生成也能保持相同哈希。

## 修改文件

- `backend/export_register.py`、`export_register_page.py`、`export_register.js`：清单查询、批次契约、筛选预览和历史界面。
- `backend/exports.py`、`invoice_xlsx.py`：共享恢复服务及多行工作簿；保留单行包装和历史文件哈希。
- `backend/phase02_export_register_schema.sql`、`migrations.py`、`app.py`：schema 4与路由。
- `backend/review_page.py`、`review.js`：审核页入口与状态说明。
- `backend/test_export_register.py`、`test_exports.py`、`test_migrations.py`：清单、迁移与跨平台恢复测试。
- 原Phase02指南第1／3／4／6／7／8／9／10／11节，manualReview_workflow、workflow_map、backend/README及handoff：统一当前流程和后续通知边界。
- `scripts/verify_phase02_export_register.py`：备份／隔离迁移演练、实际API及文件验证；保留此前单票验收脚本作为历史证据。

## 备份、迁移和验证

- 在线SQLite备份：`data/baselines/phase02-register-20261007-092835Z/`（忽略目录），同时保存34个原件／历史Excel／工作流文件及哈希。没有复制.env、令牌或邮件正文到日志。
- 对备份副本迁移3→4并重复执行两次，历史表行内容完全一致，外键和完整性检查通过。部署时只重建本地python-api，Compose端口继续绑定127.0.0.1。
- 全量174项测试通过，最后追加修复状态回归后受影响清单17项全部通过（共175个不同测试通过）。报告：`phase02_export_register_tests.xml`、`phase02_export_register_recovery_tests.xml`。只有既有pypdf弃用警告。
- 覆盖增量可见性、日期边界／供应商／币种筛选、Decimal分币种汇总、明确选择、原稿变更隔离、非法／拒绝／过期事件、Origin防护、集合并发及重叠冲突、成员不可变、旧单票兼容、映射部署幂等、五次失败上限、孤立文件复用、文件缺失／损坏与重启恢复。两种真实子进程os._exit注入验证临时文件／重命名后中断的原批次恢复。
- 已部署浏览器：默认未导出视图为空（两条批准样本均已生成历史单票）；切换All approved显示2条，EUR总额19999.99。勾选两条成功生成并下载真实合并文件；修改币种禁用旧选择，USD空结果与EUR恢复均已验证。审核页入口和旧单票链接可见。
- 合并批次：`79ae549f-bc12-44be-9189-c4130a9f6744`，成员为已有自动批准revision 1与人工批准revision 2，attempts=1；SHA256 `ddae16d45868deb98e105d1ff2e033a745976f7f2a4ff218261a6ebc699c37ed`。用户Downloads实际文件与服务端哈希相同。渲染检查两行身份／金额区域通过。
- 重放及多次服务重建仍为同一ID、成员、哈希和attempts=1。原表逐行比较未变，19份原件／162 receipts／93 processing attempts／7 review tasks／5 revisions／3 events／2历史exports保持；仅新增1批次和2成员。所有原件、旧Excel和工作流文件哈希保持。
- 最终API健康，n8n与Mailpit运行。未调用模型、未重新批准旧任务、未创建结果通知或真实邮件、未修改n8n JSON／凭据、未Git commit／push。

证据：`phase02_export_register_verification.json`及`phase02_export_register.png`。截图为真实本地页面；没有宣称整条Phase02通知链已完成。

## 使用与后续

1. 打开`http://127.0.0.1:8000/exports`。批准新发票后刷新即可进入Not yet exported清单；已有样本用All approved查看。
2. 应用筛选、勾选、Download Excel；若浏览器未自动下载，点击Download saved Excel。文件生成不表示记账或付款。
3. 历史批次用Open saved export查看／下载；文件故障显式重试原ID。租期60秒，最多5次；超限应核对原记录，不创建新决策掩盖故障。
4. 部署命令`docker compose up -d --build python-api`；可重复运行`.venv/Scripts/python.exe scripts/verify_phase02_export_register.py verify`核对当前合成验收记录。backup子命令仅用于迁移前schema 3基线，不在schema 4主库再次运行。
5. 后续02应处理审批结果／清单可导出通知，不能继续按每票审核事件自动生成文件。合并文件完成通知需要独立batch关联及去重；旧result_notifications外键指向单票exports，不能直接塞batch ID。当前receiver仍仅接收和回读事件，accepted不冒充processed；本次不修改工作流。通知与其验收仍是下一阶段。

保留Phase01基线e77ddcc、v7及全部历史版本。数据库迁移是增量；需要回退时先停写并保存schema 4及新批次文件，不能直接覆盖回旧基线而丢掉新导出历史。
