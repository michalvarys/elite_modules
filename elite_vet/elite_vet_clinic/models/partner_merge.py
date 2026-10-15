from odoo import models


class PartnerMergeWizard(models.TransientModel):
    """Managers of the clinic merge duplicate owners (menu "Sloučit duplicitní klienty").

    The standard merge touches models of other apps (website visitors, mail, payments…) that a
    clinic manager has no rights to, so for a reservation manager without the Odoo "Contact
    creation" right the merge itself runs as superuser. Odoo's limit of 3 contacts per merge
    stays; the "same e-mail" check is skipped as for an administrator.
    """

    _inherit = "base.partner.merge.automatic.wizard"

    def action_merge(self):
        user = self.env.user
        if not self.env.su and user.has_group("elite_vet_reservation.group_reservation_manager") \
                and not user.has_group("base.group_partner_manager"):
            return super(PartnerMergeWizard, self.sudo()).action_merge()
        return super().action_merge()
