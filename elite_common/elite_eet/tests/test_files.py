import os

from lxml import etree

from odoo.tests import BaseCase, tagged

from odoo.addons.elite_eet.eet import paths


@tagged("post_install", "-at_install")
class TestOfficialFiles(BaseCase):
    def test_official_files_present(self):
        for path in [paths.SCHEMA_XSD, paths.CA_DIR, paths.TEST_DATA_DIR, *paths.TEST_P12.values()]:
            self.assertTrue(os.path.exists(path), path)
        etree.XMLSchema(file=paths.SCHEMA_XSD)
        for eic in paths.TEST_P12:
            etree.parse(os.path.join(paths.TEST_DATA_DIR, f"{eic}.eet.v4.req.xml"))
        self.assertEqual(paths.TEST_P12_PASSWORD, b"aaaa1111")
