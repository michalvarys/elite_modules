"""18.0.1.0.1: the sale setup also runs on module update (the till pricelist becomes CZK, ruling R12)."""
import odoo


def migrate(cr, version):
    if not version:
        return
    env = odoo.api.Environment(cr, odoo.SUPERUSER_ID, {})
    env["elite.vet.sale.setup"].ensure_setup()
