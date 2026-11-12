import os
from datetime import datetime

import requests

from odoo.tests import BaseCase, tagged

from odoo.addons.elite_eet.eet import paths, transport


def read(name):
    with open(os.path.join(paths.TEST_DATA_DIR, name), "rb") as f:
        return f.read()


class FakeResponse:
    def __init__(self, body, status=200, headers=None):
        self.content = body
        self.status_code = status
        self.headers = headers or {}


@tagged("post_install", "-at_install")
class TestEetTransport(BaseCase):
    def parse(self, name, status=200):
        return transport.parse_response(read(name), status, {"X-Global-Transaction-Id": "abc123"})

    def test_pok(self):
        r = self.parse("resp_pok.xml")
        self.assertEqual(r.kind, "pok")
        self.assertTrue(r.pok.endswith("-ff"))
        self.assertTrue(r.test)
        self.assertEqual(r.warnings, [])
        self.assertIsInstance(r.received_at, datetime)
        self.assertIsNone(r.received_at.tzinfo)
        self.assertEqual(r.transaction_id, "abc123")
        self.assertEqual(r.http_status, 200)
        self.assertTrue(r.response_xml)

    def test_pok_with_warning(self):
        r = self.parse("resp_pok_warning.xml")
        self.assertEqual(r.kind, "pok")
        self.assertEqual([code for code, _text in r.warnings], [1])

    def test_verified(self):
        r = self.parse("resp_verified.xml")
        self.assertEqual(r.kind, "verified")
        self.assertEqual(r.code, 0)
        self.assertIsNone(r.pok)

    def test_temporary(self):
        r = self.parse("resp_error_temp.xml")
        self.assertEqual(r.kind, "temporary")
        self.assertEqual(r.code, -1)
        self.assertIn("pozdeji", r.message)

    def test_critical(self):
        r = self.parse("resp_error_critical.xml")
        self.assertEqual(r.kind, "critical")
        self.assertEqual(r.code, 4)
        self.assertIn("podpis", r.message)

    def test_fault_is_no_response(self):
        r = self.parse("resp_fault.xml", status=500)
        self.assertEqual(r.kind, "no_response")
        self.assertEqual(r.http_status, 500)

    def test_garbage_is_no_response(self):
        r = transport.parse_response(b"<html>Bad gateway", 502, {})
        self.assertEqual(r.kind, "no_response")

    def test_send_headers_and_timeout(self):
        calls = []

        def fake_post(url, data=None, headers=None, timeout=None):
            calls.append((url, data, headers, timeout))
            return FakeResponse(read("resp_pok.xml"), headers={"X-Global-Transaction-Id": "t1"})

        r = transport.send(transport.URLS["playground"], b"<x/>", 3, post=fake_post)
        self.assertEqual(r.kind, "pok")
        self.assertEqual(r.transaction_id, "t1")
        url, data, headers, timeout = calls[0]
        self.assertEqual(url, "https://pg.trzbyeet.gov.cz/eet/services/EETServiceSOAP/v4")
        self.assertEqual(headers["SOAPAction"], "http://fs.gov.cz/eet/OdeslaniTrzby")
        self.assertEqual(headers["Content-Type"], "text/xml; charset=utf-8")
        self.assertEqual(timeout, (3, 3))

    def test_send_timeout(self):
        def fake_post(*args, **kwargs):
            raise requests.Timeout("slow")

        r = transport.send(transport.URLS["playground"], b"<x/>", 2, post=fake_post)
        self.assertEqual(r.kind, "no_response")
        self.assertIsNone(r.http_status)

    def test_urls(self):
        self.assertEqual(transport.URLS["production"], "https://trzbyeet.gov.cz/eet/services/EETServiceSOAP/v4")

    def test_unexpected_structure_is_no_response(self):
        body = (b'<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" xmlns:e="http://fs.gov.cz/eet/schema/v4">'
                b'<s:Body><e:Odpoved><e:Hlavicka/></e:Odpoved></s:Body></s:Envelope>')
        self.assertEqual(transport.parse_response(body, 200, {}).kind, "no_response")
        body2 = body.replace(b"<e:Hlavicka/>", b"<e:Hlavicka/><e:Chyba>x</e:Chyba>")
        self.assertEqual(transport.parse_response(body2, 200, {}).kind, "no_response")
