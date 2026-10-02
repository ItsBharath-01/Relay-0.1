import time
import hmac
import hashlib
import pytest
from app.api.connections import _generate_oauth_state, _verify_oauth_state
from app.core.config import settings

@pytest.mark.security
def test_oauth_state_valid():
    """Verify that a correctly generated state is validated and returns requested services."""
    user_id = "user_12345"
    services = "gmail,calendar"
    state = _generate_oauth_state(user_id, services)
    
    verified = _verify_oauth_state(state, user_id)
    assert verified == ["gmail", "calendar"]


@pytest.mark.security
def test_oauth_state_tampered_signature_rejected():
    """Verify that tampering with state payload or signature fails validation."""
    user_id = "user_12345"
    services = "gmail,calendar"
    state = _generate_oauth_state(user_id, services)
    
    # Tamper with the user ID in payload
    parts = state.split(":")
    tampered_state = f"attacker_user:{parts[1]}:{parts[2]}:{parts[3]}"
    assert _verify_oauth_state(tampered_state, "attacker_user") is None

    # Tamper with signature
    tampered_sig_state = f"{parts[0]}:{parts[1]}:{parts[2]}:badsignature123"
    assert _verify_oauth_state(tampered_sig_state, user_id) is None


@pytest.mark.security
def test_oauth_state_cross_user_binding_rejected():
    """Verify that a state generated for User A cannot be redeemed by User B."""
    user_a = "user_alice"
    user_b = "user_bob"
    state = _generate_oauth_state(user_a, "gmail")

    # Bob attempts to pass Alice's state
    assert _verify_oauth_state(state, user_b) is None


@pytest.mark.security
def test_oauth_state_expiry_rejected():
    """Verify that an expired state (> 10 minutes) is rejected."""
    user_id = "user_12345"
    services = "gmail"
    old_ts = str(int(time.time()) - 601)  # 601 seconds ago
    payload = f"{user_id}:{services}:{old_ts}"
    signature = hmac.new(settings.SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()
    expired_state = f"{payload}:{signature}"

    assert _verify_oauth_state(expired_state, user_id) is None
