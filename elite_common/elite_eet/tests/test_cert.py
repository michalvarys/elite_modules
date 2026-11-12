from datetime import date

from odoo.tests import BaseCase, tagged

from odoo.addons.elite_eet.eet import cert, paths


@tagged("post_install", "-at_install")
class TestEetCert(BaseCase):
    def _read(self, eic):
        with open(paths.TEST_P12[eic], "rb") as f:
            return f.read()

    def test_playground_certificates(self):
        for eic in paths.TEST_P12:
            key, certificate, info = cert.load_p12(self._read(eic), paths.TEST_P12_PASSWORD)
            self.assertIsNotNone(key)
            self.assertIsNotNone(certificate)
            self.assertEqual(info.cn, eic)
            self.assertEqual(info.environment, "playground")
            self.assertEqual(info.valid_to.date(), date(2027, 5, 14))
            self.assertIsNone(info.valid_to.tzinfo)
            self.assertTrue(info.serial)
            self.assertTrue(info.issuer)

    def test_wrong_password(self):
        with self.assertRaises(cert.CertError) as ctx:
            cert.load_p12(self._read("CZ00000019"), b"secret-pass-123")
        self.assertNotIn("secret-pass-123", str(ctx.exception))

    def test_not_a_p12(self):
        with self.assertRaises(cert.CertError):
            cert.load_p12(b"not a certificate", b"aaaa1111")
