# cert-parser

> **ICAO Master List certificate parser** — downloads CMS/PKCS#7 binary bundles, extracts X.509 certificates & CRLs, persists to PostgreSQL.

[![Python 3.14+](https://img.shields.io/badge/python-3.14+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## Table of Contents

1. [Overview](#overview)
2. [Core Principles](#core-principles)
3. [Architecture](#architecture)
4. [Technology Stack — Selection Rationale](#technology-stack--selection-rationale)
5. [Project Structure](#project-structure)
6. [Data Flow](#data-flow)
7. [ICAO Master List — Technical Deep-Dive](#icao-master-list--technical-deep-dive)
8. [ICAO PKD LDIF Resources](#icao-pkd-ldif-resources)
9. [Database Schema](#database-schema)
10. [Safe Data Refresh Strategy](#safe-data-refresh-strategy)
11. [Retry & Backoff Strategy](#retry--backoff-strategy)
12. [Observability](#observability)
13. [Testing Strategy](#testing-strategy)
14. [Getting Started](#getting-started)
15. [Kubernetes Deployment](#kubernetes-deployment)
16. [CI/CD Pipeline](#cicd-pipeline)
17. [Further Reading](#further-reading)
18. [Design Decisions Log](#design-decisions-log)

---

## Overview

ICAO (International Civil Aviation Organization) maintains **Master Lists** of Country Signing Certification Authorities (CSCAs) — the root certificates that anchor the trust chain for biometric passports worldwide. These lists are distributed as **binary CMS (PKCS#7) bundles** (`.bin` files) through a REST service.

**cert-parser** automates the full lifecycle:

1. **Authenticate (Step 1)** → Obtain an access token via OpenID Connect password grant
2. **Authenticate (Step 2)** → Obtain an SFC token via login endpoint (using access token + border post config)
3. **Download** → Stream the `.bin` bundle using dual-token headers (`Authorization` + `x-sfc-authorization`)
4. **Parse** → Unwrap the CMS/PKCS#7 envelope → extract the ICAO Master List → extract individual X.509 certificates and CRLs with all metadata
5. **Store** → Persist to PostgreSQL (root_ca, dsc, crls, revoked_certificate_list tables)
6. **Schedule** → Repeat automatically every N hours

### Functional Programming Foundation

The entire codebase follows **Railway-Oriented Programming (ROP)** using our [`railway-rop`](python_framework/) framework. This means:

- ✅ **No exceptions in business logic** — all errors are `Result[T]` values
- ✅ **Explicit error handling** — every function declares what can go wrong
- ✅ **Composable pipelines** — `flat_map` chains connect railway segments
- ✅ **Automatic short-circuiting** — failures propagate without boilerplate

---

## Core Principles

### Simplicity & Readability — MANDATORY

> **If the code is not immediately understandable, it is wrong.**

These are non-negotiable constraints that govern every design decision:

| Principle | Meaning |
|-----------|---------|
| **Simplicity first** | Choose the simplest solution that correctly solves the problem. No premature abstractions. No "just in case" flexibility. |
| **Readability over cleverness** | Code is read 10x more than it is written. Every function, every variable name, every module must be self-documenting. |
| **Flat is better than nested** | Prefer `flat_map` chains over deeply nested callbacks. Prefer guard clauses over nested `if/else`. |
| **Small functions** | Each function does ONE thing. If it needs a comment explaining what it does, it needs a better name or a split. |
| **Obvious data flow** | The reader should be able to trace data from input to output without jumping between files. |
| **No magic** | No decorators that hide control flow. No metaclasses. No monkey-patching. The `railway` framework is the only "framework magic" allowed, and it's explicit. |
| **Minimize dependencies** | Every dependency is a liability. Each one must justify its existence with a clear, documented rationale. |

### Why This Matters

This is a **security-critical application** handling PKI trust anchors for national passport systems. The code must be:
- **Auditable** — any developer should understand the full pipeline in under 30 minutes
- **Predictable** — no hidden side effects, no surprise exceptions, no implicit state
- **Testable** — every component can be tested in isolation with mock ports

### Test-Driven Development (TDD) — MANDATORY

> **No production code exists without a failing test written first.**

All development follows the **RED → GREEN → REFACTOR** cycle:

| Phase | Action |
|-------|--------|
| **RED** | Write a failing test that defines the expected behavior |
| **GREEN** | Write the minimum production code to make the test pass |
| **REFACTOR** | Clean up both test and production code while keeping tests green |

**Rules**:
1. Tests are written **BEFORE** implementation — they drive the design
2. Every feature has **BDD acceptance tests** with Given/When/Then docstrings
3. Every adapter has **unit tests** covering both success and failure tracks
4. Integration tests verify **transactional behavior** with real PostgreSQL
5. Acceptance tests use **real ICAO fixtures** — no synthetic mocks for parser validation

---

## Architecture

### Hexagonal / Ports & Adapters

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Composition Root                             │
│                          (main.py)                                  │
│     Creates adapters, wires dependencies, starts scheduler          │
└────────────┬────────────────────────────────────────────┬───────────┘
             │                                            │
             ▼                                            ▼
┌────────────────────────┐                   ┌────────────────────────┐
│      Scheduler         │                   │      Pipeline          │
│    (scheduler.py)      │────executes──────▶│    (pipeline.py)       │
│  APScheduler wrapper   │                   │  Pure ROP flat_map     │
│                        │                   │  chain orchestration   │
└────────────────────────┘                   └───────────┬────────────┘
                                                         │
                                                depends on (Protocols)
                                                         │
                                                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│                          Domain Layer (PURE)                         │
│  ┌─────────────┐  ┌──────────────────────────────────────────────┐  │
│  │  models.py   │  │  ports.py                                    │  │
│  │              │  │  ┌────────────────────┐  ┌─────────────────────┐ │  │
│  │ Certificate  │  │  │ AccessToken      │  │ BinaryDownloader    │ │  │
│  │ Record       │  │  │ Provider Protocol│  │ Protocol            │ │  │
│  │              │  │  └────────────────────┘  └─────────────────────┘ │  │
│  │ CrlRecord    │  │  ┌────────────────────┐  ┌─────────────────────┐ │  │
│  │              │  │  │ SfcToken         │  │CertificateRepository│ │  │
│  │ MasterList   │  │  │ Provider Protocol│  │ Protocol            │ │  │
│  │ Payload      │  │  └────────────────────┘  └─────────────────────┘ │  │
│  │              │  │  ┌────────────────┐                          │  │
│  │ AuthCreds    │  │  │MasterListParser│                          │  │
│  │              │  │  │ Protocol       │                          │  │
│  │              │  │  └────────────────┘                          │  │
│  └─────────────┘  └──────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
                                    ▲
                                    │ implements
                                    │
┌─────────────────────────────────────────────────────────────────────┐
│                        Adapters Layer (IMPURE)                       │
│  ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────────┐ │
│  │  http_client.py   │ │  cms_parser.py   │ │  repository.py       │ │
│  │                   │ │                  │ │                      │ │
│  │  httpx + tenacity │ │  asn1crypto +    │ │  psycopg v3          │ │
│  │  AccessTokenProv  │ │  cryptography    │ │  CertificateRepo     │ │
│  │  SfcTokenProv     │ │  MasterListParser│ │  (transactional)     │ │
│  │  BinaryDownloader │ │                  │ │                      │ │
│  └──────────────────┘ └──────────────────┘ └──────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

**Import direction**: `main → pipeline → domain ← adapters`. The domain layer NEVER imports from adapters.

---

## Technology Stack — Selection Rationale

### Libraries Selected

| Category | Library | Version | Rationale |
|----------|---------|---------|-----------|
| **ROP Framework** | `railway-rop` | 1.0.0 (local) | Our functional error handling foundation |
| **HTTP Client** | `httpx` | ≥ 0.28.1 | Modern sync+async, streaming, HTTP/2, type-annotated |
| **CMS/PKCS#7** | `asn1crypto` | ≥ 1.5.1 | Full CMS SignedData access (eContent, certificates, CRLs) |
| **X.509** | `cryptography` | ≥ 44.0.0 | Best-in-class X.509 API, typed, SKI/AKI extraction |
| **PostgreSQL** | `psycopg` (v3) | ≥ 3.3.0 | Modern sync+async, native BYTEA/UUID/TIMESTAMP |
| **Scheduler** | `APScheduler` | ≥ 3.11, < 4.0 | Lightweight in-process, interval triggers |
| **Config** | `pydantic-settings` | ≥ 2.13.0 | Env vars, .env files, validation, Python 3.14 tested |
| **Retry/Backoff** | `tenacity` | ≥ 9.0.0 | Decorator-based retry with exponential backoff, jitter, stop conditions |
| **Observability** | `structlog` | ≥ 24.4.0 | Structured JSON logging, context binding, processor pipelines |

### Libraries Evaluated and Rejected

| Library | Reason for Rejection |
|---------|---------------------|
| **`icao-ml-tools` (ehn-dcc-development)** | Abandoned (2021), uses private pyOpenSSL internals (`OpenSSL._util`), not pip-installable, broken on modern pyOpenSSL |
| **`psvz/icao`** | Abandoned (2022), shells out to `openssl` CLI via subprocess, not a library, Linux-only, not pip-installable |
| **`asn1tools`** | Good schema-driven approach but no X.509 introspection, `CLASS` keyword limitation, less mature |
| **`pyasn1`/`pyasn1-modules`** | Extremely slow (21MB CRL: ~4100s vs 8s with asn1crypto), awkward API |
| **`requests`** | Sync-only, no HTTP/2, legacy |
| **`psycopg2`** | Maintenance-only, C extension issues on Python 3.14 |
| **`schedule`** | Too simple, unmaintained since 2024, requires manual `while True` loop |

### The Hybrid Approach: asn1crypto + cryptography

This is the key architectural decision. Neither library alone is sufficient:

| Task | Library | Why |
|------|---------|-----|
| CMS envelope unwrapping | **asn1crypto** | Only Python library that exposes `eContent`, `certificates`, and `crls` from SignedData |
| ICAO Master List ASN.1 parsing | **asn1crypto** | Custom `CscaMasterList` schema: `SEQUENCE { version INTEGER, certList SET OF Certificate }` |
| X.509 metadata extraction | **cryptography** | Best-in-class typed API: `SubjectKeyIdentifier`, `AuthorityKeyIdentifier`, `issuer.rfc4514_string()` |
| CRL parsing | **cryptography** | `x509.load_der_x509_crl()` with full extension support |

The `cryptography` library alone **cannot** extract the CMS `eContent` (the actual Master List payload) — its PKCS7 API only exposes certificates from the `certificates` SET, not the encapsulated content. This is by design, not a bug (confirmed in PyCA issue tracker). The `asn1crypto` library fills this gap perfectly.

**Validated with real ICAO data**: The hybrid approach has been tested end-to-end against 26 real Master List CMS blobs extracted from the ICAO PKD (see [ICAO PKD LDIF Resources](#icao-pkd-ldif-resources)).

---

## Project Structure

```
cert_parser/                         ← repository root
├── .github/
│   └── copilot-instructions.md      ← AI coding instructions (project "constitution")
├── python_framework/                ← railway-rop framework (local dependency)
│   ├── src/railway/                 ← Result, ErrorCode, ExecutionContext, etc.
│   └── pyproject.toml
├── src/cert_parser/                 ← main application source
│   ├── __init__.py
│   ├── config.py                    ← pydantic-settings configuration
│   ├── domain/
│   │   ├── models.py                ← CertificateRecord, CrlRecord, AuthCredentials, MasterListPayload
│   │   └── ports.py                 ← Protocol interfaces (AccessTokenProvider, SfcTokenProvider, etc.)
│   ├── adapters/
│   │   ├── http_client.py           ← httpx + tenacity: dual-token auth + download
│   │   ├── cms_parser.py            ← asn1crypto + cryptography: CMS parsing
│   │   └── repository.py            ← psycopg: PostgreSQL persistence (transactional replace)
│   ├── pipeline.py                  ← ROP orchestration (flat_map chain)
│   ├── scheduler.py                 ← APScheduler wrapper
│   ├── resources/                   ← ICAO PKD LDIF reference data (not shipped in prod)
│   │   ├── icaopkd-001-*.ldif       ← 30,216 DSC certificates
│   │   ├── icaopkd-002-*.ldif       ← 27 Master Lists (CMS blobs)
│   │   └── icaopkd-003-*.ldif       ← 502 non-conformant entries
│   └── main.py                      ← composition root (wires everything)
├── scripts/
│   └── extract_ldif_fixtures.py     ← Extract .bin test fixtures from LDIF files
├── tests/
│   ├── unit/                        ← Fast, no I/O, no infrastructure
│   ├── integration/                 ← Requires PostgreSQL (testcontainers)
│   ├── acceptance/                  ← End-to-end with real ICAO fixtures
│   └── fixtures/                    ← Real .bin/.der files extracted from ICAO PKD
│       ├── ml_*.bin                 ← 24 Master List CMS blobs (2KB–957KB)
│       ├── cert_*.der               ← 5 individual DER certificates
│       ├── corrupt.bin              ← Invalid bytes for error-path testing
│       ├── empty.bin                ← Empty file for edge-case testing
│       └── truncated.bin            ← Truncated ASN.1 for error-path testing
├── pyproject.toml                   ← project configuration & dependencies
├── .env.example                     ← template for environment variables
├── .gitignore
└── README.md                        ← this file
```

---

## Data Flow

### Complete Pipeline (per scheduled execution)

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          Scheduler (every N hours)                        │
│                                                                          │
│   LoggingExecutionContext.execute(                                        │
│     pipeline.run_sync(token_provider, downloader, parser, repository)    │
│   )                                                                      │
└────────────────────────────────────┬─────────────────────────────────────┘
                                     │
                    ┌────────────────▼──────────────────┐
                    │     1. acquire_token()             │
                    │     POST {auth_url}                │
                    │     → Result[str] (bearer token)   │
                    │     ⟳ tenacity: 3 retries, expo    │
                    └────────────────┬──────────────────┘
                                     │ flat_map
                    ┌────────────────▼──────────────────┐
                    │     2. download(token)             │
                    │     GET {download_url}             │
                    │     Authorization: Bearer {token}  │
                    │     → Result[bytes] (raw .bin)     │
                    │     ⟳ tenacity: 3 retries, expo    │
                    └────────────────┬──────────────────┘
                                     │ flat_map
                    ┌────────────────▼──────────────────┐
                    │     3. parse(raw_bin)              │
                    │     CMS unwrap → ML parse →       │
                    │     X.509 + CRL extraction         │
                    │     → Result[MasterListPayload]    │
                    │     (no retry — pure computation)  │
                    └────────────────┬──────────────────┘
                                     │ flat_map
                    ┌────────────────▼──────────────────┐
                    │     4. store(payload)              │
                    │     TRANSACTIONAL REPLACE:         │
                    │       BEGIN                        │
                    │       DELETE all old rows          │
                    │       INSERT new payload           │
                    │       COMMIT                       │
                    │     → Result[int] (rows affected)  │
                    └──────────────────────────────────┘
```

### CMS/PKCS#7 Extraction Detail

```
.bin (raw bytes from REST service)
  │
  ├─ asn1crypto: cms.ContentInfo.load(raw_bytes)
  │  └─ signed_data = content_info['content']
  │
  ├─ OUTER certificates: signed_data['certificates']
  │  └─ CSCA signing certificates (the outer CMS envelope's signers)
  │     └─ For each: cert_choice.chosen.dump() → DER bytes
  │        └─ cryptography: x509.load_der_x509_certificate(der)
  │           └─ Extract: SKI, AKI, issuer, x500_issuer, serial → CertificateRecord
  │
  ├─ CRLs: signed_data['crls']
  │  └─ For each: crl_choice.chosen.dump() → DER bytes
  │     └─ cryptography: x509.load_der_x509_crl(der)
  │        └─ Extract: issuer, country, revoked entries → CrlRecord + RevokedCertificateRecord
  │
  └─ INNER Master List: signed_data['encap_content_info']['content']
     └─ Parse CscaMasterList ASN.1: SEQUENCE { version INTEGER, certList SET OF Certificate }
        └─ certList: SET OF Certificate
           └─ For each certificate DER:
              └─ cryptography: x509.load_der_x509_certificate(der)
                 └─ Extract metadata → CertificateRecord (root_ca / dsc)
```

---

## ICAO Master List — Technical Deep-Dive

### What is a Master List?

An ICAO Master List (ML) is the trust anchor for biometric passport verification. Each ICAO member state has a **Country Signing Certification Authority (CSCA)** that issues certificates to **Document Signers (DS)**, which in turn sign the chip data in biometric passports. The Master List aggregates all CSCA certificates globally.

### Binary Format (CMS/PKCS#7 SignedData — RFC 5652)

```asn1
ContentInfo ::= SEQUENCE {
    contentType ContentType,           -- OID 1.2.840.113549.1.7.2 (signedData)
    content     [0] EXPLICIT ANY       -- SignedData
}

SignedData ::= SEQUENCE {
    version          CMSVersion,
    digestAlgorithms DigestAlgorithmIdentifiers,
    encapContentInfo EncapsulatedContentInfo,  -- ← the Master List lives here
    certificates [0] IMPLICIT CertificateSet OPTIONAL,  -- ← CSCA signing certs
    crls         [1] IMPLICIT RevocationInfoChoices OPTIONAL,  -- ← CRLs
    signerInfos      SignerInfos
}
```

### Inner Master List Structure

```asn1
-- OID: 2.23.136.1.1.2 (id-icao-mrtd-security-masterlist)
CscaMasterList ::= SEQUENCE {
    version   INTEGER,           -- typically 0
    certList  SET OF Certificate -- standard X.509v3 DER-encoded certificates
}
```

### Key Distinction: Outer vs Inner Certificates

| Source | Description | Table |
|--------|-------------|-------|
| `SignedData.certificates` | CSCA certificates used to **sign** the CMS envelope | `root_ca` |
| `CscaMasterList.certList` | CSCA certificates from the **Master List payload** | `root_ca` |
| Document Signer certs | If present in a separate structure | `dsc` |
| `SignedData.crls` | Certificate Revocation Lists | `crls` + `revoked_certificate_list` |

### Metadata Extracted per Certificate

| Field | Source | Example |
|-------|--------|---------|
| `certificate` | Raw DER bytes | `0x30 0x82 ...` |
| `subject_key_identifier` | X.509 extension 2.5.29.14 | `a4:b2:c3:...` |
| `authority_key_identifier` | X.509 extension 2.5.29.35 | `d1:e2:f3:...` |
| `issuer` | RFC 4514 string | `CN=CSCA-GERMANY,O=...` |
| `x_500_issuer` | Raw DER encoding of issuer Name | Binary bytes |
| `source` | Origin identifier | `"icao-ml-2026-02"` |
| `isn` | Serial number (hex) | `0x1a2b3c` |

---

## ICAO PKD LDIF Resources

The ICAO Public Key Directory (PKD) distributes its data as **LDIF** (LDAP Data Interchange Format) files. Three complete dumps are included in `src/cert_parser/resources/` as reference data:

| File | Content | Entries | Key Attribute |
|------|---------|---------|---------------|
| `icaopkd-001-complete-009778.ldif` | **DSC** (Document Signer Certificates) | 30,216 certs | `userCertificate;binary::` (base64 DER) |
| `icaopkd-002-complete-000338.ldif` | **Master Lists** (CMS/PKCS#7 bundles) | 27 ML blobs | `pkdMasterListContent::` (base64 CMS) |
| `icaopkd-003-complete-000090.ldif` | **Non-conformant** entries (certs w/ errors) | 502 entries | `userCertificate;binary::` + `pkdConformanceText:` |

### Test Fixtures Extracted

Real `.bin` CMS blobs have been extracted from the Master List LDIF for use as test fixtures:

| Fixture | Country | Size | Inner Certs |
|---------|---------|------|-------------|
| `ml_sc.bin` | Seychelles 🇸🇨 | 2.9 KB | 1 |
| `ml_bd.bin` | Bangladesh 🇧🇩 | 4.9 KB | 2 |
| `ml_mn.bin` | Mongolia 🇲🇳 | 6.0 KB | 2 |
| `ml_fr.bin` | France 🇫🇷 | 117.6 KB | 83 |
| `ml_de.bin` | Germany 🇩🇪 | 870.3 KB | ~300+ |
| `ml_se.bin` | Sweden 🇸🇪 | 956.8 KB | ~300+ |
| ... | **24 countries total** | 2.9 KB – 957 KB | 1 – 300+ |

**Extraction script**: `scripts/extract_ldif_fixtures.py` parses the LDIF files and writes `.bin` fixtures to `tests/fixtures/`.

---

## Database Schema

Four tables (pre-existing — we only INSERT/DELETE, never CREATE):

```sql
-- root_ca & dsc share identical schema
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

CREATE TABLE dsc (/* identical to root_ca */);

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
    crl               UUID,  -- FK → crls.id
    revocation_reason TEXT,
    revocation_date   TIMESTAMP WITHOUT TIME ZONE,
    updated_at        TIMESTAMP WITHOUT TIME ZONE
);
```

---

## Safe Data Refresh Strategy

### The Problem

Each pipeline execution must **completely replace** all data in the database with the fresh download. Naively deleting all rows before inserting opens a dangerous window: if the insert fails, the database is empty and no records remain.

### The Solution: Transactional Replace (DELETE + INSERT in one atomic transaction)

PostgreSQL transactions are **ACID** — either ALL changes commit or NONE do. By wrapping DELETE + INSERT in a single transaction, we guarantee:

- ✅ **If insert succeeds** → old data is gone, new data is in place (COMMIT)
- ✅ **If insert fails** → transaction rolls back, old data is **fully preserved** (ROLLBACK)
- ✅ **If connection drops** → PostgreSQL auto-rollbacks, old data is preserved

```
┌──────────────────────────────────────────────────────────┐
│                    PostgreSQL Transaction                  │
│                                                          │
│  BEGIN;                                                  │
│                                                          │
│  -- Phase 1: Delete old data (respecting FK order)       │
│  DELETE FROM revoked_certificate_list;                    │
│  DELETE FROM crls;                                       │
│  DELETE FROM dsc;                                        │
│  DELETE FROM root_ca;                                    │
│                                                          │
│  -- Phase 2: Insert new data                             │
│  INSERT INTO root_ca    (...) VALUES (...);              │
│  INSERT INTO dsc        (...) VALUES (...);              │
│  INSERT INTO crls       (...) VALUES (...);              │
│  INSERT INTO revoked_certificate_list (...) VALUES (...);│
│                                                          │
│  COMMIT;  ← only if ALL inserts succeed                  │
│  -- On ANY error → automatic ROLLBACK → old data intact  │
└──────────────────────────────────────────────────────────┘
```

### Implementation Pattern

```python
def store(self, payload: MasterListPayload) -> Result[int]:
    """Atomically replace all certificate data."""
    return Result.from_computation(
        lambda: self._transactional_replace(payload),
        ErrorCode.DATABASE_ERROR,
        "Failed to persist certificates",
    )

def _transactional_replace(self, payload: MasterListPayload) -> int:
    with psycopg.connect(self._dsn) as conn:
        with conn.transaction():  # ← ACID guarantee
            with conn.cursor() as cur:
                # Delete in FK-safe order (child → parent)
                cur.execute("DELETE FROM revoked_certificate_list")
                cur.execute("DELETE FROM crls")
                cur.execute("DELETE FROM dsc")
                cur.execute("DELETE FROM root_ca")
                # Insert new data
                rows = 0
                rows += self._insert_root_cas(cur, payload.root_cas)
                rows += self._insert_dscs(cur, payload.dscs)
                rows += self._insert_crls(cur, payload.crls)
                rows += self._insert_revoked(cur, payload.revoked_certificates)
                return rows
        # If ANY exception above → automatic rollback → old data preserved
```

### Why Not Other Approaches?

| Approach | Rejected Because |
|----------|-----------------|
| DELETE before pipeline | ❌ If download/parse fails later, database is empty |
| Shadow tables + RENAME | ❌ Over-engineered for 4 tables; PostgreSQL ACID is sufficient |
| Source tagging (keep old + new, delete old after) | ❌ Adds complexity; UUID primary keys mean no conflicts anyway |
| UPSERT (ON CONFLICT) | ❌ Doesn't remove certificates that were deleted upstream |

---

## Retry & Backoff Strategy

### Where Retries Are Needed

Only **external I/O operations** benefit from retries — never pure computation:

| Operation | Retry? | Why |
|-----------|--------|-----|
| Token acquisition (HTTP POST) | ✅ Yes | Transient network errors, auth service hiccups |
| SFC login (HTTP POST) | ✅ Yes | Transient network errors, login service hiccups |
| Binary download (HTTP GET) | ✅ Yes | Network timeouts, partial downloads |
| CMS parsing (CPU) | ❌ No | Deterministic — same input always produces same result |
| Database store (PostgreSQL) | ✅ Yes | Connection pool exhaustion, transient DB errors |

### tenacity Configuration Pattern

```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import httpx

# Applied at the adapter boundary, INSIDE Result.from_computation
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
    reraise=True,  # Let Result.from_computation catch the final exception
)
def _do_token_request(self) -> str:
    """OpenID Connect password grant with retry — exceptions are caught by from_computation."""
    response = self._client.post(self._url, data=self._form_data)
    response.raise_for_status()
    return response.json()["access_token"]
```

### Key Rules

1. **tenacity decorates the inner method** (the one that raises), NOT the `Result`-returning public method
2. **`reraise=True`** so that after all retries are exhausted, the exception propagates to `Result.from_computation()` which converts it to `Result.failure()`
3. **Only retry transient errors** — never retry auth failures (401), validation errors, or parsing errors
4. **Exponential backoff with jitter** to avoid thundering herd

---

## Observability

### Structured Logging with structlog

All logging uses **structlog** for structured JSON output, enabling easy ingestion by log aggregators (ELK, Datadog, CloudWatch, etc.):

```python
import structlog

log = structlog.get_logger()

# Structured context automatically included in every log line
log.info("pipeline.started", execution_id=exec_id, source="scheduled")
log.info("download.complete", size_bytes=len(data), duration_ms=elapsed)
log.warning("certificate.missing_ski", issuer=issuer, serial=serial)
log.error("store.failed", error_code="DATABASE_ERROR", detail=str(e))
```

### What We Log

| Event | Level | Context Fields |
|-------|-------|---------------|
| Pipeline started | INFO | `execution_id`, `trigger` (scheduled/manual) |
| Access token acquired | INFO | `duration_ms` |
| SFC token acquired | INFO | `duration_ms` |
| Download complete | INFO | `size_bytes`, `duration_ms` |
| Parse complete | INFO | `root_cas`, `dscs`, `crls`, `revoked_count`, `duration_ms` |
| Store complete | INFO | `rows_affected`, `duration_ms` |
| Pipeline success | INFO | `total_duration_ms` |
| Pipeline failure | ERROR | `error_code`, `error_message`, `stage` |
| Retry attempt | WARNING | `attempt`, `wait_seconds`, `exception` |
| Missing extension | WARNING | `cert_issuer`, `extension_oid` |

---

## Testing Strategy

### Test Pyramid

```
         ╱  Acceptance  ╲         ← Real ICAO fixtures, real DB
        ╱   (few, slow)   ╲         (testcontainers PostgreSQL)
       ╱────────────────────╲
      ╱    Integration       ╲    ← Real DB, mock HTTP
     ╱     (moderate)          ╲    (testcontainers PostgreSQL)
    ╱──────────────────────────╲
   ╱         Unit Tests          ╲ ← Mock ports, no I/O
  ╱       (many, fast, <1s)       ╲  (pure functions, Result checks)
 ╱──────────────────────────────────╲
```

### Test Categories

| Category | Location | Infrastructure | Speed | What It Tests |
|----------|----------|---------------|-------|---------------|
| **Unit** | `tests/unit/` | None | Fast (<1s) | Pure functions, domain models, pipeline with mock ports, parser with fixture .bin files |
| **Integration** | `tests/integration/` | PostgreSQL (testcontainers) | Medium (~5s) | Repository CRUD, transactional replace, DB constraints |
| **Acceptance** | `tests/acceptance/` | PostgreSQL (testcontainers) | Slow (~15s) | Full pipeline end-to-end with real ICAO .bin fixtures |

### Test Fixtures Available

From the ICAO PKD LDIF files, we extracted **32 real test fixtures**:

- **24 Master List CMS blobs** (`ml_*.bin`) — ranging from 2.9 KB (Seychelles, 1 cert) to 957 KB (Sweden, 300+ certs)
- **5 individual DER certificates** (`cert_*.der`) — from New Zealand DSC entries
- **3 synthetic fixtures** — `corrupt.bin`, `empty.bin`, `truncated.bin` for error-path testing

### What Each Test Level Verifies

**Unit Tests** (no I/O, mock everything):
- Domain models: creation, immutability, defaults
- CMS parser: `.bin` → `MasterListPayload` with real fixture files
- Pipeline: success track (mock ports return `Result.success()`)
- Pipeline: failure track (mock ports return `Result.failure()`)
- Error mapping: HTTP status codes → `ErrorCode` values
- Config validation: required fields, type coercion

**Integration Tests** (real PostgreSQL via testcontainers):
- Repository: INSERT into all 4 tables
- Repository: transactional replace (DELETE + INSERT atomically)
- Repository: rollback on partial failure preserves old data
- Repository: FK constraint (revoked_certificate_list → crls)
- Repository: NULL handling for optional fields

**Acceptance Tests** (full pipeline, real ICAO data):
- Parse `ml_sc.bin` (smallest, 1 cert) → store → verify in DB
- Parse `ml_fr.bin` (medium, 83 certs) → store → verify row counts
- Parse corrupt `.bin` → pipeline returns `Result.failure(TECHNICAL_ERROR)`
- Transactional replace: load data, re-run pipeline, verify old data is gone

---

## Development Roadmap

### Phase 1 — Foundation ✅

> **Goal**: Project scaffolding, domain models, ports, configuration, documentation.

| Task | Status |
|------|--------|
| Research and tool selection | ✅ Done |
| AI coding instructions (`.github/copilot-instructions.md`) | ✅ Done |
| Project structure + `pyproject.toml` | ✅ Done |
| Domain models (`CertificateRecord`, `CrlRecord`, `MasterListPayload`) | ✅ Done |
| Port interfaces (5 protocols) | ✅ Done |
| Configuration (`pydantic-settings`) | ✅ Done |
| Architecture documentation (this README) | ✅ Done |
| LDIF fixture extraction (32 real test fixtures) | ✅ Done |

**Definition of Done**: ✅ All domain types compile. ✅ All ports defined as Protocols. ✅ `pyproject.toml` installs cleanly. ✅ Test fixtures extracted and validated with real ICAO data.

---

### Phase 2 — HTTP Adapter

> **Goal**: Implement token acquisition and binary download with retry/backoff.

| Task | Definition of Done |
|------|-------------------|
| Implement `HttpAccessTokenProvider` | OpenID Connect password grant POST → `Result[str]`. tenacity retry (3×, exponential backoff). Maps HTTP errors → `ErrorCode`. |
| Implement `HttpSfcTokenProvider` | SFC login POST with bearer + JSON body → `Result[str]`. tenacity retry (3×, exponential backoff). Maps HTTP errors → `ErrorCode`. |
| Implement `HttpBinaryDownloader` | Streaming GET with dual headers (`Authorization` + `x-sfc-authorization`). tenacity retry. Returns `Result[bytes]`. |
| Unit tests — success path | `respx` mock returns 200 + valid token/binary → `Result.success()` with correct value. |
| Unit tests — failure paths | 401 → `AUTHENTICATION_ERROR`. 500 → `EXTERNAL_SERVICE_ERROR`. Timeout → `TIMEOUT_ERROR`. |
| Unit tests — retry behavior | Verify tenacity retries on transient errors, does NOT retry on 401/403. |
| structlog integration | Log `duration_ms` and `size_bytes` for download. |
| mypy + ruff clean | Zero errors on `http_client.py` + test file. |

**Definition of Done**: ✅ **Unit tests written BEFORE implementation (TDD red→green→refactor)**. ✅ All unit tests pass. ✅ Both ports satisfy Protocol. ✅ mypy strict. ✅ ruff clean. ✅ Retry verified.

---

### Phase 3 — CMS Parser Adapter (Core)

> **Goal**: Parse CMS/PKCS#7 binary → extract all certificates and CRLs with metadata.

| Task | Definition of Done |
|------|-------------------|
| CMS envelope unwrapping | `cms.ContentInfo.load()` → `SignedData`. Extracts outer certs, CRLs, eContent. |
| CscaMasterList ASN.1 schema | Custom `core.Sequence` with `SET OF Certificate`. OID `2.23.136.1.1.2`. |
| Inner certificate extraction | Parse `certList` → `CertificateRecord` with SKI, AKI, issuer, x500_issuer, serial. |
| Outer certificate extraction | Parse `signed_data['certificates']` → `CertificateRecord` for each. |
| CRL extraction | Parse `signed_data['crls']` → `CrlRecord` + `RevokedCertificateRecord`. |
| Missing extension handling | Absent SKI/AKI → set to `None`, do NOT fail. Log warning via structlog. |
| Unit tests — real fixtures (happy) | `ml_sc.bin` → 1 inner cert, 1 outer cert. `ml_fr.bin` → 83 inner certs. `ml_de.bin` → 300+ certs. |
| Unit tests — error paths | `corrupt.bin` → `Result.failure(TECHNICAL_ERROR)`. `empty.bin` → same. `truncated.bin` → same. |
| Unit tests — metadata correctness | `ml_sc.bin`: issuer contains "SC" or "Seychelles". SKI is hex. Certificate bytes are valid DER. |
| mypy + ruff clean | Zero errors on `cms_parser.py` + test file. |

**Definition of Done**: ✅ **Unit tests written BEFORE implementation (TDD red→green→refactor)**. ✅ All unit tests pass with real ICAO fixtures. ✅ 3 error fixtures → `Result.failure()`. ✅ Metadata verified for ≥3 countries. ✅ mypy strict. ✅ ruff clean.

---

### Phase 4 — Repository Adapter

> **Goal**: Implement transactional replace for PostgreSQL persistence.

| Task | Definition of Done |
|------|-------------------|
| Implement `PsycopgCertificateRepository` | `store(payload) → Result[int]` using transactional replace. |
| DELETE logic | FK-safe order: `revoked_certificate_list` → `crls` → `dsc` → `root_ca`. |
| INSERT logic | Parameterized INSERTs for all 4 tables. |
| Transaction safety | Single `conn.transaction()` block wrapping DELETE + INSERT. |
| Integration test — happy path | Insert `MasterListPayload` → all rows exist in DB with correct values. |
| Integration test — replace | Insert payload A → insert payload B → ONLY B's rows exist. |
| Integration test — rollback | Simulate INSERT failure → old data fully preserved. |
| Integration test — FK constraint | `RevokedCertificateRecord.crl` references existing `crls.id`. |
| Integration test — empty payload | Store empty payload → tables are empty. |
| structlog integration | Log `rows_affected` per table, total `duration_ms`. |
| mypy + ruff clean | Zero errors on `repository.py` + test file. |

**Definition of Done**: ✅ **Integration tests written BEFORE implementation (TDD red→green→refactor)**. ✅ All integration tests pass (testcontainers PostgreSQL). ✅ Rollback verified. ✅ mypy strict. ✅ ruff clean.

---

### Phase 5 — Pipeline & Orchestration

> **Goal**: Wire all ports into a composable ROP pipeline.

| Task | Definition of Done |
|------|-------------------|
| Implement `run_pipeline()` | `flat_map` chain: `acquire_access_token → acquire_sfc_token → build_credentials → download → parse → store`. Returns `Result[int]`. |
| `LoggingExecutionContext` | Pipeline wrapped with timing + structlog. |
| Unit test — success track | All mock ports → `Result.success()` → pipeline returns `Result.success(rows)`. |
| Unit test — failure at each stage | Token fail → `AUTHENTICATION_ERROR`. SFC login fail → `AUTHENTICATION_ERROR`. Download fail → `EXTERNAL_SERVICE_ERROR`. Parse fail → `TECHNICAL_ERROR`. Store fail → `DATABASE_ERROR`. |
| Unit test — short-circuit | Token fails → download/parse/store NEVER called (verify mock call counts). |
| Acceptance test — end-to-end | Mock HTTP returns `ml_sc.bin` → real parser → real PostgreSQL → verify rows in DB. |
| Acceptance test — replace | Run pipeline twice → only second run's data exists. |
| mypy + ruff clean | Zero errors on `pipeline.py` + test files. |

**Definition of Done**: ✅ **Unit + BDD acceptance tests written BEFORE implementation (TDD red→green→refactor)**. ✅ Unit + acceptance tests pass. ✅ Short-circuit verified. ✅ End-to-end with real ICAO data. ✅ mypy strict. ✅ ruff clean.

---

### Phase 6 — Scheduler & Entry Point

> **Goal**: APScheduler integration, CLI, Docker Compose.

| Task | Definition of Done |
|------|-------------------|
| APScheduler integration | `BlockingScheduler` + configurable `IntervalTrigger`. |
| Run-on-startup | `RUN_ON_STARTUP=true` → execute pipeline once before scheduler starts. |
| Graceful shutdown | Handle `SIGINT`/`SIGTERM` → `scheduler.shutdown(wait=False)`. |
| CLI entry point | `cert-parser` and `python -m cert_parser.main` work. |
| Docker Compose | `docker-compose.yml` with PostgreSQL + app. Tables auto-created. |
| structlog configuration | JSON in production, colored console in development. |
| Integration test — scheduler | Verify scheduler starts, triggers pipeline, respects interval. |
| mypy + ruff clean | Zero errors. |

**Definition of Done**: ✅ `cert-parser` starts and logs. ✅ Scheduler fires. ✅ Graceful shutdown. ✅ Docker Compose runs. ✅ mypy strict. ✅ ruff clean.

---

### Phase 7 — Hardening & Quality Gate

> **Goal**: Production readiness — full type safety, lint clean, high coverage.

| Task | Definition of Done |
|------|-------------------|
| mypy strict mode | `mypy --strict src/` → 0 errors. |
| ruff lint clean | `ruff check src/ tests/` → 0 errors. |
| Test coverage ≥ 90% | `pytest --cov=cert_parser` ≥ 90% line coverage. |
| All acceptance tests green | Full pipeline with real ICAO fixtures passes. |
| Structured logging review | All events documented, consistent context fields. |
| Error recovery documentation | All error codes documented with recovery actions. |
| README final review | All sections accurate, all code examples compile. |

**Definition of Done**: ✅ mypy strict: 0 errors. ✅ ruff: 0 errors. ✅ Coverage ≥ 90%. ✅ All tests green. ✅ README reviewed.

---

## Getting Started

### Prerequisites

- Python 3.14.0+
- PostgreSQL 15+ (for storage; Docker recommended)
- Docker (for integration/acceptance tests via testcontainers)
- The tables listed in [Database Schema](#database-schema) must already exist

### Installation

```bash
# Clone the repository
cd cert_parser

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install the railway-rop framework (local dependency)
pip install -e "./python_framework"

# Install cert-parser with dev dependencies
pip install -e ".[dev]"

# Copy environment template and fill in values
cp .env.example .env
# Edit .env with your actual credentials and database DSN
```

### Extract Test Fixtures (if not already present)

```bash
# Extract .bin fixtures from ICAO PKD LDIF files
python scripts/extract_ldif_fixtures.py
```

### Running

```bash
# Run the application (starts scheduler)
cert-parser

# Or directly
python -m cert_parser.main
```

### Testing

```bash
# Unit tests only (fast, no infrastructure needed)
pytest tests/unit/

# Integration tests (requires Docker for testcontainers)
pytest tests/integration/

# Acceptance tests (requires Docker for testcontainers)
pytest tests/acceptance/

# All tests
pytest

# With coverage
pytest --cov=cert_parser --cov-report=html
```

### Kubernetes Deployment

For production deployment on Kubernetes:

```bash
# 1. Build Docker image
./deployment/scripts/build-and-test.sh v0.1.0

# 2. Deploy to local K8s cluster (for testing)
./deployment/scripts/deploy-local.sh kind

# 3. Validate deployment
./deployment/scripts/validate-deployment.sh cert-parser
```

Key configuration:
- **Docker image**: Multi-stage build with Python 3.14, non-root user, health checks
- **ASGI server**: Uvicorn + FastAPI with `/health`, `/ready`, `/info`, `/trigger` endpoints
- **Configuration**: ConfigMap (non-sensitive) + Secret (sensitive — managed externally)
- **Env var naming**: pydantic-settings `env_nested_delimiter="__"` — use `AUTH__URL`, `DATABASE__HOST`, etc.
- **Graceful shutdown**: SIGTERM → Uvicorn drains connections → exit in <30s
- **Probes**: Startup (5m window), Liveness (30s interval), Readiness (10s interval)
- **Scripts**: Build, deploy, and validate helpers in `deployment/scripts/`
- **Manifests**: `deployment/` — configmap.yaml, secret.yaml, deployment.yaml, service.yaml, pdb-networkpolicy.yaml, kustomization.yaml

See `deployment/` for all Kubernetes manifests, including:
- Building and pushing Docker images
- Secrets management (sealed-secrets, kustomize, Helm)
- ConfigMap override patterns
- Health check testing
- Monitoring/alerting setup
- Troubleshooting guide
- Production checklist

---

## CI/CD Pipeline

The project ships a **Dagger Go SDK** pipeline under `dagger_go/` that automates the full CI/CD lifecycle: clone → unit tests → integration tests → lint → type-check → Docker build → publish to GHCR.

Two pipeline variants are provided:

| Variant | Entry point | Audience | Build command |
|---------|------------|----------|---------------|
| **Standard** | `dagger_go/main.go` | Open networks, Linux/macOS CI | `go build -o railway-dagger-go .` |
| **Corporate** | `dagger_go/corporate_main.go` | Windows, MITM proxies, custom CAs | `go build -tags corporate -o railway-corporate-dagger-go corporate_main.go` |

```bash
# Run the standard pipeline
cd dagger_go && ./run.sh

# Run the corporate pipeline (Windows/corporate CA environments)
cd dagger_go && ./run-corporate.sh

# Skip slow tests
cd dagger_go && RUN_INTEGRATION_TESTS=false RUN_ACCEPTANCE_TESTS=false ./run.sh
```

See [docs/developer/cicd-pipeline.md](docs/developer/cicd-pipeline.md) for the full reference, including the testcontainers/Docker-in-Docker limitation and how it is solved by running integration and acceptance tests on the host machine.

For corporate Windows environments with MITM proxies or custom CA chains, see [dagger_go/deployment/CORPORATE_PIPELINE.md](dagger_go/deployment/CORPORATE_PIPELINE.md).

---

## Further Reading

### Developer Documentation (`docs/developer/`)

| Document | Description |
|----------|-------------|
| [Tooling for Newcomers](docs/developer/tooling-for-newcomers.md) | **Start here** — plain-language explanation of ASGI, FastAPI, Uvicorn, ruff, mypy, structlog, tenacity, and every other library |
| [Dockerfile Explained](docs/developer/dockerfile.md) | How the multi-stage Docker image works; every instruction, layer caching, security rationale |
| [CI/CD Pipeline](docs/developer/cicd-pipeline.md) | Dagger Go SDK pipelines — standard and corporate variants, configuration reference, troubleshooting |
| [Railway-ROP Framework](docs/developer/railway-rop-framework.md) | How `python_framework/railway-rop` is used in cert-parser — `Result[T]`, `flat_map`, `ErrorCode` mapping |
| [Architecture](docs/developer/architecture.md) | Hexagonal architecture, layer rules, dependency injection, import direction |
| [Full developer index](docs/developer/README.md) | All 14 developer documents with descriptions |

### Business Documentation (`docs/business/`)

Plain-language explanations of what the application does and why, written for non-technical stakeholders. See [docs/business/README.md](docs/business/README.md).

### Python Framework (`python_framework/`)

The `railway-rop` package lives locally in `python_framework/`. Its full API reference is at [python_framework/README.md](python_framework/README.md).

### CI/CD Pipeline (`dagger_go/`)

The Dagger Go pipeline has its own documentation index at [dagger_go/README.md](dagger_go/README.md).

---

## Design Decisions Log

| # | Decision | Rationale | Date |
|---|----------|-----------|------|
| 1 | **Railway-Oriented Programming** as foundational paradigm | Eliminates hidden error paths, makes all failures explicit, enables composable pipelines | 2026-02-18 |
| 2 | **Hexagonal Architecture** (ports & adapters) | Decouples domain logic from infrastructure; enables testing with mock ports; adapters are swappable | 2026-02-18 |
| 3 | **asn1crypto + cryptography** hybrid for CMS parsing | `cryptography` alone cannot extract CMS `eContent`; `asn1crypto` alone lacks typed X.509 API. Together they cover 100% of the ICAO parsing needs. **Validated with 26 real ICAO ML blobs.** | 2026-02-18 |
| 4 | **Rejected icao-ml-tools & psvz/icao** as dependencies | Both abandoned (2021/2022), not pip-installable, rely on private APIs or subprocess calls to openssl CLI | 2026-02-18 |
| 5 | **httpx** over requests | Modern sync+async, streaming support, HTTP/2, type-annotated, actively maintained | 2026-02-18 |
| 6 | **psycopg v3** over psycopg2 | Modern successor, sync+async, native BYTEA/UUID/TIMESTAMP, Python 3.14 compatible | 2026-02-18 |
| 7 | **APScheduler 3.x** over 4.x alpha or schedule | Production-stable, actively maintained, interval triggers, avoids manual loops | 2026-02-18 |
| 8 | **Protocol-based ports** (structural typing) over ABC | Cleaner Python idiom; no inheritance required; adapters satisfy contracts by method signature | 2026-02-18 |
| 9 | **pydantic-settings** for configuration | Type-validated env vars, .env file support, SecretStr for credentials, Python 3.14 tested | 2026-02-18 |
| 10 | **No ORM** — raw SQL with psycopg | Four fixed tables with known schema; ORM overhead unjustified; raw SQL is transparent and predictable | 2026-02-18 |
| 11 | **Transactional replace** for data refresh | DELETE + INSERT in one ACID transaction. If insert fails → rollback → old data preserved. Simplest correct approach. | 2026-02-18 |
| 12 | **tenacity** for retry/backoff | Decorator-based, composable, well-maintained. Applied only at adapter I/O boundaries. | 2026-02-18 |
| 13 | **structlog** for observability | Structured JSON logging, context binding, no global state. Enables log aggregation without an APM agent. | 2026-02-18 |
| 14 | **testcontainers** for integration/acceptance tests | Real PostgreSQL in Docker, auto-provisioned per test session. No shared test infrastructure. | 2026-02-18 |
| 15 | **Simplicity & readability** as non-negotiable constraints | Security-critical PKI application must be auditable by any developer in under 30 minutes | 2026-02-18 |
| 16 | **Real ICAO fixtures** for acceptance tests | 32 test files extracted from ICAO PKD LDIF. Ensures parser handles real-world data, not synthetic mocks. | 2026-02-18 |
| 17 | **FastAPI + Uvicorn** for Kubernetes deployment | Scheduled job needs health checks (`/health`, `/ready`) for K8s probes; FastAPI adds minimal overhead while providing observability endpoints. APScheduler runs in background thread. | 2026-02-19 |
| 18 | **Multi-stage Docker build** | Separates build dependencies from runtime, reduces image size (~350 MB final), security: non-root user, read-only filesystems where possible | 2026-02-19 |
| 19 | **ConfigMap + Secret pattern** for K8s | Non-sensitive config in ConfigMap (environment-specific), sensitive values in Secret (managed by external systems: sealed-secrets, Vault, etc.). Supports GitOps workflows. | 2026-02-19 |
