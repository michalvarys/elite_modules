from odoo import fields, models

#: managers and the read-only API account (security/groups.xml)
WINVET_READERS = "elite_vet_reservation.group_reservation_manager,elite_vet_winvet.group_winvet_readonly"


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
    notes = fields.Text(string="Dekurz", readonly=True, help="Text záznamu návštěvy z WinVetu.")
    vital_ids = fields.One2many("elite.vet.visit.vital", "visit_id", string="Vitální hodnoty", readonly=True)
    entered_by_id = fields.Many2one("elite.vet.winvet.user", string="Zapsal(a)", ondelete="set null", readonly=True)
    entered_by_winvet_ref = fields.Integer(string="ID uživatele ve WinVetu", readonly=True)
    doctor_id = fields.Many2one(related="entered_by_id.doctor_id", string="Lékařka", store=True)
    document_id = fields.Many2one("elite.vet.sale.document", string="Doklad", ondelete="set null", readonly=True,
                                  groups=WINVET_READERS)
    document_winvet_ref = fields.Integer(string="ID dokladu ve WinVetu", index=True, readonly=True)
    line_ids = fields.One2many("elite.vet.sale.line", "visit_id", string="Položky", readonly=True,
                               groups=WINVET_READERS)
    amount = fields.Monetary(string="Částka", compute="_compute_amount", currency_field="currency_id",
                             groups=WINVET_READERS)
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


class VetVisitVital(models.Model):
    """One measurement during a WinVet visit (DENNI_ZAZNAM_HODNOTA)."""

    _name = "elite.vet.visit.vital"
    _description = "Vitální hodnoty návštěvy (WinVet)"
    _order = "visit_id, time, id"

    winvet_ref = fields.Integer(string="ID ve WinVetu", required=True, index=True, readonly=True)
    visit_id = fields.Many2one("elite.vet.visit", string="Návštěva", index=True, ondelete="cascade", readonly=True)
    visit_winvet_ref = fields.Integer(string="ID návštěvy ve WinVetu", index=True, readonly=True)
    pet_id = fields.Many2one(related="visit_id.pet_id", string="Pacient", store=True, index=True)
    date = fields.Date(related="visit_id.date", string="Datum", store=True)
    time = fields.Char(string="Čas", readonly=True)
    temperature = fields.Float(string="Teplota (°C)", readonly=True, digits=(4, 1))
    heart_rate = fields.Integer(string="Tep (/min)", readonly=True)
    respiratory_rate = fields.Integer(string="Dech (/min)", readonly=True)
    weight = fields.Float(string="Hmotnost (kg)", readonly=True, digits=(6, 2))
    bp_systolic = fields.Integer(string="Tlak systolický", readonly=True)
    bp_diastolic = fields.Integer(string="Tlak diastolický", readonly=True)

    _sql_constraints = [
        ("winvet_ref_uniq", "unique(winvet_ref)", "Měření s tímto ID z WinVetu už existuje."),
    ]

    def summary(self):
        """'T 38,5 °C · P 120/min · D 30/min · 12,4 kg · TK 120/80' (empty values left out)."""
        self.ensure_one()

        def num(value, digits):
            return ("%.*f" % (digits, value)).rstrip("0").rstrip(".").replace(".", ",")

        parts = []
        if self.temperature:
            parts.append("T %s °C" % num(self.temperature, 1))
        if self.heart_rate:
            parts.append("P %d/min" % self.heart_rate)
        if self.respiratory_rate:
            parts.append("D %d/min" % self.respiratory_rate)
        if self.weight:
            parts.append("%s kg" % num(self.weight, 2))
        if self.bp_systolic or self.bp_diastolic:
            parts.append("TK %s/%s" % (self.bp_systolic or "–", self.bp_diastolic or "–"))
        return " · ".join(parts)
