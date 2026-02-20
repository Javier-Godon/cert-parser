# Certificates Explained

## What Is a Digital Certificate?

A digital certificate is an electronic document that proves identity. Think of it like an official ID card, but for computers and organizations:

| Physical ID Card | Digital Certificate |
|-----------------|-------------------|
| Your name | Subject (organization name, country) |
| Your photo | Public key (unique cryptographic fingerprint) |
| Issuing authority (government) | Issuer (the organization that created it) |
| ID number | Serial number |
| Expiration date | Validity period |
| Hologram/security features | Digital signature (mathematical proof of authenticity) |

The standard format for digital certificates is **X.509 version 3** — a universally agreed-upon structure used across the internet (HTTPS/TLS), government identity systems, and passport security.

## Types of Certificates in the Passport Ecosystem

### CSCA — Country Signing CA (Root Certificate)

**What it is**: The highest level of trust for a country's passport system.

**Who creates it**: Each country's national authority (e.g., the Federal Office for Information Security in Germany, the Ministry of Foreign Affairs, etc.)

**What it does**: It signs (vouches for) the Document Signer Certificates. It's the anchor of trust — if you trust this certificate, you trust everything it signs.

**Analogy**: The government office that issues official seals. If you trust the government, you trust the seals they distribute.

**In cert-parser**: Stored in the `root_ca` database table.

### DSC — Document Signer Certificate

**What it is**: The certificate of the machine that actually signs passport chip data.

**Who creates it**: Issued by the country's CSCA (signed by the root certificate).

**What it does**: It's the certificate loaded into the passport personalization equipment. When a passport is issued, this certificate's private key signs the chip data.

**Analogy**: The official seal given to a specific passport office. The seal was issued by the government (CSCA), and each stamped passport (chip signature) can be traced back to the government through this seal.

**In cert-parser**: Stored in the `dsc` database table (currently empty — DSCs are distributed separately from Master Lists).

### Trust Chain

```
CSCA Root Certificate (root_ca table)
   │
   │ signs / issues
   ▼
DSC Document Signer Certificate (dsc table)
   │
   │ signs
   ▼
Passport Chip Data
```

To verify a passport, you follow this chain backwards: check the chip signature → find the DSC → check the DSC was signed by a trusted CSCA.

## Certificate Metadata — What Each Field Means

When cert-parser extracts a certificate, it saves these fields:

### `id` — Unique Identifier

A randomly generated UUID assigned by cert-parser when it processes the certificate. This is NOT part of the certificate itself — it's created by our application for database management.

Example: `a1b2c3d4-e5f6-7890-abcd-ef1234567890`

### `certificate` — The Raw Certificate

The complete certificate in its original binary format (DER encoding). This is the "source of truth" — everything else is metadata extracted from this blob.

Stored as binary data. Downstream systems that need to verify signatures use this field.

### `subject_key_identifier` (SKI)

A unique fingerprint of the certificate's **own** public key. Think of it as the certificate's personal ID number.

Example: `a1b2c3d4e5f6789012345678abcdef01`

**Why it matters**: When a DSC says "I was signed by the CSCA with key X," the SKI is how you find that CSCA. It's the primary lookup key for building trust chains.

**Can be missing**: Some older or simpler certificates don't include this extension. cert-parser logs a warning and stores `NULL`.

### `authority_key_identifier` (AKI)

The fingerprint of the **issuer's** public key — the certificate that signed this one.

Example: `d4e5f6789012345678abcdef0123456789`

**Why it matters**: It points "upward" in the trust chain. If a DSC has AKI = `X`, you look for a CSCA with SKI = `X`.

**Can be missing**: Self-signed root certificates (where issuer = subject) may not include this.

### `issuer`

The name of the organization that created and signed this certificate, in a standard text format called RFC 4514.

Example: `C=DE,O=bsi,CN=csca-germany`

This tells you:
- `C=DE` — Country: Germany
- `O=bsi` — Organization: Federal Office for Information Security (BSI)
- `CN=csca-germany` — Common Name: Germany's CSCA certificate

### `x_500_issuer`

The same issuer information as above, but in its original binary encoding (X.500 Distinguished Name format).

**Why keep both formats?** The text format (`issuer`) is human-readable and good for searching. The binary format (`x_500_issuer`) is needed for cryptographic operations — when verifying signatures, you must compare exact binary representations to avoid encoding differences.

### `source`

Where this certificate came from. Always `"icao-masterlist"` in our case.

Future expansion could include other sources (bilateral agreements, direct country submissions).

### `isn` — Issuer Serial Number

The certificate's serial number, stored in hexadecimal format.

Example: `0x1a2b3c4d5e6f`

**Why it matters**: Together with the issuer name, the serial number uniquely identifies a certificate worldwide. No two certificates from the same issuer should share a serial number.

### `updated_at`

Timestamp of when this record was last updated. Currently not set by cert-parser (reserved for future use).

## How Many Certificates Are We Talking About?

The ICAO PKD contains certificates from 100+ countries. A typical complete download yields:

| Type | Approximate Count |
|------|:-----------------:|
| Root CAs (CSCA) | 300-500 |
| Document Signers (DSC) | 500-1000+ |
| CRLs | 10-50 |
| Revoked entries | 100-500 |

cert-parser currently processes Master Lists only, which contain root CAs. DSC processing is planned for future expansion.

## Why Do Countries Have So Many Certificates?

A single country might publish 20+ root certificates because:

1. **Keys expire** — Certificates have validity periods (typically 10-20 years for CSCAs). Before expiration, a new certificate is issued.

2. **Algorithms change** — Cryptographic standards evolve. A country might issue certificates using:
   - RSA 2048 (older)
   - RSA 4096 (more secure)
   - ECDSA P-256 (modern)
   - ECDSA P-384 (even more modern)

3. **Passports last 10 years** — A passport issued in 2015 with an old key is still valid in 2025. You need the 2015 certificate to verify it.

4. **Compromise recovery** — If a private key is compromised, a new certificate is issued and the old one is revoked. Both stay in the record (the old one in the CRL).

5. **Organizational restructuring** — The issuing authority might change names or structure, resulting in new certificates with different issuer names.
