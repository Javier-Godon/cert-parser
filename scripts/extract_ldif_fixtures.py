#!/usr/bin/env python3
"""
Extract test fixtures from ICAO PKD LDIF files.

Parses LDIF format and produces:
  - Master List CMS/PKCS#7 .bin blobs from icaopkd-002 (pkdMasterListContent)
  - Sample DER certificates from icaopkd-001 (userCertificate;binary)
  - Synthetic fixtures (corrupt, empty) for error-path testing

LDIF format recap:
  - Entries separated by blank lines
  - Continuation lines start with exactly one space
  - `attr:: value` means base64-encoded
  - `attr: value` means plain UTF-8
"""
from __future__ import annotations

import base64
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class LdifEntry:
    """A single LDIF entry (dn + attributes)."""

    dn: str = ""
    attributes: dict[str, list[str]] = field(default_factory=dict)

    @property
    def country(self) -> str:
        """Extract country code from DN (e.g., c=FR → FR)."""
        match = re.search(r",c=([A-Z]{2}),", self.dn)
        if match:
            return match.group(1)
        # Try direct attribute
        if "c" in self.attributes:
            return self.attributes["c"][0]
        return "XX"

    @property
    def cn(self) -> str:
        if "cn" in self.attributes:
            return self.attributes["cn"][0]
        return ""


def _unfold_continuation_lines(lines: list[str]) -> list[str]:
    """
    Join LDIF continuation lines with their preceding line.

    RFC 2849: A continuation line starts with exactly one space.
    The space is stripped and the rest is appended to the prior line.
    """
    unfolded: list[str] = []
    for line in lines:
        if line.startswith(" ") and unfolded:
            unfolded[-1] += line[1:]
        else:
            unfolded.append(line)
    return unfolded


def _parse_attribute_line(
    line: str,
    entry: LdifEntry,
) -> None:
    """Parse a single unfolded LDIF attribute line into the entry."""
    if line.startswith("#") or line.startswith("version:"):
        return

    # Base64 value (double colon)
    if ":: " in line or line.endswith("::"):
        sep_idx = line.index("::")
        attr_name = line[:sep_idx].strip()
        attr_value = line[sep_idx + 2 :].strip()
        entry.attributes.setdefault(attr_name + "::b64", []).append(attr_value)
    elif ": " in line:
        sep_idx = line.index(": ")
        attr_name = line[:sep_idx].strip()
        attr_value = line[sep_idx + 2 :].strip()
        if attr_name == "dn":
            entry.dn = attr_value
        else:
            entry.attributes.setdefault(attr_name, []).append(attr_value)


def _parse_ldif_entry(raw_lines: list[str]) -> LdifEntry | None:
    """Parse a group of raw LDIF lines into a single LdifEntry."""
    if not raw_lines:
        return None

    unfolded = _unfold_continuation_lines(raw_lines)
    entry = LdifEntry()
    for line in unfolded:
        _parse_attribute_line(line, entry)
    return entry if entry.dn else None


def parse_ldif(filepath: Path) -> list[LdifEntry]:
    """Parse an LDIF file into a list of entries."""
    entries: list[LdifEntry] = []
    current_lines: list[str] = []

    with open(filepath) as f:
        for raw_line in f:
            line = raw_line.rstrip("\n\r")
            if line == "":
                entry = _parse_ldif_entry(current_lines)
                if entry:
                    entries.append(entry)
                current_lines = []
            else:
                current_lines.append(line)

    # Last entry (no trailing blank line)
    entry = _parse_ldif_entry(current_lines)
    if entry:
        entries.append(entry)

    return entries


def _decode_master_list_entry(entry: LdifEntry) -> bytes | None:
    """Decode the base64 pkdMasterListContent from an LDIF entry."""
    b64_key = "pkdMasterListContent::b64"
    if b64_key not in entry.attributes:
        return None
    try:
        return base64.b64decode(entry.attributes[b64_key][0])
    except Exception as e:
        print(f"  ⚠ Failed to decode ML for {entry.country}: {e}")
        return None


def extract_master_lists(
    ldif_path: Path,
    output_dir: Path,
    max_entries: int = 27,
) -> int:
    """Extract Master List CMS/PKCS#7 blobs from LDIF."""
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"  Parsing {ldif_path.name} ...")
    entries = parse_ldif(ldif_path)
    print(f"  Found {len(entries)} LDIF entries total")

    sizes: list[tuple[str, int, str]] = []

    for entry in entries:
        raw_bytes = _decode_master_list_entry(entry)
        if raw_bytes is None:
            continue

        country = entry.country.lower()
        filename = f"ml_{country}.bin"
        (output_dir / filename).write_bytes(raw_bytes)
        sizes.append((filename, len(raw_bytes), entry.cn))

        if len(sizes) >= max_entries:
            break

    # Print summary sorted by size
    sizes.sort(key=lambda x: x[1])
    for filename, size, cn in sizes:
        print(f"  ✓ {filename:30s} {size / 1024:8.1f} KB  ({cn})")

    return len(sizes)


def _write_certificate(
    b64_lines: list[str],
    country: str,
    serial: str,
    output_dir: Path,
) -> bool:
    """Decode and write a single DER certificate from base64 lines."""
    b64_data = "".join(b64_lines)
    try:
        raw_bytes = base64.b64decode(b64_data)
    except Exception as e:
        print(f"  ⚠ Failed to decode cert: {e}")
        return False

    filename = f"cert_{country.lower()}_{serial[:8]}.der"
    (output_dir / filename).write_bytes(raw_bytes)
    print(f"  ✓ {filename} ({len(raw_bytes)} bytes)")
    return True


def extract_certificates(
    ldif_path: Path,
    output_dir: Path,
    max_entries: int = 5,
) -> int:
    """
    Extract individual DER certificates from LDIF (first N entries).

    Uses a streaming parser for efficiency (the LDIF file can be 1.3M+ lines).
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"  Parsing {ldif_path.name} (first {max_entries} certs) ...")

    count = 0
    in_cert = False
    b64_lines: list[str] = []
    current_country = "XX"
    current_sn = ""

    with open(ldif_path) as f:
        for raw_line in f:
            line = raw_line.rstrip("\n\r")

            # Track metadata from plain-text attributes
            if line.startswith("c: "):
                current_country = line[3:].strip()
            elif line.startswith("sn: "):
                current_sn = line[4:].strip()

            # Start of a new certificate block
            elif line.startswith("userCertificate;binary:: "):
                in_cert = True
                b64_lines = [line.split("::", 1)[1].strip()]

            # Continuation of base64 block
            elif in_cert and line.startswith(" "):
                b64_lines.append(line[1:])

            # End of base64 block (any non-continuation line)
            elif in_cert:
                if _write_certificate(
                    b64_lines, current_country, current_sn, output_dir,
                ):
                    count += 1
                in_cert = False
                b64_lines = []
                if count >= max_entries:
                    break

                # Reset metadata on entry boundary
                if not line:
                    current_country = "XX"
                    current_sn = ""

    return count


def create_synthetic_fixtures(output_dir: Path) -> None:
    """Create synthetic fixtures for error-path testing."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Corrupt bytes — not valid ASN.1/CMS
    (output_dir / "corrupt.bin").write_bytes(b"this-is-not-valid-cms-data-at-all")
    print("  ✓ corrupt.bin (33 bytes)")

    # Empty file
    (output_dir / "empty.bin").write_bytes(b"")
    print("  ✓ empty.bin (0 bytes)")

    # Truncated — valid ASN.1 tag but truncated length
    (output_dir / "truncated.bin").write_bytes(b"\x30\x83\x01\x00")
    print("  ✓ truncated.bin (4 bytes)")


def main() -> None:
    resources = Path("src/cert_parser/resources")
    fixtures = Path("tests/fixtures")

    print("=" * 65)
    print(" Extracting ICAO PKD test fixtures from LDIF files")
    print("=" * 65)

    print("\n📦 Master Lists (CMS/PKCS#7 blobs from icaopkd-002):")
    ml_count = extract_master_lists(
        resources / "icaopkd-002-complete-000338.ldif",
        fixtures,
    )
    print(f"  Total: {ml_count} Master List fixtures\n")

    print("📦 DSC Certificates (DER from icaopkd-001, first 5):")
    cert_count = extract_certificates(
        resources / "icaopkd-001-complete-009778.ldif",
        fixtures,
    )
    print(f"  Total: {cert_count} certificate fixtures\n")

    print("📦 Synthetic fixtures (error paths):")
    create_synthetic_fixtures(fixtures)

    total = ml_count + cert_count + 3
    print(f"\n✅ All fixtures written to: {fixtures}/")
    print(f"   {ml_count} MLs + {cert_count} certs + 3 synthetic = {total} files")


if __name__ == "__main__":
    main()
