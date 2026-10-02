import json
import logging
import os
import secrets
from pathlib import Path
from typing import Optional, List, Any
from cryptography.fernet import Fernet
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator

logger = logging.getLogger(__name__)

KNOWN_PLACEHOLDERS = {
    "relay_secret_key_development_only_replace_in_prod_a982f1b4908c",
    "change_this_to_a_secure_random_jwt_secret_in_production_32b",
    "replace_with_generated_hex32_jwt_secret_key_in_production",
    "replace_with_generated_fernet_base64_encryption_key_here=",
    "dev_insecure_jwt_secret_key_change_in_production_12345",
    "change_this_secret",
    "replace_in_production",
    "secret",
    "password",
    "default",
    "W03_3n9D3vE10pm3ntK3yF0rR31ay02App11cat1onS3cur1ty=",
    "_JHCRHGuTE5O9qv1DQ8raHDpsy9iHW7xX5_QK5idYUA=",
}


def _get_dev_secrets_file() -> Path:
    # Anchor dev secrets to backend/.dev-secrets.json
    base_dir = Path(__file__).resolve().parent.parent.parent
    return base_dir / ".dev-secrets.json"


def _load_or_create_dev_secrets() -> dict:
    fpath = _get_dev_secrets_file()
    if fpath.exists():
        try:
            data = json.loads(fpath.read_text(encoding="utf-8"))
            if "SECRET_KEY" in data and "ENCRYPTION_KEY" in data:
                return data
        except Exception:
            pass

    # Generate random ephemeral secrets for dev
    sec = secrets.token_hex(32)
    enc = Fernet.generate_key().decode("utf-8")
    data = {"SECRET_KEY": sec, "ENCRYPTION_KEY": enc}
    try:
        fpath.write_text(json.dumps(data, indent=2), encoding="utf-8")
        logger.warning(
            f"LOUD WARNING: Generating ephemeral dev secrets in {fpath}. "
            "Never use in production."
        )
    except Exception as e:
        logger.warning(f"Could not persist dev secrets: {e}")
    return data


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Environment mode
    ENVIRONMENT: str = Field(
        default="production",
        description="development | test | production"
    )

    # App
    PROJECT_NAME: str = "Relay"
    API_V1_STR: str = "/api/v1"
    DEBUG: bool = False
    EXECUTION_TIMEOUT_SECONDS: int = 1800  # P0-3: 30 minutes max wall-clock execution

    # Database
    DATABASE_URL: str = Field(
        default="sqlite+aiosqlite:///./relay.db",
        description="Async database connection string"
    )

    # Auth & Security
    SECRET_KEY: Optional[str] = Field(
        default=None,
        description="JWT signing key"
    )
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60  # P1-5: 60 minutes
    ENCRYPTION_KEY: Optional[str] = Field(
        default=None,
        description="Comma-separated Fernet key(s) for credential encryption at rest"
    )

    # LLM Settings (Ollama-first, local by default)
    LLM_PROVIDER: str = Field(default="ollama", description="ollama | gemini | openai | anthropic")
    OLLAMA_BASE_URL: str = Field(default="http://localhost:11434")
    OLLAMA_MODEL: str = Field(default="qwen3:4b")
    OLLAMA_NUM_CTX: int = Field(default=8192)
    OLLAMA_TIMEOUT: float = Field(default=300.0)
    OLLAMA_MAX_RETRIES: int = Field(default=3)

    # Hosted LLM API Keys (optional; never required for local Ollama)
    GEMINI_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None

    # Google OAuth
    GOOGLE_CLIENT_ID: Optional[str] = None
    GOOGLE_CLIENT_SECRET: Optional[str] = None
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/api/v1/connections/oauth/google/callback"

    # Slack & GitHub OAuth
    SLACK_CLIENT_ID: Optional[str] = None
    SLACK_CLIENT_SECRET: Optional[str] = None
    GITHUB_CLIENT_ID: Optional[str] = None
    GITHUB_CLIENT_SECRET: Optional[str] = None

    # Trusted MCP Stdio Configurations (P0-2)
    # JSON list of trusted server dicts: [{"id": "...", "path": "...", "args": [...], "allowed_env": [...]}]
    RELAY_TRUSTED_MCP_SERVERS: str = "[]"

    # Network / SSRF Settings (P1-1)
    ALLOW_PRIVATE_NETWORKS: bool = Field(
        default=False,
        description="Dev/test escape hatch to permit loopback/RFC1918 addresses in REST/MCP/Web tools"
    )

    # MCP-only local development allowlist (P1-1 narrow exception)
    # These settings ONLY affect MCP connection registration and health checks.
    # They have NO effect on REST adapter, web reader, browser, or any other tool.
    # In production, set RELAY_DEV_ALLOW_LOCAL_MCP=false (the default).
    RELAY_DEV_ALLOW_LOCAL_MCP: bool = Field(
        default=False,
        description=(
            "Development only: permit explicitly allowlisted local MCP endpoints "
            "(e.g. 127.0.0.1:8085/mcp). Has NO effect on REST, web reader, or browser tools. "
            "Must remain False in production."
        )
    )
    RELAY_DEV_LOCAL_MCP_HOSTS: str = Field(
        default="127.0.0.1,localhost",
        description=(
            "Comma-separated hostnames/IPs allowed when RELAY_DEV_ALLOW_LOCAL_MCP=true. "
            "Only exact matches are permitted — no wildcards, no subnets."
        )
    )

    # Frontend & CORS
    FRONTEND_URL: Optional[str] = Field(
        default=None,
        description="Public URL of the frontend (e.g. https://relay-app.vercel.app)"
    )
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:3000",
        "http://localhost:8000"
    ]

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Any) -> List[str]:
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return []
            if v.startswith("[") and v.endswith("]"):
                try:
                    return json.loads(v)
                except Exception:
                    pass
            return [i.strip() for i in v.split(",") if i.strip()]
        elif isinstance(v, (list, tuple)):
            return [str(i).strip() for i in v if str(i).strip()]
        return v



def _validate_and_initialize_settings() -> Settings:
    s = Settings()
    env = s.ENVIRONMENT.lower()

    if env == "production":
        # Validate SECRET_KEY
        if not s.SECRET_KEY or len(s.SECRET_KEY.encode("utf-8")) < 32 or s.SECRET_KEY in KNOWN_PLACEHOLDERS:
            raise RuntimeError(
                "PRODUCTION STARTUP FAILURE: SECRET_KEY must be provided, at least 32 bytes, "
                "and not a known placeholder. Generate one using: python scripts/generate_secrets.py"
            )

        # Validate ENCRYPTION_KEY
        if not s.ENCRYPTION_KEY or s.ENCRYPTION_KEY in KNOWN_PLACEHOLDERS:
            raise RuntimeError(
                "PRODUCTION STARTUP FAILURE: ENCRYPTION_KEY must be provided and not a known placeholder. "
                "Generate one using: python scripts/generate_secrets.py"
            )

        # Validate Fernet keys (supports comma-separated list for rotation)
        keys = [k.strip() for k in s.ENCRYPTION_KEY.split(",") if k.strip()]
        if not keys:
            raise RuntimeError("PRODUCTION STARTUP FAILURE: ENCRYPTION_KEY contains no valid keys.")
        for k in keys:
            try:
                Fernet(k.encode("utf-8"))
            except Exception as e:
                raise RuntimeError(
                    f"PRODUCTION STARTUP FAILURE: Invalid Fernet key '{k[:6]}...': {e}"
                )

    elif env == "development":
        dev_secrets = None
        if not s.SECRET_KEY or s.SECRET_KEY in KNOWN_PLACEHOLDERS:
            dev_secrets = _load_or_create_dev_secrets()
            s.SECRET_KEY = dev_secrets["SECRET_KEY"]
        if not s.ENCRYPTION_KEY or s.ENCRYPTION_KEY in KNOWN_PLACEHOLDERS:
            if not dev_secrets:
                dev_secrets = _load_or_create_dev_secrets()
            s.ENCRYPTION_KEY = dev_secrets["ENCRYPTION_KEY"]

    elif env == "test":
        if not s.SECRET_KEY:
            s.SECRET_KEY = secrets.token_hex(32)
        if not s.ENCRYPTION_KEY:
            s.ENCRYPTION_KEY = Fernet.generate_key().decode("utf-8")
        if "ALLOW_PRIVATE_NETWORKS" not in os.environ:
            s.ALLOW_PRIVATE_NETWORKS = True

    # Ensure FRONTEND_URL is included in CORS origins if specified
    if s.FRONTEND_URL and s.FRONTEND_URL.strip():
        f_url = s.FRONTEND_URL.strip().rstrip("/")
        if f_url and f_url not in s.BACKEND_CORS_ORIGINS:
            s.BACKEND_CORS_ORIGINS.append(f_url)

    return s



settings = _validate_and_initialize_settings()
