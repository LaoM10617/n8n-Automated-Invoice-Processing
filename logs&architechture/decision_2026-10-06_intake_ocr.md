# 2026-10-06：最小接收接口与 OCR 决策

## 当前选择与替代方案

用户确认：第一阶段不能仅适配格式规整的文本 PDF。替代此前“文本主线完成后再考虑 OCR”的阶段验收方式：OCR 从第一轮样本和接口设计起纳入；第一阶段最终完成必须包含实际 OCR 执行。开发仍分小步推进，本次完成真实接收持久化，OCR 引擎不在本次伪实现。

- 接收格式：PDF、JPEG、PNG；图像 PDF 与混合 PDF 均纳入设计。
- 文本提取与 OCR 最终汇入共同的结构化提取/校验流程。文本非空不代表质量合格；后续按页判断，保留原始文本、来源与规范化值。
- 不依据固定模板、坐标、文件名或样本公司名称获取字段。样本标注只用于评估。
- 原件中的错误必须忠实提取后报告，不自动修正金额或补造日期、币种。
- 自动批准保持关闭；审核任务仍在真实处理结果保存之后创建。

## 首轮材料检查

目录：`test_data/first_round`。

- `text_pdf`：5 份 PDF，均为单页、有文本层、无嵌入位图。
- `ocr`：11 份 PDF，均为单页、零可提取文本、各含一幅图片；它们确实会要求图像识别，不存在误走隐藏文本层的情况。
- 使用 Poppler 渲染并目视抽查 OCR 第 1、11 份，均可读；未逐张人工审定所有字段，也未执行 OCR。
- OCR 文件已改用通用序号命名；目录未包含原 FATURA 样本映射或人工预期值。接收开发可继续，但提取验收前需补 case_id、原始来源、人工核对字段及预期异常清单。
- 不要求 FATURA 每张业务数据都合法；将“忠实提取”和“业务校验结果”分别评估。至少保留不同模板供独立验收。

## 本次技术选择

单个 FastAPI 应用、SQLite、持久化原件目录。先本地 loopback 运行，Compose 暂不改动。后端应用通过环境变量 AP_DATA_DIR 定位数据，默认 data/ap。

真实实现：

1. `POST /api/ap/intakes`：multipart 文件及 source_type、source_namespace、source_id、attachment_id。
2. `GET /api/ap/invoices/{invoice_id}`：原件信息、接收记录和明确的未处理状态。
3. `GET /api/ap/invoices/{invoice_id}/original`：读取原件。
4. `GET /health`：数据库连通及能力标记。
5. `POST /api/ap/invoices/{invoice_id}/process`：仅保留接口位置，已有发票返回 501 PROCESSING_NOT_IMPLEMENTED。

source_type 为 upload/email；source_namespace 区分上传客户端或邮箱/provider；source_id 为上传事件 ID 或 provider message ID；attachment_id 标识该消息中的附件。四字段联合组成接收幂等键。不能把 SMTP Message-ID 与 Gmail provider message ID 混用。

相同键相同字节返回 200 和已有 receipt_id；相同键不同字节返回 409，不覆盖。新键返回 201 并建立新的接收记录；若字节哈希相同则关联已有 invoice_id。哈希不同的业务重复目前仍建立独立候选，business_duplicate_status=not_checked，后续字段提取后再关联。

真实状态为 processing_status=received、review_status=not_created、review_url=null、is_mock=false。is_mock=false 仅表示保存真实，不表示 OCR 已实现。金额字段和校验结果尚未生成，不用空的通过结果冒充验证。

文件按内容识别，限 20 MiB；PDF 限 50 页且不接受加密/空文档。inspection 提供页数、每页文本字符数及 ocr_required 提示。非空文本暂不评质量，因此 text_quality_assessed=false；ocr_required=false 不是可以永远绕过 OCR 的判定。

## 后续处理契约（尚未实现）

process 从已保存原件读取，不能接收标准答案。按页识别输入和文本质量 → 原生文本或 OCR → 结构化提取 → 字段规范化 → Decimal 金额校验 → 业务查重 → 持久化处理结果。

缺失/有歧义字段保留 null 与原因；日期原始值和 ISO 值分开；单独 $ 不自动映射 USD；不得默认添加 30 天账期。OCR 技术失败与原件业务异常分开记录。

review-task、审核页面、通知、02 事件、03 查询继续待实现。本次不创建虚构审核链接或触发下游。

## 验证与限制

详见 handoff.md 最新节。当前测试是后端接收验证，不是 OCR、n8n 或端到端完成报告。

已知限制：未接认证，仅本机演示；未实现解析进程隔离；极端进程中断可能在文件写入后、数据库提交前留下孤立文件。后续处理前检查原件存在，完善恢复时再加入清理核对，不提前扩展复杂基础设施。
