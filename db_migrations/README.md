# Database Migrations — Reference Only

> **⚠️ These SQL files are NOT intended to be applied automatically.**
>
> They serve as **reference documentation** for the database schema that the
> application expects. The actual table creation must be performed **manually**
> by a database administrator.

## Purpose

This folder contains the DDL (Data Definition Language) statements that define
the PostgreSQL schema required by cert-parser. They document:

- Table structures (`root_ca`, `dsc`, `crls`, `revoked_certificate_list`)
- Column types and constraints
- The `certs` schema prefix used in production

## How to Use

1. **Review** the SQL files to understand the expected schema
2. **Apply manually** to your PostgreSQL instance before running the application
3. **Verify** that the table structures match what the application persists

The application's persistence layer ([repository.py](../src/cert_parser/adapters/repository.py))
must be kept in sync with these schema definitions. If a column exists in the SQL
but not in the repository's INSERT statements, data will be lost.

## Schema Overview

| Table | Description |
|-------|-------------|
| `root_ca` | Root CA (CSCA) certificates extracted from Master Lists |
| `dsc` | Document Signer Certificates |
| `crls` | Certificate Revocation Lists |
| `revoked_certificate_list` | Individual revoked certificate entries from CRLs |

## Important Notes

- The SQL uses the `certs.` schema prefix (e.g., `certs.root_ca`). Ensure the
  `certs` schema exists in your database, or adjust the `search_path` accordingly.
- The `root_ca` table includes a `master_list_issuer` column that tracks which
  entity signed the CMS Master List envelope — this is distinct from the
  certificate's own `issuer` field.
- No migration tool (Flyway, Alembic, etc.) is configured. These files follow
  Flyway naming conventions (`V1_0_0__description.sql`) purely for organizational
  clarity.
