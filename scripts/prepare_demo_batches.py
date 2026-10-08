"""Create exact-text demo invoice images and copy five unchanged FATURA originals."""
import hashlib
import json
from decimal import Decimal
from pathlib import Path
import shutil
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.validation import validate

FONT = 'C:/Windows/Fonts/arial.ttf'
BOLD = 'C:/Windows/Fonts/arialbd.ttf'
manual_names = ['Template12_Instance0', 'Template17_Instance101', 'Template18_Instance105',
                'Template46_Instance0', 'Template12_Instance102']
dataset = ROOT / 'test_data/FATURA/invoices_dataset_final'
records = []

for batch in range(1, 6):
    folder = ROOT / 'test_data' / f'batch{batch}'
    folder.mkdir(exist_ok=True)
    for slot in (1, 2):
        number = f'DEMO-2026-B{batch:02d}-{slot:02d}'
        net = Decimal(400 + batch * 300 + slot * 125)
        tax = net * Decimal('0.19')
        total = net + tax
        fields = dict(supplier_name=f'Demo Supplier {batch}{slot}',
                      supplier_address=f'Musterstrasse {batch}{slot}, 10115 Berlin, Germany',
                      supplier_tax_id=None, invoice_number=number, invoice_date='2026-10-07',
                      due_date='2026-11-06', currency='EUR', net_amount=f'{net:.2f}',
                      tax_amount=f'{tax:.2f}', total_amount=f'{total:.2f}',
                      discount_amount=None, shipping_amount=None, has_adjustments=False)
        _, issues, check = validate(fields)
        assert not issues and total < 10000 and check['difference'] == '0.00'
        im = Image.new('RGB', (1654, 2339), 'white')
        draw = ImageDraw.Draw(im)
        def text(x, y, value, size=32, bold=False, color='#172432'):
            draw.text((x, y), value, font=ImageFont.truetype(BOLD if bold else FONT, size), fill=color)
        text(100, 95, 'DEMO INVOICE - FICTIONAL DATA - NOT FOR PAYMENT', 29, True)
        text(100, 185, 'INVOICE', 68, True)
        text(100, 310, 'Supplier', 28, True)
        text(100, 365, fields['supplier_name'], 40, True)
        text(100, 425, fields['supplier_address'], 32)
        text(100, 540, 'Bill to: Demo Finance Team', 34, True)
        text(100, 595, 'Beispielweg 20, 10115 Berlin, Germany')
        for y, label, value in [(730, 'Invoice number', number), (795, 'Invoice date', '2026-10-07'),
                                (860, 'Due date', '2026-11-06'), (925, 'Currency', 'EUR')]:
            text(100, y, label, 32, True)
            text(510, y, value)
        draw.line((100, 1045, 1550, 1045), fill='#172432', width=3)
        text(100, 1080, 'Description', 31, True)
        text(950, 1080, 'Quantity', 31, True)
        text(1200, 1080, 'Net amount', 31, True)
        text(100, 1160, 'Document processing workshop')
        text(995, 1160, '1')
        text(1200, 1160, f'{net:.2f} EUR')
        draw.line((100, 1260, 1550, 1260), fill='#172432', width=2)
        for y, label, value in [(1380, 'Subtotal / net amount', net),
                                (1470, 'VAT (19%) / tax amount', tax), (1590, 'TOTAL AMOUNT', total)]:
            text(650, y, label, 32, True)
            text(1200, y, f'{value:.2f} EUR', 34, True)
        text(100, 1780, 'Payment terms: due on 2026-11-06.')
        text(100, 1850, 'No discounts, shipping charges or other adjustments.')
        text(100, 2130, 'Training document. All parties and transactions are fictional.', 27)
        text(100, 2180, 'Page 1 of 1', 27)
        target = folder / f'{slot:02d}_auto_candidate_{number}.png'
        assert not target.exists(), f'Refusing to overwrite {target}'
        im.save(target, dpi=(200, 200))
        records.append(dict(batch=batch, file=str(target.relative_to(ROOT)), role='automatic_candidate',
                            expected_fields=fields, validation='Exact source fields pass deterministic validation; extraction not tested.',
                            sha256=hashlib.sha256(target.read_bytes()).hexdigest()))
    stem = manual_names[batch - 1]
    source = dataset / 'images' / (stem + '.jpg')
    target = folder / f'03_manual_review_{stem}.jpg'
    assert not target.exists(), f'Refusing to overwrite {target}'
    shutil.copy2(source, target)
    assert source.read_bytes() == target.read_bytes()
    annotation = json.loads((dataset / 'Annotations/Original_Format' / (stem + '.json')).read_text())
    records.append(dict(batch=batch, file=str(target.relative_to(ROOT)), role='manual_review_candidate',
                        source=str(source.relative_to(ROOT)),
                        reason='Printed total differs from subtotal plus tax; adjustments require review. Do not force approval.',
                        annotated_fields={k: v['text'] for k, v in annotation.items()
                                          if k in ('NUMBER', 'SUB_TOTAL', 'TAX', 'TOTAL', 'DISCOUNT', 'DATE', 'DUE_DATE')},
                        sha256=hashlib.sha256(target.read_bytes()).hexdigest()))

assert len(records) == 15 and len({r['sha256'] for r in records}) == 15
(ROOT / 'test_data/demo_batch_manifest.json').write_text(json.dumps(records, indent=2), encoding='utf-8')
print(json.dumps({'batches': 5, 'generated_png': 10, 'unchanged_fatura_jpg': 5, 'provider_calls': 0}))
