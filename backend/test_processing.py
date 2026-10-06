"""Deterministic tests. Model test doubles do not establish extraction accuracy."""

from decimal import Decimal
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.document_text import ProcessingError, usable_text
from backend.extraction import grounded_fields
from backend.validation import duplicate_candidates, money, parse_date, validate


def fields(**changes):
    result = dict(supplier_name='Example Ltd', supplier_address='12 Example Road', supplier_tax_id=None,
                  invoice_number='X-001', invoice_date='2026-10-01', due_date='2026-10-15', currency='EUR',
                  net_amount='100.00', tax_amount='19.00', total_amount='119.00',
                  discount_amount=None, shipping_amount=None, has_adjustments=False)
    result.update(changes)
    return result


@pytest.mark.parametrize('raw,value', [('1.234,56', '1234.56'), ('1,234.56', '1234.56'), ('EUR 129.00', '129.00'), ('(12,50)', '-12.50')])
def test_money(raw, value):
    assert money(raw) == Decimal(value)


@pytest.mark.parametrize('raw', ['1,234', '12.34.56', 'NaN', '1,23.45'])
def test_uncertain_money(raw):
    with pytest.raises(ValueError):
        money(raw)


def test_dates():
    assert parse_date('19-Sep-2020') == '2020-09-19'
    assert parse_date('31.12.2026') == '2026-12-31'
    assert parse_date('12/31/2026') == '2026-12-31'
    with pytest.raises(ValueError):
        parse_date('03/04/2026')


def test_printed_mismatch_is_preserved():
    normalized, issues, check = validate(fields(total_amount='129.00'))
    assert normalized['total_amount'] == '129.00'
    assert check['computed_total'] == '119.00'
    assert check['difference'] == '10.00'
    assert 'TOTAL_MISMATCH' in {x['code'] for x in issues}


def test_adjustments_currency_and_missing_are_not_guessed():
    normalized, issues, check = validate(fields(currency='$', due_date=None, has_adjustments=True, discount_amount='3.00'))
    assert normalized['currency'] is None and normalized['due_date'] is None
    assert check['total_equation'] == 'not_evaluated'
    assert {'CURRENCY_UNRESOLVED', 'TOTAL_EQUATION_REVIEW', 'MISSING_FIELD'} <= {x['code'] for x in issues}


def test_old_due_date_and_unknown_supplier():
    _, issues, _ = validate(fields(due_date='2012-03-26'))
    assert 'DUE_BEFORE_INVOICE' in {x['code'] for x in issues}
    assert duplicate_candidates(fields(supplier_address=None), [('other', fields())]) == ('not_evaluable', [])
    assert duplicate_candidates(fields(invoice_number='X-002'), [('other', fields())]) == ('no_candidates', [])
    status, candidates = duplicate_candidates(fields(), [('other', fields())])
    assert status == 'candidate' and candidates[0]['invoice_id'] == 'other'
    status, _ = duplicate_candidates(fields(supplier_address='12 Example Road, City', invoice_number='X- 001'), [('other', fields(supplier_address='12 Example Road\nCity'))])
    assert status == 'candidate'


def test_evidence_and_native_quality():
    draft = {'fields': {'total_amount': '129.00'}, 'evidence': [{'field': 'total_amount', 'page': 1, 'quote': 'Total 119.00'}]}
    grounded, issues = grounded_fields(draft, [{'page': 1, 'text': 'Total 119.00'}])
    assert grounded['total_amount'] is None and issues[0]['code'] == 'UNSUPPORTED_EXTRACTION'
    assert not usable_text('Header 123')
    assert not usable_text(('broken \ufffd invoice data ' * 20))


def test_normal_fixture_arithmetic():
    data = json.loads((Path(__file__).resolve().parents[1] / 'test_data/ap_invoices/input.json').read_text())
    for record in data['records']:
        _, issues, _ = validate(fields(net_amount=str(record['document_total_net']), tax_amount=str(record['document_total_tax']), total_amount=str(record['document_total_amount'])))
        mismatch = any(i['code'] == 'TOTAL_MISMATCH' for i in issues)
        assert mismatch == record['invoice_number'].startswith('INV-C')


def test_processing_persistence_replay_and_failure(tmp_path, monkeypatch):
    import backend.app as module
    raw = fields()
    text = '\n'.join(v for v in raw.values() if isinstance(v, str))
    pages = [{'page': 1, 'method': 'native_text', 'text': text, 'ocr_confidence': None}]
    monkeypatch.setattr(module, 'read_pages', lambda *_: pages)
    calls = []
    def extractor(_):
        calls.append(1)
        return {'fields': raw, 'evidence': [{'field': k, 'page': 1, 'quote': v} for k, v in raw.items() if isinstance(v, str)], 'uncertainties': []}
    monkeypatch.setattr(module, 'extract_fields', extractor)
    original = Path(__file__).resolve().parents[1] / 'test_data/first_round/text_pdf/01_invoice_A.pdf'
    with TestClient(create_app(tmp_path)) as client:
        r = client.post('/api/ap/intakes', data={'source_type':'upload','source_namespace':'test','source_id':'one','attachment_id':'0'}, files={'file':('a.pdf',original.read_bytes())})
        invoice_id = r.json()['invoice_id']
        url = f'/api/ap/invoices/{invoice_id}/process'
        first = client.post(url)
        assert first.status_code == 200 and first.json()['processing_status'] == 'processed'
        assert client.post(url).json()['processing_attempt_id'] == first.json()['processing_attempt_id']
        assert len(calls) == 1
        assert first.json()['review_status'] == 'not_created'
    with TestClient(create_app(tmp_path)) as client:
        assert client.get(f'/api/ap/invoices/{invoice_id}').json()['extracted_fields']['total_amount'] == '119.00'


def test_failure_retains_ocr_and_retry(tmp_path, monkeypatch):
    import backend.app as module
    pages = [{'page': 1, 'method': 'tesseract', 'text': 'OCR evidence preserved', 'ocr_confidence': 90}]
    monkeypatch.setattr(module, 'read_pages', lambda *_: pages)
    def unavailable(_):
        raise ProcessingError('MODEL_NOT_CONFIGURED', 'Model configuration missing')
    monkeypatch.setattr(module, 'extract_fields', unavailable)
    original = Path(__file__).resolve().parents[1] / 'test_data/first_round/text_pdf/01_invoice_A.pdf'
    with TestClient(create_app(tmp_path)) as client:
        r = client.post('/api/ap/intakes', data={'source_type':'upload','source_namespace':'test','source_id':'one','attachment_id':'0'}, files={'file':('a.pdf',original.read_bytes())})
        url = '/api/ap/invoices/' + r.json()['invoice_id']
        assert client.post(url+'/process').status_code == 503
        state = client.get(url).json()
        assert state['processing_status'] == 'failed'
        assert state['processing_result']['pages'] == pages
        assert state['extracted_fields'] is None and state['validation_issues'] is None
        first_attempt = state['processing_attempt_id']
        assert client.post(url+'/process').status_code == 503
        assert client.get(url).json()['processing_attempt_id'] > first_attempt


def test_multiline_address_evidence_preserves_column_layout():
    from backend.extraction import grounded_fields
    pages = [{'page': 1, 'text': '12 Seller Road    44 Buyer Street\nBerlin    Paris'}]
    raw = {'fields': {'supplier_address': '12 Seller Road\nBerlin'},
           'evidence': [{'field': 'supplier_address', 'page': 1, 'quote': '12 Seller Road Berlin'}]}
    fields, issues = grounded_fields(raw, pages)
    assert fields['supplier_address'] == '12 Seller Road\nBerlin'
    assert not issues
    raw['fields']['supplier_address'] = '12 Seller Road\nLondon'
    raw['evidence'][0]['quote'] = '12 Seller Road London'
    fields, issues = grounded_fields(raw, pages)
    assert fields['supplier_address'] is None
    assert issues[0]['code'] == 'UNSUPPORTED_EXTRACTION'


def test_spaced_currency_evidence():
    from backend.extraction import grounded_fields
    raw = {'fields': {'currency': 'EUR'}, 'evidence': [{'field': 'currency', 'page': 1, 'quote': 'E U R'}]}
    assert grounded_fields(raw, [{'page': 1, 'text': 'E U R SALES INVOICE'}])[0]['currency'] == 'EUR'
    assert grounded_fields(raw, [{'page': 1, 'text': 'USD SALES INVOICE'}])[0]['currency'] is None


def test_model_cooldown_without_network(monkeypatch):
    import backend.extraction as module
    monkeypatch.setattr(module, '_next_request_at', 0)
    monkeypatch.setenv('AP_LLM_MIN_INTERVAL_SECONDS', '60')
    clock = [100.0]
    monkeypatch.setattr(module.time, 'monotonic', lambda: clock[0])
    module.reserve_model_request()
    with pytest.raises(ProcessingError) as error:
        module.reserve_model_request()
    assert error.value.code == 'MODEL_LOCAL_RATE_LIMIT'
    clock[0] = 160.0
    module.reserve_model_request()


def test_provider_429_is_not_retried(monkeypatch):
    import backend.extraction as module
    import urllib.error
    monkeypatch.setenv('AP_LLM_BASE_URL', 'https://example.invalid/v1')
    monkeypatch.setenv('AP_LLM_MODEL', 'test-model')
    monkeypatch.setenv('AP_LLM_API_KEY', 'test-key')
    monkeypatch.setattr(module, 'reserve_model_request', lambda: None)
    calls = []
    def limited(*args, **kwargs):
        calls.append(1)
        raise urllib.error.HTTPError('https://example.invalid', 429, 'Limited', {}, None)
    monkeypatch.setattr(module.urllib.request, 'urlopen', limited)
    with pytest.raises(ProcessingError) as error:
        module.extract_fields([{'page': 1, 'text': 'test invoice'}])
    assert error.value.code == 'MODEL_RATE_LIMITED'
    assert len(calls) == 1


def test_ocr_tsv_quote_is_literal_not_csv_escape(monkeypatch):
    import backend.document_text as module
    tsv = 'level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n'
    tsv += '5\t1\t1\t1\t1\t1\t10\t20\t5\t10\t80\t"\n'
    tsv += '5\t1\t1\t1\t2\t1\t10\t40\t30\t10\t95\tSubtotal\n'
    monkeypatch.setattr(module, 'run_tool', lambda _: tsv.encode())
    text, confidence, tokens = module.ocr_image(Path('unused.png'))
    assert text == '"\nSubtotal'
    assert len(tokens) == 2
    assert confidence == 87.5
