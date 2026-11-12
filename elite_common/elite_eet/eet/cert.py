"""Reading of CA EET cashier certificates (.p12)."""
from dataclasses import dataclass
from datetime import datetime

from cryptography import x509
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

from . import paths


class CertError(Exception):
    """Certificate problem; the message is shown to the user (Czech)."""


@dataclass(frozen=True)
class CertInfo:
    cn: str
    issuer: str
    serial: str
    valid_from: datetime
    valid_to: datetime
    environment: str  # "playground" | "production"


def _load_ca(path):
    with open(path, "rb") as f:
        data = f.read()
    if b"-----BEGIN" in data:
        return x509.load_pem_x509_certificate(data)
    return x509.load_der_x509_certificate(data)


def _issuer_environments():
    return {
        _load_ca(paths.CA_SUB_PLAYGROUND).subject: "playground",
        _load_ca(paths.CA_SUB_PRODUCTION).subject: "production",
    }


def load_p12(data, password):
    """Return (private_key, certificate, CertInfo) from .p12 bytes."""
    try:
        key, certificate, _chain = pkcs12.load_key_and_certificates(data, password)
    except Exception:  # noqa: BLE001 - any parsing failure means unusable file or password
        raise CertError("Heslo k certifikátu nesouhlasí, nebo soubor není certifikát .p12.") from None
    if key is None or certificate is None:
        raise CertError("Soubor .p12 neobsahuje certifikát se soukromým klíčem.")
    environment = _issuer_environments().get(certificate.issuer)
    if not environment:
        raise CertError("Certifikát nevydala CA EET.")
    cn_attrs = certificate.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    info = CertInfo(
        cn=cn_attrs[0].value if cn_attrs else "",
        issuer=certificate.issuer.rfc4514_string(),
        serial=format(certificate.serial_number, "X"),
        valid_from=certificate.not_valid_before,
        valid_to=certificate.not_valid_after,
        environment=environment,
    )
    return key, certificate, info
