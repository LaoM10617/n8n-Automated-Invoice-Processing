"""Configured approval boundary and immutable prior decisions."""
import json

import pytest

from backend.reviews import Reviews, approval_threshold
from backend.test_review_decisions import env, seed


@pytest.mark.parametrize('total,status', [('1499.99', 'approved'), ('1500.00', 'pending'), ('1500.01', 'pending')])
def test_configured_limit(env, monkeypatch, total, status):
    monkeypatch.setenv('AP_AUTO_APPROVAL_LIMIT_EUR', '1500.00')
    invoice_id, _ = seed(env, total, task=False)
    result = Reviews(env[1]).automatic(invoice_id, new_only=True)
    assert result['status'] == status
    assert result['policy_version'] == 'eur-gross-under-1500-v1'
    assert json.loads(result['policy_inputs_json'])['threshold'] == '1500.00'


def test_changed_limit_preserves_final_decision(env, monkeypatch):
    monkeypatch.setenv('AP_AUTO_APPROVAL_LIMIT_EUR', '1500.00')
    invoice_id, _ = seed(env, '1400.00', task=False)
    before = Reviews(env[1]).automatic(invoice_id, new_only=True)
    monkeypatch.setenv('AP_AUTO_APPROVAL_LIMIT_EUR', '1000.00')
    after = Reviews(env[1]).automatic(invoice_id, new_only=True)
    assert after['status'] == 'approved'
    assert after['policy_inputs_json'] == before['policy_inputs_json']
    assert after['event']['event_id'] == before['event']['event_id']


@pytest.mark.parametrize('value', ['0', '-1', 'NaN', 'Infinity', '1.234', 'abc', '1,500'])
def test_invalid_limit(value, monkeypatch):
    monkeypatch.setenv('AP_AUTO_APPROVAL_LIMIT_EUR', value)
    with pytest.raises(ValueError, match='AP_AUTO_APPROVAL_LIMIT_EUR'):
        approval_threshold()
