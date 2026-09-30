import os
from typing import Optional, List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # App
    PROJECT_NAME: str = "Relay"
    API_V1_STR: str = "/api/v1"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str = Field(
        default="sqlite+aiosqlite:///./relay.db",
        description="Async database connection string"
    )

    # Auth & Security
    SECRET_KEY: str = Field(
        default="relay_secret_key_development_only_replace_in_prod_a982f1b4908c",
        description="JWT signing key"
    )
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440 # 24 hours
    ENCRYPTION_KEY: str = Field(
        default="_JHCRHGuTE5O9qv1DQ8raHDpsy9iHW7xX5_QK5idYUA=",
        description="Fernet key for encrypting credentials at rest"
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

    # CORS
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:3000",
        "http://localhost:8000"
    ]

settings = Settings()
