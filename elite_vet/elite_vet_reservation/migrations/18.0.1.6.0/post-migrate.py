"""18.0.1.6.0: sender of reservation e-mails taken from the booking settings.

The templates are noupdate, so their sender is changed here - only where nobody
edited it manually (still the original company e-mail)."""
from odoo import SUPERUSER_ID, api

OLD_SENDER = "{{ user.company_id.email_formatted }}"
NEW_SENDER = "{{ object._mail_sender() }}"
TEMPLATES = ("mail_web_received", "mail_new_for_clinic", "mail_confirmed", "mail_rescheduled",
             "mail_cancelled", "mail_reminder")


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    for xmlid in TEMPLATES:
        template = env.ref("elite_vet_reservation." + xmlid, raise_if_not_found=False)
        if template and (template.email_from or "").strip() == OLD_SENDER:
            template.email_from = NEW_SENDER
