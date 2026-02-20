# Business Documentation — cert-parser

> This documentation explains what cert-parser does and why, for people who don't need to read or write code.

## Table of Contents

| Document | Description |
|----------|-------------|
| [What Is This Application?](what-is-this-application.md) | High-level overview — what cert-parser does and why it exists |
| [Passports and Trust](passports-and-trust.md) | How biometric passports work, what trust anchors are, and why certificates matter |
| [The Files We Process](the-files-we-process.md) | What `.bin` files are, what they contain, and where they come from |
| [Certificates Explained](certificates-explained.md) | Types of certificates (CSCA, DSC), their metadata, and what each field means |
| [Revocation — When Certificates Go Bad](revocation.md) | What CRLs are, why certificates get revoked, and how we track revocations |
| [How The Application Works](how-the-application-works.md) | The complete processing cycle: download → parse → store → repeat |

## One-Sentence Summary

**cert-parser** downloads cryptographic trust lists from the international aviation authority (ICAO), extracts the certificates inside them, and saves everything to a database — automatically, every few hours.
