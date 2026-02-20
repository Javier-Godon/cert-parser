# CMS & PKCS#7 Internals

## What is CMS/PKCS#7?

CMS (Cryptographic Message Syntax, RFC 5652) is a standard for wrapping cryptographic data — signed content, encrypted content, etc. PKCS#7 is the older name for the same standard. The ICAO Master Lists are distributed as **CMS SignedData** structures.

A `.bin` file from the ICAO PKD is NOT a raw certificate dump. It's a **signed envelope** — a container that includes:
1. The actual certificates (the payload)
2. Digital signatures proving authenticity
3. The signing certificates themselves (so you can verify the signatures)
4. Optionally, Certificate Revocation Lists (CRLs)

## ASN.1 Encoding

All CMS structures are encoded in **ASN.1 DER** (Distinguished Encoding Rules) — a binary format. This is NOT human-readable. You need specialized libraries to parse it.

ASN.1 is a schema language for defining data structures. DER is the encoding that serializes those structures to bytes. Think of ASN.1 as the "protobuf schema" and DER as the "wire format."

## CMS SignedData Structure

The top-level structure is `ContentInfo`:

```
ContentInfo ::= SEQUENCE {
    contentType    OBJECT IDENTIFIER,   -- 1.2.840.113549.1.7.2 = signedData
    content  [0]  EXPLICIT ANY         -- the SignedData structure
}
```

Inside `content` is `SignedData`:

```
SignedData ::= SEQUENCE {
    version            INTEGER,
    digestAlgorithms   SET OF DigestAlgorithmIdentifier,
    encapContentInfo   EncapsulatedContentInfo,      ← the actual payload
    certificates [0]   IMPLICIT CertificateSet,       ← signing certificates
    crls         [1]   IMPLICIT RevocationInfoChoices, ← optional CRLs
    signerInfos        SET OF SignerInfo               ← digital signatures
}
```

### Key Fields for cert-parser

| Field | What it contains | How cert-parser uses it |
|-------|-----------------|------------------------|
| `encapContentInfo.eContent` | The ICAO Master List payload (ASN.1 bytes) | Parsed to extract inner certificates |
| `certificates` | X.509 certificates of the CMS signers (outer certificates) | Extracted as additional root CAs |
| `crls` | Certificate Revocation Lists | Parsed for revoked certificate entries |
| `signerInfos` | Digital signatures (for verification) | **Not used** — cert-parser trusts the REST service |

### Why Signatures Are Not Verified

cert-parser downloads `.bin` files from an authenticated REST service (OAuth2). The trust boundary is the REST service itself — if the REST service is compromised, signature verification wouldn't help because the attacker could provide valid signatures. Signature verification would add complexity without meaningful security benefit in this specific deployment model.

## ICAO Master List Inner Structure

The `eContent` inside the CMS envelope contains the actual ICAO Master List. Its OID is `2.23.136.1.1.2` (id-icao-mrtd-security-masterlist). The ASN.1 schema is:

```
CscaMasterList ::= SEQUENCE {
    version    INTEGER,            -- always 0
    certList   SET OF Certificate  -- the CSCA root certificates
}
```

Each `Certificate` in `certList` is a standard X.509v3 DER-encoded certificate.

### Inner vs. Outer Certificates

This is a crucial distinction:

| Type | Location in CMS | What they are | Count |
|------|----------------|---------------|-------|
| **Inner certificates** | `encapContentInfo.eContent → certList` | The actual CSCA root CAs — the Master List payload | 1 to many per country |
| **Outer certificates** | `SignedData.certificates` | The CMS envelope's signing certificates (used to sign the ML) | Usually 1-3 |

Both are X.509 certificates, both are extracted and persisted as `CertificateRecord` objects in the `root_ca` table. The distinction only matters during parsing — afterward they're treated identically.

## How cert-parser Implements This in Python

### Step 1: Load CMS Envelope (asn1crypto)

```python
from asn1crypto import cms

content_info = cms.ContentInfo.load(raw_bytes)
signed_data = content_info['content']  # → SignedData
```

`asn1crypto` is the ONLY Python library that properly exposes the `certificates` and `crls` fields from `SignedData`. The `cryptography` library can verify CMS signatures but doesn't give access to these fields.

### Step 2: Extract Outer Certificates

```python
certs_set = signed_data['certificates']  # CertificateSet (optional)
for cert_choice in certs_set:
    der_bytes = cert_choice.chosen.dump()  # DER-encoded X.509
```

`cert_choice.chosen` resolves the ASN.1 CHOICE (a certificate can be one of several types — we always get `Certificate`). `.dump()` serializes back to DER bytes.

### Step 3: Extract Inner Certificates (Master List)

```python
encap_content = signed_data['encap_content_info']['content']
inner_bytes = encap_content.native  # raw OCTET STRING bytes

# Parse as CscaMasterList (custom ASN.1 schema)
master_list = _CscaMasterList.load(inner_bytes)
cert_list = master_list['cert_list']  # SET OF Certificate

for asn1_cert in cert_list:
    der_bytes = asn1_cert.dump()
```

The custom ASN.1 classes `_CscaMasterList` and `_CertificateSet` are defined in `cms_parser.py` to match the ICAO specification:

```python
class _CertificateSet(core.SetOf):
    _child_spec = asn1_x509.Certificate

class _CscaMasterList(core.Sequence):
    _fields = [
        ("version", core.Integer),
        ("cert_list", _CertificateSet),
    ]
```

### Step 4: Extract CRLs

```python
crls_set = signed_data['crls']  # RevocationInfoChoices (optional)
for crl_choice in crls_set:
    crl_der = crl_choice.chosen.dump()  # DER-encoded CRL
```

CRLs are optional — many Master Lists don't include them. The Colombia Master List (`ml_co.bin`) includes CRLs with revoked entries.

### Step 5: Extract X.509 Metadata (cryptography)

For each DER-encoded certificate, `cryptography` extracts metadata:

```python
from cryptography import x509

cert = x509.load_der_x509_certificate(der_bytes)
issuer = cert.issuer.rfc4514_string()       # "C=DE,O=bsi,CN=..."
x500_issuer = cert.issuer.public_bytes()     # raw DER of issuer Name
serial = hex(cert.serial_number)             # "0x1a2b3c..."
ski = cert.extensions.get_extension_for_class(x509.SubjectKeyIdentifier)
aki = cert.extensions.get_extension_for_class(x509.AuthorityKeyIdentifier)
```

### Step 6: Parse CRL Entries

Each CRL is also parsed with `cryptography`:

```python
crl_obj = x509.load_der_x509_crl(crl_der)
issuer = crl_obj.issuer.rfc4514_string()
country = _extract_country_from_issuer(crl_obj.issuer)  # C= attribute

for revoked_cert in crl_obj:
    serial = hex(revoked_cert.serial_number)
    date = revoked_cert.revocation_date_utc  # timezone-aware datetime
    reason = revoked_cert.extensions.get_extension_for_class(x509.CRLReason)
```

## X.509 Certificate Extensions

Not all certificates have all extensions. cert-parser handles this gracefully:

| Extension | OID | Purpose | Handling if absent |
|-----------|-----|---------|-------------------|
| Subject Key Identifier (SKI) | 2.5.29.14 | Unique fingerprint of the certificate's public key | `None` + warning log |
| Authority Key Identifier (AKI) | 2.5.29.35 | Fingerprint of the issuer's public key (links to parent cert) | `None` (silent) |
| CRL Reason | 2.5.29.21 | Why a certificate was revoked | `None` (silent) |

The `_extract_ski()` and `_extract_aki()` functions use PEP 758 bare-comma except syntax:

```python
try:
    ext = cert.extensions.get_extension_for_class(x509.SubjectKeyIdentifier)
    return ext.value.digest.hex()
except ExtensionNotFound, ValueError:  # PEP 758 — catches BOTH types
    return None
```

## Real-World Data Characteristics

From parsing all 24 ICAO Master List fixtures in the test suite:

- **File sizes**: 2 KB (Seychelles, 1 cert) to 957 KB (Germany, 200+ certs)
- **Inner certificates**: 1 to 200+ per country
- **Outer certificates**: 0 to 3 per CMS envelope (signers)
- **CRLs**: Usually 0; Colombia includes CRLs with 15+ revoked entries
- **Missing SKI**: Some older/smaller country certificates lack the SKI extension
- **Missing AKI**: Some self-signed root CAs have no AKI (they ARE the authority)

## OIDs Reference

| OID | Name | Where it appears |
|-----|------|-----------------|
| `1.2.840.113549.1.7.2` | signedData | ContentInfo.contentType |
| `2.23.136.1.1.2` | id-icao-mrtd-security-masterlist | encapContentInfo.eContentType |
| `2.5.29.14` | subjectKeyIdentifier | X.509 extension |
| `2.5.29.35` | authorityKeyIdentifier | X.509 extension |
| `2.5.29.21` | cRLReason | Revoked entry extension |
| `2.5.4.6` | countryName (C=) | X.509 issuer attribute |
