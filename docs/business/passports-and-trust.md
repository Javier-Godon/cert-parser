# Passports and Trust

## How Biometric Passports Work

Since 2006, most countries issue **biometric passports** (also called e-Passports). These passports contain a small chip (like the one in a credit card) that stores:

- The holder's personal data (name, date of birth, nationality)
- A digital photo of the holder
- Optionally: fingerprints, iris scans
- **A digital signature** proving all this data is authentic

The chip can be read wirelessly by border control equipment. But reading data from a chip isn't enough — the system needs to know: **can I trust this data?**

## The Trust Problem

Anyone with the right equipment could create a fake chip with fake data. The signature is what prevents this. Here's how it works:

### The Signing Chain

```
COUNTRY GOVERNMENT
   │
   └── issues a ROOT CERTIFICATE (CSCA)
          "I am Germany, and I vouch for my document signers"
          │
          └── signs a DOCUMENT SIGNER CERTIFICATE (DSC)
                 "This signing machine is authorized by Germany"
                 │
                 └── signs the PASSPORT CHIP DATA
                        "This person's data is authentic"
```

When border control reads a passport chip:

1. It checks the **data signature** against the **Document Signer Certificate** (DSC)
2. It checks the **DSC** against the country's **Root Certificate** (CSCA)
3. It checks whether the DSC has been **revoked** (e.g., the signing machine was compromised)

If all checks pass → the passport data is trusted.

### What If You Don't Have the Certificates?

Without the root certificates and DSCs, you can't verify any passport. You'd have to either:
- Trust the data blindly (insecure)
- Reject every passport (impractical)

This is why cert-parser exists — it ensures the verification system always has the latest certificates.

## ICAO — The International Authority

**ICAO** (International Civil Aviation Organization) is a United Nations agency that sets standards for international aviation, including passport security.

ICAO maintains the **Public Key Directory (PKD)** — a central repository where countries publish:

| What | Description |
|------|-------------|
| **Master Lists** | Bundles of root certificates (CSCAs) per country |
| **DSCs** | Individual Document Signer Certificates |
| **CRLs** | Certificate Revocation Lists (which certs are no longer valid) |

### Master Lists

A Master List is a country's official publication of its trusted root certificates. Each country maintains its own Master List. ICAO collects them all and makes them available through the PKD.

For example:
- Germany's Master List contains ~20 root certificates
- Seychelles' Master List contains 1 root certificate
- Some countries have 50+ certificates (they rotate keys periodically)

### The PKD (Public Key Directory)

The PKD is ICAO's distribution system. It works like this:

```
COUNTRY A ──publishes──→ PKD ──distributes──→ BORDER CONTROL SYSTEMS
COUNTRY B ──publishes──→     ──distributes──→ WORLDWIDE
COUNTRY C ──publishes──→     ──distributes──→
    ...
```

Countries who **participate** in the PKD:
- Upload their Master Lists, DSCs, and CRLs
- Get access to ALL other participating countries' certificates
- Connect via LDAP (a directory protocol) or download LDIF dumps

Countries who **don't participate**:
- Must distribute certificates through bilateral agreements
- Their passports may be harder to verify in non-partner countries

cert-parser downloads data from a REST service that provides ICAO PKD content.

## Why Multiple Certificates Per Country?

Countries issue multiple root certificates for several reasons:

1. **Key rotation** — old keys expire, new keys are issued
2. **Algorithm upgrades** — moving from RSA to ECDSA, for example
3. **Disaster recovery** — backup keys in case the primary is compromised
4. **Organizational changes** — the issuing authority restructures

All versions remain in the Master List because old passports (valid for 10 years) were signed with old keys. You need the old certificates to verify old passports.

## What "Trust" Means in Practice

When we say a certificate is "trusted," we mean:

1. It was **published by ICAO** through the official PKD
2. It **hasn't been revoked** (isn't on any CRL)
3. It **chains back to a known root** (we can trace DSC → CSCA)

cert-parser handles items 1 and 2. Item 3 is performed by the downstream passport verification system that reads from cert-parser's database.
