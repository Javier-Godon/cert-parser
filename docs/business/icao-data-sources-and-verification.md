# ICAO Data Sources, Certificate Types, and Passport Verification

> **Purpose of this document**: Explain the difference between the three ICAO download
> sources, clarify what each type of certificate does, answer why the Master List only
> contains root CAs, and describe exactly what is needed to fully verify a digitally
> signed travel document such as a passport or national ID card.

---

## Table of Contents

1. [The Three ICAO Download Sources](#1-the-three-icao-download-sources)
2. [Why the Numbers Are So Different](#2-why-the-numbers-are-so-different)
3. [The Full Verification Chain — What You Actually Need](#3-the-full-verification-chain--what-you-actually-need)
4. [Are Root CAs Alone Enough?](#4-are-root-cas-alone-enough)
5. [What cert-parser Processes Today](#5-what-cert-parser-processes-today)
6. [The Role of CRLs](#6-the-role-of-crls)
7. [Summary — Data Source Decision Matrix](#7-summary--data-source-decision-matrix)

---

## 1. The Three ICAO Download Sources

ICAO distributes PKD data through multiple channels. You encountered three of them.
They are **not the same data** — they serve different purposes.

### Source A — PKD Download (https://pkddownloadsg.icao.int/download)

This site offers three separate downloadable files:

---

#### File 1 — eMRTD PKI Objects (DSCs, BCSCs, CRLs)

**What it contains**:
- **DSC** — Document Signer Certificates (the certificates loaded into the passport personalization machines)
- **BCSC / VDS** — Barcode Signer Certificates (for Visible Digital Seals — used on paper documents like COVID certificates, visas, etc.)
- **BCSC-NC / VDS-NC** — Non-constrained environment barcode signer certificates
- **CRL** — Certificate Revocation Lists (the blacklists of revoked DSCs)

**Format**: An LDIF dump (`icaopkd-001`). Each entry contains:
- `userCertificate;binary` → a single DER-encoded DSC/BCSC
- `certificateRevocationList;binary` → a single DER-encoded CRL

**Who publishes this**: Each participating country submits their DSCs and CRLs to ICAO PKD.
This is the **largest** collection because:
- Every country that issues passports creates new DSCs frequently (every few months to years)
- Each passport office / personalization line gets its own DSC
- Old DSCs stay in the list because old passports (10-year validity) were signed by them
- A country like Germany might have hundreds of DSCs (one per personalization batch)

**Key insight**: This file does NOT contain root CA certificates. It contains the working-level
signing certificates used by individual passport offices.

---

#### File 2 — CSCA Master Lists

**What it contains**:
- **CSCA certificates** — Country Signing Certificate Authority root certificates

**Format**: A collection of per-country CMS/PKCS#7 SignedData bundles.
Each bundle (one per country) contains:
- The inner Master List payload: a `SET OF Certificate` of that country's CSCAs
- The outer signing certificates: the CSCA(s) used to sign the bundle itself
- Optional CRLs: the CMS format supports embedded CRLs, but **in practice none of the
  24 countries in our real-world fixtures embed CRLs in their Master Lists**. The
  format allows it; countries simply don't use it.

> **Empirical finding from our fixture analysis**: All 24 real per-country Master List
> `.bin` files (Austria, Bangladesh, Botswana, Switzerland, Germany, Spain, India, Italy,
> Latvia, Moldova, Mongolia, Netherlands, Norway, Seychelles, Sweden, Ukraine, Uganda,
> Uzbekistan, and others) contain **zero embedded CRLs**. CRLs are distributed exclusively
> via PKD File 1 (`icaopkd-001`) as separate entries — not inside Master Lists.
> The composite test fixture (`ml_composite.bin`) artificially injects a real Colombia
> CRL to exercise that code path, since no real Master List triggers it.

**Who publishes this**: Each participating country submits their Master List to ICAO PKD.
ICAO also maintains an **ICAO-signed Master List** (the `ml_un.bin` or `ml_xx.bin` in our
fixtures) that bundles all countries' CSCAs into a single ICAO-vouched collection.

**Why this is smaller than File 1**:
- Each country has only a few CSCAs (1–10 is typical)
- CSCAs rotate rarely — every 3–5 years, or after a key compromise
- A country like Germany might have ~20 CSCAs total (covering past rotations)
- But that same country might have 500+ DSCs (one per passport office, per year)

**This is what cert-parser currently downloads and stores.**

---

#### File 3 — Non-Conformant DSCs and CRLs (deprecated)

**What it contains**: DSCs and CRLs from countries that do not fully conform to ICAO Doc 9303
(the standard for e-Passports). These certificates may have minor encoding errors or
use deprecated algorithms.

**Status**: **Deprecated** — ICAO has stopped updating this collection. Non-conformant
countries have either upgraded or stopped participating.

**cert-parser relevance**: Low. You may encounter these certificates when verifying
passports from specific countries, but the mainstream verification path uses conformant
certificates from Files 1 and 2.

---

### Source B — ICAO Master List (https://www.icao.int/icao-pkd/icao-master-list)

**What it contains**: A single, **ICAO-signed** Master List that bundles the CSCAs from
**all participating countries** into one file. ICAO itself acts as the signer — providing
a single trust anchor for the entire collection.

**Format**: A single CMS/PKCS#7 SignedData bundle. This is equivalent to having all the
per-country Master Lists (File 2 above) merged into one, signed by ICAO rather than by
individual countries.

**Key difference from File 2**:
- File 2 (per-country): Germany signs Germany's Master List, France signs France's, etc.
- Source B (ICAO-signed): ICAO signs everything — you only need to trust ICAO's root

**Why it exists**: For deployments that want a single trust anchor (ICAO) rather than
having to trust each country's signing key independently. This is a simpler trust model.

**cert-parser relevance**: This corresponds to our `ml_un.bin` or similar "universal" fixture.
If your verifier trusts the ICAO root certificate, this single file gives you all CSCAs.

---

## 2. Why the Numbers Are So Different

This directly answers the confusion about the huge difference in certificate counts:

```
ICAO Master Lists (CSCAs)   →  ~200–500 certificates worldwide
PKD DSCs + CRLs             →  50,000–500,000+ certificates worldwide
```

The reason is the structure of the trust hierarchy:

```
Each country has:
    1–10 CSCA root certificates (long-lived, rarely rotated)
         │
         │  each CSCA signs many DSCs:
         ▼
    100–1,000+ DSC certificates per country
    (one per passport office, per production batch, per year)
```

A country like Germany:
- Has ~20 CSCA root certificates (spanning 20+ years of e-Passports)
- Has 300–600+ DSCs (one per personalization system, per year)

Globally across ~170 participating countries:
- ~300 CSCA certificates → the Master Lists
- ~100,000+ DSC certificates → the eMRTD PKI Objects file

**The Master List is small because CSCAs are rare and long-lived.**
**The DSC file is huge because DSCs are numerous and frequently replaced.**

---

## 3. The Full Verification Chain — What You Actually Need

To cryptographically verify a digitally signed travel document (passport, national ID card,
residence permit), a verifier must complete this chain:

```
STEP 1 — Read the passport chip
    │
    │  The chip contains:
    │    • Data Groups (DG1: personal data, DG2: photo, DG14: security info, ...)
    │    • Document Security Object (SOD): a CMS-signed structure
    │      inside SOD: hashes of all DGs, signed by a DSC
    │
    ▼
STEP 2 — Verify the Document Signature (SOD)
    │
    │  The SOD tells you:  "I was signed by DSC with serial X, issued by Country Y"
    │  You need:           the DSC certificate (from the DSC collection)
    │  Action:             verify SOD signature against DSC public key
    │  Result:             data integrity confirmed (chip data wasn't tampered with)
    │
    ▼
STEP 3 — Verify the DSC Trust (chain to CSCA)
    │
    │  The DSC tells you:  "I was issued by Country Y's CSCA with key Z"
    │  You need:           Country Y's CSCA certificate (from the Master List)
    │  Action:             verify DSC signature against CSCA public key
    │  Result:             DSC is legitimate (issued by the real country authority)
    │
    ▼
STEP 4 — Check Revocation (CRL check)
    │
    │  Action:  look up the DSC's serial number in Country Y's CRL
    │  Result:  if NOT revoked → passport is valid; if revoked → REJECT
    │
    ▼
STEP 5 — (Optional) Verify the CSCA itself
    │
    │  For maximum trust: verify the CSCA is on ICAO's Master List
    │  Action:  check Country Y's CSCA against ICAO's signed collection
    │  Result:  ICAO vouches for this country's root certificate
    │
    ▼
DECISION: ACCEPT or REJECT
```

### The Complete Certificate Requirements

| Verification Step | Certificate Type Needed | Source |
|------------------|------------------------|--------|
| Verify chip data integrity | **DSC** (Document Signer Certificate) | PKD File 1 |
| Verify DSC legitimacy | **CSCA** (root CA) | Master Lists (File 2 / Source B) |
| Check DSC revocation | **CRL** for DSCs | PKD File 1 |
| Verify CSCA legitimacy | **ICAO Master List** | Source B |
| Check CSCA revocation | **CRL** for CSCAs | PKD File 2 (rare) |

---

## 4. Are Root CAs Alone Enough?

**The honest answer is: it depends on your use case.**

### Scenario A — You have CSCAs only (what cert-parser stores today)

**What you can do**:
- ✅ Verify that a DSC was issued by a legitimate country authority (once you have the DSC)
- ✅ Build a complete list of trusted CSCA roots for all participating countries
- ✅ Validate that a passport's chain traces back to a known government authority

**What you cannot do** without the DSC collection:
- ❌ Perform full passive authentication of a passport chip standalone
  (you need the DSC to verify the chip's SOD signature)
- ❌ Check whether a specific DSC has been revoked (you need DSC CRLs)

**When CSCAs alone are sufficient**:
- Your downstream system (the one reading passport chips) already has the DSCs loaded locally
  or fetches them separately
- You only need cert-parser to keep the CSCA trust store updated
- Your verifier receives DSC information from the passport chip itself (CSCA + chip → verify)

> **Important note**: Modern passport verification systems often operate in two modes:
>
> 1. **Online mode**: The verifier fetches the DSC from ICAO PKD in real time using the
>    certificate reference embedded in the passport's SOD. In this case, you only need
>    the CSCA to validate the fetched DSC.
>
> 2. **Offline mode**: The verifier has a local database of all DSCs. It looks up the DSC
>    by serial/issuer and verifies the chain. In this case, you need BOTH DSCs and CSCAs.

### Scenario B — You have CSCAs + DSCs + CRLs (full collection)

**What you can do**:
- ✅ Everything in Scenario A, plus:
- ✅ Full offline passport verification without any external calls
- ✅ DSC revocation checking (critical for security)
- ✅ Verify that the specific signing machine that signed a passport is still trusted

**This is the complete solution** required by border control systems operating in
offline or low-connectivity environments.

### The Role of the CSCA in Verification — A Precise Explanation

Here is the exact moment a CSCA is used during passport verification:

```
Passport chip SOD contains:
  → signerInfo.sid = { issuer: "C=DE, CN=csca-germany", serialNumber: 0xABCDEF }
  → this identifies WHICH DSC was used to sign this passport

Verifier fetches/finds the DSC with that issuer+serial combination.

DSC contains:
  → issuer: "C=DE, CN=csca-germany"           ← points to a CSCA
  → subjectKeyIdentifier: <fingerprint>
  → authorityKeyIdentifier: <fingerprint>      ← matches CSCA's SKI

NOW the CSCA is used:
  → Verify: DSC.signature == CSCA.publicKey.verify(DSC.tbsCertificate)
  → If yes: this DSC was genuinely issued by Germany's CSCA
  → Then: the SOD signature verifies against the DSC public key
  → Then: the chip data (photo, name, etc.) is trustworthy
```

The CSCA is the **trust anchor** — you need it to trust the DSC.
The DSC is the **working key** — you need it to verify the chip data.
Both are required for a complete verification.

---

## 4b. What a Real Country `.bin` Actually Contains — Empirical Findings

> **Direct answer to the question**: "For a country like Portugal, can I expect only CSCAs
> or could it contain CSCAs, DSCs, and CRLs?"

### The DSC Trust Chain Has Exactly One Step

First, confirming the trust chain structure (ICAO Doc 9303 is explicit about this):

```
CSCA  →  signs  →  DSC  →  signs  →  Passport chip
```

**There are no intermediate CAs between CSCA and DSC.** Every DSC is directly signed by a
CSCA. You never need "a DSC that signs another DSC." The chain is always exactly two levels:
root (CSCA) and leaf (DSC).

### What a Master List `.bin` Contains in Practice

A per-country Master List `.bin` contains **only CSCAs** — no DSCs, no standalone CRLs.
This is confirmed by analysing all 24 real-world fixtures from the ICAO PKD:

| File | Country | Inner CSCAs | Outer signers | Embedded CRLs |
|------|---------|:-----------:|:-------------:|:-------------:|
| `ml_at.bin` | Austria | 9 | 2 | 0 |
| `ml_bd.bin` | Bangladesh | 2 | 2 | 0 |
| `ml_bw.bin` | Botswana | 2 | 2 | 0 |
| `ml_ch.bin` | Switzerland | 474 | 2 | 0 |
| `ml_cm.bin` | Cameroon | 6 | 2 | 0 |
| `ml_de.bin` | Germany | 581 | 2 | 0 |
| `ml_ec.bin` | Ecuador | 1 | 2 | 0 |
| `ml_es.bin` | Spain | 277 | 1 | 0 |
| `ml_fi.bin` | Finland | 7 | 2 | 0 |
| `ml_fr.bin` | France | 83 | 2 | 0 |
| `ml_in.bin` | India | 635 | 2 | 0 |
| `ml_it.bin` | Italy | 626 | 1 | 0 |
| `ml_lv.bin` | Latvia | 13 | 1 | 0 |
| `ml_md.bin` | Moldova | 7 | 4 | 0 |
| `ml_mn.bin` | Mongolia | 1 | 2 | 0 |
| `ml_nl.bin` | Netherlands | 382 | 1 | 0 |
| `ml_no.bin` | Norway | 6 | 1 | 0 |
| `ml_sc.bin` | Seychelles | 1 | 1 | 0 |
| `ml_se.bin` | Sweden | 639 | 2 | 0 |
| `ml_ua.bin` | Ukraine | 3 | 1 | 0 |
| `ml_ug.bin` | Uganda | 3 | 2 | 0 |
| `ml_un.bin` | ICAO (universal) | 536 | 2 | 0 |
| `ml_uz.bin` | Uzbekistan | 4 | 2 | 0 |
| `ml_xx.bin` | Unknown/Test | 580 | 2 | 0 |

**Every single real-world fixture has 0 embedded CRLs and 0 DSCs.**

### So What Will Portugal's `.bin` Contain?

For any country served by the same REST service, you can expect:

- ✅ **Inner CSCAs**: Portugal's root CA certificates (probably 2–10 for a country that
  has been issuing e-Passports since ~2006)
- ✅ **Outer signer cert(s)**: The CSCA(s) that signed the Master List envelope itself
  (typically 1–2)
- ❌ **DSCs**: None — DSCs are not distributed in Master Lists
- ❌ **Embedded CRLs**: Almost certainly none — no real-world country uses this field

### Why Is the CRL Path in the Code Then?

The CMS SignedData format supports an optional `crls` field (RFC 5652), and ICAO Doc 9303
allows countries to embed CRLs in Master Lists. We implement it because:

1. **The format allows it** — any conformant parser must handle it
2. **Future-proofing** — a country might start embedding CRLs
3. **The composite fixture tests it** — `ml_composite.bin` artificially injects a real
   Colombia CRL (`crl_sample.der`) to ensure the code path works correctly

In practice, the CRL code path in cert-parser is exercised **only** by the synthetic
`ml_composite.bin` fixture. No real country `.bin` in the wild has triggered it.

### The Right Test Fixture Strategy

Because no real Master List contains DSCs or standalone CRLs, testing the full
classification (root_ca + dsc + crls + revoked) requires:

1. **Real country fixtures** (e.g., `ml_es.bin`) → test CSCA extraction only
2. **`ml_composite.bin`** → test CRL extraction and revoked entries (synthetic, real data)
3. **A new `ml_full_coverage.bin`** → built from real CSCA certs + real CRL + synthetic
   structure to exercise ALL four database table insertions in one fixture

The `ml_composite.bin` already covers items 2 and 3 for the parser. The acceptance tests
verify all four tables are populated by running the full pipeline against it.

---

## 5. What cert-parser Processes Today

cert-parser currently processes **CSCA Master Lists** only. Specifically:

| What we process | Source | Database table |
|----------------|--------|---------------|
| CSCA root certificates (inner Master List payload) | Per-country Master List `.bin` | `certs.root_ca` |
| CSCA outer signing certificates (CMS envelope signers) | Per-country Master List `.bin` | `certs.root_ca` |
| CRLs embedded in Master Lists | `.bin` (format allows it; synthetic fixture only) | `certs.crls` |
| Revoked certificate entries from embedded CRLs | `.bin` (format allows it; synthetic fixture only) | `certs.revoked_certificate_list` |

| What we do NOT yet process | Source | Database table |
|--------------------------|--------|---------------|
| DSC certificates | PKD `icaopkd-001` LDIF | `certs.dsc` (schema exists, empty) |
| Standalone CRLs (for DSC revocation) | PKD `icaopkd-001` LDIF | `certs.crls` |
| Non-conformant DSCs/CRLs | PKD non-conformant LDIF | Not planned |
| BCSC / VDS certificates | PKD `icaopkd-001` LDIF | Not planned |

The `certs.dsc` table already exists in the database schema (see `db_migrations/V1_0_0__certs.sql`)
because the data model anticipated DSC ingestion. The table is currently empty.

### Why cert-parser starts with Master Lists

The CSCA Master Lists are the **foundation of the trust hierarchy**. Without the root CAs,
DSC verification is impossible. Starting with CSCAs gives downstream systems the ability to:

1. Validate any DSC they encounter against a known-good CSCA store
2. Build trust chains for passports from all participating countries
3. Detect DSCs signed by unknown or untrusted authorities

The DSC collection is the logical next step — it enables fully offline verification and
is significantly larger and more complex to ingest (100,000+ entries vs ~300 for CSCAs).

---

## 6. The Role of CRLs

CRLs exist at **two levels** of the trust hierarchy, which causes confusion:

### Level 1 — CSCA CRLs (rare)

These revoke **root CA certificates**. This happens when a country's CSCA key is compromised
(a very serious event). Very few countries publish CSCA-level CRLs, and they are sometimes
embedded in Master Lists (as cert-parser currently captures).

**Consequence of CSCA revocation**: All passports signed by DSCs issued by that CSCA
become unverifiable — the entire country's passport chain is broken until a new CSCA is
established. This is catastrophic and extremely rare.

### Level 2 — DSC CRLs (common and important)

These revoke **Document Signer Certificates** — individual signing machines or batches.
These are distributed as part of the `icaopkd-001` file (PKD File 1).

**Why this matters**: If the signing key of a passport office is compromised:
- All passports signed by that DSC could theoretically be forged
- The DSC is added to the CRL
- Verifiers checking the CRL will reject those passports
- A new DSC is issued and used going forward

**Consequence of DSC revocation**: Only passports signed by that specific DSC are affected,
not an entire country's passport programme.

### CRL Summary

```
cert-parser currently captures:
  ✅ CSCA-level CRLs (CMS format allows them in Master Lists;
     code works correctly; no real country uses this in practice)  → certs.crls
  ❌ DSC-level CRLs (distributed separately in PKD File 1)         → not yet ingested

For complete revocation checking you need:
  → DSC-level CRLs from PKD File 1 (icaopkd-001)
```

---

## 7. Summary — Data Source Decision Matrix

| If you want to... | You need | Source |
|------------------|----------|--------|
| Know which countries have valid root authorities | CSCA Master Lists | Source B or PKD File 2 |
| Verify a DSC was issued by a legitimate country | CSCA + DSC | Master Lists + PKD File 1 |
| Fully verify a passport chip offline | CSCA + DSC | Master Lists + PKD File 1 |
| Check if a signing machine was revoked | DSC CRLs | PKD File 1 |
| Check if a CSCA was revoked | CSCA CRLs | PKD File 2 / embedded in Master Lists |
| Verify with a single trust anchor (ICAO) | ICAO-signed Master List | Source B |
| Support non-conformant old passports | Non-conformant DSCs | PKD File 3 (deprecated) |
| Verify Visible Digital Seals (VDS/paper docs) | BCSC certificates | PKD File 1 |

### What This Means for cert-parser's Roadmap

The current implementation (Master Lists → CSCA store) is the **necessary first step** and
is useful as a standalone trust anchor database. Downstream systems that implement passport
verification can use cert-parser's CSCA database immediately.

**Phase 2** (future): Ingest PKD File 1 (`icaopkd-001` LDIF) to populate:
- `certs.dsc` — all Document Signer Certificates
- `certs.crls` — all DSC-level CRLs (supplementing the CSCA CRLs already captured)
- `certs.revoked_certificate_list` — all DSC revocation entries

With Phase 2 complete, the database would contain everything required for **fully offline,
complete cryptographic verification** of any e-Passport or national ID card from a
participating country.
