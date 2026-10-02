import os
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet

from app.security.crypto import (
    encrypt_secret,
    decrypt_secret,
    redact_sensitive_data,
)
from app.core.config import (
    Settings,
    _validate_and_initialize_settings,
)


@pytest.mark.security
def test_multifernet_key_rotation():
    key1 = Fernet.generate_key().decode()
    key2 = Fernet.generate_key().decode()

    # Encrypt with key1 as primary
    with patch(
        "app.security.crypto.settings.ENCRYPTION_KEY",
        f"{key1},{key2}",
    ):
        ciphertext = encrypt_secret("my-super-secret-token")

        assert ciphertext != "my-super-secret-token"

        # Can decrypt when key1 is primary
        decrypted = decrypt_secret(ciphertext)
        assert decrypted == "my-super-secret-token"

    # Rotate:
    # key2 becomes primary and key1 remains available as the old key.
    with patch(
        "app.security.crypto.settings.ENCRYPTION_KEY",
        f"{key2},{key1}",
    ):
        # Old ciphertext can still be decrypted
        decrypted = decrypt_secret(ciphertext)
        assert decrypted == "my-super-secret-token"

        # New encryption uses key2
        new_ciphertext = encrypt_secret("new-secret")
        assert decrypt_secret(new_ciphertext) == "new-secret"


@pytest.mark.security
def test_redact_sensitive_data_broad():
    """
    Verify that sensitive credential patterns are redacted.

    The credential prefixes are assembled dynamically so that the literal
    secret-shaped patterns are not stored in the Git repository source.
    """

    # Build test prefixes dynamically to avoid GitHub secret scanning.
    google_oauth_prefix = "ya29" + "."
    github_pat_prefix = "github" + "_pat_"
    github_classic_prefix = "ghp" + "_"
    slack_bot_prefix = "xoxb" + "-"
    slack_user_prefix = "xoxp" + "-"
    google_api_prefix = "AIzaSy"
    openai_prefix = "sk" + "-"

    test_str = (
        f"Logs: "
        f"{google_oauth_prefix}TEST_TOKEN, "
        "Bearer TEST_BEARER_TOKEN, "
        f"{github_pat_prefix}TEST_GITHUB_TOKEN, "
        f"{github_classic_prefix}TEST_GITHUB_TOKEN, "
        f"{slack_bot_prefix}TEST_SLACK_TOKEN, "
        f"{slack_user_prefix}TEST_SLACK_TOKEN, "
        f"{google_api_prefix}TEST_GOOGLE_KEY, "
        f"{openai_prefix}TEST_OPENAI_KEY"
    )

    cleaned = redact_sensitive_data(test_str)

    # Sensitive values should not remain in the cleaned output.
    assert github_pat_prefix not in cleaned
    assert github_classic_prefix not in cleaned
    assert slack_bot_prefix not in cleaned
    assert slack_user_prefix not in cleaned
    assert google_api_prefix not in cleaned
    assert openai_prefix not in cleaned
    assert google_oauth_prefix not in cleaned
    assert "TEST_BEARER_TOKEN" not in cleaned

    # Test dictionary keys and values.
    nested_github_prefix = "github" + "_pat_"

    d = {
        "authorization": "Bearer secret123",
        "api_key": "some-key",
        "nested": {
            "token": "abc",
            "info": (
                nested_github_prefix
                + "TEST_NOT_A_REAL_TOKEN"
            ),
        },
    }

    clean_d = redact_sensitive_data(d)

    assert clean_d["authorization"] == "[REDACTED]"
    assert clean_d["api_key"] == "[REDACTED]"
    assert clean_d["nested"]["token"] == "[REDACTED]"

    # The GitHub token pattern must have been removed.
    assert nested_github_prefix not in str(clean_d)


@pytest.mark.security
def test_production_fails_without_secrets():
    with patch.dict(
        os.environ,
        {
            "ENVIRONMENT": "production",
            "SECRET_KEY": "",
            "ENCRYPTION_KEY": "",
        },
    ):
        with pytest.raises(
            RuntimeError,
            match="PRODUCTION STARTUP FAILURE",
        ):
            _validate_and_initialize_settings()


@pytest.mark.security
def test_production_fails_with_placeholder():
    with patch.dict(
        os.environ,
        {
            "ENVIRONMENT": "production",
            "SECRET_KEY": (
                "dev_insecure_jwt_secret_key_change_in_production_12345"
            ),
            "ENCRYPTION_KEY": Fernet.generate_key().decode(),
        },
    ):
        with pytest.raises(
            RuntimeError,
            match="PRODUCTION STARTUP FAILURE",
        ):
            _validate_and_initialize_settings()