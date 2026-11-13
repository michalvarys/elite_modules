from datetime import datetime
from unittest.mock import patch

from odoo.exceptions import ValidationError
from odoo.tests import tagged

from odoo.addons.elite_eet.eet import paths
from odoo.addons.elite_eet.eet.transport import Result
from odoo.addons.elite_eet.tests.common import p12_b64
from odoo.addons.point_of_sale.tests.common import TestPoSCommon

PASSWORD = paths.TEST_P12_PASSWORD.decode()


@tagged("post_install", "-at_install")
class TestPosEetSettings(TestPoSCommon):
    """EET is set up in Point of Sale → Configuration → Settings, per till."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config = cls.basic_config
        cls.other_config = cls.basic_config.copy({"name": "Elite Arena"})

    def save_settings(self, config=None, **eet):
        """Save the POS settings form the way the web client does (all pos_ fields in vals)."""
        config = config or self.config
        vals = {"pos_config_id": config.id}
        vals.update({"pos_" + key: value for key, value in eet.items()})
        settings = self.env["res.config.settings"].create(vals)
        settings.execute()
        return settings

    def test_untouched_settings_create_no_device(self):
        self.save_settings(eet_enabled=False, eet_eic=False, eet_id_jednotky=False,
                           eet_start_datetime=self.config.eet_start_datetime)
        self.assertFalse(self.config.eet_device_id)

    def test_setup_from_settings(self):
        self.save_settings(
            eet_id_jednotky="303",
            eet_certificate_file=p12_b64("CZ683555118"),
            eet_certificate_filename="trafika.p12",
            eet_certificate_password=PASSWORD,
            eet_start_datetime=datetime(2027, 1, 1),
            eet_enabled=True,
            eet_eic=False,
        )
        device = self.config.eet_device_id
        self.assertTrue(device.active_eet)
        self.assertEqual(device.eic, "CZ683555118", "EIČ comes from the certificate")
        self.assertEqual(device.environment, "playground", "environment comes from the certificate")
        self.assertEqual(device.id_jednotky, "303")
        self.assertTrue(device.id_pokl)
        self.assertEqual(device.pos_config_id, self.config)
        self.assertEqual(self.config.eet_eic, "CZ683555118")
        self.assertEqual(self.config.eet_environment, "playground")
        self.assertTrue(self.config.eet_cert_valid_to)

    def test_enable_without_data_explains_what_is_missing(self):
        with self.assertRaisesRegex(ValidationError, "certifikát"):
            self.save_settings(eet_enabled=True, eet_id_jednotky="303")

    def test_resave_keeps_values(self):
        self.save_settings(eet_id_jednotky="303", eet_certificate_file=p12_b64(),
                           eet_certificate_password=PASSWORD)
        device = self.config.eet_device_id
        # the form sends back every field, the binary possibly as a size label
        self.save_settings(eet_id_jednotky="303", eet_eic=self.config.eet_eic, eet_certificate_file=b"2.50 Kb",
                           eet_certificate_password=PASSWORD, eet_enabled=False,
                           eet_start_datetime=self.config.eet_start_datetime)
        self.assertEqual(device.sudo().certificate_file, p12_b64())
        self.assertEqual(device.eic, "CZ00000019")

    def test_copy_certificate_from_other_till(self):
        self.save_settings(eet_id_jednotky="303", eet_certificate_file=p12_b64("CZ683555118"),
                           eet_certificate_filename="fortis.p12", eet_certificate_password=PASSWORD)
        self.save_settings(self.other_config, eet_id_jednotky="304", eet_cert_source_config_id=self.config.id)
        device = self.other_config.eet_device_id
        self.assertEqual(device.sudo().certificate_file, p12_b64("CZ683555118"))
        self.assertEqual(device.eic, "CZ683555118")
        self.assertFalse(self.other_config.eet_cert_source_config_id)

    def test_status(self):
        self.assertEqual(self.config.eet_status_level, "none")
        self.save_settings(eet_id_jednotky="303")
        self.assertEqual(self.config.eet_status_level, "warning")
        self.assertIn("certifikát", self.config.eet_status)
        self.save_settings(eet_certificate_file=p12_b64(), eet_certificate_password=PASSWORD)
        device = self.config.eet_device_id
        ok = Result(kind="verified", http_status=200, code=0, message="Overeni")
        with patch("odoo.addons.elite_eet.eet.transport.send", return_value=ok):
            settings = self.env["res.config.settings"].create({"pos_config_id": self.config.id})
            action = settings.action_pos_eet_check_connection()
        self.assertEqual(action["params"]["type"], "success")
        self.config.invalidate_recordset()
        self.assertIn("Spojení ověřeno", self.config.eet_status)
        self.assertTrue(device.attempt_ids)

    def test_settings_view(self):
        arch = self.env["res.config.settings"].get_views([(False, "form")])["views"]["form"]["arch"]
        for name in ("pos_eet_enabled", "pos_eet_id_jednotky", "pos_eet_certificate_file",
                     "pos_eet_certificate_password", "pos_eet_status", "action_pos_eet_check_connection"):
            self.assertIn(name, arch)
