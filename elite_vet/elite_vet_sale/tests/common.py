from odoo.addons.elite_vet_clinic.tests.common import ClinicCase


class SaleCase(ClinicCase):
    """ClinicCase with the sale/POS/stock setup of elite_vet_sale applied (idempotent)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.setup = cls.env["elite.vet.sale.setup"]
        cls.setup.ensure_setup()
        cls.company = cls.env.company
        cls.pos_config = cls.setup.pos_config()
        cls.tax21 = cls.setup.tax_for_rate(21)
        cls.tax12 = cls.setup.tax_for_rate(12)
        cls.tax0 = cls.setup.tax_for_rate(0)
