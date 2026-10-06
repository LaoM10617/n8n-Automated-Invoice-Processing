# 本地读取与布局优化交付（2026-10-06）

## 当前实现

参考并迁移 SITECO-document-chat/backend/app/pdf_layout.py 的来源坐标、空白分区思路到 backend/pdf_layout.py；使用同版 pdfplumber 0.11.10 获取原生文字几何。源项目没有改动。没有迁移宣传册的标题传播、加粗分类、RAG字符分块，也没有固定发票坐标或供应商规则。

- 原生文本采用去重字符后的词框，统一组织行与块。小图片总面积不超过页面积3%且文字质量可用时保留原生路径，并记录 SMALL_IMAGES_NOT_OCR；这是几何启发式，不能证明图片一定是logo，图片内的重要小字仍需复核。
- 单张扫描图覆盖至少85%页面积、无原生文字/线条/曲线/注释、未旋转/裁剪且图片变换无翻转/倾斜时，提取原始图片，不再一律重新渲染。白边允许保留，保存image_pdf_bbox和PDF页尺寸。复合页、旋转页继续渲染。
- 原图长边小于1000像素时，以bicubic放大2倍作为OCR工作图；保留source_image_size与ocr_scale，原附件不变。不依据预期金额或OCR置信度挑选结果。高于阈值不放大，防止不必要的重采样。
- 原生/扫描共同输出tokens、lines、blocks及raw_text；坐标统一采用左上角x/y/width/height，coordinate_unit明确pt或px。像素坐标映射PDF：先按OCR width/height归一化，再映射image_pdf_bbox（若为整页渲染则映射整页）。
- 大水平间隔切断行片段，附近左边界一致的片段组成块；同一物理行保留row_id，避免只看按栏输出的文字误丢表格对应。它不是表格单元格语义识别；多段行标记layout_uncertain，不猜供应商、买方或数值对应。
- Gemini输入随之包含页尺寸、坐标单位、row/line/block ID，服务配置不变。本轮没有调用Gemini，不能宣称端到端字段归属已改善。
- 当前QUALITY_VERSION=layout-quality-v3、pipeline=step4-layout-v1。旧结果保留；下次显式process会重新读取，避免复用旧页缓存，不会自动批量重跑。

## 验证与结果

47项后端测试通过，包括左右栏隔离、token无丢失、小logo不触发OCR、原始图像像素一致、低分辨率工作图比例、旋转页渲染回退。依赖有两项非失败弃用警告（Starlette TestClient和测试中pypdf页面合并）。

纯本地读取回归16份：5份文本均native，11份扫描均embedded_original。完整文字、框坐标与路由见local_layout_results.json。未运行模型、不读取答案来处理文档。

困难件为OCR 4、7、11：分别针对发票号空格、双栏布局、低分辨率扫描与金额。对照26个诊断用文字片段，旧已保存Tesseract输出24/26；新Tesseract26/26；PaddleOCR26/26。它们是开发中选定的诊断片段，含重复金额，不是独立保留集，不是整页CER/WER，也不能证明字段语义正确。

单次本机耗时：新读取+Tesseract约0.66–1.57秒/张；Paddle推理约5.67–9.99秒/张，首张可能含惰性初始化。不同实现计时范围略有差异，仅用于本机观察，不作吞吐性能承诺。

OCR 11目前739.69、23.70、747.34和293.22均可读，供应商/客户地址分为独立块。OCR 4的发票号额外空格消失。原生不同版式A的FROM与BILL TO已分块。低分辨率原图不放大时曾损失税额/明细，实验输出保留在tesseract_variants_raw.json，不隐瞒该回退现象。

## PaddleOCR对照

隔离Docker镜像pexon-paddle-probe:local：paddleocr3.7.0、paddlepaddle3.2.2、PP-OCRv5_mobile_det + en_PP-OCRv5_mobile_rec，CPU两线程，关闭旋转分类/去畸变/文本行旋转及MKLDNN。此选择用于轻量CPU对照，不代表最新PP-OCRv6或大型布局/VL模型成绩。公开模型权重下载到被忽略的tmp/paddle-probe，不需要API密钥。

主Python镜像没有安装Paddle。基于三张结果尚不值得全面替换；保留独立测试环境。若后续加入大量歪斜照片、复杂表格或新模板，再扩展评测并评估是否作为明确的困难件第二路径。

复现步骤：test_data/ocr_benchmark/README.md；镜像定义、准备脚本、推理脚本均在该目录。原始输出paddle_ocr_comparison_raw.json；指标ocr_layout_comparison.json。PP-StructureV3未测试，不应将本次普通OCR框结果称作已实现完整表格解析。

## 部署与下一步

新后端镜像已部署，n8n无需改接口。GET旧发票仍显示历史结果及版本；新的显式process才使用新布局。没有创建审核任务、改主模型、调用外部付费服务或提交Git。

建议下一次只挑OCR11及另一张新模板，各一次、间隔至少60秒，验证Gemini是否正确归类供应商与买方，并补足地址、折扣、明细关联评分。当前只完成OCR/布局层真实验证，历史OpenAI的123/128结果不更新为本轮结果。
