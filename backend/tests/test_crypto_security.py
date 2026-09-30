import pytest
from app.security.crypto import hash_payload, verify_password, get_password_hash, create_access_token, decode_access_token

def test_hash_payload_deterministic():
    payload_a = {"query": "AI research", "limit": 10, "nested": {"a": 1, "b": 2}}
    payload_b = {"nested": {"b": 2, "a": 1}, "limit": 10, "query": "AI research"}
    
    assert hash_payload(payload_a) == hash_payload(payload_b)

def test_password_hashing_and_verification():
    raw_pw = "SuperSecureSecret123!"
    hashed = get_password_hash(raw_pw)
    assert verify_password(raw_pw, hashed) is True
    assert verify_password("WrongPassword", hashed) is False

def test_jwt_token_lifecycle():
    user_id = "test-user-uuid-123"
    token = create_access_token({"sub": user_id})
    payload = decode_access_token(token)
    assert payload is not None
    assert payload.get("sub") == user_id
