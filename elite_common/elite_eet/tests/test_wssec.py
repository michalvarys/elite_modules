import os
import subprocess
import sys
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

    def test_sign_verify_varied_data(self):
        # Regression: digests computed on the in-memory tree differed from the
        # canonical form of the serialized message for some data (EET error 4).
        key, certificate = load_key("CZ00000019")
        for now in [datetime(2026, 11, 11, 20, 0, 0), datetime(2026, 11, 11, 20, 0, 0, 123456)]:
          for porad_cis, id_pokl in [("P-1", "Probe 1"), ("Arena/0001", "Pokladna 1"), ("1", "B")]:
            trzba = build(
                sale_data(porad_cis=porad_cis, id_pokl=id_pokl, dat_trzby=now, celk_trzba=1.0),
                sent_at=now,
            )
            envelope = wssec.sign_envelope(trzba, key, certificate)
            self.assertTrue(wssec.verify_envelope(envelope), (now, porad_cis))

    def test_first_signature_in_fresh_process(self):
        # Regression (EET error 4 "Neplatny podpis"): the first message signed in a new
        # process had a digest of the in-memory tree, not of the serialized message.
        code = (
            "import sys, types, datetime\n"
            "pkg = types.ModuleType('eetpkg'); pkg.__path__ = [sys.argv[1]]; sys.modules['eetpkg'] = pkg\n"
            "from eetpkg import cert, message, paths, wssec\n"
            "key, crt, _i = cert.load_p12(open(paths.TEST_P12['CZ00000019'], 'rb').read(), paths.TEST_P12_PASSWORD)\n"
            "now = datetime.datetime.utcnow()\n"
            "d = message.SaleData('CZ00000019', '303', 'Probe 1', 'P-1', now, 1.0)\n"
            "t = message.build_trzba(d, 'fecde4d0-820f-4c48-99f0-2e1d1ef5bc23', now, True, False)\n"
            "print(wssec.verify_envelope(wssec.sign_envelope(t, key, crt)))\n"
        )
        eet_dir = os.path.dirname(paths.__file__)
        for _run in range(3):
            out = subprocess.run(
                [sys.executable, "-I", "-c", code, eet_dir], capture_output=True, text=True, check=True
            )
            self.assertEqual(out.stdout.strip(), "True", out.stderr)

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
