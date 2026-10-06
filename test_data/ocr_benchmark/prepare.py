"""Prepare the three reviewed images without changing production fixtures."""
from pathlib import Path
from pypdf import PdfReader
import shutil
root = Path(__file__).resolve().parents[2]
work = root / 'tmp/paddle-probe'
(work / 'images').mkdir(parents=True, exist_ok=True)
for number in (4, 7, 11):
    source = root / f'test_data/first_round/ocr/invoice_ocr ({number}).pdf'
    list(PdfReader(source).pages[0].images)[0].image.save(work / f'images/case-{number}.png')
for name in ('run.py', 'tesseract_variants.py'):
    shutil.copyfile(Path(__file__).parent / name, work / name)
