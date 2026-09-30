import pytest
import time
from app.api.connections import _generate_oauth_state, _verify_oauth_state
from app.connections.resolver import redact_sensitive_data

def test_oauth_state_generation_and_verification():
    user_id = "user_123456"
    services = "gmail,calendar"
    
    state = _generate_oauth_state(user_id, services)
    assert isinstance(state, str)
    assert user_id in state
    
    # Valid verification
    verified_services = _verify_oauth_state(state, user_id)
    assert verified_services == ["gmail", "calendar"]

def test_oauth_state_tampered_rejected():
    user_id = "user_123456"
    services = "gmail,calendar"
    state = _generate_oauth_state(user_id, services)
    
    # Tamper with user_id or signature
    tampered_state = state.replace("user_123456", "user_attacker")
    assert _verify_oauth_state(tampered_state, user_id) is None
    assert _verify_oauth_state(tampered_state, "user_attacker") is None

def test_oauth_state_wrong_user_rejected():
    user_id = "user_123456"
    services = "gmail"
    state = _generate_oauth_state(user_id, services)
    
    # Different user attempts to use this state
    assert _verify_oauth_state(state, "other_user_999") is None

def test_redact_sensitive_data():
    raw_log = "User logged in with Google Token ya29.a0AfH6SMD8... and Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjMifQ.abc"
    clean_log = redact_sensitive_data(raw_log)
    assert "ya29." not in clean_log
    assert "[REDACTED_GOOGLE_TOKEN]" in clean_log
    assert "[REDACTED_TOKEN]" in clean_log or "[REDACTED_JWT]" in clean_log

    data_dict = {
        "user": "alice",
        "access_token": "secret_access_token_value",
        "nested": {
            "password": "secret_password",
            "info": "public"
        }
    }
    clean_dict = redact_sensitive_data(data_dict)
    assert clean_dict["access_token"] == "[REDACTED]"
    assert clean_dict["nested"]["password"] == "[REDACTED]"
    assert clean_dict["nested"]["info"] == "public"
