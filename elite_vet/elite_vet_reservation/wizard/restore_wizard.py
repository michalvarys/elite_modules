"""Request 25. 10.: Obnovit – a cancelled reservation back to confirmed (Správce rezervací).

Only when its slot is still free (the same overlap check as booking, _check_overlap); otherwise a
clear message and the wizard stays open with the time and the room to change. The client gets
the confirmation e-mail only when "Poslat klientovi potvrzení" is ticked (default: no e-mail).
"""
from markupsafe import escape

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

MANAGER_GROUP = "elite_vet_reservation.group_reservation_manager"


class ReservationRestoreWizard(models.TransientModel):
    _name = "elite.vet.reservation.restore.wizard"
    _description = "Obnovit zrušenou rezervaci"

    reservation_id = fields.Many2one("elite.vet.reservation", string="Rezervace", required=True, readonly=True,
                                     ondelete="cascade")
    name = fields.Char(related="reservation_id.name", string="Název rezervace")
    cancelled_by_id = fields.Many2one(related="reservation_id.cancelled_by_id")
    cancelled_at = fields.Datetime(related="reservation_id.cancelled_at")
    cancel_reason = fields.Selection(related="reservation_id.cancel_reason")
    start = fields.Datetime(string="Začátek", required=True, compute="_compute_slot", store=True, readonly=False,
                            help="Původní čas; když už není volný, zvolte jiný.")
    room_id = fields.Many2one("elite.vet.room", string="Ordinace", required=True, compute="_compute_slot",
                              store=True, readonly=False)
    contact_email = fields.Char(related="reservation_id.contact_email", string="E-mail klienta")
    send_confirmation = fields.Boolean(string="Poslat klientovi potvrzení", default=False,
                                       help="Klientovi odejde e-mail s potvrzením rezervace (jako u nové).")

    @api.depends("reservation_id")
    def _compute_slot(self):
        for wizard in self:
            wizard.start = wizard.reservation_id.start
            wizard.room_id = wizard.reservation_id.room_id

    def action_restore(self):
        self.ensure_one()
        if not self.env.user.has_group(MANAGER_GROUP):
            raise UserError(_("Obnovit rezervaci může jen správce rezervací."))
        res = self.reservation_id
        if res.kind != "reservation" or res.state != "cancelled":
            raise UserError(_("Obnovit jde jen zrušenou rezervaci (tato je teď ve stavu %s).")
                            % dict(res._fields["state"]._description_selection(self.env)).get(res.state))
        if res.is_second_room:
            raise UserError(_("Toto je kopie ve druhé ordinaci – obnovte hlavní rezervaci."))
        if self.start <= fields.Datetime.now():
            raise UserError(_("Termín je v minulosti. Zvolte v tomto okně nový začátek a klikněte znovu Obnovit."))
        vals = {"state": "confirmed", "start": self.start, "stop": self.start + (res.stop - res.start),
                "room_id": self.room_id.id, "cancel_reason": False, "reminder_sent": False}
        try:
            with self.env.cr.savepoint():
                # no automatic e-mail (a new time would send "změna termínu"); see send_confirmation
                res.with_context(ev_skip_mail=True).write(vals)
        except ValidationError as err:
            raise UserError(_(
                "Rezervaci nejde obnovit, termín už není volný.\n%s\n\n"
                "Zvolte v tomto okně jiný začátek nebo ordinaci a klikněte znovu Obnovit "
                "(nebo rezervaci nechte zrušenou a založte novou).") % err.args[0]) from None
        sent = bool(self.send_confirmation and res.contact_email)
        if sent:
            res._send_template("mail_confirmed")
        body = _("Rezervaci obnovil(a) %s.") % self.env.user.name
        body += " " + (_("Klientovi odešlo potvrzení na %s.") % res.contact_email if sent
                       else _("Klientovi se nic neposílalo."))
        if res.linked_reservation_id and res.linked_reservation_id.state == "cancelled":
            body += " " + _("Kopie ve druhé ordinaci zůstává zrušená.")
        res._message_log(body=escape(body))   # a note in the chatter (author: the user, no e-mail)
        return {"type": "ir.actions.act_window_close"}
