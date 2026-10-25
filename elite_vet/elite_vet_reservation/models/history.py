"""Request 25. 10.: history of reservations for Správce rezervací (menu Historie rezervací).

The change history itself is the chatter (mail tracking on the important fields). Here only who
and when cancelled a reservation (shown in the list) and restoring a cancelled reservation
(wizard/restore_wizard.py).
"""
from odoo import _, fields, models
from odoo.exceptions import UserError

# Filter "Přesunuté": a tracked change of the time or the room (chatter), no extra data stored.
MOVED_TRACKING_FIELDS = ("start", "room_id")


class ReservationHistory(models.Model):
    _inherit = "elite.vet.reservation"

    # Tracking also of the client's pet and of the cancel reason (state, start, room, doctor,
    # procedure and client are tracked in reservation.py).
    pet_id = fields.Many2one(tracking=True)
    cancel_reason = fields.Selection(tracking=True)
    cancelled_by_id = fields.Many2one("res.users", string="Zrušil(a)", readonly=True, copy=False,
                                      ondelete="set null",
                                      help="Kdo rezervaci zrušil (u zrušení klientem z webu veřejný uživatel webu).")
    cancelled_at = fields.Datetime(string="Zrušeno", readonly=True, copy=False)
    # Filter "Přesunuté". Tracking values are readable only by the system administrator, so a
    # domain on message_ids.tracking_value_ids would raise an access error for the manager.
    was_moved = fields.Boolean(string="Přesunutá", compute="_compute_was_moved", search="_search_was_moved",
                               help="V historii změn je změna času nebo ordinace.")

    def _moved_ids(self, ids=None):
        """Ids of reservations with a tracked change of the time or the room (chatter)."""
        query = """
            SELECT DISTINCT m.res_id
              FROM mail_message m
              JOIN mail_tracking_value t ON t.mail_message_id = m.id
              JOIN ir_model_fields f ON f.id = t.field_id
             WHERE m.model = %s AND f.name IN %s"""
        params = [self._name, MOVED_TRACKING_FIELDS]
        if ids is not None:
            query += " AND m.res_id IN %s"
            params.append(tuple(ids) or (0,))
        self.env.flush_all()
        self.env.cr.execute(query, params)
        return {row[0] for row in self.env.cr.fetchall()}

    def _compute_was_moved(self):
        moved = self._moved_ids(self.ids) if self.ids else set()
        for rec in self:
            rec.was_moved = rec.id in moved

    def _search_was_moved(self, operator, value):
        if operator not in ("=", "!="):
            raise UserError(_("Nepodporovaný operátor."))
        positive = bool(value) == (operator == "=")
        return [("id", "in" if positive else "not in", list(self._moved_ids()))]

    def write(self, vals):
        if "state" in vals and "cancelled_by_id" not in vals:
            vals = dict(vals)
            if vals["state"] == "cancelled":
                vals.update(cancelled_by_id=self.env.uid, cancelled_at=fields.Datetime.now())
            else:
                vals.update(cancelled_by_id=False, cancelled_at=False)
        return super().write(vals)

    def action_restore_wizard(self):
        """Obnovit (Správce rezervací): the wizard checks the slot and optionally e-mails the client."""
        self.ensure_one()
        if not self.env.user.has_group("elite_vet_reservation.group_reservation_manager"):
            raise UserError(_("Obnovit rezervaci může jen správce rezervací."))
        if self.kind != "reservation" or self.state != "cancelled":
            raise UserError(_("Obnovit jde jen zrušenou rezervaci."))
        if self.is_second_room:
            raise UserError(_("Toto je kopie ve druhé ordinaci – obnovte hlavní rezervaci."))
        return {
            "type": "ir.actions.act_window", "res_model": "elite.vet.reservation.restore.wizard",
            "name": _("Obnovit rezervaci"), "view_mode": "form", "views": [[False, "form"]],
            "target": "new", "context": {"default_reservation_id": self.id},
        }
