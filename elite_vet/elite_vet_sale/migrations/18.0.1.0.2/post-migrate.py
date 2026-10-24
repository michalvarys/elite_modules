"""18.0.1.0.2 (task 14): doctors and nurses without POS and stock. security/groups.xml removed the
implied links of the old chain; here the users set up by it are cleaned up once (a manual tick
made later is kept)."""
import odoo


def migrate(cr, version):
    if not version:
        return
    env = odoo.api.Environment(cr, odoo.SUPERUSER_ID, {})
    env["res.users"]._elite_vet_split_till_rights()
