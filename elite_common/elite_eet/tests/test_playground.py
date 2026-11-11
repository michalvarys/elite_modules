"""Integration tests against the real EET Playground (network).

Run explicitly: --test-tags eet_playground. They never touch production.
"""
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.tests import tagged

from odoo.addons.elite_eet.eet import paths, transport

from .common import EetCase, p12_b64

REAL_SEND = transport.send


@tagged("eet_playground", "-standard", "post_install", "-at_install")
class TestEetPlayground(EetCase):
    def make_sale(self, device, porad_cis, **vals):
        values = {
            "device_id": device.id,
            "porad_cis": porad_cis,
            "dat_trzby": fields.Datetime.now() - timedelta(seconds=5),
            "celk_trzba": 1.0,
        }
        values.update(vals)
        return self.env["elite.eet.sale"].create(values)

    def unique(self, prefix):
        return "%s-%s" % (prefix, fields.Datetime.now().strftime("%Y%m%d%H%M%S%f"))

    def assertRegistered(self, sale):
        self.assertEqual(sale.state, "registered", sale.last_error)
        self.assertTrue(sale.pok.endswith("-ff"), sale.pok)
        self.assertTrue(sale.is_test)

    def test_pok_all_certificates(self):
        for eic in paths.TEST_P12:
            device = self.device if eic == "CZ00000019" else self.make_device(eic=eic)
            self.assertEqual(device._eet_url(), transport.URLS["playground"])
            sale = self.make_sale(device, self.unique("PG"))
            sale._eet_send()
            self.assertRegistered(sale)
            self.assertFalse(sale.warning_text)

    def test_verification_mode(self):
        action = self.device.action_check_connection()
        self.assertEqual(action["params"]["type"], "success", action["params"]["message"])
        self.assertEqual(self.device.attempt_ids[:1].code, 0)

    def test_negative_sale(self):
        sale = self.make_sale(self.device, self.unique("PGR"), celk_trzba=-120.5)
        sale._eet_send()
        self.assertRegistered(sale)

    def test_voucher_fields(self):
        sale = self.make_sale(self.device, self.unique("PGV"), celk_trzba=327, urceno_cerp_zuct=25, cerp_zuct=302)
        sale._eet_send()
        self.assertRegistered(sale)
        self.assertIn('urceno_cerp_zuct="25.00"', sale.attempt_ids.request_xml)

    def test_resend_same_sale(self):
        sale = self.make_sale(self.device, self.unique("PGS"))
        sale._eet_send()
        self.assertRegistered(sale)
        sale.state = "pending"
        sale._eet_send()
        self.assertEqual(len(sale.attempt_ids), 2)
        self.assertRegistered(sale)

    def test_bad_signature(self):
        def tampered(url, envelope, timeout, post=None):
            return REAL_SEND(url, envelope.replace(b'celk_trzba="1.00"', b'celk_trzba="2.00"'), timeout)

        sale = self.make_sale(self.device, self.unique("PGB"))
        with patch("odoo.addons.elite_eet.eet.transport.send", tampered):
            sale._eet_send()
        self.assertEqual(sale.state, "error")
        self.assertIn(sale.attempt_ids.code, (3, 4))

    def test_eic_mismatch_warning(self):
        device = self.make_device(eic="CZ683555118", certificate_file=p12_b64("CZ00000019"))
        sale = self.make_sale(device, self.unique("PGW"))
        sale._eet_send()
        self.assertRegistered(sale)
        self.assertTrue(sale.warning_text.startswith("1:"), sale.warning_text)

    def test_unreachable_stays_pending(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "elite_eet.playground_url_override", "https://10.255.255.1/eet/services/EETServiceSOAP/v4"
        )
        self.device.response_timeout = 2
        sale = self.make_sale(self.device, self.unique("PGU"))
        sale._eet_send()
        self.assertEqual(sale.state, "pending")
        self.assertEqual(sale.attempt_ids.result, "no_response")
