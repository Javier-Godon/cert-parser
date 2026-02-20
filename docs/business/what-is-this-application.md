# What Is This Application?

## The Short Version

**cert-parser** is a backend service that keeps a database of trusted cryptographic certificates used to verify biometric passports worldwide. It downloads official trust lists from the international aviation authority (ICAO), extracts the certificates from them, and stores everything in a PostgreSQL database.

## Why Does It Exist?

When someone presents a biometric passport at border control, the system needs to verify two things:

1. **Is the data on the chip authentic?** (Was it signed by a legitimate authority?)
2. **Has the signing certificate been revoked?** (Is the authority still trusted?)

To answer these questions, the verification system needs an up-to-date list of all trusted certificates issued by every country in the world. This is exactly what cert-parser provides — it keeps that list fresh and available in a database.

## What Does It Do?

Every few hours (configurable), cert-parser:

1. **Authenticates** with a REST service (using OAuth2 credentials)
2. **Downloads** the latest ICAO Master List file (a `.bin` file)
3. **Parses** the file to extract all certificates and revocation lists inside it
4. **Stores** everything in a PostgreSQL database, replacing any previous data

If anything goes wrong at any step (network error, invalid file, database down), the process stops safely — the previous data in the database is preserved intact.

## What Data Does It Produce?

After each successful run, the database contains:

| Table | What it holds | Example count |
|-------|--------------|:------------:|
| **Root CAs** | Trusted root certificates from countries worldwide | ~200-500 |
| **DSCs** | Document Signer Certificates (currently empty — sourced differently) | 0 |
| **CRLs** | Certificate Revocation Lists | 0-10 |
| **Revoked Certificates** | Individual certificates that have been revoked | 0-100+ |

## Who Uses This Data?

The database produced by cert-parser is consumed by downstream services that:
- Verify passport chip signatures
- Check if a document signer certificate is still valid
- Build trust chains from document signers back to country root CAs

cert-parser itself doesn't verify passports — it provides the **trust material** that other systems need to do so.

## How Often Does It Run?

By default, every **6 hours**. This is configurable. On startup, it runs once immediately and then enters the scheduled loop.

## Is It Safe?

Yes. The design prioritizes data safety:
- If the download fails → old data remains in the database
- If parsing fails → old data remains in the database
- If the database write fails → old data remains in the database (guaranteed by database transactions)
- The application never leaves the database in a partial or inconsistent state
