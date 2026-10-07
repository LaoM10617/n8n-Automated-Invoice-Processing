当前实现（2026-10-07）：Web修改／重新校验／批准／拒绝与确定性自动批准已经实现，两条分支共用不可变快照和事务内待投递事件。独立02、事件网络投递和Excel生成尚未连接。当前选定持久化outbox，不采用Wait回调；下文模板讨论作为历史背景。详见phase02_review_log.md。

**二、人工审核结果与导出：独立工作流**

```text
审核人员打开 Web 页面
  → 修改字段／批准／拒绝
  → Python 重新校验并保存结果
  → 向 n8n 发出审核事件

n8n Webhook 接收事件
  → 从 Python 重新读取当前发票状态
  → 按审核结果分流
      ├─ 已批准：请求导出 → 保存导出结果 → 完成通知
      ├─ 已拒绝：记录处理结果 → 结束
      └─ 仍待审核：不导出
```

节点骨架是：

**Webhook → HTTP Request → Switch → HTTP Request（导出）→ 通知。**

我倾向于这种“审核后重新触发”的方式：原始收票执行不需要一直等着人，审核页面也有独立入口。Webhook 是事件通知，**最终是否允许导出，以数据库当前状态为准**；重复收到批准事件时，也不能重复导出。

社区模板里经常会用 **Wait + 审批回调**，这种方式也可以。如果找到简洁、可用的模板，可以采用；第一版只选一种审核恢复机制。

AP 的自动批准分支和人工批准分支，最终应进入**同一段导出逻辑**。这部分适合后续抽成子工作流；n8n 支持通过 Execute Sub-workflow 调用并传递输入。[官方说明](https://github.com/n8n-io/n8n-docs/blob/main/docs/integrations/builtin/core-nodes/n8n-nodes-base.executeworkflow.md)
