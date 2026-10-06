import json,time
from pathlib import Path
from PIL import Image
from backend.document_text import ocr_image
from backend.pdf_layout import organize
results=[]
for p in sorted(Path('/probe/images').glob('*.png')):
 with Image.open(p) as im:
  for factor in [1,2]:
   image=im.resize((im.width*factor,im.height*factor),Image.Resampling.BICUBIC)
   dest=Path('/tmp/variant.png'); image.save(dest)
   start=time.monotonic(); text,conf,tokens=ocr_image(dest)
   results.append({'file':p.name,'factor':factor,'seconds':round(time.monotonic()-start,3),'raw_text':text,'confidence':conf,**organize(tokens),'tokens':tokens})
Path('/probe/tesseract_variants.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
print('Local variants saved')
