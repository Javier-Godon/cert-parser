# Configuration

## Overview

cert-parser uses **pydantic-settings** to load typed, validated configuration from environment variables and `.env` files. All configuration errors are caught at startup — not at runtime during pipeline execution.

## Configuration Structure

```python
AppSettings (root)
├── auth: AuthSettings          # OpenID Connect authentication (Step 1)
│   ├── url: str                # AUTH_URL
│   ├── client_id: str          # AUTH_CLIENT_ID
│   ├── client_secret: SecretStr # AUTH_CLIENT_SECRET
│   ├── username: str           # AUTH_USERNAME
│   └── password: SecretStr     # AUTH_PASSWORD
├── login: LoginSettings        # SFC login service (Step 2)
│   ├── url: str                # LOGIN_URL
│   ├── border_post_id: int     # LOGIN_BORDER_POST_ID
│   ├── box_id: int             # LOGIN_BOX_ID
│   └── passenger_control_type: int # LOGIN_PASSENGER_CONTROL_TYPE
├── download: DownloadSettings  # Binary download (Step 3)
│   └── url: str                # DOWNLOAD_URL
├── database: DatabaseSettings  # PostgreSQL
│   └── dsn: SecretStr          # DATABASE_DSN
├── scheduler: SchedulerSettings # Scheduling
│   └── interval_hours: int     # SCHEDULER_INTERVAL_HOURS (default: 6)
├── http_timeout_seconds: int   # HTTP_TIMEOUT_SECONDS (default: 60)
├── run_on_startup: bool        # RUN_ON_STARTUP (default: true)
└── log_level: str              # LOG_LEVEL (default: "INFO")
```

## Environment Variables

| Variable | Required | Default | Description |
|----------|:--------:|---------|-------------|
| `AUTH_URL` | Yes | — | OpenID Connect token endpoint URL |
| `AUTH_CLIENT_ID` | Yes | — | OAuth2 client ID |
| `AUTH_CLIENT_SECRET` | Yes | — | OAuth2 client secret (masked in logs) |
| `AUTH_USERNAME` | Yes | — | Resource owner username (password grant) |
| `AUTH_PASSWORD` | Yes | — | Resource owner password (masked in logs) |
| `LOGIN_URL` | Yes | — | SFC login endpoint URL |
| `LOGIN_BORDER_POST_ID` | Yes | — | Border post identifier (integer) |
| `LOGIN_BOX_ID` | Yes | — | Box identifier (integer) |
| `LOGIN_PASSENGER_CONTROL_TYPE` | Yes | — | Passenger control type identifier (integer) |
| `DOWNLOAD_URL` | Yes | — | Master List download endpoint URL |
| `DATABASE_DSN` | Yes | — | PostgreSQL connection string (masked in logs) |
| `SCHEDULER_INTERVAL_HOURS` | No | `6` | Hours between scheduled pipeline executions |
| `HTTP_TIMEOUT_SECONDS` | No | `60` | Timeout in seconds for HTTP requests |
| `RUN_ON_STARTUP` | No | `true` | Run pipeline immediately on startup |
| `LOG_LEVEL` | No | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |

## .env File

Copy `.env.example` to `.env` and fill in actual values:

```dotenv
AUTH_URL=https://example.com/auth/realms/myrealm/protocol/openid-connect/token
AUTH_CLIENT_ID=your-client-id
AUTH_CLIENT_SECRET=your-client-secret
AUTH_USERNAME=your-username
AUTH_PASSWORD=your-password
LOGIN_URL=https://example.com/api/auth/v1/login
LOGIN_BORDER_POST_ID=1
LOGIN_BOX_ID=1
LOGIN_PASSENGER_CONTROL_TYPE=1
DOWNLOAD_URL=https://example.com/api/certificates/csca
DATABASE_DSN=postgresql://user:password@localhost:5432/cert_parser_db
SCHEDULER_INTERVAL_HOURS=6
HTTP_TIMEOUT_SECONDS=60
RUN_ON_STARTUP=true
LOG_LEVEL=INFO
```

**NEVER commit `.env`** — it contains secrets. The `.gitignore` excludes it.

## How Configuration Loading Works

### Load Order (highest priority first)

1. **Environment variables** — override everything
2. **`.env` file** — fallback for local development
3. **Default values** — coded in the settings classes

### Sub-Settings Pattern

Each settings group has its own `BaseSettings` subclass with an `env_prefix`:

```python
class AuthSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AUTH_")
    url: str
    client_id: str
    client_secret: SecretStr
    username: str
    password: SecretStr

class LoginSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LOGIN_")
    url: str
    border_post_id: int
    box_id: int
    passenger_control_type: int
```

With `env_prefix="AUTH_"`, pydantic-settings maps:
- `AUTH_URL` → `url`
- `AUTH_CLIENT_ID` → `client_id`
- `AUTH_CLIENT_SECRET` → `client_secret`
- `AUTH_USERNAME` → `username`
- `AUTH_PASSWORD` → `password`

With `env_prefix="LOGIN_"`, pydantic-settings maps:
- `LOGIN_URL` → `url`
- `LOGIN_BORDER_POST_ID` → `border_post_id`
- `LOGIN_BOX_ID` → `box_id`
- `LOGIN_PASSENGER_CONTROL_TYPE` → `passenger_control_type`

### Root Settings Aggregation

`AppSettings` composes all sub-settings:

```python
class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    auth: AuthSettings = Field(default_factory=AuthSettings)
    login: LoginSettings = Field(default_factory=LoginSettings)
    download: DownloadSettings = Field(default_factory=DownloadSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    scheduler: SchedulerSettings = Field(default_factory=SchedulerSettings)
    http_timeout_seconds: int = Field(default=60, ge=1)
    run_on_startup: bool = Field(default=True)
    log_level: str = Field(default="INFO")
```

Key details:
- **`extra="ignore"`** — ignores unknown environment variables (no crash on extra vars)
- **`default_factory=AuthSettings`** — sub-settings are loaded lazily from their own env vars
- **`ge=1`** on `http_timeout_seconds` — validates minimum value at startup
- **`SecretStr`** — `.get_secret_value()` must be called explicitly to access the actual value

### DatabaseSettings Special Case

`DatabaseSettings` uses an `alias` instead of `env_prefix` because the DSN doesn't follow a prefix pattern:

```python
class DatabaseSettings(BaseSettings):
    dsn: SecretStr = Field(alias="DATABASE_DSN")
```

This maps `DATABASE_DSN` → `dsn`.

## Startup Validation

In `main.py`, configuration is loaded inside a try/except:

```python
try:
    settings = AppSettings()
except Exception as e:
    print(f"FATAL: Configuration error — {e}", file=sys.stderr)
    sys.exit(1)
```

If any required variable is missing or invalid, the application exits immediately with a clear error message. This is the **only** try/except in `main.py` — all other error handling uses `Result`.

## How Adapters Receive Configuration

The composition root (`main.py`) creates adapters by extracting values from settings:

```python
access_token_provider = HttpAccessTokenProvider(
    auth_url=settings.auth.url,
    client_id=settings.auth.client_id,
    client_secret=settings.auth.client_secret.get_secret_value(),  # ← explicit unwrap
    username=settings.auth.username,
    password=settings.auth.password.get_secret_value(),            # ← explicit unwrap
    timeout=settings.http_timeout_seconds,
)

sfc_token_provider = HttpSfcTokenProvider(
    login_url=settings.login.url,
    border_post_id=settings.login.border_post_id,
    box_id=settings.login.box_id,
    passenger_control_type=settings.login.passenger_control_type,
    timeout=settings.http_timeout_seconds,
)

repository = PsycopgCertificateRepository(
    dsn=settings.database.dsn.get_secret_value(),  # ← explicit unwrap
)
```

Adapters never access `AppSettings` directly — they receive plain values (str, int). This makes them testable without configuration infrastructure.

## Adding New Configuration

1. Decide if it belongs to an existing sub-settings group or needs a new one
2. Add the field to the appropriate `BaseSettings` subclass
3. If new group: create a new class with `env_prefix`, add it to `AppSettings`
4. Update `.env.example` with the new variable
5. Thread the value through `_create_adapters()` in `main.py`
