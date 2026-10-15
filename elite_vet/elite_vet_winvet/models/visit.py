from odoo import fields, models


class VetVisit(models.Model):
    _name = "elite.vet.visit"
    _description = "Návštěva (WinVet)"
    _order = "date desc, time desc, id desc"
    _rec_name = "display_label"

    winvet_ref = fields.Integer(string="ID ve WinVetu", required=True, index=True, readonly=True)
    pet_id = fields.Many2one("elite.vet.pet", string="Pacient", index=True, ondelete="cascade", readonly=True)
    pet_winvet_ref = fields.Integer(string="ID pacienta ve WinVetu", index=True, readonly=True)
    partner_id = fields.Many2one(related="pet_id.partner_id", string="Majitel", store=True, index=True)
    species = fields.Selection(related="pet_id.species", string="Druh", store=True)
    date = fields.Date(string="Datum", index=True, readonly=True)
    time = fields.Char(string="Čas", readonly=True)
    case_name = fields.Char(string="Případ", readonly=True)
    diagnosis_code = fields.Char(string="Kód diagnózy", readonly=True)
    diagnosis_name = fields.Char(string="Diagnóza", readonly=True)
    entered_by_id = fields.Many2one("elite.vet.winvet.user", string="Zapsal(a)", ondelete="set null", readonly=True)
    entered_by_winvet_ref = fields.Integer(string="ID uživatele ve WinVetu", readonly=True)
    doctor_id = fields.Many2one(related="entered_by_id.doctor_id", string="Lékařka", store=True)
    document_id = fields.Many2one("elite.vet.sale.document", string="Doklad", ondelete="set null", readonly=True,
                                  groups="elite_vet_reservation.group_reservation_manager")
    document_winvet_ref = fields.Integer(string="ID dokladu ve WinVetu", index=True, readonly=True)
    line_ids = fields.One2many("elite.vet.sale.line", "visit_id", string="Položky", readonly=True,
                               groups="elite_vet_reservation.group_reservation_manager")
    amount = fields.Monetary(string="Částka", compute="_compute_amount", currency_field="currency_id",
                             groups="elite_vet_reservation.group_reservation_manager")
    currency_id = fields.Many2one("res.currency", compute="_compute_amount")
    display_label = fields.Char(compute="_compute_display_label")

    _sql_constraints = [
        ("winvet_ref_uniq", "unique(winvet_ref)", "Návštěva s tímto ID z WinVetu už existuje."),
    ]

    def _compute_amount(self):
        czk = self.env.ref("base.CZK")
        for rec in self:
            rec.currency_id = czk
            rec.amount = sum(rec.sudo().line_ids.mapped("amount"))

    def _compute_display_label(self):
        for rec in self:
            parts = [fields.Date.to_string(rec.date) if rec.date else "", rec.pet_id.name or "",
                     rec.diagnosis_name or rec.case_name or ""]
            rec.display_label = " – ".join(p for p in parts if p) or "Návštěva %s" % rec.winvet_ref
