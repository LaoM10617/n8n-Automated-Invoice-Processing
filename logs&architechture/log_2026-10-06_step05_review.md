# 第五步：审核任务与最小页面

日期：2026-10-06

## 本轮结果

第五步／指南第8节已完成。上传→持久化→提取/校验/查重→创建待审核任务→返回真实页面链接已经在本地 n8n v3 执行。第六步通知尚未实现。任务停在 pending，不支持修改、批准、拒绝、导出或付款。

## 接口与设计

- POST `/api/ap/invoices/{invoice_id}/review-task`：仅最新处理成功且存在字段时允许创建。第一次201、重复200；invoice_id唯一约束与事务保证并发幂等。技术失败/未处理返回409，不伪造正常审核任务。
- SQLite新增review_tasks，保存review_id、invoice_id、pending、created_attempt_id与时间；无破坏性迁移。
- GET `/reviews/{invoice_id}`：真实只读页面，显示原件、字段、校验异常、重复候选、提取证据与接收历史。GET不创建任务。
- 页面展示最新数据库结果；若处理版本变化或失败，显示提示。任务保留创建时attempt。未来批准必须重新校验当前状态与版本，不能直接采用页面旧值。
- AP_PUBLIC_BASE_URL默认http://127.0.0.1:8000；n8n内部调用python-api:8000，返回给人的链接使用外部可访问地址。此配置不改变服务监听范围。
- 浏览器验证发现PDF iframe空白，因此采用已有Poppler按页渲染PNG。GET `/api/ap/invoices/{invoice_id}/preview/{page}`，最长边1600像素、30秒超时、页码限制；页面按需加载各页。保留原始文件入口，可查看更高分辨率的原件。此预览不参与OCR和字段提取，不修改原件。
- 页面转义字段及来源文本，设置CSP；仍是本地loopback无认证Demo，不是生产审核门户。

## 工作流

新增 `n8n_workflows/01_AP_intake_review_v3.json`，基于v2延伸。原始模板与v1/v2保留。
新增 Processing Completed → Create Review Task，仅processed分支创建；失败进入结果页。
JSON检查、连接目标检查、导入、发布、本地实际执行已完成。实例ID APIntakeReviewV3；导出JSON保持active=false，另一个实例需导入发布。此链路没有额外邮件凭据。
入口：http://127.0.0.1:5678/form/ap-intake-review-v3
审核示例：http://127.0.0.1:8000/reviews/1771e496-d925-4832-a504-fbcb96eba30e

## 验证

- 最终 `pytest backend -q`：49 passed；2条既有依赖弃用警告，无失败。
- 四并发创建：一次201、三次200，唯一任务。未处理/失败不能建任务；不存在404；HTML注入文本转义；刷新、重建app后记录仍在。
- 真实n8n上传不同版式A及同源重放：均返回同一真实审核URL。处理attempt保持82，无新增模型调用。
- 同source_id换成其他字节：显示HTTP409，没有继续处理/创建。
- Docker后端容器重建后任务ID不变，原件逐字节一致；浏览器刷新后仍显示记录及原件。
- OCR11和异常C从已有持久化结果建立任务，原件PNG接口成功，非法页码404。浏览器确认C保留129.00并显示TOTAL_MISMATCH、差额10.00 EUR；A显示业务重复候选。
- C使用历史提取结果，未重新调用Gemini；整轮模型调用0。JSON证据见step_05_review_verification.json。
- 预览改动后首次回归失败是旧iframe文字断言；改为新页面图片的可访问名称后，最终全套通过。

## 文件与运行

本轮实现：backend/app.py、backend/review_page.py、backend/test_review.py、compose.yaml、.env.example、backend/README.md、新v3工作流及本日志/交接/进度文件。
后端已使用 `docker compose up -d --build python-api` 部署；n8n使用CLI import:workflow、publish:workflow并重启生效。数据继续持久化于data/ap。
未创建Git提交。现有工作区还包含上一阶段未提交改动。

## 下一步

第六步／第9节：配置Mailpit本地收件，n8n发送真实审核链接；将通知状态与审核任务分开记录，通知失败不重建任务。验收为收到邮件并点击正确链接。之后第七步再接邮件入口。批准/拒绝闭环、02导出与到期提醒继续后置。
