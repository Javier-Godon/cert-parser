# How The Application Works

## The Big Picture

cert-parser is a **scheduled service** — it runs continuously and performs the same job every few hours:

```
┌──────────────────────────────────────────────────────────┐
│                  cert-parser lifecycle                    │
│                                                          │
│  START UP                                                │
│    │                                                     │
│    ├── Load configuration from environment               │
│    ├── Connect to the REST service                       │
│    ├── Run pipeline IMMEDIATELY (first sync)             │
│    │                                                     │
│    └── Enter scheduler loop:                             │
│         │                                                │
│         ├── Wait 6 hours...                              │
│         ├── Run pipeline (scheduled sync)                │
│         ├── Wait 6 hours...                              │
│         ├── Run pipeline (scheduled sync)                │
│         └── ... (forever, until stopped)                 │
│                                                          │
│  SHUT DOWN (Ctrl+C or docker stop)                       │
│    └── Graceful exit                                     │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

## The Pipeline — Five Steps

Each pipeline execution follows five steps:

### Step 1: Get Permission — Access Token (OpenID Connect)

Before downloading anything, cert-parser needs to authenticate with the identity service:

```
cert-parser: "I'd like to access the certificate service, please"
Auth service: "Who are you?"
cert-parser: "Here are my credentials (client ID + secret + username + password)"
Auth service: "OK, here's a temporary access pass (access token)"
```

This uses the OpenID Connect **password grant** — the application authenticates with both client credentials and user credentials to obtain an access token.

**If this fails** (wrong credentials, service down): Pipeline stops. Old database data preserved.

### Step 2: Get Service Access — SFC Login

The access token alone isn't enough to download certificates. cert-parser must also log in to the SFC service:

```
cert-parser: "Here's my access pass. I need to access border post X"
SFC service: "OK, here's your service-specific pass (SFC token)"
```

This step sends the access token plus border post configuration (post ID, box ID, control type) to obtain a second, service-specific token.

**If this fails** (invalid access token, service down): Pipeline stops. Old database data preserved.

### Step 3: Download the `.bin` File

Using BOTH tokens from Steps 1 and 2:

```
cert-parser: "Here are my two passes. Give me the Master List"
REST service: "OK, here's the .bin file (bytes)"
```

The download request includes two authorization headers — the access token and the SFC token — proving the application has completed both authentication steps.

The downloaded file is a binary blob — typically between 2 KB and 1 MB depending on the country.

**If this fails** (network error, file not found): Pipeline stops. Old database data preserved.

### Step 4: Parse the File

This is where the real work happens. The parser "opens the envelope" and extracts everything inside:

```
.bin file (sealed envelope)
    │
    ├── Unwrap the digital envelope (CMS/PKCS#7 format)
    │
    ├── Extract the Master List payload
    │   └── Parse each certificate inside
    │       ├── Read the certificate's identity (issuer, country)
    │       ├── Read the certificate's fingerprint (SKI)
    │       ├── Read who issued it (AKI)
    │       └── Store the raw certificate bytes
    │
    ├── Extract the envelope's signing certificates
    │   └── Same metadata extraction as above
    │
    └── Extract CRLs (if present)
        └── Parse each revoked entry
            ├── Which certificate was revoked (serial number)
            ├── When it was revoked
            └── Why it was revoked (reason code)
```

**If this fails** (corrupted file, invalid format): Pipeline stops. Old database data preserved.

### Step 5: Store Everything in the Database

The final step replaces all previous data with the freshly parsed data:

```
DATABASE OPERATION (atomic — all or nothing):

  1. DELETE all previously stored data
     ├── Delete revoked certificate entries
     ├── Delete CRLs
     ├── Delete DSCs
     └── Delete root CAs

  2. INSERT all new data
     ├── Insert root CAs (inner + outer certs)
     ├── Insert DSCs (if any)
     ├── Insert CRLs (if any)
     └── Insert revoked entries (if any)

  3. COMMIT (make changes permanent)
```

**The safety guarantee**: Steps 1-3 happen inside a single database transaction. If ANYTHING goes wrong during the insert (database crashes, full disk, constraint violation), the entire operation is rolled back — the old data remains exactly as it was before.

**If this fails**: Old database data preserved intact. That's the whole point of the transactional design.

## Data Freshness

### Why Replace Everything?

When cert-parser downloads a Master List, it gets the **complete current state** — ALL certificates that are currently valid. Rather than trying to figure out "what changed since last time?" (which would be complex and error-prone), cert-parser simply:

1. Throws away the old data
2. Stores the new data

This is simple, reliable, and impossible to get wrong. The small amount of data (hundreds of rows) makes this approach fast enough.

### What If the Data Hasn't Changed?

If the REST service returns the same certificates as before, cert-parser will still delete and re-insert them. This is by design — the operation is so fast (milliseconds for hundreds of rows) that optimizing it away would add complexity without measurable benefit.

## Error Handling — The Railway Model

cert-parser uses a design pattern where each step either **succeeds** (passes data to the next step) or **fails** (stops the entire pipeline):

```
Step 1 ──success──→ Step 2 ──success──→ Step 3 ──success──→ Step 4 ──success──→ Step 5
  │                   │                   │                   │                   │
  └──failure──────────┴──failure──────────┴──failure──────────┴──failure──────────┴──→ STOP (log error)
```

This means:
- If access token acquisition fails → nothing else runs
- If SFC login fails → download, parsing, and storage never happen
- If download fails → parsing and storage never happen
- If parsing fails → the database is never touched
- If storage fails → the transaction rolls back automatically

In every failure scenario, the database retains its previous valid state.

## Monitoring

cert-parser produces structured log entries that tell you exactly what happened:

### Successful Run

```
app.starting          version=0.1.0  interval_hours=6  run_on_startup=true
access_token.acquired
sfc_token.acquired
download.complete     size_bytes=24576
parser.complete       inner_certs=5  outer_certs=3  total_root_cas=8  crls=1  revoked=15
repository.stored     root_cas=8  dscs=0  crls=1  revoked=15  total_rows=24
scheduler.job_completed  rows_stored=24
```

### Failed Run

```
access_token.acquired
sfc_token.acquired
download.complete     size_bytes=0
scheduler.job_failed  failure="TECHNICAL_ERROR: Failed to parse CMS Master List binary"
```

The old data in the database is untouched. The scheduler will retry on the next interval.

## Deployment

cert-parser is designed to run in Docker:

```
docker run cert-parser
  → Starts up
  → Runs pipeline immediately
  → Enters scheduler loop (every 6 hours)
  → Runs indefinitely

docker stop cert-parser
  → Receives shutdown signal
  → Logs graceful shutdown
  → Exits cleanly
```

### Required Configuration

The application needs these settings (provided as environment variables or in a `.env` file):

| Setting | What it is |
|---------|-----------|
| `AUTH_URL` | Where to get the access token |
| `AUTH_CLIENT_ID` | Your client identity |
| `AUTH_CLIENT_SECRET` | Your client password (kept secret) |
| `AUTH_USERNAME` | Your user identity |
| `AUTH_PASSWORD` | Your user password (kept secret) |
| `LOGIN_URL` | Where to get the SFC service token |
| `LOGIN_BORDER_POST_ID` | Which border post to connect to |
| `LOGIN_BOX_ID` | Which box to connect to |
| `LOGIN_PASSENGER_CONTROL_TYPE` | Type of passenger control |
| `DOWNLOAD_URL` | Where to download the Master List |
| `DATABASE_DSN` | How to connect to PostgreSQL |

### Optional Configuration

| Setting | Default | What it does |
|---------|---------|-------------|
| `SCHEDULER_INTERVAL_HOURS` | 6 | How often to sync (in hours) |
| `RUN_ON_STARTUP` | true | Whether to sync immediately on startup |
| `LOG_LEVEL` | INFO | How much detail in logs |
| `HTTP_TIMEOUT_SECONDS` | 60 | How long to wait for network responses |
