# The Files We Process

## What Are `.bin` Files?

The `.bin` files that cert-parser downloads are **digitally signed containers**. Think of them as sealed envelopes:

```
┌─────────────────────────────────────────────┐
│  SEALED ENVELOPE (.bin file)                │
│                                             │
│  ┌─────────────────────────────────────┐    │
│  │  THE LETTER (certificates inside)   │    │
│  │                                     │    │
│  │  Certificate 1: Germany CSCA        │    │
│  │  Certificate 2: Germany CSCA (old)  │    │
│  │  Certificate 3: Germany CSCA (new)  │    │
│  │  ...                                │    │
│  └─────────────────────────────────────┘    │
│                                             │
│  SEAL: Digital signature proving this       │
│        envelope came from the real sender   │
│                                             │
│  SIGNER'S ID CARD: The certificate of       │
│        whoever sealed this envelope         │
│                                             │
│  BLACKLIST: Certificates that are no        │
│        longer valid (optional)              │
│                                             │
└─────────────────────────────────────────────┘
```

### The Technical Name

The file format is called **CMS SignedData** (Cryptographic Message Syntax, defined in RFC 5652). It's also historically known as **PKCS#7**. The `.bin` extension is just a naming convention — the actual format is a standard binary encoding called DER (Distinguished Encoding Rules).

### What's Inside a `.bin` File?

Each `.bin` file contains four types of content:

| Component | What it is | Analogy |
|-----------|-----------|---------|
| **Inner certificates** | The actual root CA certificates — this is the *payload* | The letter inside the envelope |
| **Outer certificates** | The certificates of whoever signed/sealed this envelope | The signer's ID card |
| **Digital signatures** | Proof that the envelope hasn't been tampered with | The wax seal |
| **CRLs** (optional) | Lists of revoked certificates | A blacklist attached to the envelope |

### Inner vs. Outer Certificates

This distinction is important:

**Inner certificates** (the Master List payload):
- These are the actual **CSCA root certificates** that countries publish
- Germany's `.bin` might contain 20 inner certificates
- Seychelles' `.bin` contains just 1 inner certificate
- These are the certificates that border control systems use to verify passports

**Outer certificates** (the CMS signers):
- These are the certificates of whoever *signed* the `.bin` file itself
- Usually 1-3 certificates
- They prove the `.bin` file is authentic and hasn't been tampered with
- cert-parser extracts and stores these too (they're also valid trust anchors)

### File Sizes

Real-world `.bin` files range dramatically:

| Country | File size | Certificates |
|---------|-----------|:------------:|
| Seychelles | ~2 KB | 1 |
| Bangladesh | ~5 KB | 2 |
| Germany | ~957 KB | 200+ |
| Composite (test) | ~20 KB | 8 + CRLs |

## Where Do The Files Come From?

### The Distribution Chain

```
COUNTRY'S CSCA AUTHORITY
    │
    ├── Creates root CA certificates
    ├── Packages them into a signed Master List (.bin)
    │
    └──publishes to──→ ICAO PKD (Public Key Directory)
                           │
                           └──served via──→ REST SERVICE
                                              │
                                              └──downloaded by──→ cert-parser
```

### ICAO PKD Distribution Methods

ICAO distributes PKD data in two ways:

1. **LDAP** (for participating countries) — real-time directory protocol
2. **LDIF dumps** (public) — periodic file exports at https://download.pkd.icao.int/

The REST service that cert-parser connects to serves this same data through a standard web API.

### LDIF Source Details

In the PKD's LDIF directory structure:

| LDIF directory | Contains | cert-parser interest |
|---------------|----------|:-------------------:|
| `icaopkd-002` | Master Lists (`.bin` files) | **Yes** — our primary data source |
| `icaopkd-001` | Individual DSCs and CRLs | Future expansion |

Each Master List is stored under the LDIF attribute `pkdMasterListContent`.

## What Happens After Download?

cert-parser's job is to "open the envelope" and extract everything useful:

```
.bin file (the sealed envelope)
    │
    ▼  UNWRAP the CMS envelope
    │
    ├── Extract INNER CERTIFICATES → save to database (root_ca table)
    ├── Extract OUTER CERTIFICATES → save to database (root_ca table)
    ├── Extract CRLs → save to database (crls table)
    │   └── Extract REVOKED ENTRIES → save to database (revoked_certificate_list table)
    │
    ▼  DONE — database is up to date
```

## Other File Formats You Might See

| Extension | Format | What it is |
|-----------|--------|-----------|
| `.bin` | CMS/PKCS#7 SignedData (DER) | Signed Master List bundle — what cert-parser downloads |
| `.der` | DER-encoded X.509 | A single certificate (no envelope) |
| `.pem` | Base64-encoded DER | Same as .der but text-encoded (human-readable) |
| `.crl` | DER-encoded CRL | A single Certificate Revocation List |
| `.ldif` | LDAP Data Interchange Format | Text file with directory entries (PKD dumps) |

cert-parser works exclusively with `.bin` (CMS bundles) and internally handles `.der`-encoded certificates and CRLs extracted from those bundles.
