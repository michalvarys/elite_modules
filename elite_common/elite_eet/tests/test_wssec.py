import os
from datetime import datetime

from lxml import etree

from odoo.tests import BaseCase, tagged

from odoo.addons.elite_eet.eet import cert, message, paths, wssec

from .test_message import build, sale_data


def load_key(eic):
    with open(paths.TEST_P12[eic], "rb") as f:
        key, certificate, _info = cert.load_p12(f.read(), paths.TEST_P12_PASSWORD)
    return key, certificate


def sample(eic):
    with open(os.path.join(paths.TEST_DATA_DIR, f"{eic}.eet.v4.req.xml"), "rb") as f:
        return f.read()


@tagged("post_install", "-at_install")
class TestEetWsSecurity(BaseCase):
    def test_gfr_samples_verify(self):
        for eic in paths.TEST_P12:
            self.assertTrue(wssec.verify_envelope(sample(eic)), eic)

    def test_gfr_sample_tampered(self):
        xml = sample("CZ00000019").replace(b'celk_trzba="188580.00"', b'celk_trzba="188581.00"')
        self.assertFalse(wssec.verify_envelope(xml))

    def test_sign_and_verify_roundtrip(self):
        for eic in paths.TEST_P12:
            key, certificate = load_key(eic)
            envelope = wssec.sign_envelope(build(sale_data(eic_popl=eic)), key, certificate)
            self.assertIsInstance(envelope, bytes)
            self.assertTrue(wssec.verify_envelope(envelope), eic)
            envelope.decode("ascii")
            self.assertFalse(envelope.startswith(b"<?xml"))
            root = etree.fromstring(envelope)
            self.assertEqual(root.tag, "{http://schemas.xmlsoap.org/soap/envelope/}Envelope")
            self.assertIsNone(root.find(".//{*}Timestamp"))

    def test_signed_envelope_tampered(self):
        key, certificate = load_key("CZ00000019")
        envelope = wssec.sign_envelope(build(sale_data()), key, certificate)
        self.assertFalse(wssec.verify_envelope(envelope.replace(b'"250.00"', b'"251.00"')))

    def test_size_limit(self):
        key, certificate = load_key("CZ00000019")
        trzba = build(sale_data())
        trzba.find("{http://fs.gov.cz/eet/schema/v4}Data").set("padding", "x" * 13000)
        with self.assertRaises(message.MessageError):
            wssec.sign_envelope(trzba, key, certificate)
