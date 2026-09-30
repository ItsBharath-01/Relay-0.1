import pytest
from app.risk.classifier import risk_classifier
from app.models.entities import UserPreference
from app.security.crypto import hash_payload

def test_risk_classifier_critical_no_bypass():
    """Verify that financial/critical actions always require approval regardless of preferences."""
    prefs = UserPreference(ask_payments=False, ask_purchases=False)
    params = {"amount": 100, "currency": "USD", "action": "pay"}
    
    assessment = risk_classifier.assess_action(
        capability_id="api_request",
        action="pay_stripe_invoice",
        params=params,
        preferences=prefs
    )
    assert assessment.risk_level == "critical"
    assert assessment.requires_approval is True
    assert assessment.payload_hash == hash_payload(params)

def test_risk_classifier_browser_interaction():
    """Verify browser navigation with interaction/form submission is high risk and requires approval."""
    params = {"url": "https://example.com/login", "action": "submit_form", "credentials": "..."}
    assessment = risk_classifier.assess_action(
        capability_id="browser_fill",
        action="submit",
        params=params
    )
    assert assessment.risk_level == "high"
    assert assessment.requires_approval is True

def test_risk_classifier_browser_pure_navigate():
    """Verify read-only browser navigation is medium risk."""
    params = {"url": "https://example.com/docs"}
    assessment = risk_classifier.assess_action(
        capability_id="browser_navigate",
        action="navigate",
        params=params
    )
    assert assessment.risk_level == "medium"
    assert assessment.requires_approval is False

def test_risk_classifier_deletion():
    """Verify deletion actions are high risk."""
    params = {"event_id": "cal_12345"}
    assessment = risk_classifier.assess_action(
        capability_id="calendar_delete",
        action="delete_event",
        params=params
    )
    assert assessment.risk_level == "high"
    assert assessment.requires_approval is True
