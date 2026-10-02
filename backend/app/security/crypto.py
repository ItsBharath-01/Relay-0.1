import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Optional, Any, Dict, List
import jwt
from cryptography.fernet import Fernet, MultiFernet

from app.core.config import settings

import bcrypt


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain password against the hashed password using bcrypt."""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8")[:72],
            hashed_password.encode("utf-8")
        )
    except Exception:
        return False


def get_password_hash(password: str) -> str:
    """Hashes a password with bcrypt directly."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8")[:72], salt).decode("utf-8")


# JWT creation and decoding
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Creates a signed JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> Optional[dict]:
    """Decodes and validates a JWT token."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except jwt.PyJWTError:
        return None


# Fernet / MultiFernet encryption for credentials at rest
def _get_fernet() -> MultiFernet:
    """
    Instantiates MultiFernet supporting key rotation with comma-separated keys.
    The first key is used for encryption; all keys are tried in order for decryption.
    """
    raw_keys = settings.ENCRYPTION_KEY or ""
    keys = [k.strip() for k in raw_keys.split(",") if k.strip()]
    if not keys:
        raise RuntimeError("No encryption keys configured.")
    fernets = [Fernet(k.encode("utf-8")) for k in keys]
    return MultiFernet(fernets)


def encrypt_secret(secret_data: str) -> str:
    """Encrypts a plaintext secret (such as an OAuth refresh token or API key) for safe storage."""
    if not secret_data:
        return ""
    f = _get_fernet()
    encrypted = f.encrypt(secret_data.encode("utf-8"))
    return encrypted.decode("utf-8")


def decrypt_secret(encrypted_data: Any) -> str:
    """Decrypts encrypted credentials, trying primary then rotated secondary keys."""
    if not encrypted_data:
        return ""
    try:
        f = _get_fernet()
        data_bytes = encrypted_data if isinstance(encrypted_data, bytes) else str(encrypted_data).encode("utf-8")
        decrypted = f.decrypt(data_bytes)
        return decrypted.decode("utf-8")
    except Exception:
        # If decryption fails (e.g. data is unencrypted raw string or encrypted with old lost key)
        return str(encrypted_data)


def hash_payload(payload: Any) -> str:
    """Computes a deterministic SHA-256 hash of an action payload for approval matching."""
    if isinstance(payload, str):
        payload_str = payload
    else:
        # Sort keys to ensure deterministic serialization
        payload_str = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(payload_str.encode("utf-8")).hexdigest()


# Known sensitive token patterns for sanitization
SENSITIVE_PATTERNS = [
    # Google OAuth token
    (re.compile(r"ya29\.[A-Za-z0-9_\-\.]+"), "[REDACTED_GOOGLE_TOKEN]"),
    # GitHub Personal Access Token (classic & fine-grained)
    (re.compile(r"github_pat_[A-Za-z0-9_]+"), "[REDACTED_GITHUB_PAT]"),
    (re.compile(r"ghp_[A-Za-z0-9_]{10,}"), "[REDACTED_GITHUB_TOKEN]"),
    (re.compile(r"gho_[A-Za-z0-9_]{10,}"), "[REDACTED_GITHUB_OAUTH]"),
    (re.compile(r"ghu_[A-Za-z0-9_]{10,}"), "[REDACTED_GITHUB_USER]"),
    (re.compile(r"ghs_[A-Za-z0-9_]{10,}"), "[REDACTED_GITHUB_SERVER]"),
    (re.compile(r"ghr_[A-Za-z0-9_]{10,}"), "[REDACTED_GITHUB_REFRESH]"),
    # Slack tokens (bot, user, app)
    (re.compile(r"xox[baprs]-[A-Za-z0-9_\-]+"), "[REDACTED_SLACK_TOKEN]"),
    # Google API Key
    (re.compile(r"AIza[0-9A-Za-z_\-]{10,}"), "[REDACTED_GOOGLE_API_KEY]"),
    # OpenAI / generic sk- keys
    (re.compile(r"sk-(?:[A-Za-z0-9_\-]{8,})"), "[REDACTED_API_KEY]"),
    # Bearer tokens in headers or logs
    (re.compile(r"Bearer\s+[A-Za-z0-9_\-\.]+"), "Bearer [REDACTED_TOKEN]"),
    # JWT tokens
    (re.compile(r"eyJ[A-Za-z0-9_\-]+\.eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+"), "[REDACTED_JWT]"),
    # Fernet ciphertext pattern: gAAAAA...
    (re.compile(r"gAAAAA[A-Za-z0-9_\-=]{50,}"), "[REDACTED_FERNET_CIPHERTEXT]"),
]

SENSITIVE_KEYS = {
    "token", "secret", "password", "credential", "refresh_token",
    "access_token", "api_key", "authorization", "client_secret",
    "private_key", "proxy_authorization"
}


def redact_sensitive_data(data: Any) -> Any:
    """
    Central redaction utility that removes secrets, bearer tokens, OAuth refresh tokens,
    API keys, Fernet ciphertext, and passwords from logging, exceptions, and event payloads.
    """
    if isinstance(data, str):
        redacted = data
        for pattern, replacement in SENSITIVE_PATTERNS:
            redacted = pattern.sub(replacement, redacted)
        return redacted
    elif isinstance(data, dict):
        clean = {}
        for k, v in data.items():
            k_lower = str(k).lower()
            if any(s in k_lower for s in SENSITIVE_KEYS):
                clean[k] = "[REDACTED]"
            else:
                clean[k] = redact_sensitive_data(v)
        return clean
    elif isinstance(data, list):
        return [redact_sensitive_data(item) for item in data]
    return data
