"""Create three explicitly synthetic saved-analysis probes in the local demo.

Run inside the python-api container. No model is called. The matching PDF originals
and cached records are labeled synthetic; these verify approval, not extraction.
"""
from contextlib import closing
import io
import json
import os
from pathlib import Path
import sqlite3
import urllib.request
from uuid import uuid4

from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
from backend.document_stages import PIPELINE
from backend.document_text import QUALITY_VERSION
from backend.invoice_agent import ANALYSIS_SIGNATURE
from backend.validation import validate


def main():
    root = Path(os.environ['AP_DATA_DIR'])
    output = root / 'phase02_review_probes.json'
    if output.exists():
        print(output.read_text())
        return
    records = []
    for label, net, tax, total in [('auto', '9999.99', '0.00', '9999.99'), ('manual', '10000.00', '0.00', '10000.00'), ('reject', '100.00', '19.00', '129.00')]:
        number = 'PHASE02-' + label.upper() + '-' + str(uuid4())[:8]
        fields = dict(supplier_name='Synthetic Review Supplier', supplier_address='Example Street 1', supplier_tax_id='TEST-PHASE02',
                      invoice_number=number, invoice_date='2026-10-01', due_date='2026-10-31', currency='EUR',
                      net_amount=net, tax_amount=tax, total_amount=total, discount_amount=None, shipping_amount=None, has_adjustments=False)
        lines = ['SYNTHETIC APPROVAL TEST - NO PAYMENT', 'Saved analysis is simulated; no model was called.', *[f'{key}: {value}' for key, value in fields.items() if value is not None]]
        writer = PdfWriter()
        page = writer.add_blank_page(width=595, height=842)
        font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
        content = DecodedStreamObject()
        content.set_data(('BT /F1 11 Tf 45 795 Td 19 TL ' + ' '.join('(' + line + ') Tj T*' for line in lines) + ' ET').encode())
        page[NameObject('/Contents')] = writer._add_object(content)
        stream = io.BytesIO(); writer.write(stream)
        boundary = 'probe-' + str(uuid4())
        source_id = 'phase02-review-' + label
        form = {'source_type': 'upload', 'source_namespace': 'n8n-ap-upload-v1', 'source_id': source_id, 'attachment_id': '0'}
        body = b''
        for key, value in form.items():
            body += f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode()
        body += f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{number}.pdf"\r\nContent-Type: application/pdf\r\n\r\n'.encode() + stream.getvalue() + f'\r\n--{boundary}--\r\n'.encode()
        request = urllib.request.Request('http://127.0.0.1:8000/api/ap/intakes', data=body, headers={'Content-Type': f'multipart/form-data; boundary={boundary}'})
        intake = json.load(urllib.request.urlopen(request))
        normalized, issues, arithmetic = validate(fields)
        raw = dict(fields)
        if label == 'manual':
            raw['supplier_address'] = 'Simulated OCR draft error'
            normalized['supplier_address'] = None
            issues.append({'code': 'UNSUPPORTED_EXTRACTION', 'field': 'supplier_address', 'message': 'Synthetic draft address has no original evidence. Read page 1.'})
        result = {'fields': normalized, 'raw_extraction': {'fields': raw, 'evidence': [], 'uncertainties': []},
                  'validation_issues': issues, 'arithmetic_check': arithmetic,
                  'pages': [{'page': 1, 'text': '\n'.join(lines), 'ocr_confidence': None, 'quality_rule': QUALITY_VERSION, 'warnings': []}],
                  'pipeline_version': PIPELINE, 'analysis_signature': ANALYSIS_SIGNATURE,
                  'model': os.environ.get('AP_LLM_MODEL'), 'model_base_url': os.environ.get('AP_LLM_BASE_URL'),
                  'analysis_source': 'synthetic_saved_analysis_no_model', 'is_mock': True}
        with closing(sqlite3.connect(root / 'invoices.sqlite3')) as db:
            db.execute('PRAGMA foreign_keys=ON')
            attempt = db.execute("INSERT INTO processing_attempts(invoice_id,status,result_json) VALUES(?,'processed',?)", (intake['invoice_id'], json.dumps(result))).lastrowid
            stored = db.execute('SELECT stored_name FROM invoices WHERE invoice_id=?', (intake['invoice_id'],)).fetchone()[0]
            db.commit()
        records.append({'case': label, 'invoice_id': intake['invoice_id'], 'attempt_id': attempt, 'source_id': source_id, 'stored_name': stored, 'is_mock_analysis': True})
    output.write_text(json.dumps(records, indent=2))
    print(output.read_text())


if __name__ == '__main__':
    main()
