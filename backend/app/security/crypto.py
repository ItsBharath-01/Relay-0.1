import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Optional, Any, Dict
import jwt
from cryptography.fernet import Fernet

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

# Fernet encryption for credentials at rest
def _get_fernet() -> Fernet:
    """Instantiates a Fernet cipher with the configured key."""
    key = settings.ENCRYPTION_KEY.encode()
    return Fernet(key)

def encrypt_secret(secret_data: str) -> str:
    """Encrypts a plaintext secret (such as an OAuth refresh token) for safe storage."""
    if not secret_data:
        return ""
    f = _get_fernet()
    encrypted = f.encrypt(secret_data.encode())
    return encrypted.decode()

def decrypt_secret(encrypted_data: str) -> str:
    """Decrypts encrypted credentials."""
    if not encrypted_data:
        return ""
    f = _get_fernet()
    decrypted = f.decrypt(encrypted_data.encode())
    return decrypted.decode()

def hash_payload(payload: Any) -> str:
    """Computes a deterministic SHA-256 hash of an action payload for approval matching."""
    if isinstance(payload, str):
        payload_str = payload
    else:
        # Sort keys to ensure deterministic serialization
        payload_str = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(payload_str.encode("utf-8")).hexdigest()
