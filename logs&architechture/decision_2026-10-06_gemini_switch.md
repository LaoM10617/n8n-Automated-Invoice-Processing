# 模型切换与 OCR 说明（2026-10-06）

当前主模型改为 Gemini `gemini-3.5-flash-lite`，替代上一轮 OpenAI `gpt-4.1-mini` 默认选择。原因是用户自己的 Gemini 使用经验与额度归属；OpenAI key 属于朋友，本轮不再调用。Grok 不接入，任何失败均不自动切换供应商。

OCR 仍是 Docker 内本地 Poppler + Tesseract eng/deu，不是 Smallpdf，也不是 Gemini 视觉输入。PDF 文本层质量足够时使用 pypdf；图像页识别后的文本/词坐标交给 Gemini 做结构化字段提取。无需付费 OCR 订阅。

Smallpdf 官方支持页说明 Pro 包含 OCR，但本次未找到公开 OCR API 接入文档，不能把付费网页会员视为 API 访问许可。当前无需购买新 OCR 服务。来源：https://smallpdf.com/support 。

## 模型切换入口

项目根目录 `.env`（Git 忽略）是唯一运行配置入口；可公开查看 `.env.example` 的无密钥示例。

```dotenv
AP_LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai
AP_LLM_MODEL=gemini-3.5-flash-lite
AP_LLM_API_KEY=<your local Gemini key>
AP_LLM_MIN_INTERVAL_SECONDS=60
```

切换供应商时同时更改地址、模型、密钥；然后在根目录执行 `docker compose up -d python-api`。不改 n8n 工作流。OpenAI 兼容端点可使用同一 schema 适配器；其他供应商是否兼容需单独验证，不能仅凭配置存在宣称已跑通。OpenAI 的历史端点为 https://api.openai.com/v1，历史模型 gpt-4.1-mini，只有用户明确选择时才切回。

Google 官方模型 ID：https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite 。兼容 API：https://ai.google.dev/gemini-api/docs/openai 。Gemini 密钥只在程序内部从用户本地文件读取并写入被忽略的 .env，未打印到聊天或日志。

已有结果不会在切换配置时自动批量重跑。对某张发票再次 POST process 时，若模型/端点已改变，则创建新 attempt，保留旧结果；相同模型、端点、处理版本则复用完成结果。GET 可看到原结果所用模型，不把历史 OpenAI 结果称为 Gemini 结果。

## 调用预算与测试习惯

- 单 worker 进程内默认至少 60 秒才允许发起下一次模型请求；间隔内请求返回 429 MODEL_LOCAL_RATE_LIMIT，不调用供应商、不排队。
- 供应商 429 返回 MODEL_RATE_LIMITED，不自动重试，不自动切备用账户。此间隔不是 TPM/RPD 配额保证；大量文本仍可能超出供应商限额。
- 冷却状态在进程重启时重置，不用于生产多实例配额管理。
- evaluate.py --process 现在默认仅 1 个文件，批量需显式 --limit，默认间隔 65 秒，遇 429 停止；新报告写 step_04_field_evaluation_latest.json，保留历史完整评估。
- 本轮仅 1 次 Gemini 生成调用，样本 A 返回 200，关键字段与预期一致；无 OpenAI 调用、无完整样本重跑。因此不能把此前 123/128 的 OpenAI 评估算到 Gemini 名下。
- 42 项离线测试通过，包括冷却与供应商 429 单次调用验证；真实单样本记录见 gemini_switch_verification.json。

下一步仍为真实人工审核任务和页面。模型切换不改变业务状态、审核边界或下游导出计划。
