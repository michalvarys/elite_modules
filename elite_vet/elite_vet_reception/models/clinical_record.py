from odoo import api, fields, models

from odoo.addons.elite_vet_reservation.models.live import notify_board

VISIT_STAGES = [("waiting", "Čeká"), ("in_room", "V ordinaci")]
# Context key of the reception API: the record is created under sudo after the role check
# (elite.vet.reception), so the clinic write check must let it through.
RECEPTION_CONTEXT = "elite_vet_reception_api"


class ClinicalRecordVisitStage(models.Model):
    """Visit stage of a record: Čeká (reception checked the client in) -> V ordinaci
    (doctor/nurse called the patient or opened today's record from the card)."""

    _inherit = "elite.vet.clinical.record"

    visit_stage = fields.Selection(VISIT_STAGES, string="Stav návštěvy", default=False, index=True, tracking=True)
    arrived_at = fields.Datetime(string="Příchod", copy=False)
    called_at = fields.Datetime(string="Zavolán(a)", copy=False)
    received_by = fields.Char(string="Přijal(a)", copy=False, help="Zaměstnanec pokladny, který klienta přijal.")
    # Task 15: the consultation room of the visit (screen Ordinace). Taken from the reservation
    # (also for records that existed before the field); empty = not assigned yet (walk-ins).
    # Moving the visit to another room does not move the reservation.
    room_id = fields.Many2one("elite.vet.room", string="Ordinace", compute="_compute_room_id", store=True,
                              readonly=False, index=True, tracking=True, ondelete="set null", copy=False)

    @api.depends("reservation_id")
    def _compute_room_id(self):
        for rec in self:
            if rec.reservation_id.room_id:
                rec.room_id = rec.reservation_id.room_id
            elif not rec.room_id:
                rec.room_id = False

    @api.model
    def _elite_vet_is_room_account(self, user):
        """Task 23: a room account never becomes the treating doctor."""
        return bool(user.sudo().elite_vet_room_id) or super()._elite_vet_is_room_account(user)

    @api.model
    def _can_write(self):
        if self.env.su and self.env.context.get(RECEPTION_CONTEXT):
            return True
        return super()._can_write()

    # Ruling R15: the till's "K pokladně" column follows finishing, reopening and cancelling live.
    def action_done(self):
        res = super().action_done()
        notify_board(self.env)
        return res

    def action_reopen(self):
        res = super().action_reopen()
        notify_board(self.env)
        return res

    def action_cancel(self):
        res = super().action_cancel()
        notify_board(self.env)
        return res

    def _call_in(self):
        """Move draft records that are waiting (or have no stage yet) into the room."""
        todo = self.filtered(lambda r: r.state == "draft" and r.visit_stage in (False, "waiting"))
        if todo:
            todo.write({"visit_stage": "in_room", "called_at": fields.Datetime.now()})
        return todo

    @api.model
    def open_today_record(self, pet_id, reservation_id=False, force_new=False):
        data = super().open_today_record(pet_id, reservation_id=reservation_id, force_new=force_new)
        if not self.env.context.get(RECEPTION_CONTEXT) \
                and self.env.user.has_group("elite_vet_clinic.group_clinic_nurse"):
            record = self.browse(data["id"])
            if record._call_in():
                data = record._record_data()
        return data
