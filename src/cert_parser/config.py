"""
Configuration — typed, validated settings loaded from environment/.env.

Uses pydantic-settings to:
  - Load from environment variables (12-factor app)
  - Fall back to .env file
  - Validate types and constraints at startup
  - Keep secrets out of source control

Designed for Kubernetes deployment: a ConfigMap overrides environment variables.
All configuration errors are caught at import time, not at runtime.
"""

from __future__ import annotations

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class AuthSettings(BaseSettings):
    """
    OpenID Connect authentication configuration (Step 1).

    Authenticates via password grant to obtain an access_token
    that grants permission to call downstream services.
    """

    model_config = SettingsConfigDict(env_prefix="AUTH_")

    url: str = Field(description="OpenID Connect token endpoint URL")
    client_id: str = Field(description="OAuth2 client ID")
    client_secret: SecretStr = Field(description="OAuth2 client secret")
    username: str = Field(description="Resource owner username")
    password: SecretStr = Field(description="Resource owner password")


class LoginSettings(BaseSettings):
    """
    SFC login service configuration (Step 2).

    Authenticates via the access_token from Step 1 to obtain
    an SFC-specific token for certificate download access.
    """

    model_config = SettingsConfigDict(env_prefix="LOGIN_")

    url: str = Field(description="SFC login endpoint URL")
    border_post_id: int = Field(description="Border post identifier")
    box_id: int = Field(description="Box identifier")
    passenger_control_type: int = Field(description="Passenger control type identifier")


class DownloadSettings(BaseSettings):
    """Certificate download service configuration (Step 3)."""

    model_config = SettingsConfigDict(env_prefix="DOWNLOAD_")

    url: str = Field(description="CSCA certificate download endpoint URL")


class DatabaseSettings(BaseSettings):
    """PostgreSQL connection configuration."""

    dsn: SecretStr = Field(
        alias="DATABASE_DSN",
        description="PostgreSQL connection string",
    )


class SchedulerSettings(BaseSettings):
    """Scheduler configuration."""

    model_config = SettingsConfigDict(env_prefix="SCHEDULER_")

    interval_hours: int = Field(default=6, ge=1, description="Hours between scheduled runs")


class AppSettings(BaseSettings):
    """
    Root application settings — aggregates all sub-settings.

    Load order (highest priority first):
      1. Environment variables (Kubernetes ConfigMap)
      2. .env file
      3. Default values
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    auth: AuthSettings = Field(default_factory=AuthSettings)
    login: LoginSettings = Field(default_factory=LoginSettings)
    download: DownloadSettings = Field(default_factory=DownloadSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    scheduler: SchedulerSettings = Field(default_factory=SchedulerSettings)

    http_timeout_seconds: int = Field(default=60, ge=1)
    run_on_startup: bool = Field(default=True)
    log_level: str = Field(default="INFO")
