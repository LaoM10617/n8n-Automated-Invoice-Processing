import json,time
from pathlib import Path
from paddleocr import PaddleOCR
import paddle,paddleocr
start=time.monotonic()
ocr=PaddleOCR(text_detection_model_name="PP-OCRv5_mobile_det", text_recognition_model_name="en_PP-OCRv5_mobile_rec", use_doc_orientation_classify=False, use_doc_unwarping=False, use_textline_orientation=False, device="cpu", enable_mkldnn=False, cpu_threads=2)
print("Models ready",flush=True)
results=[]
for image in sorted(Path('/probe/images').glob('*.png')):
    started=time.monotonic()
    result=list(ocr.predict(str(image)))[0]
    data=result.json
    if isinstance(data,str): data=json.loads(data)
    payload=data.get('res',data)
    results.append({'file':image.name,'seconds':round(time.monotonic()-started,3),'result':payload})
    Path('/probe/paddle_results.json').write_text(json.dumps({'paddleocr':paddleocr.__version__,'paddlepaddle':paddle.__version__,'models':['PP-OCRv5_mobile_det','en_PP-OCRv5_mobile_rec'],'cases':results},ensure_ascii=False,indent=2),encoding='utf-8')
    print(image.name,results[-1]['seconds'],flush=True)
