#!/usr/bin/env python3
"""
scripts/generate_secrets.py

Generates cryptographically strong random secrets for Relay 0.2:
- SECRET_KEY (hex-encoded 32-byte secret for JWT signing)
- ENCRYPTION_KEY (URL-safe base64 Fernet key for credential encryption at rest)

Usage:
    python scripts/generate_secrets.py
"""

import secrets
from cryptography.fernet import Fernet


def main():
    secret_key = secrets.token_hex(32)
    fernet_key = Fernet.generate_key().decode("utf-8")

    print("=" * 60)
    print("RELAY 0.2 GENERATED SECRETS (Store securely in .env)")
    print("=" * 60)
    print(f"SECRET_KEY={secret_key}")
    print(f"ENCRYPTION_KEY={fernet_key}")
    print("=" * 60)
    print("WARNING: Keep these values confidential. Never commit .env to version control.")


if __name__ == "__main__":
    main()
