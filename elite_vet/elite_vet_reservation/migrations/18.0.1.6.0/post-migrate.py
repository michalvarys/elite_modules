"""18.0.1.6.0: odesílatel e-mailů k rezervacím z nastavení rezervací.

Šablony jsou noupdate, takže se jim odesílatel změní tady - jen tam, kde ho nikdo
ručně neupravil (pořád původní e-mail firmy)."""
from odoo import SUPERUSER_ID, api

PUVODNI = "{{ user.company_id.email_formatted }}"
NOVY = "{{ object._mail_sender() }}"
SABLONY = ("mail_web_received", "mail_new_for_clinic", "mail_confirmed", "mail_rescheduled",
           "mail_cancelled", "mail_reminder")


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    for xmlid in SABLONY:
        t = env.ref("elite_vet_reservation." + xmlid, raise_if_not_found=False)
        if t and (t.email_from or "").strip() == PUVODNI:
            t.email_from = NOVY
