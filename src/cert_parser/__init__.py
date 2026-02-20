"""
cert_parser — ICAO Master List certificate parser.

Downloads CMS/PKCS#7 binary bundles from a REST service,
extracts X.509 certificates and CRLs, and stores them in PostgreSQL.

Built on the Railway-Oriented Programming (ROP) framework for
explicit, composable, functional error handling.
"""

__version__ = "0.1.0"
