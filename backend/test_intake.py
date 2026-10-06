import io
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from backend.app import create_app

FIXTURES = Path(__file__).resolve().parents[1] / 'test_data/first_round'
A = FIXTURES / 'text_pdf/01_invoice_A.pdf'
B = FIXTURES / 'text_pdf/02_invoice_B.pdf'


def send(client, data=None, source='upload-A', name='invoice.pdf'):
    return client.post('/api/ap/intakes', files={'file': (name, data if data is not None else A.read_bytes(), 'application/octet-stream')},
                       data={'source_type': 'upload', 'source_namespace': 'test', 'source_id': source, 'attachment_id': '0'})


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path)) as test_client:
        yield test_client


@pytest.mark.parametrize('path', sorted(FIXTURES.rglob('*.pdf')), ids=lambda p: p.name)
def test_first_round_files(client, path):
    response = send(client, path.read_bytes())
    assert response.status_code == 201
    item = response.json()
    assert item['inspection']['ocr_required'] == (path.parent.name == 'ocr')
    assert client.get(item['original_ref']).content == path.read_bytes()
    assert item['review_url'] is None


def test_replay_new_receipt_and_conflict(client):
    first = send(client).json()
    replay = send(client)
    assert replay.status_code == 200
    assert replay.json()['receipt_id'] == first['receipt_id']
    second = send(client, source='new-email').json()
    assert second['invoice_id'] == first['invoice_id']
    assert second['receipt_id'] != first['receipt_id']
    assert second['content_duplicate'] and not second['delivery_duplicate']
    assert send(client, B.read_bytes()).status_code == 409
    record = client.get(f"/api/ap/invoices/{first['invoice_id']}").json()
    assert len(record['receipts']) == 2


def test_different_layout_is_not_automatically_merged(client):
    first = send(client).json()
    other = send(client, (FIXTURES / 'text_pdf/04_invoice_A_business_duplicate.pdf').read_bytes(), source='other').json()
    assert first['invoice_id'] != other['invoice_id']
    assert other['business_duplicate_status'] == 'not_checked'


@pytest.mark.parametrize('fmt', ['PNG', 'JPEG'])
def test_images(client, fmt):
    output = io.BytesIO()
    Image.new('RGB', (20, 20), 'white').save(output, format=fmt)
    result = send(client, output.getvalue(), name='../../untrusted.pdf')
    assert result.status_code == 201
    assert result.json()['inspection']['ocr_required']
    assert client.get(result.json()['original_ref']).content == output.getvalue()


def test_invalid_files_and_unknown_id(client):
    assert send(client, b'').status_code == 413
    assert send(client, b'not a PDF').status_code == 422
    assert send(client, b'%PDF-broken').status_code == 422
    assert send(client, b'x' * (20 * 1024 * 1024 + 1)).status_code == 413
    assert client.get('/api/ap/invoices/missing').status_code == 404


def test_restart_and_concurrent_replay(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: send(client), range(4)))
        assert sorted(r.status_code for r in results) == [200, 200, 200, 201]
        invoice_id = results[0].json()['invoice_id']
    with TestClient(create_app(tmp_path)) as restarted:
        record = restarted.get(f'/api/ap/invoices/{invoice_id}').json()
        assert len(record['receipts']) == 1
        assert restarted.get(record['original_ref']).content == A.read_bytes()
