"""Verify fixture artifacts only, not the AP application or n8n workflow."""
import hashlib
import json
import re
import subprocess
from decimal import Decimal
from pathlib import Path
import pdfplumber

OUT = Path(__file__).resolve().parent
QA = OUT / 'verification'
QA.mkdir(exist_ok=True)
data = json.loads((OUT / 'input.json').read_text(encoding='utf-8'))
entries = []
for case in data['cases']:
    file = OUT / case['file_name']
    record = data['records'][case['record_index']]
    with pdfplumber.open(file) as pdf:
        assert len(pdf.pages) == 1, file.name
        text = pdf.pages[0].extract_text()
        assert text and not pdf.pages[0].images, file.name
        assert all(0 <= c['x0'] < c['x1'] <= pdf.pages[0].width and 0 <= c['top'] < c['bottom'] <= pdf.pages[0].height for c in pdf.pages[0].chars)
    flat = ' '.join(text.split())
    for field in ('supplier_name', 'supplier_address', 'customer_name', 'customer_address', 'invoice_number', 'document_date', 'due_date', 'document_currency'):
        assert all(part in flat for part in record[field].split(', ')), (file.name, field)
    assert not re.search(r'synthetic|demo|fictional|no payment will be collected', flat, re.IGNORECASE)
    for field in ('document_total_net', 'document_total_tax', 'document_total_amount'):
        assert f'{record[field]:.2f}' in flat, (file.name, field)
    for item in record['line_items']:
        assert item['description'] in flat
        assert f"{item['unit_price']:.2f}" in flat and f"{item['amount']:.2f}" in flat
        assert Decimal(str(item['quantity'])) * Decimal(str(item['unit_price'])) == Decimal(str(item['amount']))
        assert Decimal(str(item['amount'])) * Decimal('0.19') == Decimal(str(item['tax_amount']))
    assert '19%' in flat
    assert not re.search(r'IBAN|BIC|Account No|Sort Code|@', text)
    net = sum(Decimal(str(i['amount'])) for i in record['line_items'])
    tax = sum(Decimal(str(i['tax_amount'])) for i in record['line_items'])
    assert net == Decimal(str(record['document_total_net']))
    assert tax == Decimal(str(record['document_total_tax']))
    delta = Decimal(str(record['document_total_amount'])) - net - tax
    assert delta == (Decimal('10.00') if case['record_index'] == 2 else Decimal('0.00'))
    (QA / (file.stem + '.txt')).write_text(text, encoding='utf-8')
    subprocess.run(['pdftoppm', '-scale-to', '1200', '-singlefile', '-png', str(file), str(QA / file.stem)], check=True)
    duplicate = case['record_index'] == 0 and file.name != '01_invoice_A.pdf'
    entries.append({
        'file_name': file.name,
        'sha256': hashlib.sha256(file.read_bytes()).hexdigest(),
        'input_record_index': case['record_index'],
        'expected_fields': record,
        'expected_validation': {
            'required_fields': 'pass', 'line_arithmetic': 'pass', 'vat_19_percent': 'pass',
            'net_plus_tax_equals_printed_total': 'fail' if delta else 'pass',
            'computed_total': f'{net + tax:.2f}', 'printed_total_difference': f'{delta:.2f}',
            'issues': ['TOTAL_MISMATCH'] if delta else [],
            'review': 'Manual review required; no automatic approval.'
        },
        'duplicate_relationship': {
            'business_duplicate_of': '01_invoice_A.pdf' if duplicate else None,
            'byte_identical_to': case.get('copy_from'),
            'file_hash_duplicate_expected': 'copy_from' in case,
            'source_upload_id': 'demo-upload-A-replay' if 'copy_from' in case or file.name == '01_invoice_A.pdf' else 'demo-upload-' + file.stem,
            'delivery_replay_instruction': 'For a repeated delivery test, reuse the original source identifier and attachment identifier. Identical PDF bytes alone do not establish repeated delivery. A new source identifier represents a new receipt.'
        },
        'actual_artifact_checks': {'text_extraction': 'pass', 'key_fields': 'pass', 'page_count': 1, 'text_within_page': 'pass', 'raster_images': 0}
    })
assert entries[0]['sha256'] == entries[2]['sha256']
assert entries[0]['sha256'] != entries[3]['sha256']
manifest = {
    'description': 'SYNTHETIC — DEMO ONLY. Fixed English AP invoice fixtures; EUR and test VAT of 19%.',
    'created_date': '2026-10-06',
    'source': {'project': 'synthetic-invoice-gen', 'local_path': 'D:/Projects/synthetic-invoice-gen', 'upstream': 'https://github.com/alamgirqazi/synthetic-invoice-gen', 'commit': 'bd20ae9b0a3fa4a6080ef883c7c734ffc87c2b18', 'license': 'MIT', 'license_copy': 'templates/LICENSE'},
    'generation': 'Fixed input.json -> adapted upstream Jinja2 templates -> headless Edge PDF. No LLM, random context, math correction, scan noise, or bank details. Native WeasyPrint was unavailable (missing GObject/Pango). Case 03 is a byte copy; case 04 uses exactly the same input record as case 01.',
    'scope': 'Artifact verification only. No AP ingestion, application validation, n8n execution, approval, export, or payment has been tested.',
    'cases': entries
}
(OUT / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print('PASS: 5 one-page text PDFs; fields and arithmetic checked; C retains 129.00; A/copy hashes equal; A/layout hashes differ.')
