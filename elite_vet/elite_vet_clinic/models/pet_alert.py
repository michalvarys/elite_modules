from odoo import api, fields, models

ALERT_KINDS = [("bites", "Kouše"), ("allergy", "Alergie"), ("other", "Jiné")]


class VetPetAlert(models.Model):
    """Warning shown as a colored tag in the patient card header (Odoo-only data)."""

    _name = "elite.vet.pet.alert"
    _description = "Upozornění na pacientovi"
    _order = "pet_id, kind, id"

    pet_id = fields.Many2one("elite.vet.pet", string="Pacient", required=True, index=True, ondelete="cascade")
    kind = fields.Selection(ALERT_KINDS, string="Druh", required=True, default="other")
    note = fields.Char(string="Poznámka", help="Např. na co je alergický nebo jak s ním zacházet.")
    active = fields.Boolean(string="Aktivní", default=True)

    @api.depends("kind", "note")
    def _compute_display_name(self):
        labels = dict(ALERT_KINDS)
        for rec in self:
            label = labels.get(rec.kind, "")
            rec.display_name = "%s: %s" % (label, rec.note) if rec.note else label


class VetPet(models.Model):
    _inherit = "elite.vet.pet"

    alert_ids = fields.One2many("elite.vet.pet.alert", "pet_id", string="Upozornění")
    alert_summary = fields.Char(string="Upozornění (souhrn)", compute="_compute_alert_summary",
                                help="Aktivní upozornění oddělená středníkem.")
    clinical_record_ids = fields.One2many("elite.vet.clinical.record", "pet_id", string="Záznamy návštěv")

    @api.depends("alert_ids.kind", "alert_ids.note", "alert_ids.active")
    def _compute_alert_summary(self):
        for pet in self:
            pet.alert_summary = "; ".join(pet.alert_ids.filtered("active").mapped("display_name")) or False
