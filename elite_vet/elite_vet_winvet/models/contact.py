from odoo import fields, models

CONTACT_TYPES = [("mobile", "Mobil"), ("phone", "Telefon"), ("fax", "Fax"), ("email", "E-mail"),
                 ("web", "Web"), ("other", "Jiný")]
CONTACT_TYPE_CODES = {-1: "mobile", -2: "phone", -3: "fax", -4: "email", -5: "web"}


class WinvetContact(models.Model):
    _name = "elite.vet.winvet.contact"
    _description = "Kontakt z WinVetu"
    _order = "partner_id, type, winvet_ref"

    winvet_ref = fields.Integer(string="ID ve WinVetu", required=True, index=True, readonly=True)
    partner_id = fields.Many2one("res.partner", string="Majitel", index=True, ondelete="cascade", readonly=True)
    owner_winvet_ref = fields.Integer(string="ID majitele ve WinVetu", index=True, readonly=True)
    type = fields.Selection(CONTACT_TYPES, string="Typ", readonly=True)
    value = fields.Char(string="Hodnota", readonly=True)
    label = fields.Char(string="Popis", readonly=True)
    active = fields.Boolean(string="Aktivní", default=True)

    _sql_constraints = [
        ("winvet_ref_uniq", "unique(winvet_ref)", "Kontakt s tímto ID z WinVetu už existuje."),
    ]
