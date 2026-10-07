# Phase02 第7节：Excel导出契约与幂等

日期：2026-10-07。基线提交 `e055499`。本轮未Git commit。范围为Python Excel服务、Web显式生成／下载及恢复验证；02画布扩展和结果通知仍是后续步骤。

## 实现与字段契约

- `backend/exports.py`复用 `ReviewEvents.load`，独立核对事件、当前终态、revision及不可变批准快照。POST只接受event_id；不接受外来金额、approved字符串、文件名或路径。机器最新提取结果不会替代批准字段。
- `backend/invoice_xlsx.py`定义 `invoice-excel-v1`，一条批准记录生成一份标准.xlsx。工作表 `Invoice export`；19列英语表头、首行冻结、筛选、合理列宽／换行，第4行明确“Invoice export — not submitted to an accounting system”。
- 字段顺序以COLUMNS为准：invoice_id、review_revision、supplier_name/address/tax_id、invoice_number、invoice_date、due_date、currency、net/tax/total、discount/shipping、approved_at、export_id、mapping_version、approval_method、policy_version。
- 标识／供应商等文本强制字符串类型；保留前导零和=／+／-／@前缀，不生成公式。invoice_date／due_date为Excel日期单元格，格式yyyy-mm-dd；approved_at作为精确UTC ISO时间文本保存，避免Excel时间精度损失。金额由Decimal验证和比较，写入数值，按币种精度显示；缺失值留空。超过Excel15位有效数字能力或不符合币种精度时明确失败，不擅自舍入。
- 保存后重新打开工作簿逐列核对值、类型、金额精度、日期、表头、提示和布局；拒绝公式、宏、外部链接。运行时固定openpyxl3.1.5，已有Python容器无需宿主机Artifact工具。参考：[官方保存／读取说明](https://openpyxl.readthedocs.io/en/3.1/tutorial.html)、[官方单元格类型实现](https://openpyxl.pages.heptapod.net/openpyxl/_modules/openpyxl/cell/cell.html)。本轮另用宿主Artifact工具只读导入／渲染检查实际输出，未重新导出或改写业务文件。

## 幂等与恢复

- 数据库保留唯一键invoice_id＋review_revision＋target=excel；事务内INSERT ON CONFLICT复用记录，mapping_version不在唯一键中。现有导出永远保留自己的映射版本；新增映射不会自动生成第二份业务导出。
- schema2→3仅新增exports.attempts。新导出ID、writing状态和次数先持久化；60秒租约和文件操作期间SQLite写锁阻止并发／过期写者覆盖。单文件生成很短，不增加队列或后台线程。
- 每次显式生成／恢复一次，累计最多5次；已完成且文件完好的重放不增加次数。失败保存安全错误码，批准不回滚。额度耗尽需操作者核查，不自动重置或制造新event／export_id。
- 路径固定为data/ap/exports/服务端UUID.xlsx，数据库相对路径也必须与该受控路径一致；不接受用户路径。临时文件flush／fsync，再原子replace；重新读取最终文件，校验批准快照和SHA256后提交completed。固定ZIP时间与核心元数据使相同快照的v1生成结果可重现。
- 临时文件中断：原ID仍writing，租约过期后明确重试，覆盖残留临时文件。
- 最终文件已落盘、数据库完成未提交：回读并复用有效孤立文件，不生成第二条业务记录。
- completed但文件缺失／损坏：GET下载409且不重建，查询显示missing_or_invalid；POST相同event从快照恢复，要求与原SHA256一致。
- 通知失败不调用生成逻辑，不修改文件。该行为已隔离测试；本轮不新增结果通知发送器，也不把event提前改processed。

## 接口与页面

- POST `/api/ap/exports`：`{"event_id":"UUID"}`，本地Web沿用Origin／Host／X-AP-Review防护；n8n可复用既有X-AP-Event-Token认证。
- GET `/api/ap/exports/{export_id}`：状态、次数、错误、file_health与可用下载链接。下载／查询仍属于本地Demo只读接口，不宣称多用户认证。
- GET `/api/ap/exports/{export_id}/files/xlsx`：校验后返回现有字节，no-store；不触发生成。
- 审核页新增Generate / retry Excel和Download Excel。显示Excel saved、导出失败或文件需恢复状态；机器异常和人工修订照常保留。health的excel_export=true。

## 验证与部署

- 在线一致性备份：`data/baselines/phase02-step7-20261007-090025Z`。隔离副本执行schema2→3并重复迁移，原表字段逐行一致、外键无错误；未删库重建。迁移旧测试仅把当前schema期望从2改为3，其他约束断言保留。
- 专项23项通过，加入真实进程中断等覆盖后完整157项通过（原135＋新22）。仅原有pypdf弃用警告；测试报告 `phase02_step7_tests.xml`。
- 新测试覆盖自动／人工批准导出、snapshot与新机器字段隔离、前导零、四类公式前缀、空值、JPY／KWD精度、超大金额明确失败、唯一并发导出、mapping变更不绕过去重、拒绝／pending／伪造／过期事件、认证和路径限制、写权限失败与次数上限、落盘后数据库失败、missing／corrupt显式修复、通知失败不重建。
- 真实子进程os._exit分别发生于临时文件部分写入和原子rename之后，操作仅针对隔离测试库；恢复使用同一export_id，残留临时文件清理。不把隔离故障测试描述为主库真实崩溃。
- `docker compose up -d --build python-api`成功，容器健康，schema3生效。已有自动批准样本export_id=`e906032b-1d6f-469f-a0a6-187e4a25d947`；人工批准样本export_id=`d567a817-8f5f-4356-b2fd-2624ab1ad14c`。两者真实API下载字节等于磁盘文件，与批准快照逐列一致。拒绝样本409、没有导出。
- 实际浏览器显示下载链接并点击重复生成，仍为同一文件、attempts=1；截图 `phase02_excel_review.png`。Artifact只读导入／渲染检查19列内容和两段预览，文本／日期／金额／空值及提示显示正常；未启动Microsoft Excel桌面，不冒称其原生验收。
- 实际重启python-api后重新调用两条导出并下载，ID／SHA256／次数不变。验证脚本 `scripts/verify_phase02_exports.py`，摘要 `phase02_step7_verification.json`。
- 当前仅新增2条exports和2个.xlsx；19原件、93attempt、7审核任务、5修订、3事件及通知行全部保持不变。历史工作流／原件哈希一致；模型调用0、结果通知0、真实记账／付款0。

## 后续与运行

用户可在已批准审核页点击Generate / retry Excel，再Download Excel。接口示例和恢复说明见backend/README.md。已完成文件不因为下载或通知失败而重新生成。

下一步：扩展独立02画布，按后端当前状态分流并调用共用导出服务，再实现独立结果通知／processed确认与集中验收。本轮02工作流文件及运行入口未变，仍是接收与状态回读，不宣称自动批准→事件→Excel→通知全链路已经接通。
