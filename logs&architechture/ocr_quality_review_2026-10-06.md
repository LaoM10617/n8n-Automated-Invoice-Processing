# OCR 质量诊断与优化方向

日期：2026-10-06。检查当前后端、历史字段评估、OCR 11 原图及已保存文本；只读检查 SITECO README、backend/app/parsing.py、pdf_layout.py。未修改 SITECO。此次没有模型或付费 OCR 调用。

## 现状与新发现

此前 123/128 是 OCR/文本解析 + OpenAI + 字段证据与标准化的联合结果，含空值与重复样本，不能称为 OCR 准确率。OCR 11 文件部分为 83/88 字段匹配，仍不是纯 OCR 评分。Gemini 仅验证过文本 A，尚无 OCR 整批效果结论。

OCR 4/5/6 发票号有额外空格。OCR 11 原文的 Richardson-Davis 已识别，但与右侧客户地址交错，模型将供应商留空，并把银行信息误归类为供应商地址（当前8字段评估未覆盖该地址）。因此原评估不足以覆盖所有字段。739.69 在已保存 OCR 中为 FIRA8，属于真实识别错误。

还发现代码缺陷：csv.DictReader 默认处理引号，Tesseract TSV 的孤立引号使后续多行控制数据进入单个 text 值。已改为 quoting=csv.QUOTE_NONE，新增复现回归测试。43 项测试通过并部署。页版本 text-quality-v2、pipeline step4-v6；旧页缓存不再直接复用。没有自动重跑旧发票或调用模型，历史评估结果保持原样。

## 单样本本地对照（非整体质量基准）

直接使用此前从 OCR 11 PDF 提取的嵌入图片（595x842），仅运行 Tesseract eng+deu，对比原始宽度与2倍宽度、PSM 3/6/11，共六次本地 OCR。

- 595px / PSM3：供应商名与739.69均出现，但左右栏仍交错。
- 595px / PSM6：739.69出现，供应商名未精确匹配。
- 595px / PSM11：供应商名与739.69均出现，分别成行。
- 1190px / PSM3、6、11：供应商名与739.69均出现；PSM6仍有串栏。
- 单次耗时约0.92至1.54秒（本机容器本次观察，不是通用性能承诺）。

当前生产读取会渲染到长边2400；该样本表明重新渲染/缩放与分区选择能改变识别结果。不能据此宣称所有原图、PSM11或更高分辨率都更好。仅检查关键字符串出现，没有完成整页CER/WER或端到端模型验收。

## SITECO 可借鉴与不可照搬部分

可复用设计：SourceSpan(text,bbox)、Region、按空白分区、保留表格行与页坐标、page状态/布局不确定标记、解析版本与来源证据。它能够帮助供应商/客户两栏隔离，并在审核页面高亮字段来源。

不能直接搬入：无文字页当前直接跳过，不提供OCR；依赖字体加粗/字号/矢量横线，扫描页不存在这些原生对象；按2400/6000字符为RAG切块可能拆断发票表头和汇总；同一显著标题传播到表格是宣传册检索启发式，不应给发票推断供应商/字段关系。建议抽取思路、重新针对发票定义结构，不复制整套检索分块流程。

## 建议实施顺序

1. 原图/渲染策略：对于可确认整页扫描的PDF保留原始嵌入图像；复杂组合页继续渲染。不能直接拿第一张图片，否则可能拿到logo或漏字。
2. 文本/图像区域分开处理：小logo不应迫使可靠文字页整页OCR。为原生文本和OCR统一输出页尺寸、坐标、行/块与读取方式。
3. 基于几何关系组织左右栏、表头、明细和汇总，复用SITECO来源框思路。保留不确定关系，不按本批固定坐标裁剪。
4. 在少量困难件上比较Tesseract配置与PaddleOCR；不按“置信度最高”或“金额能凑平”选结果。固定引擎后再少量、间隔调用Gemini验证字段关联。
5. 评分拆分：OCR关键字/金额字符、供应商/客户归属与表格对应、标准化字段、业务校验；补地址、折扣等当前未覆盖字段，并增加新模板保留集。

## 替换候选（未安装/未验证）

- PaddleOCR：开源首选对照；文本识别与PP-StructureV3布局/表格组件可分别评估。官方当前仓库包含PP-OCRv6以及更重的VL方案；先从普通OCR与布局模块开始，衡量本机CPU资源，不直接引入大VLM。https://github.com/PaddlePaddle/PaddleOCR
- Gemini直接看原PDF/图片：可用现有账户对少数困难件做第二视角；当前仅传OCR文本，尚未接入视觉。不能把模型生成的文本当作可定位OCR证据，也不能跳过金额校验。https://ai.google.dev/gemini-api/docs/document-processing
- Google Document AI Invoice Parser：专门发票解析候选，独立于Gemini API凭据/计费。本次官方标准价为每文档1–10页0.10美元；20份单页约2美元，仅算解析、不含其他服务与税费。https://cloud.google.com/products/document-ai/pricing
- AWS Textract AnalyzeExpense：提供SummaryFields和LineItemGroups，也适合作为付费对照，需独立AWS配置。https://docs.aws.amazon.com/textract/latest/APIReference/API_AnalyzeExpense.html

Tesseract官方质量建议也强调输入图像、倾斜、边界与页面分区模式的重要性：https://tesseract-ocr.github.io/tessdoc/ImproveQuality.html 。本次不购买服务、不启用云OCR，不改主模型。建议下一步先完善本地读取与布局，再用实测决定是否更换引擎。
