# Developer Documentation — cert-parser

> Comprehensive technical reference for developers working on or integrating with cert-parser.

## Table of Contents

| Document | Description |
|----------|-------------|
| [Architecture](architecture.md) | Hexagonal architecture, layer rules, dependency injection, import direction |
| [CMS & PKCS#7 Internals](cms-pkcs7-internals.md) | How CMS/PKCS#7 SignedData files work, ASN.1 structures, ICAO Master List format |
| [Parsing Pipeline](parsing-pipeline.md) | Step-by-step extraction: raw bytes → CertificateRecords, CRLs, revoked entries |
| [Libraries & Tooling](libraries-and-tooling.md) | Why asn1crypto + cryptography, httpx, psycopg, APScheduler — rationale and usage |
| [Configuration](configuration.md) | Environment variables, pydantic-settings, sub-settings pattern |
| [Database & Persistence](database-persistence.md) | Schema, transactional replace pattern, FK-safe deletion order |
| [Error Handling & ROP](error-handling-rop.md) | Railway-Oriented Programming, Result monad, ErrorCode mapping, from_computation |
| [HTTP & Retry](http-retry.md) | Dual-token authentication (OpenID Connect + SFC login), download with dual headers, tenacity retry/backoff |
| [Scheduler](scheduler.md) | APScheduler configuration, signal handling, LoggingExecutionContext |
| [Testing Strategy](testing-strategy.md) | Unit/integration/acceptance layers, fixtures, testcontainers, TDD workflow |

## Quick Orientation

```
src/cert_parser/
├── domain/           # PURE — no I/O
│   ├── models.py     # Frozen dataclasses (value objects)
│   └── ports.py      # Protocol interfaces (5 ports)
├── adapters/         # IMPURE — I/O boundary
│   ├── http_client.py    # Dual-token auth + binary download
│   ├── cms_parser.py     # CMS unwrapping + X.509 extraction
│   └── repository.py     # PostgreSQL persistence
├── pipeline.py       # PURE — flat_map chain (5 stages)
├── scheduler.py      # APScheduler wiring
├── config.py         # pydantic-settings  
└── main.py           # Composition root
```

**Import direction**: `main → pipeline → domain ← adapters`. Domain NEVER imports from adapters.

## Technology Stack

| Technology | Version | Purpose |
|-----------|---------|---------|
| Python | 3.14+ | PEP 758 bare-comma except, `type` aliases, `X \| Y` unions |
| railway-rop | 1.0.0 | Result monad, ROP framework (local, `python_framework/`) |
| asn1crypto | 1.5.1 | CMS/PKCS#7 envelope unwrapping |
| cryptography | 46.0.5 | X.509 metadata extraction, CRL parsing |
| httpx | 0.28.1 | Sync HTTP client with streaming |
| tenacity | 9.1.4 | Retry/backoff on transient network errors |
| psycopg | 3.3.2 | PostgreSQL v3 driver |
| APScheduler | 3.11.2 | Periodic job scheduling |
| pydantic-settings | 2.13.0 | Typed configuration from environment |
| structlog | 25.5.0 | Structured JSON logging |
| testcontainers | 4.14.1 | PostgreSQL in Docker for tests |
| respx | 0.22.0 | httpx mock for unit tests |
| pytest | 8.x | Test runner |
| mypy | strict | Static type checking |
| ruff | latest | Linting + formatting (line length 100) |
