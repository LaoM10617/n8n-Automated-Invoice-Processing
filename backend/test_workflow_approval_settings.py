"""Workflow ceiling is authorized, persisted and isolated from later config changes."""
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.test_intake_stages import setup
from backend.test_processing import fields
from backend.test_review import FIXTURE


def upload(client, limit, headers=None):
    source = dict(source_type='upload', source_namespace='settings-test', source_id='fixture',
                  attachment_id='0', auto_approval_limit_eur=limit)
    return client.post('/api/ap/stages/archive', headers=headers or {},
                       data={'metadata': json.dumps(source)},
                       files={'file': ('invoice.pdf', FIXTURE.read_bytes(), 'application/pdf')})


@pytest.mark.parametrize('limit,status', [('100.00', 'pending'), ('200.00', 'approved')])
def test_stage_uses_saved_workflow_limit_after_restart(tmp_path, monkeypatch, limit, status):
    import backend.test_intake_stages as helpers
    monkeypatch.setattr(helpers, 'fields', lambda **_: fields(total_amount='119.00'))
    setup(monkeypatch)
    monkeypatch.setenv('AP_REVIEW_EVENT_TOKEN', 'isolated-test-token')
    monkeypatch.setenv('AP_AUTO_APPROVAL_LIMIT_EUR', '1500.00')
    with TestClient(create_app(tmp_path), base_url="http://localhost") as client:
        response = upload(client, limit, {'X-AP-Event-Token': 'isolated-test-token'})
        assert response.status_code == 200
        run = response.json()
        assert run['source']['auto_approval_limit_eur'] == limit
        assert client.post(f"/api/ap/stages/{run['run_id']}/analyze").status_code == 200
    monkeypatch.setenv('AP_AUTO_APPROVAL_LIMIT_EUR', '50.00')
    with TestClient(create_app(tmp_path), base_url="http://localhost") as client:
        response = client.post(f"/api/ap/stages/{run['run_id']}/validate-policy", headers={'X-AP-Review': '1'})
        assert response.status_code == 200
        assert response.json()['review_status'] == status
        review = client.get(f"/api/ap/invoices/{run['invoice_id']}/review").json()
        assert json.loads(review['policy_inputs_json'])['threshold'] == limit


def test_override_requires_auth_and_invalid_value_leaves_no_run(tmp_path, monkeypatch):
    setup(monkeypatch)
    monkeypatch.setenv('AP_REVIEW_EVENT_TOKEN', 'isolated-test-token')
    with TestClient(create_app(tmp_path), base_url="http://localhost") as client:
        assert upload(client, '5000.00').status_code == 403
        for value in ['0', '-1', 'NaN', '1.234', 'abc']:
            assert upload(client, value, {'X-AP-Event-Token': 'isolated-test-token'}).status_code == 422
        with sqlite3.connect(tmp_path / 'invoices.sqlite3') as db:
            assert db.execute('SELECT COUNT(*) FROM intake_runs').fetchone()[0] == 0
