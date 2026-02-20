# Database & Persistence

## Schema

cert-parser uses four PostgreSQL tables:

```sql
CREATE TABLE root_ca (
    id                        UUID PRIMARY KEY,
    certificate               BYTEA NOT NULL,
    subject_key_identifier    TEXT,
    authority_key_identifier  TEXT,
    issuer                    TEXT,
    x_500_issuer              BYTEA,
    source                    TEXT,
    isn                       TEXT,
    updated_at                TIMESTAMP WITHOUT TIME ZONE
);

CREATE TABLE dsc (
    -- Identical schema to root_ca
    id                        UUID PRIMARY KEY,
    certificate               BYTEA NOT NULL,
    subject_key_identifier    TEXT,
    authority_key_identifier  TEXT,
    issuer                    TEXT,
    x_500_issuer              BYTEA,
    source                    TEXT,
    isn                       TEXT,
    updated_at                TIMESTAMP WITHOUT TIME ZONE
);

CREATE TABLE crls (
    id          UUID PRIMARY KEY,
    crl         BYTEA NOT NULL,
    source      TEXT,
    issuer      TEXT,
    country     TEXT,
    updated_at  TIMESTAMP WITHOUT TIME ZONE
);

CREATE TABLE revoked_certificate_list (
    id                UUID PRIMARY KEY,
    source            TEXT,
    country           TEXT,
    isn               TEXT,
    crl               UUID REFERENCES crls(id),   -- FK to parent CRL
    revocation_reason TEXT,
    revocation_date   TIMESTAMP WITHOUT TIME ZONE,
    updated_at        TIMESTAMP WITHOUT TIME ZONE
);
```

### Table Relationships

```
root_ca  ←──(no FK)
dsc      ←──(no FK)
crls     ←──1:N──── revoked_certificate_list.crl → crls.id
```

The only foreign key is `revoked_certificate_list.crl → crls.id`.

### Column Details

**Certificates (root_ca / dsc)**:

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Application-generated UUID (uuid4) |
| `certificate` | BYTEA | Raw DER-encoded X.509 certificate |
| `subject_key_identifier` | TEXT | Hex-encoded SKI extension (may be NULL) |
| `authority_key_identifier` | TEXT | Hex-encoded AKI extension (may be NULL) |
| `issuer` | TEXT | RFC 4514 string (e.g., `C=DE,O=bsi,CN=csca-germany`) |
| `x_500_issuer` | BYTEA | Raw DER-encoded X.500 Name |
| `source` | TEXT | Always `"icao-masterlist"` |
| `isn` | TEXT | Certificate serial number in hex (e.g., `0x1a2b3c`) |
| `updated_at` | TIMESTAMP | Currently NULL (reserved for future use) |

**CRLs (crls)**:

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Application-generated UUID |
| `crl` | BYTEA | Raw DER-encoded CRL |
| `source` | TEXT | Always `"icao-masterlist"` |
| `issuer` | TEXT | RFC 4514 string of CRL issuer |
| `country` | TEXT | ISO 3166-1 alpha-2 extracted from `C=` attribute |
| `updated_at` | TIMESTAMP | Currently NULL |

**Revoked Certificates (revoked_certificate_list)**:

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Application-generated UUID |
| `source` | TEXT | Always `"icao-masterlist"` |
| `country` | TEXT | Inherited from parent CRL |
| `isn` | TEXT | Revoked certificate serial number in hex |
| `crl` | UUID | FK to `crls.id` — the parent CRL |
| `revocation_reason` | TEXT | e.g., `"key_compromise"` (may be NULL) |
| `revocation_date` | TIMESTAMP | When the certificate was revoked |
| `updated_at` | TIMESTAMP | Currently NULL |

## Transactional Replace Pattern

### The Problem

Each pipeline execution downloads the **complete** current ICAO Master List. The database should reflect exactly what was just downloaded — no stale entries from previous runs, no partial updates if something fails mid-write.

### The Solution

**DELETE all → INSERT all** in a single ACID transaction:

```python
def _transactional_replace(self, payload: MasterListPayload) -> int:
    with psycopg.connect(self._dsn) as conn, conn.transaction(), conn.cursor() as cur:
        self._delete_all(cur)
        rows = self._insert_all(cur, payload)
        return rows
```

### How It Works

1. `psycopg.connect(dsn)` — opens a new connection
2. `conn.transaction()` — starts a transaction (auto-rollback on exception)
3. `conn.cursor()` — creates a cursor for SQL execution
4. **DELETE** all rows in FK-safe order (child → parent):
   ```sql
   DELETE FROM revoked_certificate_list;  -- child of crls
   DELETE FROM crls;
   DELETE FROM dsc;
   DELETE FROM root_ca;
   ```
5. **INSERT** all new rows from the payload
6. **COMMIT** happens automatically when the `transaction()` context manager exits cleanly
7. **ROLLBACK** happens automatically if any exception occurs → old data preserved

### Why This Is Safe

- PostgreSQL transactions are **ACID** — either ALL changes commit or NONE do
- If the DELETE succeeds but INSERT fails → ROLLBACK → old data is still there
- If the application crashes mid-transaction → PostgreSQL rolls back on cleanup
- External queries during the transaction see the old data (MVCC isolation)

### Why Not UPSERT?

`INSERT ... ON CONFLICT DO UPDATE` (UPSERT) would be more complex:
- Need to handle deletions (certs removed from the ML since last sync)
- Need to detect changes vs. no-op updates
- Would require tracking "which certs were seen this run"
- The data set is small enough (hundreds of rows) that full replace is fast

### FK-Safe Deletion Order

Foreign key constraints require deleting in child-first order:

```
1. revoked_certificate_list  (references crls.id)
2. crls
3. dsc
4. root_ca
```

If you deleted `crls` before `revoked_certificate_list`, PostgreSQL would raise a foreign key violation error.

## SQL Templates

No ORM — raw parameterized SQL with `%s` placeholders:

```python
_INSERT_CERT = """
INSERT INTO {table} (
    id, certificate, subject_key_identifier, authority_key_identifier,
    issuer, x_500_issuer, source, isn, updated_at
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

_INSERT_CRL = """
INSERT INTO crls (id, crl, source, issuer, country, updated_at)
VALUES (%s, %s, %s, %s, %s, %s)
"""

_INSERT_REVOKED = """
INSERT INTO revoked_certificate_list (
    id, source, country, isn, crl, revocation_reason, revocation_date, updated_at
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
"""
```

Note: `_INSERT_CERT` uses `.format(table=table)` for the table name (either `root_ca` or `dsc`). The table name is not user input — it's hardcoded in the application.

## Error Wrapping

The public `store()` method wraps the entire transaction in `Result.from_computation()`:

```python
def store(self, payload: MasterListPayload) -> Result[int]:
    return Result.from_computation(
        lambda: self._transactional_replace(payload),
        ErrorCode.DATABASE_ERROR,
        "Failed to persist certificates to database",
    )
```

Any exception (connection refused, constraint violation, timeout) is caught and converted to `Result.failure(DATABASE_ERROR, ...)`. The pipeline sees a failed Result and stops — no downstream code executes.

## Testing the Repository

### Integration Tests (testcontainers)

Integration tests use `testcontainers` to spin up a real PostgreSQL 16 instance:

```python
@pytest.fixture(scope="session")
def postgres_container():
    with PostgresContainer("postgres:16-alpine") as pg:
        dsn = pg.get_connection_url().replace("postgresql+psycopg2", "postgresql")
        with psycopg.connect(dsn) as conn:
            conn.execute(DDL)
            conn.commit()
        yield pg
```

Each test gets a clean database via `TRUNCATE ... CASCADE` before execution.

### What Integration Tests Verify

1. **Basic store + verify** — insert, then SELECT to confirm data
2. **Transactional replace** — store once, store again, verify old data is gone
3. **FK constraints** — revoked entries link to CRLs correctly
4. **Rollback preservation** — on failure, old data remains intact
5. **Empty payload** — storing no data clears all tables
