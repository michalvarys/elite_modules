"""HTTP transport to the EET 2.0 service and parsing of its answers."""
from dataclasses import dataclass, field
from datetime import datetime, timezone

import requests
from lxml import etree

from .message import NS_V4

URLS = {
    "playground": "https://pg.trzbyeet.gov.cz/eet/services/EETServiceSOAP/v4",
    "production": "https://trzbyeet.gov.cz/eet/services/EETServiceSOAP/v4",
}
SOAP_ACTION = "http://fs.gov.cz/eet/OdeslaniTrzby"


@dataclass
class Result:
    kind: str  # "pok" | "verified" | "temporary" | "critical" | "no_response"
    pok: str | None = None
    test: bool = False
    code: int | None = None
    message: str = ""
    warnings: list = field(default_factory=list)
    received_at: datetime | None = None
    http_status: int | None = None
    transaction_id: str | None = None
    response_xml: bytes | None = None


def _utc(value):
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def parse_response(body, http_status, headers):
    """Turn the service answer into a Result; anything unreadable is "no_response"."""
    try:
        return _parse_response(body, http_status, headers)
    except (AttributeError, TypeError, ValueError):
        return Result(
            "no_response",
            message="Neočekávaná odpověď (HTTP %s)." % http_status,
            http_status=http_status,
            transaction_id=(headers or {}).get("X-Global-Transaction-Id"),
            response_xml=body,
        )


def _parse_response(body, http_status, headers):
    transaction_id = (headers or {}).get("X-Global-Transaction-Id")
    base = dict(http_status=http_status, transaction_id=transaction_id, response_xml=body)
    try:
        root = etree.fromstring(body)
    except (etree.XMLSyntaxError, ValueError):
        return Result("no_response", message="Nečitelná odpověď (HTTP %s)." % http_status, **base)
    answer = root.find(f".//{{{NS_V4}}}Odpoved")
    if answer is None:
        fault = root.findtext(".//faultstring") or ""
        return Result("no_response", message=("SOAP Fault: " + fault).strip(), **base)
    head = answer.find(f"{{{NS_V4}}}Hlavicka")
    warnings = [
        (int(w.get("kod_varov")), (w.text or "").strip()) for w in answer.findall(f"{{{NS_V4}}}Varovani")
    ]
    confirmation = answer.find(f"{{{NS_V4}}}Potvrzeni")
    if confirmation is not None:
        return Result(
            "pok",
            pok=confirmation.get("pok"),
            test=confirmation.get("test") == "true",
            warnings=warnings,
            received_at=_utc(head.get("dat_prij")),
            **base,
        )
    error = answer.find(f"{{{NS_V4}}}Chyba")
    code = int(error.get("kod"))
    if code == 0:
        kind = "verified"
    elif code < 0:
        kind = "temporary"
    else:
        kind = "critical"
    return Result(
        kind,
        test=error.get("test") == "true",
        code=code,
        message=(error.text or "").strip(),
        warnings=warnings,
        received_at=_utc(head.get("dat_odmit")),
        **base,
    )


def send(url, envelope, timeout, post=requests.post):
    """POST one signed envelope; network problems become "no_response"."""
    headers = {"Content-Type": "text/xml; charset=utf-8", "SOAPAction": SOAP_ACTION}
    try:
        response = post(url, data=envelope, headers=headers, timeout=(timeout, timeout))
    except requests.RequestException as e:
        return Result("no_response", message="Bez odpovědi: %s" % type(e).__name__)
    return parse_response(response.content, response.status_code, response.headers)
