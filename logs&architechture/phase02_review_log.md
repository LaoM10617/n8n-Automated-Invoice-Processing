# Phase02 5.1／5.2：人工修订与确定性自动批准

日期：2026-10-07。范围：5.1、5.2及它们依赖的共用门禁、人工决定与同事务事件保存。没有实现事件网络投递、独立02或Excel生成；不宣称Phase02全部完成。

## 实现与决策

- `backend/reviews.py`统一审核读取、修订、重新校验、自动政策和人工决定。原始 processing_result/raw_extraction 不覆盖；不可变版本保存字段、修改前后差异、manual来源、页码、理由、校验和重复／证据处理结果。
- GET读取绑定attempt的机器稿与当前版本，不默默换到最新提取。PATCH同时检查expected_revision和processing_attempt_id；出现新attempt必须显式传adopt_attempt_id，页面提供对比与Accept latest analysis。已有人工值保留，但旧证据处理不自动继承到新attempt。
- 原有required字段、日期、币种、Decimal金额等式和查重重新执行。机器证据异常、OCR低置信度、提取不确定、页面质量提示使用明确代码映射，人工逐项提供页码和理由；原始问题永久保留。未知异常默认阻止批准。金额矛盾、复杂调整、无法查重等不能通过通用勾选绕过。可空金额的解析异常也不能因规范化成null而丢失。
- 疑似重复按候选ID及当前字段摘要处理；审批重新查重，新增或修改候选会使旧处理失效。对比其他发票时优先使用其人工／已批准版本。
- 每次人工Save创建新版本；决定再次检查并保存新的不可变决定快照。同一BEGIN IMMEDIATE事务保存终态、快照和outbox事件。批准／拒绝为终态；相同决定重放返回原事件，相反决定409。拒绝必填理由；尚未保存的修改不能随决定请求提交。
- schema version 1→2新增review_requests，保证同一请求ID不同内容冲突，包括终态重放使用的新请求ID。不修改上一阶段迁移的历史证据；5项迁移测试中的当前版本期望随新迁移改为2。
- 自动政策`eur-gross-under-10000-v1`，固定EUR含税总额Decimal阈值10000.00。仅0<total<10000且所有门禁通过时批准，actor=system，保存阈值、币种、金额口径、完整检查和理由。人工修订后不自动批准。没有环境参数悄悄改变阈值；将来改规则须升级policy_version。
- 自动／人工决定共用commit_decision、review_revisions与review_events。网络发送不在事务内，本次没有投递器；事件均为pending，页面明确Approved; export pending。
- 终态禁止新分析；缓存命中可以重放但不重置任务或修订。v7重放终态在后端返回skipped/REVIEW_ALREADY_FINAL，v8返回decision_ready，不发送待审核通知。
- 本地写接口要求X-AP-Review: 1；浏览器Origin必须同源，Host限定本地／容器服务。页面CSP仅允许同源脚本与连接，所有发票文本HTML转义或textContent；没有可信多用户身份认证，actor明确为本地演示审核人。

## 画布与接口

`n8n_workflows/01_AP_approval_intake_v8.json`由v7独立派生，生成器为`scripts/build_approval_workflow.py`。15个执行节点、2个说明节点；业务主线为：Archive & Read → Invoice Analysis Agent → Validate & Apply Approval Policy → Decision Saved? → 返回／待审核通知／异常。未将内部数据库读写拆成节点。v7及所有历史JSON哈希保持不变。

- 上传：`http://127.0.0.1:5678/form/ap-approval-intake-v8`
- 编辑器：`http://localhost:5678/workflow/APApprovalIntakeV8`
- GET/PATCH `/api/ap/invoices/{invoice_id}/review`
- POST `/api/ap/invoices/{invoice_id}/review/decision`
- POST `/api/ap/invoices/{invoice_id}/review/evaluate-policy`：显式选中历史记录时才用；要求版本信息，启动时不调用。
- POST `/api/ap/stages/{run_id}/validate-policy`：新v8专用，仅对本阶段新建的任务自动评估。已有pending任务直接保留人工路径。

GET `/api/ap/invoices/{invoice_id}`仍是Phase01提取结果接口；审核当前值和决定快照由review接口／revision读取。后续02不得把该提取接口的最新字段替代批准快照。

## 实际验证

部署前数据库备份位于忽略目录`data/baselines/phase02-start-20261007-075205Z`，是schema1数据快照；代码快照已包含本轮实现，不把它称为本轮改动前代码。原Phase01完整基线073157Z仍保留。

完整离线101项通过（此前74项+新增27项）；最后的绑定机器证据显示修正后，相关29项再次通过。覆盖阈值9999.99/10000/10000.01、零／负值、非EUR、字段缺失、金额矛盾、复杂调整、证据／OCR／质量问题、无法查重、人工修订、迟到重复、过期页面、新attempt显式接纳、拒绝理由、请求重放、并发决定、自动／人工竞争、事件写入失败事务回滚、原稿保留、终态保护、CSRF及新阶段分流。模型与SMTP测试替身不冒充真实模型或邮件。

三个明确标记的合成PDF及模拟提取缓存通过真实v8生产上传和浏览器审核验证。生成／接收脚本`scripts/phase02_review_live_probe.py`，仅3个新增processing attempts，标记synthetic_saved_analysis_no_model，不含Agent执行轨迹，不把模拟缓存当作真实提取准确率。页面与PDF均显示来源说明。

1. €9999.99，无异常：真实自动批准，revision1，system，一条待投递approved事件；没有待审核通知。
2. €10000.00，模拟地址证据异常：转人工，Mailpit收到通知。在真实页面核对原件地址Example Street 1，填写修改、页码和逐项处理理由，Save→Approve成功；机器地址仍null、原草稿错误仍在，人工值另存，最终revision2。
3. €129.00，但100+19不等于129：低金额仍转人工，Mailpit通知。页面Save后Approve保持禁用，填写理由Reject成功，revision2及一条rejected事件，无导出。
4. 后端与n8n真实重启后重放自动样本，复用同attempt与event，不新增任务／通知。未模拟服务故障恢复投递，那是后续第6节范围。

当前业务数量：19原件、162接收、93attempt、7审核任务（原4个pending不变）、5修订、3决定事件、0导出、7通知尝试。Mailpit116→118，仅新增2封本地待审核通知。原16原件、90attempt及其他历史行逐行一致；历史工作流／原件SHA256一致。新模型调用0。

验收层级：JSON解析和连线检查通过；独立v8实际导入、发布、重启生效；v7/v8实例nodes/connections与文件一致。Gmail凭据引用复用并保持绑定，但本轮没有重新执行Gmail；不扩大权限。真实上传执行及UI修改／批准／拒绝通过。v7继续作为Phase01默认展示，v8为新能力入口，尚未把整个Phase02标作完成。

## 文件与后续

核心：reviews.py、review.js、review_page.py、phase02_review_schema.sql；app.py接入接口／页面，document_stages.py保护终态，intake_stages.py接入新政策阶段，email_receipts.py支持decision_ready，notifications.py更新审核操作说明，Dockerfile打包SQL／JS。源码、n8n JSON和日志没有写入密钥。

证据：phase02_review_tests.xml、phase02_review_ui_regression.xml、phase02_review_verification.json、phase02_review_before_restart.json、phase02_review_executions.json、phase02_manual_approved.png。v8真实上传执行426/427/428/429均success；429为重启后自动批准样本回放。最后仅更新通知文案，2项通知测试再次通过并部署，没有为文案变化重发通知。最初两次阶段记录未包含后来补充的analysis_source字段，分析attempt自创建起即带模拟来源标记，未回写旧执行记录。只读复核脚本verify_phase02_review.py，n8n执行元数据脚本phase02_execution_status.cjs（依赖当前容器sqlite3安装路径）。服务当前运行；未Git commit/push。

下一步：实现持久化事件投递／有界恢复，独立02重新读取决定与批准快照，Excel生成／下载／幂等和结果通知。现存3条pending事件需按相同ID处理，不造第二份决定；拒绝不导出。OCR11历史质量限制保留，未重新调用模型或修改其历史任务。
