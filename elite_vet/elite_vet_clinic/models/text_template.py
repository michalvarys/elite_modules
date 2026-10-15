from odoo import api, fields, models

SECTIONS = [("anamnesis", "Anamnéza"), ("examination", "Vyšetření"), ("diagnosis", "Diagnóza a doporučení"),
            ("any", "Kterýkoli")]
# Text fields of the clinical record a template can be applied to.
RECORD_SECTIONS = ("anamnesis", "examination", "diagnosis")


class VetTextTemplate(models.Model):
    """Text template (WinVet FRAZE or created in Odoo) inserted into a clinical record."""

    _name = "elite.vet.text.template"
    _description = "Šablona textu"
    _order = "section, sequence, name, id"

    name = fields.Char(string="Název", required=True)
    section = fields.Selection(SECTIONS, string="Oddíl", required=True, default="any",
                               help="Ve kterém poli záznamu se šablona nabízí.")
    body = fields.Text(string="Text", required=True)
    sequence = fields.Integer(string="Pořadí", default=10)
    active = fields.Boolean(string="Aktivní", default=True)
    group_name = fields.Char(string="Skupina ve WinVetu", readonly=True)
    winvet_ref = fields.Integer(string="ID ve WinVetu", index=True, readonly=True, copy=False)
    edited_in_odoo = fields.Boolean(
        string="Upraveno v Odoo", readonly=True, copy=False,
        help="Šablona z WinVetu, jejíž název nebo text někdo změnil v Odoo. Most ji už nepřepisuje.")

    def init(self):
        super().init()
        self.env.cr.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS elite_vet_text_template_winvet_ref_uniq"
            " ON elite_vet_text_template (winvet_ref) WHERE winvet_ref IS NOT NULL AND winvet_ref <> 0")

    def write(self, vals):
        if not self.env.context.get("winvet_sync") and ("name" in vals or "body" in vals):
            synced = self.filtered(lambda t: t.winvet_ref and not t.edited_in_odoo)
            if synced:
                super(VetTextTemplate, synced).write({"edited_in_odoo": True})
        return super().write(vals)
