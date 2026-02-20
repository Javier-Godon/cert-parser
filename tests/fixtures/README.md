# Test Fixtures — Real ICAO PKD Data

Extracted from the ICAO Public Key Directory LDIF files using `scripts/extract_ldif_fixtures.py`.

## Master List CMS Blobs (`ml_*.bin`)

Real CMS/PKCS#7 SignedData structures containing ICAO Master Lists.
Each `.bin` file is a complete CMS envelope with:
- Outer signing certificates (CSCA chain)
- Inner CscaMasterList (version + SET OF Certificate)
- Optional CRLs

| File | Country | Size | Notes |
|------|---------|------|-------|
| `ml_sc.bin` | Seychelles | 2.9 KB | Smallest — 1 inner cert. Ideal for fast unit tests. |
| `ml_bd.bin` | Bangladesh | 4.9 KB | 2 inner certs. |
| `ml_fr.bin` | France | 117.6 KB | 83 inner certs. Good for medium-volume testing. |
| `ml_de.bin` | Germany | 870.3 KB | 300+ certs. Large-volume testing. |
| `ml_se.bin` | Sweden | 956.8 KB | Largest fixture. Stress testing. |
| ... | 24 countries total | | |

## Individual DER Certificates (`cert_*.der`)

Individual X.509v3 certificates extracted from the DSC LDIF (New Zealand entries).
Use for testing `cryptography` metadata extraction (SKI, AKI, issuer) in isolation.

## Synthetic Fixtures (Error Paths)

| File | Content | Purpose |
|------|---------|---------|
| `corrupt.bin` | `this-is-not-valid-cms-data-at-all` | Invalid data → `TECHNICAL_ERROR` |
| `empty.bin` | Empty (0 bytes) | Empty input → `TECHNICAL_ERROR` |
| `truncated.bin` | `\x30\x83\x01\x00` (valid ASN.1 tag, truncated body) | Partial parse → `TECHNICAL_ERROR` |

## Regenerating Fixtures

```bash
# From the project root:
python scripts/extract_ldif_fixtures.py
```

Requires LDIF files in `src/cert_parser/resources/`.
