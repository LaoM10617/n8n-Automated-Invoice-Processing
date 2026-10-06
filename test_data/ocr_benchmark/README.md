# Local OCR comparison

Development cases: OCR 4 (invoice-number spacing), OCR 7 (two-column layout),
OCR 11 (small scan, supplier/buyer columns, subtotal and line items).
No API keys or LLM calls are used. Reference spans are only diagnostic checks:
text occurrence is not proof of correct field assignment or whole-page accuracy.

From the project root in PowerShell:

```powershell
.venv/Scripts/python.exe test_data/ocr_benchmark/prepare.py
docker build -t pexon-paddle-probe:local test_data/ocr_benchmark
$probeDir = (Resolve-Path 'tmp/paddle-probe').Path
docker run --rm --mount "type=bind,source=$probeDir,target=/probe" --mount "type=bind,source=$probeDir,target=/root/.paddlex" pexon-paddle-probe:local python /probe/run.py
```

Initial execution downloads public model weights. Subsequent runs reuse the mounted
model cache. The container receives only the probe folder, not `.env` or invoice DB.
The production image does not include PaddleOCR. This benchmark intentionally uses
CPU/mobile PP-OCRv5 detection and English recognition; PP-OCRv6, server models and
PP-StructureV3 have not been measured here. Installed package/framework versions are
written in paddle_results.json. Raw outputs and final comparison are copied under
logs&architechture, with timings measured on this machine (not throughput guarantees).
The first image timing can include lazy initialization. Images are identical original
inputs; Tesseract's optimized path applies its documented low-resolution scaling.
