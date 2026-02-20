# Revocation — When Certificates Go Bad

## What Is Revocation?

Sometimes a certificate that was once valid needs to be **revoked** — declared no longer trustworthy. This is similar to cancelling a credit card: the physical card still exists, but it's no longer accepted.

## Why Are Certificates Revoked?

| Reason | What happened | Example |
|--------|--------------|---------|
| **Key compromise** | The private key was stolen or leaked | A hacker obtained the signing key from a passport office |
| **CA compromise** | The certificate authority itself was compromised | The root authority's systems were breached |
| **Affiliation changed** | The organization no longer operates | A passport office was reorganized |
| **Superseded** | A newer certificate replaces this one | Algorithm upgrade from RSA to ECDSA |
| **Cessation of operation** | The certificate is no longer in use | A signing machine was decommissioned |
| **Unspecified** | No reason given | Administrative decision |

## What Is a CRL?

A **CRL** (Certificate Revocation List) is an official document published by a certificate authority that says: *"These certificates are no longer valid."*

Think of it as a blacklist:

```
CERTIFICATE REVOCATION LIST
Issued by: Colombia's Certificate Authority
Date: 2024-01-15

REVOKED CERTIFICATES:
  Serial: 0x1a2b3c  — Revoked on 2023-06-01 — Reason: Key compromise
  Serial: 0x4d5e6f  — Revoked on 2023-09-15 — Reason: Superseded
  Serial: 0x7a8b9c  — Revoked on 2024-01-10 — Reason: Cessation of operation
  ... (15 entries total)
```

## How cert-parser Handles CRLs

### Where CRLs Come From

CRLs can be found in two places:

1. **Inside Master List `.bin` files** — Some countries include CRLs alongside their root certificates (e.g., Colombia)
2. **Separately in the PKD** — Distributed as standalone files (future expansion)

cert-parser currently extracts CRLs from inside `.bin` files.

### What Gets Stored

For each CRL, cert-parser saves:

| Field | What it is | Example |
|-------|-----------|---------|
| `crl` (raw bytes) | The complete CRL in binary format | Binary blob |
| `issuer` | Who published the CRL | `C=CO,O=REGISTRADURIA,CN=CSCA Colombia` |
| `country` | ISO country code extracted from the issuer | `CO` (Colombia) |
| `source` | Where we got it | `icao-masterlist` |

For each **revoked entry** inside the CRL:

| Field | What it is | Example |
|-------|-----------|---------|
| `isn` (serial number) | Which certificate was revoked | `0x1a2b3c4d` |
| `revocation_date` | When it was revoked | `2023-06-01 12:00:00 UTC` |
| `revocation_reason` | Why it was revoked | `key_compromise` |
| `country` | Which country's certificate | `CO` |
| `crl` (FK) | Link to the parent CRL record | UUID of the CRL |

### Database Relationships

```
crls table                         revoked_certificate_list table
──────────                         ──────────────────────────────
id: UUID  ←────────────────────── crl: UUID (foreign key)
issuer: "C=CO,..."                 isn: "0x1a2b3c"
country: "CO"                      revocation_date: 2023-06-01
```

Each CRL record has zero or more revoked certificate entries linked to it.

## Why Revocation Matters for Passport Verification

When a border control system verifies a passport:

1. It reads the passport chip and finds: "This chip was signed by certificate with serial `0x1a2b3c` issued by Colombia"
2. It checks the CRL from Colombia
3. If serial `0x1a2b3c` is on the CRL → **REJECT** — the signing certificate has been revoked
4. If NOT on the CRL → the certificate is still valid → proceed with verification

Without revocation checking, a passport signed by a compromised key would still appear valid. CRLs are what prevent this.

## Real-World Data

From the ICAO PKD data in cert-parser's test fixtures:

- **Colombia** publishes CRLs with 15+ revoked entries
- **Most countries** do not include CRLs in their Master Lists (they distribute them separately)
- The composite test fixture (built for testing) contains a real Colombia CRL

## Not All Master Lists Have CRLs

It's important to understand that CRLs inside Master Lists are **optional**. Many countries distribute their CRLs through separate channels:

| Distribution Method | Countries | cert-parser support |
|--------------------|-----------|:-------------------:|
| Inside Master List `.bin` | Few (e.g., Colombia) | **Yes** (current) |
| Separate PKD entries | Most countries | Future expansion |
| Bilateral agreements | Some | Not applicable |

cert-parser extracts CRLs when they're present in the `.bin` file, but doesn't fail or report errors when they're absent — that's normal behavior.
