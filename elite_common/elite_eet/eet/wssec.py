"""WS-Security signature of EET 2.0 SOAP messages.

The layout follows the signed sample messages published by the Financial
Administration: only soap:Body is signed, exclusive C14N, SHA-256 digest,
RSA-SHA256 signature, certificate as BinarySecurityToken (X509v3).
"""
import base64
import hashlib
import uuid as uuid_lib

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography import x509
from lxml import etree

from .message import NS_V4, MessageError

NS_SOAP = "http://schemas.xmlsoap.org/soap/envelope/"
NS_WSSE = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
NS_WSU = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd"
NS_DS = "http://www.w3.org/2000/09/xmldsig#"
NS_EC = "http://www.w3.org/2001/10/xml-exc-c14n#"

ALG_EXC_C14N = "http://www.w3.org/2001/10/xml-exc-c14n#"
ALG_RSA_SHA256 = "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"
ALG_SHA256 = "http://www.w3.org/2001/04/xmlenc#sha256"
ENC_BASE64 = (
    "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary"
)
VT_X509 = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-x509-token-profile-1.0#X509v3"

MAX_SIZE = 12288


def _q(ns, tag):
    return f"{{{ns}}}{tag}"


def _c14n(element, prefixes):
    return etree.tostring(element, method="c14n", exclusive=True, inclusive_ns_prefixes=prefixes)


def _inclusive(parent, prefixes):
    etree.SubElement(
        parent, _q(NS_EC, "InclusiveNamespaces"), PrefixList=" ".join(prefixes), nsmap={"ec": NS_EC}
    )


def sign_envelope(trzba, private_key, certificate):
    """Wrap the Trzba element in a signed SOAP envelope and return its bytes."""
    token = uuid_lib.uuid4().hex.upper()
    x509_id, body_id = f"X509-{token}1", f"id-{token}2"

    root = etree.Element(_q(NS_SOAP, "Envelope"), nsmap={"soapenv": NS_SOAP, "v4": NS_V4})
    header = etree.SubElement(root, _q(NS_SOAP, "Header"))
    security = etree.SubElement(header, _q(NS_WSSE, "Security"), nsmap={"wsse": NS_WSSE, "wsu": NS_WSU})
    bst = etree.SubElement(
        security, _q(NS_WSSE, "BinarySecurityToken"), EncodingType=ENC_BASE64, ValueType=VT_X509
    )
    bst.set(_q(NS_WSU, "Id"), x509_id)
    bst.text = base64.b64encode(certificate.public_bytes(serialization.Encoding.DER)).decode()

    signature = etree.SubElement(security, _q(NS_DS, "Signature"), Id=f"SIG-{token}3", nsmap={"ds": NS_DS})
    signed_info = etree.SubElement(signature, _q(NS_DS, "SignedInfo"))
    c14n_method = etree.SubElement(signed_info, _q(NS_DS, "CanonicalizationMethod"), Algorithm=ALG_EXC_C14N)
    _inclusive(c14n_method, ["soapenv", "v4"])
    etree.SubElement(signed_info, _q(NS_DS, "SignatureMethod"), Algorithm=ALG_RSA_SHA256)
    reference = etree.SubElement(signed_info, _q(NS_DS, "Reference"), URI=f"#{body_id}")
    transforms = etree.SubElement(reference, _q(NS_DS, "Transforms"))
    transform = etree.SubElement(transforms, _q(NS_DS, "Transform"), Algorithm=ALG_EXC_C14N)
    _inclusive(transform, ["v4"])
    etree.SubElement(reference, _q(NS_DS, "DigestMethod"), Algorithm=ALG_SHA256)
    digest_value = etree.SubElement(reference, _q(NS_DS, "DigestValue"))
    signature_value = etree.SubElement(signature, _q(NS_DS, "SignatureValue"))
    key_info = etree.SubElement(signature, _q(NS_DS, "KeyInfo"), Id=f"KI-{token}4")
    str_el = etree.SubElement(key_info, _q(NS_WSSE, "SecurityTokenReference"))
    str_el.set(_q(NS_WSU, "Id"), f"STR-{token}5")
    etree.SubElement(str_el, _q(NS_WSSE, "Reference"), URI=f"#{x509_id}", ValueType=VT_X509)

    body = etree.SubElement(root, _q(NS_SOAP, "Body"), nsmap={"wsu": NS_WSU})
    body.set(_q(NS_WSU, "Id"), body_id)
    body.append(trzba)
    etree.cleanup_namespaces(root, keep_ns_prefixes=["soapenv", "v4"])

    # Canonicalize a tree parsed from the serialized bytes: lxml's exclusive C14N of a
    # freshly built tree does not always match the canonical form of the message the
    # server receives (seen as EET error 4 on the first message of a process).
    root = etree.fromstring(etree.tostring(root))
    body = root.find(_q(NS_SOAP, "Body"))
    signed_info = root.find(f".//{_q(NS_DS, 'SignedInfo')}")
    digest_value = signed_info.find(f".//{_q(NS_DS, 'DigestValue')}")
    signature_value = signed_info.getparent().find(_q(NS_DS, "SignatureValue"))

    digest = hashlib.sha256(_c14n(body, ["v4"])).digest()
    digest_value.text = base64.b64encode(digest).decode()
    signed = private_key.sign(_c14n(signed_info, ["soapenv", "v4"]), padding.PKCS1v15(), hashes.SHA256())
    signature_value.text = base64.b64encode(signed).decode()

    envelope = etree.tostring(root)
    if len(envelope) > MAX_SIZE:
        raise MessageError("Zpráva EET je větší než 12 kB.")
    return envelope


def _prefixes(element):
    found = element.find(_q(NS_EC, "InclusiveNamespaces"))
    return found.get("PrefixList", "").split() if found is not None else None


def verify_envelope(xml):
    """Check digest and signature of a signed EET envelope."""
    try:
        root = etree.fromstring(xml)
        signed_info = root.find(f".//{_q(NS_DS, 'SignedInfo')}")
        reference = signed_info.find(_q(NS_DS, "Reference"))
        body_id = reference.get("URI").lstrip("#")
        body = root.find(f"{_q(NS_SOAP, 'Body')}[@{_q(NS_WSU, 'Id')}='{body_id}']")
        transform = reference.find(f"{_q(NS_DS, 'Transforms')}/{_q(NS_DS, 'Transform')}")
        digest = hashlib.sha256(_c14n(body, _prefixes(transform))).digest()
        if base64.b64encode(digest).decode() != reference.findtext(_q(NS_DS, "DigestValue")).strip():
            return False
        c14n_method = signed_info.find(_q(NS_DS, "CanonicalizationMethod"))
        signature = signed_info.getparent()
        bst = root.find(f".//{_q(NS_WSSE, 'BinarySecurityToken')}")
        certificate = x509.load_der_x509_certificate(base64.b64decode(bst.text))
        certificate.public_key().verify(
            base64.b64decode(signature.findtext(_q(NS_DS, "SignatureValue"))),
            _c14n(signed_info, _prefixes(c14n_method)),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        return True
    except (InvalidSignature, AttributeError, ValueError, etree.XMLSyntaxError):
        return False
