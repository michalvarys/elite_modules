import base64
from datetime import datetime, timedelta

from odoo.tests import TransactionCase

from odoo.addons.elite_eet.eet import paths


def p12_b64(eic="CZ00000019"):
    with open(paths.TEST_P12[eic], "rb") as f:
        return base64.b64encode(f.read())


class EetCase(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.device = cls.make_device()

    @classmethod
    def make_device(cls, eic="CZ00000019", **vals):
        values = {
            "name": "Pokladna test %s" % eic,
            "eic": eic,
            "id_jednotky": "303",
            "id_pokl": "Pokladna 1",
            "start_datetime": datetime.now() - timedelta(days=1),
            "certificate_file": p12_b64(eic),
            "certificate_filename": "cert.p12",
            "certificate_password": paths.TEST_P12_PASSWORD.decode(),
            "active_eet": True,
        }
        values.update(vals)
        return cls.env["elite.eet.device"].create(values)
