import pytest
import os
from unittest.mock import patch
from cryptography.fernet import Fernet
from app.security.crypto import encrypt_secret, decrypt_secret, redact_sensitive_data
from app.core.config import Settings, _validate_and_initialize_settings

@pytest.mark.security
def test_multifernet_key_rotation():
    key1 = Fernet.generate_key().decode()
    key2 = Fernet.generate_key().decode()
    
    # Encrypt with key1 as primary
    with patch("app.security.crypto.settings.ENCRYPTION_KEY", f"{key1},{key2}"):
        ciphertext = encrypt_secret("my-super-secret-token")
        assert ciphertext != "my-super-secret-token"
        
        # Can decrypt when key1 is primary
        decrypted = decrypt_secret(ciphertext)
        assert decrypted == "my-super-secret-token"

    # Now rotate: key2 is primary, key1 is secondary (old)
    with patch("app.security.crypto.settings.ENCRYPTION_KEY", f"{key2},{key1}"):
        # Can still decrypt old ciphertext encrypted with key1
        decrypted = decrypt_secret(ciphertext)
        assert decrypted == "my-super-secret-token"
        
        # New encryption uses key2
        new_ciphertext = encrypt_secret("new-secret")
        assert decrypt_secret(new_ciphertext) == "new-secret"


@pytest.mark.security
def test_redact_sensitive_data_broad():
    # Test tokens: ya29, Bearer, JWT, github, slack, AIza, sk-
    test_str = (
        "Logs: ya29.a0AfH6SMA, Bearer my_raw_token_xyz, "
        + "github" + "_pat_" + "TEST_MOCK_TOKEN, "
        + "ghp" + "_" + "1234567890abcdef1234567890abcdef123456, "
        + "xoxb-1234-5678-abcdef, xoxp-9876-5432-fedcba, "
        + "AIzaSyD-example123456789, sk-live-abcdef123456"
    )
    cleaned = redact_sensitive_data(test_str)
    assert ("github" + "_pat_") not in cleaned
    assert ("ghp" + "_") not in cleaned
    assert "xoxb-" not in cleaned
    assert "xoxp-" not in cleaned
    assert "AIzaSy" not in cleaned
    assert "sk-" not in cleaned
    assert "ya29." not in cleaned
    assert "my_raw_token_xyz" not in cleaned

    # Test dict keys and values
    d = {
        "authorization": "Bearer secret123",
        "api_key": "some-key",
        "nested": {"token": "abc", "info": ("github" + "_pat_" + "TEST_MOCK_TOKEN_2")}
    }
    clean_d = redact_sensitive_data(d)
    assert clean_d["authorization"] == "[REDACTED]"
    assert clean_d["api_key"] == "[REDACTED]"
    assert clean_d["nested"]["token"] == "[REDACTED]"
    assert ("github" + "_pat_") not in str(clean_d)


@pytest.mark.security
def test_production_fails_without_secrets():
    with patch.dict(os.environ, {"ENVIRONMENT": "production", "SECRET_KEY": "", "ENCRYPTION_KEY": ""}):
        with pytest.raises(RuntimeError, match="PRODUCTION STARTUP FAILURE"):
            _validate_and_initialize_settings()


@pytest.mark.security
def test_production_fails_with_placeholder():
    with patch.dict(os.environ, {
        "ENVIRONMENT": "production",
        "SECRET_KEY": "dev_insecure_jwt_secret_key_change_in_production_12345",
        "ENCRYPTION_KEY": Fernet.generate_key().decode()
    }):
        with pytest.raises(RuntimeError, match="PRODUCTION STARTUP FAILURE"):
            _validate_and_initialize_settings()
