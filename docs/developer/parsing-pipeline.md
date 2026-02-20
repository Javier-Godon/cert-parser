# Parsing Pipeline — Step-by-Step Extraction

## End-to-End Data Flow

```
REST Services
     │
     ▼ OpenID Connect access token (password grant)
HttpAccessTokenProvider.acquire_token()
     │ Result[str]
     ▼
HttpSfcTokenProvider.acquire_token(access_token)
     │ Result[str]   ← SFC service token
     ▼
_build_credentials(access_token, sfc_token)
     │ Result[AuthCredentials]   ← both tokens packaged
     ▼
HttpBinaryDownloader.download(credentials)
     │ Result[bytes]   ← raw .bin file (CMS/PKCS#7 envelope)
     │   (dual headers: Authorization + x-sfc-authorization)
     ▼
CmsMasterListParser.parse(raw_bin)
     │ Result[MasterListPayload]
     │   ├── root_cas: list[CertificateRecord]      (inner + outer certs)
     │   ├── dscs: list[CertificateRecord]           (currently empty)
     │   ├── crls: list[CrlRecord]                   (DER-encoded CRLs)
     │   └── revoked_certificates: list[RevokedCertificateRecord]
     ▼
PsycopgCertificateRepository.store(payload)
     │ Result[int]   ← total rows stored
     ▼
  Done (success or failure)
```

The pipeline is orchestrated by `run_pipeline()` in `pipeline.py`, which chains stages via `flat_map`. A failure at any stage short-circuits the rest — no downstream stages execute.

## Stage 1: Access Token Acquisition

**Adapter**: `HttpAccessTokenProvider` in `http_client.py`

**What happens**:
1. POST to `AUTH_URL` with `grant_type=password`, `client_id`, `client_secret`, `username`, `password` (OpenID Connect password grant)
2. Parse the response JSON for `access_token`
3. Return `Result.success(token)` or `Result.failure(AUTHENTICATION_ERROR, ...)`

**Retry behavior**: tenacity retries up to 3 times with exponential backoff (0.1s → 30s) on `httpx.TimeoutException` and `httpx.NetworkError`. Non-retryable errors (401, 403, 500) fail immediately.

**Error wrapping**: The `_do_token_request()` method may raise exceptions — `Result.from_computation()` catches them and converts to `Result.failure(AUTHENTICATION_ERROR, ...)`.

## Stage 2: SFC Token Acquisition

**Adapter**: `HttpSfcTokenProvider` in `http_client.py`

**What happens**:
1. POST to `LOGIN_URL` with `Authorization: Bearer {access_token}` header and JSON body `{"borderPostId": INT, "boxId": INT, "passengerControlType": INT}`
2. Read the response text as the SFC token
3. Return `Result.success(sfc_token)` or `Result.failure(AUTHENTICATION_ERROR, ...)`

The helper function `_build_credentials()` in `pipeline.py` combines both tokens into an `AuthCredentials` value object that the downloader requires.

**Retry behavior**: Same tenacity retry as access token acquisition (3 attempts, exponential backoff, transient errors only).

## Stage 3: Binary Download

**Adapter**: `HttpBinaryDownloader` in `http_client.py`

**What happens**:
1. GET to `DOWNLOAD_URL` with `Authorization: Bearer {access_token}` and `x-sfc-authorization: Bearer {sfc_token}` headers
2. Read the full response body as bytes
3. Return `Result.success(bytes)` or `Result.failure(EXTERNAL_SERVICE_ERROR, ...)`

**Retry behavior**: Same tenacity retry as token acquisition (3 attempts, exponential backoff, transient errors only).

**Note**: The response is the complete `.bin` file in memory. Typical sizes range from 2 KB to ~1 MB. For the current ICAO data volumes, streaming is not strictly necessary, but the adapter supports it.

## Stage 4: CMS Parsing

**Adapter**: `CmsMasterListParser` in `cms_parser.py`

This is the most complex stage. The `_do_parse()` method performs five sub-steps:

### Sub-step 3.1: Load CMS ContentInfo

```python
content_info = cms.ContentInfo.load(raw_bin)
signed_data = content_info['content']
```

`asn1crypto` deserializes the raw bytes into a typed ASN.1 object graph. If the bytes are not valid ASN.1 or not a CMS SignedData, an exception is raised (caught by `from_computation`).

### Sub-step 3.2: Extract Outer Certificates

```python
outer_certs = _extract_outer_certificates(signed_data, source="icao-masterlist")
```

**Function**: `_extract_outer_certificates(signed_data, source) → list[CertificateRecord]`

- Accesses `signed_data['certificates']` — the CMS envelope's signing certificates
- If `None` (no signing certs), returns empty list
- For each `CertificateChoice`, calls `.chosen.dump()` to get DER bytes
- Each DER is converted to a `CertificateRecord` via `_der_to_certificate_record()`

### Sub-step 3.3: Extract Inner Certificates (Master List)

```python
inner_certs = _extract_inner_certificates(signed_data, source="icao-masterlist")
```

**Function**: `_extract_inner_certificates(signed_data, source) → list[CertificateRecord]`

1. Gets `encapContentInfo.eContent` — the OCTET STRING containing the Master List payload
2. Extracts `.native` to get raw bytes
3. Loads those bytes as `_CscaMasterList` (custom ICAO ASN.1 schema)
4. Iterates `cert_list` (SET OF Certificate)
5. Each certificate's DER bytes are extracted via `.dump()`
6. Converted to `CertificateRecord` via `_der_to_certificate_record()`

### Sub-step 3.4: Extract CRLs

```python
crl_records, revoked_records = _extract_crls(signed_data, source="icao-masterlist")
```

**Function**: `_extract_crls(signed_data, source) → tuple[list[CrlRecord], list[RevokedCertificateRecord]]`

1. Accesses `signed_data['crls']` — optional CRL set
2. If `None`, returns `([], [])`
3. For each CRL choice, gets DER bytes via `.chosen.dump()`
4. Each CRL is parsed by `_parse_single_crl(crl_der, source)`

**Function**: `_parse_single_crl(crl_der, source) → tuple[CrlRecord, list[RevokedCertificateRecord]]`

1. Loads the CRL via `x509.load_der_x509_crl(crl_der)`
2. Extracts issuer string and country code (from `C=` attribute)
3. Creates a `CrlRecord` with a unique UUID
4. Iterates all revoked certificate entries
5. Each revoked entry becomes a `RevokedCertificateRecord` via `_build_revoked_record()`

**Function**: `_build_revoked_record(revoked_cert, crl_id, source, country) → RevokedCertificateRecord`

1. Extracts the serial number: `hex(revoked_cert.serial_number)`
2. Tries to extract the CRLReason extension (may not exist)
3. Uses `revocation_date_utc` (timezone-aware, not the deprecated `revocation_date`)
4. Links to the parent CRL via `crl_id` (UUID foreign key)

### Sub-step 3.5: Build MasterListPayload

```python
all_root_cas = inner_certs + outer_certs

return MasterListPayload(
    root_cas=all_root_cas,
    crls=crl_records,
    revoked_certificates=revoked_records,
)
```

Inner and outer certificates are combined into a single list. The `dscs` field is currently empty — DSCs are distributed separately by the PKD, not inside Master List CMS bundles.

## Stage 5: Database Persistence

**Adapter**: `PsycopgCertificateRepository` in `repository.py`

**Pattern**: Transactional Replace (DELETE all → INSERT all in one ACID transaction)

### Why Transactional Replace?

Each pipeline execution downloads the **complete** current state of the Master List. The database should reflect exactly what was downloaded — no stale data, no partial updates. The safest approach:

1. **BEGIN** transaction
2. **DELETE** all rows from all tables (FK-safe order)
3. **INSERT** all new rows
4. **COMMIT**

If anything fails between steps 2-3, PostgreSQL automatically rolls back the entire transaction — the old data remains perfectly intact.

### FK-Safe Deletion Order

Tables must be deleted in child-first order to respect foreign key constraints:

```
1. DELETE FROM revoked_certificate_list  (references crls.id)
2. DELETE FROM crls
3. DELETE FROM dsc
4. DELETE FROM root_ca
```

### Insertion

Raw parameterized SQL (no ORM) with `%s` placeholders:

```sql
INSERT INTO root_ca (id, certificate, subject_key_identifier, authority_key_identifier,
                     issuer, x_500_issuer, source, isn, updated_at)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
```

Each `CertificateRecord`, `CrlRecord`, and `RevokedCertificateRecord` is inserted individually. The function returns the total row count.

## X.509 Metadata Extraction Detail

**Function**: `_der_to_certificate_record(der_bytes, source) → CertificateRecord`

This is where raw DER bytes become rich metadata:

| Field | How it's extracted | Type |
|-------|-------------------|------|
| `certificate` | The raw DER bytes, stored as-is | `bytes` |
| `id` | `uuid4()` — generated per extraction | `UUID` |
| `subject_key_identifier` | `cert.extensions.get_extension_for_class(SubjectKeyIdentifier).value.digest.hex()` | `str \| None` |
| `authority_key_identifier` | `cert.extensions.get_extension_for_class(AuthorityKeyIdentifier).value.key_identifier.hex()` | `str \| None` |
| `issuer` | `cert.issuer.rfc4514_string()` — e.g., `"C=DE,O=bsi,CN=..."` | `str` |
| `x_500_issuer` | `cert.issuer.public_bytes()` — raw DER-encoded X.500 Name | `bytes` |
| `source` | `"icao-masterlist"` (hardcoded) | `str` |
| `isn` | `hex(cert.serial_number)` — e.g., `"0x1a2b3c"` | `str` |
| `updated_at` | `None` (set by DB triggers or application logic if needed) | `datetime \| None` |

## Error Propagation

Each stage is wrapped with `Result.from_computation()`, which catches any exception and converts it to a typed `Result.failure()`:

| Stage | Error Code | Example Failure |
|-------|-----------|-----------------|
| Access token acquisition | `AUTHENTICATION_ERROR` | 401 Unauthorized, network timeout |
| SFC token acquisition | `AUTHENTICATION_ERROR` | 401 Unauthorized, invalid access token |
| Binary download | `EXTERNAL_SERVICE_ERROR` | 404 Not Found, connection refused |
| CMS parsing | `TECHNICAL_ERROR` | Invalid ASN.1, malformed CMS structure |
| Database storage | `DATABASE_ERROR` | Connection refused, constraint violation |

Failures propagate through the `flat_map` chain automatically — if token acquisition fails, download/parse/store are never called.

## Logging

The parser emits structured log events:

```
parser.complete  inner_certs=5  outer_certs=3  total_root_cas=8  crls=1  revoked=15
certificate.missing_ski  issuer="C=SC,..."  serial="0x1a2b"
repository.stored  root_cas=8  dscs=0  crls=1  revoked=15  total_rows=24
```

All logging uses `structlog` with key=value context — never format strings.
