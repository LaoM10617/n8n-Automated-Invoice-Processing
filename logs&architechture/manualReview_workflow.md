## Phase02 final integration — 2026-10-07 (current)

The recommended intake is `APApprovalIntakeV9` (`/form/ap-approval-intake-v9`), followed by independent `APReviewExportV1`. Both are imported and published in the local instance; existing v7/v8 and historical workflows remain intact. Approval snapshots enter `/exports` immediately. The user selects a combined Excel download; 02 sends local Mailpit approval/rejection and completed-batch notifications without generating a workbook on every approval.

Schema 5 adds a separate outcome notification ledger. Final acceptance, recovery instructions, evidence and precise mock limitations are in `phase02_final_log.md` and `phase02_final_verification.json`. Earlier sections below are historical snapshots where they conflict with this update.

当前实现（2026-10-07，导出清单修订）：批准后立即查询到不可变快照；用户打开 `/exports`，按发票日期／供应商／币种筛选并勾选，下载一份合并Excel。数据库为权威数据源，不逐条写物理工作簿；历史单票文件保持兼容。详细契约见phase_02_AP_review_export_implementation_guide_zh.md第7节，验证见phase02_export_register_log.md。

当前业务连接：

```text
Automatic / manual approval → Persist decision + snapshot + outbox
                              ├─ Export register → Preview / select → Download combined Excel
                              └─ Review event → Independent 02 → Reload decision → Outcome notification (planned)
```

02当前仅完成鉴权接收与回读后端，尚未接入结果通知；accepted不代表processed，也不代表用户导出了文件。后续02发送“可在清单导出”的审批结果通知，不能按每票事件自动生成Excel。批次文件完成通知应独立绑定batch/export_id。保留outbox恢复，不使用Wait回调。

---

以下为被替代的历史模板讨论，不能作为当前实施要求（逐票自动导出已由用户明确选择的合并下载替代）：

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
