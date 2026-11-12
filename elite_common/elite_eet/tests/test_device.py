from datetime import date

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged

from .common import EetCase, p12_b64


@tagged("post_install", "-at_install")
class TestEetDevice(EetCase):
    def test_certificate_read_on_create(self):
        self.assertEqual(self.device.cert_cn, "CZ00000019")
        self.assertEqual(self.device.cert_environment, "playground")
        self.assertEqual(self.device.cert_valid_to.date(), date(2027, 5, 14))
        self.assertTrue(self.device.cert_serial)
        self.assertFalse(self.device.cert_warning)

    def test_wrong_password(self):
        with self.assertRaises(UserError):
            self.make_device(certificate_password="wrong-one")

    def test_wrong_password_on_write(self):
        with self.assertRaises(UserError):
            self.device.write({"certificate_password": "wrong-one"})

    def test_production_with_playground_cert(self):
        with self.assertRaises(ValidationError):
            self.make_device(environment="production")

    def test_timeout_minimum(self):
        with self.assertRaises(ValidationError):
            self.device.response_timeout = 1.5

    def test_id_pokl_pattern(self):
        with self.assertRaises(ValidationError):
            self.device.id_pokl = "Bar č.1"

    def test_eic_and_unit_patterns(self):
        with self.assertRaises(ValidationError):
            self.device.eic = "CZ12"
        with self.assertRaises(ValidationError):
            self.device.id_jednotky = "0303"

    def test_active_requires_settings(self):
        with self.assertRaises(ValidationError):
            self.env["elite.eet.device"].create({"name": "Bez nastavení", "active_eet": True})
        inactive = self.env["elite.eet.device"].create({"name": "Vypnuto"})
        self.assertFalse(inactive.active_eet)
        self.assertEqual(inactive.environment, "playground")
        self.assertEqual(inactive.response_timeout, 3.0)

    def test_eic_mismatch_is_warning(self):
        device = self.make_device(eic="CZ683555118", certificate_file=p12_b64("CZ00000019"))
        self.assertTrue(device.cert_warning)

    def test_certificate_hidden_from_manager(self):
        manager = self.env["res.users"].create({
            "name": "EET manager",
            "login": "eet_manager_test",
            "groups_id": [(6, 0, [self.env.ref("base.group_user").id, self.env.ref("elite_eet.group_eet_manager").id])],
        })
        device = self.device.with_user(manager)
        self.assertEqual(device.cert_cn, "CZ00000019")
        with self.assertRaises(AccessError):
            device.read(["certificate_password"])
        with self.assertRaises(AccessError):
            device.read(["certificate_file"])

    def test_url(self):
        self.assertEqual(self.device._eet_url(), "https://pg.trzbyeet.gov.cz/eet/services/EETServiceSOAP/v4")
        prod = self.env["elite.eet.device"].create({"name": "Prod", "environment": "production"})
        with self.assertRaises(UserError):
            prod._eet_url()

    def test_playground_url_override(self):
        self.env["ir.config_parameter"].sudo().set_param("elite_eet.playground_url_override", "https://10.255.255.1/eet")
        self.assertEqual(self.device._eet_url(), "https://10.255.255.1/eet")

    def test_key_and_cert(self):
        key, certificate = self.device._eet_key_and_cert()
        self.assertTrue(key and certificate)
