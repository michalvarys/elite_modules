"""Note of a room for one day, shown above the doctors' shifts on the boards."""
import uuid

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from .live import notify_board
from .recurrence import occurrence_dates
from .reservation import WEEKDAY_FIELDS


class VetRoomNote(models.Model):
    """One row = one day; a repeated note = materialized copies sharing `series_uid` (as blocks)."""

    _name = "elite.vet.room.note"
    _description = "Poznámka k ordinaci na den"
    _order = "date, id"
    _rec_name = "text"

    room_id = fields.Many2one("elite.vet.room", string="Ordinace", required=True, ondelete="cascade", index=True)
    date = fields.Date(string="Den", required=True, index=True, default=fields.Date.context_today)
    text = fields.Char(string="Poznámka", required=True)
    series_uid = fields.Char(string="Série", readonly=True, copy=False, index=True)
    in_series = fields.Boolean(string="Opakovaná", compute="_compute_in_series")
    # Used once in create() and cleared, like the repetition of a block.
    repeat_rule = fields.Selection(
        [("none", "Neopakovat"), ("daily", "Denně"), ("weekly", "Týdně"),
         ("monthly", "Měsíčně"), ("yearly", "Ročně")],
        string="Opakování", default="none")
    repeat_interval = fields.Integer(string="Opakovat každý", default=1)
    repeat_mon = fields.Boolean(string="po")
    repeat_tue = fields.Boolean(string="út")
    repeat_wed = fields.Boolean(string="st")
    repeat_thu = fields.Boolean(string="čt")
    repeat_fri = fields.Boolean(string="pá")
    repeat_sat = fields.Boolean(string="so")
    repeat_sun = fields.Boolean(string="ne")
    repeat_end = fields.Selection(
        [("never", "Bez konce"), ("count", "Konec po"), ("until", "Konec v")],
        string="Konec opakování", default="never",
        help="Bez konce: poznámka se založí na rok dopředu.")
    repeat_count = fields.Integer(string="Počet opakování", default=10)
    repeat_until = fields.Date(string="Opakovat do")

    @api.depends("series_uid")
    def _compute_in_series(self):
        for rec in self:
            rec.in_series = bool(rec.series_uid)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._repeat_notes()
        notify_board(self.env)
        return records

    def write(self, vals):
        result = super().write(vals)
        notify_board(self.env)
        return result

    def unlink(self):
        result = super().unlink()
        notify_board(self.env)
        return result

    def _repeat_notes(self):
        for rec in self.filtered(lambda r: r.repeat_rule != "none"):
            rule, interval, end = rec.repeat_rule, rec.repeat_interval, rec.repeat_end
            count, until = rec.repeat_count, rec.repeat_until
            weekdays = [wd for wd, name in enumerate(WEEKDAY_FIELDS) if rec[name]]
            if interval < 1:
                raise ValidationError(_("Opakovat každý: zadejte aspoň 1."))
            if end == "count" and count < 1:
                raise ValidationError(_("Konec po: zadejte aspoň 1 opakování."))
            if end == "until" and (not until or until < rec.date):
                raise ValidationError(_("Konec opakování musí být v den poznámky nebo později."))
            dates = occurrence_dates(rec.date, rule, interval, weekdays, end, count=count, until=until)
            dates = [d for d in dates if d != rec.date]
            if end == "count":
                dates = dates[:count - 1]
            uid = uuid.uuid4().hex
            rec.write(dict({name: False for name in WEEKDAY_FIELDS},
                           repeat_rule="none", repeat_until=False, series_uid=uid if dates else False))
            if dates:
                self.create([{"room_id": rec.room_id.id, "date": day, "text": rec.text, "series_uid": uid}
                             for day in dates])

    def action_delete(self):
        self.unlink()
        return {"type": "ir.actions.act_window_close"}

    def action_delete_following(self):
        """This day and the later ones of the series; the earlier days stay."""
        self.ensure_one()
        self.search([("series_uid", "=", self.series_uid), ("date", ">=", self.date)]).unlink()
        return {"type": "ir.actions.act_window_close"}
