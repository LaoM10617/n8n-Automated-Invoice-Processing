# Phase02 第6节：审核事件与失败恢复

日期：2026-10-07。沿用未提交的5.3改动，本轮未Git commit。范围为持久化投递与可靠交接，不提前实现第7节Excel。

## 实现与决策

- 决定／不可变快照／审计／outbox继续在同一事务提交。新增 `backend/review_events.py`，使用现有表，无新迁移。显式命令在独立事务认领后进行网络请求，不持有决定事务等待n8n。
- 每次命令仅投递一个event一次，累计最多5次；60秒认领租约防并发，进程中断后可显式重投。不会启动批处理或无限循环。额度耗尽应先核查接收方，由操作者处理，不制造新的决定或event绕过去重。
- 仅发送event_id、invoice_id、review_id、review_revision、event_type。只允许本地HTTP目标，拒绝重定向和环境代理转发凭据。传输错误只保存安全错误码，不保存响应正文／秘密。
- `accepted`不等于`processed`：2xx仅表示HTTP接收，仍可重投；失去响应记unknown；HTTP失败记failed。后续业务服务才能在实际完成后标processed，本轮不提供盲目信任回调的完成接口。
- GET `/api/ap/review-events/{event_id}`必须Header凭据，并核对数据库事件、当前终态／revision与不可变快照；旧版本／伪造ID拒绝，rejected不授予导出资格。不把传入approved字符串视为授权。第7节导出接口必须再次复用该核验并读取不可变快照，不能仅信任n8n判断。
- 页面展示事件状态、次数和错误，批准仍显示Approved; export pending。投递尚未自动连接到决定按钮：第一版按指南选用显式本地命令。

## 真实实例与凭据处理

新增独立 `n8n_workflows/02_AP_review_events_v1.json`，ID `APReviewEventsV1`，2个执行节点＋1说明节点：Review Decision Received → Load Current Decision。它是第6节接收骨架，未来再接批准／拒绝分流及Excel；不宣称已完成导出画布。v7、v8和其他历史文件未修改。

已核对安装版本2.42.3源码支持Header Auth、credential导入及响应参数。新随机令牌只保存在忽略的.env和n8n credential中；导入经stdin及容器私有临时文件，导入后移除。工作流JSON仅含凭据ID／名称。Compose仍仅绑定127.0.0.1。

验证发现两项实例差异并修正：

1. Webhook v2的202配置需要 `options.responseCode.values.responseCode`，早期探针实际返回200（投递语义仍是accepted）。修正后真实发送探针明确断言202。早期错误断言中断一次投递，记录保持delivering；租约过期后同一event恢复，未改写或删除记录。
2. 关闭saveDataSuccessExecution/saveDataErrorExecution仍会留下软删除的初始execution_data，其中包含Header令牌。新增版本针对性的 `scripts/n8n_review_header_privacy.cjs`，通过n8n.ready在请求处理前使专用认证头不可序列化，Header Auth仍可读取它；作用范围仅为新Webhook生产／测试路径。Compose只读挂载该钩子。此前8条本轮探针载荷中的令牌原地替换为[REDACTED]，不删除执行记录、不修改其他工作流。新请求后再次扫描，令牌未出现在持久化载荷。升级n8n必须重验此行为，不能仅依赖关闭保存选项。

## 验证与边界

- 135项Python测试通过，1条原有pypdf弃用警告。新增7项覆盖投递事务边界、仅标识载荷、失败／超时／重放、接受后再驱动、次数上限、并发租约、陈旧事件、认证、拒绝不导出。独立Node检查认证读取仍有效、序列化无秘密、非目标路径不变。
- 实际停止n8n：自动批准样本事件首次投递unknown，批准快照及事件保留；启动后同ID重投accepted。
- 实际停止python-api：Webhook先接收人工批准事件，随后Load Current Decision因DNS／连接不可用失败；恢复后同ID重新驱动，后端回读200。HTTP接受不置processed。
- 实际向Webhook发送后，在客户端注入TimeoutError，记录unknown；同ID再次投递恢复accepted。这是客户端响应丢失注入，不冒称物理网络故障。
- 无凭据请求实际403；带凭据请求实际接受，后端凭据认证通过。拒绝事件回读can_export=false。全程没有新模型调用、决定、通知或导出。
- n8n禁用保存时执行元数据被软删除，原status可能仍显示running；不能据此声称仍执行或成功。真实回读成功以python-api访问记录200确认，故障以实际停机和n8n错误记录确认。交付分别报告解析／连接、导入／发布、凭据绑定、真实请求及业务未完成。
- 部署前SQLite在线一致性备份见 `phase02_step6_verification.json`。原件、机器结果、审核快照、任务和通知保持不变；仅原有3条合成决定事件投递状态／次数更新。processed=0、exports=0符合当前范围。

## 运行与后续

显式投递：`docker compose exec -T python-api python -m backend.review_events EVENT_ID`。从审核API的event对象取得ID。n8n不可用时恢复后再执行同一命令；delivering中断需等待60秒租约，accepted仍可重投。原3个演示事件已有多次故障演练记录，不宜无意义耗尽剩余额度。

重新部署：`docker compose up -d --build python-api`；首次配置可运行 `scripts/configure_review_event_local.py`，安装Compose的隐私钩子，导入／绑定／发布02，再重启n8n。详细参数见backend/README.md。不要把.env、令牌或未脱敏执行导出纳入版本库。

下一步第7节：批准快照驱动的幂等Excel服务及恢复；其后扩展02业务画布和结果通知。导出／通知完成后才实现真实业务processed确认，不因HTTP成功提前出队。
