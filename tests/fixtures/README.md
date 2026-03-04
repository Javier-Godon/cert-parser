# Test Fixtures — Real ICAO PKD Data

Extracted from the ICAO Public Key Directory LDIF files using `scripts/extract_ldif_fixtures.py`.

## Master List CMS Blobs (`ml_*.bin`)

Real CMS/PKCS#7 SignedData structures containing ICAO Master Lists (one per country).
Each `.bin` file is a complete CMS envelope with:
- Inner `CscaMasterList` payload: a `SET OF Certificate` of that country's CSCA root certificates
- Outer signing certificates: the CSCA(s) that signed the envelope (also stored as root_ca)
- **No DSCs** — Document Signer Certificates are never in Master Lists
- **No embedded CRLs** — all 24 real fixtures have 0 embedded CRLs (verified empirically)

| File | Country | Inner CSCAs | Outer | Notes |
|------|---------|:-----------:|:-----:|-------|
| `ml_sc.bin` | Seychelles | 1 | 1 | Smallest — ideal for fast unit tests |
| `ml_bd.bin` | Bangladesh | 2 | 2 | |
| `ml_bw.bin` | Botswana | 2 | 2 | |
| `ml_mn.bin` | Mongolia | 1 | 2 | |
| `ml_ec.bin` | Ecuador | 1 | 2 | |
| `ml_ua.bin` | Ukraine | 3 | 1 | |
| `ml_ug.bin` | Uganda | 3 | 2 | |
| `ml_uz.bin` | Uzbekistan | 4 | 2 | |
| `ml_no.bin` | Norway | 6 | 1 | |
| `ml_fi.bin` | Finland | 7 | 2 | |
| `ml_md.bin` | Moldova | 7 | 4 | |
| `ml_at.bin` | Austria | 9 | 2 | |
| `ml_lv.bin` | Latvia | 13 | 1 | |
| `ml_cm.bin` | Cameroon | 6 | 2 | |
| `ml_fr.bin` | France | 83 | 2 | Good for medium-volume testing |
| `ml_es.bin` | Spain | 277 | 1 | |
| `ml_nl.bin` | Netherlands | 382 | 1 | |
| `ml_ch.bin` | Switzerland | 474 | 2 | |
| `ml_un.bin` | ICAO (universal) | 536 | 2 | ICAO-signed bundle of all CSCAs |
| `ml_xx.bin` | Unknown/Test | 580 | 2 | |
| `ml_de.bin` | Germany | 581 | 2 | Large-volume testing |
| `ml_it.bin` | Italy | 626 | 1 | |
| `ml_in.bin` | India | 635 | 2 | |
| `ml_se.bin` | Sweden | 639 | 2 | Largest fixture — stress testing |

## Composite Fixture (`ml_composite.bin`)

A **synthetic** CMS bundle that exercises ALL parser code paths in a single file:
- Inner CSCAs from 3 countries: Seychelles (1) + Bangladesh (2) + Botswana (2) = **5 inner certs**
- Outer signer certs from 3 countries: **3 outer certs**
- **1 embedded CRL** (real Colombia CRL from `crl_sample.der`, 15 revoked entries)

This is the **only fixture with embedded CRLs**. Built by `scripts/build_composite_fixture.py`.
No real country Master List triggers the CRL code path — this fixture exists solely to
ensure that code path is tested.

## Individual DER Certificates (`cert_*.der`)

Individual X.509v3 certificates extracted from the DSC LDIF.
Use for testing `cryptography` metadata extraction (SKI, AKI, issuer) in isolation.

## Colombia CRL (`crl_sample.der`)

Real Colombia CRL: 967 bytes, 15 revoked certificate entries.
Source: `icaopkd-001` LDIF (`certificateRevocationList;binary`), **not** from any Master List.
Used as input by `build_composite_fixture.py` to build `ml_composite.bin`.

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
python scripts/build_composite_fixture.py  # rebuilds ml_composite.bin
```

