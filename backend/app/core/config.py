"""Application configuration loaded from environment variables."""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central settings object. Values come from environment / .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    app_env: str = "development"
    log_level: str = "INFO"
    api_v1_prefix: str = "/api/v1"

    # Database
    # App uses the asyncpg driver (Windows-compatible with the default event
    # loop). Alembic normalizes this to sync psycopg for migrations.
    database_url: str = "postgresql+asyncpg://ccc:ccc_password@localhost:55432/ccc"

    # Redis
    redis_url: str = "redis://localhost:63790/0"

    # Clerk
    clerk_secret_key: str = ""
    clerk_publishable_key: str = ""
    clerk_jwks_url: str = ""
    clerk_issuer: str = ""
    clerk_webhook_secret: str = ""

    # Groq
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"

    # AWS (local development)
    aws_region: str = "us-east-1"
    aws_profile: str = "cost-management-dev"
    aws_allow_real_calls: bool = False

    # AWS cross-account AssumeRole (production).
    # The IAM principal (role/user ARN) that the deployed application runs as
    # and that customer roles must trust. Empty in local dev; REQUIRED before
    # customers can connect via AssumeRole in production.
    app_aws_principal_arn: str = ""
    # Optional named profile used to obtain the application's base credentials
    # in local dev when exercising the AssumeRole path. In production the base
    # credentials come from the instance/task role (default chain).
    app_aws_profile: str = ""
    # Server-side secret used to derive a stable, per-connection External ID
    # (HMAC). Not an AWS credential; must be set in production.
    external_id_secret: str = "dev-external-id-secret-change-me"

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    @property
    def assume_role_configured(self) -> bool:
        """True when the deployment has a stable app principal for AssumeRole."""
        return bool(self.app_aws_principal_arn)


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
