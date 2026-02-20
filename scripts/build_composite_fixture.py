"""
Build a composite CMS/PKCS#7 SignedData fixture for testing.

Infrastructure script — generates tests/fixtures/ml_composite.bin by combining
real ICAO data from multiple countries into a single CMS envelope that exercises
ALL parser code paths (inner certs, outer certs, CRLs, revoked entries).

Sources:
  - Inner CSCA certs: ml_sc.bin (Seychelles), ml_bd.bin (Bangladesh), ml_bw.bin (Botswana)
  - Outer ML signer certs: one per source ML
  - CRL: crl_sample.der (Colombia, 15 revoked entries)

Output structure:
  ContentInfo (signedData)
  └── SignedData
      ├── encapContentInfo (OID 2.23.136.1.1.2 = ICAO Master List)
      │   └── CscaMasterList { version=0, certList=[5 CSCA certs] }
      ├── certificates [3 outer ML signer certs]
      └── crls [1 Colombia CRL, 15 revoked entries]

Usage:
  python scripts/build_composite_fixture.py
"""

from __future__ import annotations

from pathlib import Path

from asn1crypto import cms, core
from asn1crypto import x509 as asn1_x509

FIXTURES_DIR = Path(__file__).parent.parent / "tests" / "fixtures"
SOURCE_MLS = ["ml_sc.bin", "ml_bd.bin", "ml_bw.bin"]
CRL_FILE = "crl_sample.der"
OUTPUT_FILE = "ml_composite.bin"


# ─── ICAO ASN.1 schema (mirrors cms_parser.py) ───


class _CertificateSet(core.SetOf):  # type: ignore[misc]
    _child_spec = asn1_x509.Certificate


class _CscaMasterList(core.Sequence):  # type: ignore[misc]
    _fields = [
        ("version", core.Integer),
        ("cert_list", _CertificateSet),
    ]


def _extract_certs_from_ml(ml_path: Path) -> tuple[list[bytes], bytes | None]:
    """Extract inner cert DERs and one outer cert DER from a Master List .bin."""
    data = ml_path.read_bytes()
    ci = cms.ContentInfo.load(data)
    sd = ci["content"]

    inner_bytes = sd["encap_content_info"]["content"].native
    ml = _CscaMasterList.load(inner_bytes)
    inner_ders = [cert.dump() for cert in ml["cert_list"]]

    outer_der = None
    if sd["certificates"]:
        for cert_choice in sd["certificates"]:
            outer_der = cert_choice.chosen.dump()
            break

    return inner_ders, outer_der


def build_composite() -> Path:
    """Build the composite CMS fixture and return the output path."""
    # Gather certs from multiple countries
    all_inner_ders: list[bytes] = []
    outer_ders: list[bytes] = []

    for ml_name in SOURCE_MLS:
        inner, outer = _extract_certs_from_ml(FIXTURES_DIR / ml_name)
        all_inner_ders.extend(inner)
        if outer:
            outer_ders.append(outer)

    # Load real CRL
    crl_der = (FIXTURES_DIR / CRL_FILE).read_bytes()

    # Build CscaMasterList inner content
    cert_set = _CertificateSet(
        [asn1_x509.Certificate.load(d) for d in all_inner_ders]
    )
    master_list = _CscaMasterList({"version": 0, "cert_list": cert_set})
    inner_content_bytes = master_list.dump()

    # Build CMS envelope
    certs = cms.CertificateSet()
    for der in outer_ders:
        certs.append(cms.CertificateChoices.load(der))

    crls = cms.RevocationInfoChoices()
    crls.append(cms.RevocationInfoChoice.load(crl_der))

    signed_data = cms.SignedData({
        "version": "v3",
        "digest_algorithms": cms.DigestAlgorithms([
            cms.DigestAlgorithm({"algorithm": "sha256"}),
        ]),
        "encap_content_info": cms.EncapsulatedContentInfo({
            "content_type": "2.23.136.1.1.2",
            "content": core.ParsableOctetString(inner_content_bytes),
        }),
        "certificates": certs,
        "crls": crls,
        "signer_infos": cms.SignerInfos([]),
    })

    content_info = cms.ContentInfo({
        "content_type": "signed_data",
        "content": signed_data,
    })

    output_path = FIXTURES_DIR / OUTPUT_FILE
    composite_bin = content_info.dump()
    output_path.write_bytes(composite_bin)

    print(f"✓ {output_path} ({len(composite_bin)} bytes)")
    print(f"  Inner CSCA certs: {len(all_inner_ders)}")
    print(f"  Outer ML signers: {len(outer_ders)}")
    print(f"  CRLs: 1 ({len(crl_der)} bytes)")
    return output_path


if __name__ == "__main__":
    build_composite()
