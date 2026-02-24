"""
Configuration — typed, validated settings loaded from environment/.env.

Uses pydantic-settings to:
  - Load from environment variables (12-factor app)
  - Fall back to .env file
  - Validate types and constraints at startup
  - Keep secrets out of source control

Designed for Kubernetes deployment: a ConfigMap overrides environment variables.
All configuration errors are caught at import time, not at runtime.

Architecture: Only AppSettings is a BaseSettings instance. Sub-settings are plain
BaseModel classes populated by AppSettings via env_nested_delimiter="__", so the env
var AUTH__URL maps to auth.url, DATABASE__HOST maps to database.host, etc.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve the .env file relative to the project root (two levels above this file),
# so settings load correctly regardless of the working directory at runtime.
_ENV_FILE = Path(__file__).parent.parent.parent / ".env"


class AuthSettings(BaseModel):
    """
    OpenID Connect authentication configuration (Step 1).

    Authenticates via password grant to obtain an access_token
    that grants permission to call downstream services.
    """

    url: str = Field(description="OpenID Connect token endpoint URL")
    client_id: str = Field(description="OAuth2 client ID")
    client_secret: SecretStr = Field(description="OAuth2 client secret")
    username: str = Field(description="Resource owner username")
    password: SecretStr = Field(description="Resource owner password")


class LoginSettings(BaseModel):
    """
    SFC login service configuration (Step 2).

    Authenticates via the access_token from Step 1 to obtain
    an SFC-specific token for certificate download access.
    """

    url: str = Field(description="SFC login endpoint URL")
    border_post_id: str = Field(description="Border post identifier")
    box_id: str = Field(description="Box identifier")
    passenger_control_type: str = Field(description="Passenger control type identifier")


class DownloadSettings(BaseModel):
    """Certificate download service configuration (Step 3)."""

    url: str = Field(description="CSCA certificate download endpoint URL")


class DatabaseSettings(BaseModel):
    """
    PostgreSQL connection configuration.

    Accepts either a full connection string via DATABASE_DSN or individual
    components (DATABASE_HOST, DATABASE_PORT, DATABASE_NAME, DATABASE_USERNAME,
    DATABASE_PASSWORD). DATABASE_DSN takes priority when both are provided.
    The DSN is always available via `dsn` after construction.
    """

    # Option 1: full connection string (takes priority)
    dsn: SecretStr | None = Field(
        default=None,
        description="Full PostgreSQL connection string (overrides individual fields)",
    )

    # Option 2: individual components
    host: str | None = Field(default=None, description="PostgreSQL host")
    port: int = Field(default=5432, ge=1, le=65535, description="PostgreSQL port")
    name: str | None = Field(default=None, description="PostgreSQL database name")
    username: str | None = Field(default=None, description="PostgreSQL username")
    password: SecretStr | None = Field(default=None, description="PostgreSQL password")

    @model_validator(mode="after")
    def resolve_dsn(self) -> DatabaseSettings:
        """
        Ensure `dsn` is always populated.

        If DATABASE_DSN is not set, build the DSN from the individual
        component fields. Raises ValueError at startup if neither a full DSN
        nor all required components are provided.
        """
        if self.dsn is not None:
            return self
        missing = [f for f, v in [
            ("DATABASE_HOST", self.host),
            ("DATABASE_NAME", self.name),
            ("DATABASE_USERNAME", self.username),
            ("DATABASE_PASSWORD", self.password),
        ] if not v]
        if missing:
            raise ValueError(
                "Set DATABASE_DSN or provide all of: "
                + ", ".join(missing)
            )
        dsn_value = (
            f"postgresql://{self.username}:{self.password.get_secret_value()}"  # type: ignore[union-attr]
            f"@{self.host}:{self.port}/{self.name}"
        )
        object.__setattr__(self, "dsn", SecretStr(dsn_value))
        return self

    def get_dsn(self) -> str:
        """
        Return the active database DSN as a plain string.

        Always safe to call after construction — `resolve_dsn` guarantees
        `dsn` is populated whether it came from DATABASE_DSN or components.
        """
        assert self.dsn is not None  # guaranteed by resolve_dsn validator
        return self.dsn.get_secret_value()


class SchedulerSettings(BaseModel):
    """
    Scheduler configuration using a standard 5-field cron expression.

    Format: minute hour day-of-month month day-of-week
    Examples:
      "0 */6 * * *"  — every 6 hours (default)
      "0 2 * * *"    — daily at 02:00
      "0 2 * * 1"    — every Monday at 02:00
      "*/30 * * * *" — every 30 minutes
    """

    cron: str = Field(
        default="0 */6 * * *",
        description="Cron expression (5 fields: minute hour dom month dow)",
    )

    @field_validator("cron")
    @classmethod
    def validate_cron(cls, value: str) -> str:
        """Reject expressions that don't have exactly 5 space-separated fields."""
        fields = value.strip().split()
        if len(fields) != 5:
            raise ValueError(
                f"Cron expression must have exactly 5 fields "
                f"(minute hour dom month dow), got {len(fields)}: {value!r}"
            )
        return value.strip()


class AppSettings(BaseSettings):
    """
    Root application settings — aggregates all sub-settings.

    Load order (highest priority first):
      1. Environment variables (Kubernetes ConfigMap)
      2. .env file
      3. Default values

    env_nested_delimiter="__" maps AUTH__URL → auth.url, DATABASE__HOST → database.host,
    etc. All sub-settings classes are plain BaseModel so they inherit this mapping.
    """

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )

    auth: AuthSettings
    login: LoginSettings
    download: DownloadSettings
    database: DatabaseSettings
    scheduler: SchedulerSettings = Field(default_factory=lambda: SchedulerSettings())

    http_timeout_seconds: int = Field(default=60, ge=1)
    run_on_startup: bool = Field(default=True)
    log_level: str = Field(default="INFO")
