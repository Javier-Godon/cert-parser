# HTTP & Retry

## Token Acquisition

### Dual-Token Authentication Flow

cert-parser uses a **3-endpoint dual-token** authentication flow. Two tokens are acquired sequentially, then both are sent on the download request.

#### Step 1: OpenID Connect Access Token (Password Grant)

The first token is obtained via **password grant** (OpenID Connect). This authenticates the application using client credentials plus resource owner credentials (username/password).

```
cert-parser                              Auth Server
    │                                        │
    │  POST /protocol/openid-connect/token   │
    │  grant_type=password                   │
    │  client_id=xxx                         │
    │  client_secret=yyy                     │
    │  username=uuu                          │
    │  password=ppp                          │
    ├───────────────────────────────────────→ │
    │                                        │
    │  200 OK                                │
    │  {"access_token": "eyJ...", ...}       │
    │ ←──────────────────────────────────────┤
    │                                        │
```

#### Step 2: SFC Login Token

The access token is used to authenticate against the SFC login endpoint, which returns a service-specific token:

```
cert-parser                              SFC Login Service
    │                                        │
    │  POST /auth/v1/login                   │
    │  Authorization: Bearer {access_token}  │
    │  {"borderPostId": 1, "boxId": 1,       │
    │   "passengerControlType": 1}            │
    ├───────────────────────────────────────→ │
    │                                        │
    │  200 OK                                │
    │  "sfc-token-value..."                   │
    │ ←──────────────────────────────────────┤
    │                                        │
```

### Implementation

```python
class HttpAccessTokenProvider:
    def __init__(self, auth_url, client_id, client_secret, username, password, timeout=60):
        self._auth_url = auth_url
        self._client_id = client_id
        self._client_secret = client_secret
        self._username = username
        self._password = password
        self._timeout = timeout

    def acquire_token(self) -> Result[str]:
        return Result.from_computation(
            lambda: self._do_token_request(),
            ErrorCode.AUTHENTICATION_ERROR,
            "Access token acquisition failed",
        )

    @retry(...)
    def _do_token_request(self) -> str:
        with httpx.Client(timeout=self._timeout) as client:
            response = client.post(self._auth_url, data={
                "grant_type": "password",
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "username": self._username,
                "password": self._password,
            })
            response.raise_for_status()
            return response.json()["access_token"]
```

```python
class HttpSfcTokenProvider:
    def __init__(self, login_url, border_post_id, box_id, passenger_control_type, timeout=60):
        self._login_url = login_url
        self._border_post_id = border_post_id
        self._box_id = box_id
        self._passenger_control_type = passenger_control_type
        self._timeout = timeout

    def acquire_token(self, access_token: str) -> Result[str]:
        return Result.from_computation(
            lambda: self._do_login_request(access_token),
            ErrorCode.AUTHENTICATION_ERROR,
            "SFC token acquisition failed",
        )

    @retry(...)
    def _do_login_request(self, access_token: str) -> str:
        with httpx.Client(timeout=self._timeout) as client:
            response = client.post(
                self._login_url,
                headers={"Authorization": f"Bearer {access_token}"},
                json={
                    "borderPostId": self._border_post_id,
                    "boxId": self._box_id,
                    "passengerControlType": self._passenger_control_type,
                },
            )
            response.raise_for_status()
            return response.text
```

### Key Decisions

- **`data=` not `json=`** for Step 1 — OAuth2 spec requires `application/x-www-form-urlencoded`
- **`json=` for Step 2** — the SFC login endpoint expects a JSON body
- **New `httpx.Client` per call** — connections aren't reused across infrequent calls (every 6 hours)
- **`.raise_for_status()`** — converts HTTP errors to exceptions, caught by `from_computation`
- **Tokens are not cached** — each pipeline execution acquires fresh tokens

## Binary Download

### Streaming GET with Dual-Token Auth

```python
class HttpBinaryDownloader:
    def download(self, credentials: AuthCredentials) -> Result[bytes]:
        return Result.from_computation(
            lambda: self._do_download(credentials),
            ErrorCode.EXTERNAL_SERVICE_ERROR,
            "Binary download failed",
        )

    @retry(...)
    def _do_download(self, credentials: AuthCredentials) -> bytes:
        with httpx.Client(timeout=self._timeout) as client:
            response = client.get(
                self._download_url,
                headers={
                    "Authorization": f"Bearer {credentials.access_token}",
                    "x-sfc-authorization": f"Bearer {credentials.sfc_token}",
                },
            )
            response.raise_for_status()
            return response.content
```

### Why Not Streaming?

The current implementation reads the full response into memory via `response.content`. This is intentional:
- ICAO Master Lists are small (max ~1 MB)
- The data needs to be in memory for ASN.1 parsing anyway
- Streaming would add complexity without benefit

If file sizes grew significantly, switch to `client.stream("GET", ...)` with chunked reading.

## Retry Strategy

### tenacity Configuration

Both token acquisition adapters and the binary downloader use identical retry configuration:

```python
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=0.1, max=30),
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
    reraise=True,
)
```

| Parameter | Value | Meaning |
|-----------|-------|---------|
| `stop_after_attempt(3)` | 3 | Maximum 3 attempts total (1 original + 2 retries) |
| `wait_exponential(min=0.1, max=30)` | 0.1s → 30s | Exponential backoff between retries |
| `retry_if_exception_type(...)` | Timeout + Network | Only retry transient failures |
| `reraise=True` | — | Final exception propagates to `from_computation` |

### Retry Timeline

```
Attempt 1  →  TimeoutException  →  wait ~0.1s
Attempt 2  →  NetworkError      →  wait ~0.2s
Attempt 3  →  TimeoutException  →  reraise to from_computation
                                   → Result.failure(ERROR_CODE, ...)
```

### What Gets Retried

| Exception Type | Retried? | Why |
|---------------|:--------:|-----|
| `httpx.TimeoutException` | Yes | Network congestion, slow server |
| `httpx.NetworkError` | Yes | DNS failure, connection reset |
| `httpx.HTTPStatusError` (4xx/5xx) | **No** | Server explicitly rejected the request |
| Any other exception | **No** | Unknown failure — don't retry blindly |

### Critical Architecture Rule

```python
# ✅ Correct — @retry on the INNER method
@retry(...)
def _do_token_request(self) -> str:    # may raise (HttpAccessTokenProvider)
    ...

@retry(...)
def _do_login_request(self, access_token: str) -> str:  # may raise (HttpSfcTokenProvider)
    ...

# ✅ Correct — from_computation on the PUBLIC method (no @retry)
def acquire_token(self) -> Result[str]:
    return Result.from_computation(lambda: self._do_token_request(), ...)
```

**Never** put `@retry` on the `Result`-returning method. `from_computation` would catch the first exception and return `Result.failure` — tenacity would never see the exception to retry.

## Testing HTTP Adapters

HTTP unit tests use `respx` to mock httpx calls:

```python
@respx.mock
def test_acquire_access_token_success(respx_mock):
    respx_mock.post("https://auth.example.com/token").respond(
        json={"access_token": "test-token-123"}
    )
    provider = HttpAccessTokenProvider(
        auth_url="https://auth.example.com/token",
        client_id="test-id",
        client_secret="test-secret",
        username="test-user",
        password="test-pass",
    )
    result = provider.acquire_token()
    token = ResultAssertions.assert_success(result)
    assert token == "test-token-123"

@respx.mock
def test_acquire_access_token_401(respx_mock):
    respx_mock.post("https://auth.example.com/token").respond(status_code=401)
    result = provider.acquire_token()
    ResultAssertions.assert_failure(result, ErrorCode.AUTHENTICATION_ERROR)
```

### Testing Retry Behavior

To verify retry works without waiting, set very short backoff in tests:

```python
HttpAccessTokenProvider(
    auth_url="...",
    client_id="...",
    client_secret="...",
    username="...",
    password="...",
    timeout=60,  # doesn't affect retry timing, which is 0.1s min
)
```

The `min=0.1` wait makes retry tests complete in <1 second.

## Error Code Mapping

| Scenario | HTTP Status | Error Code |
|----------|:-----------:|-----------|
| Invalid credentials (Step 1) | 401 | `AUTHENTICATION_ERROR` |
| Invalid access token (Step 2) | 401/403 | `AUTHENTICATION_ERROR` |
| Forbidden | 403 | `AUTHENTICATION_ERROR` |
| Server error | 500 | `AUTHENTICATION_ERROR` or `EXTERNAL_SERVICE_ERROR` |
| Network timeout | — | `AUTHENTICATION_ERROR` or `EXTERNAL_SERVICE_ERROR` |
| DNS failure | — | `AUTHENTICATION_ERROR` or `EXTERNAL_SERVICE_ERROR` |
| Successful but invalid JSON (Step 1) | 200 | `AUTHENTICATION_ERROR` (KeyError on "access_token") |

The error code depends on which adapter is making the call — `HttpAccessTokenProvider` and `HttpSfcTokenProvider` always use `AUTHENTICATION_ERROR`, `HttpBinaryDownloader` always uses `EXTERNAL_SERVICE_ERROR`.
