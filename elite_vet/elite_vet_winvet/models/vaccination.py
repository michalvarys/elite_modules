from odoo import fields, models


class VetVaccination(models.Model):
    _name = "elite.vet.vaccination"
    _description = "Očkování / odčervení (WinVet)"
    _order = "date desc, id desc"
    _rec_name = "item_name"

    winvet_ref = fields.Integer(string="ID ve WinVetu", required=True, index=True, readonly=True)
    pet_id = fields.Many2one("elite.vet.pet", string="Pacient", index=True, ondelete="cascade", readonly=True)
    pet_winvet_ref = fields.Integer(string="ID pacienta ve WinVetu", index=True, readonly=True)
    partner_id = fields.Many2one(related="pet_id.partner_id", string="Majitel", store=True, index=True)
    date = fields.Date(string="Datum", index=True, readonly=True)
    next_date = fields.Date(string="Příští termín", readonly=True)
    item_id = fields.Many2one("elite.vet.winvet.item", string="Položka", ondelete="set null", readonly=True)
    item_winvet_ref = fields.Integer(string="ID položky ve WinVetu", index=True, readonly=True)
    item_name = fields.Char(string="Název", readonly=True)
    quantity = fields.Float(string="Množství", readonly=True)
    unit = fields.Char(string="Jednotka", readonly=True)
    kind = fields.Integer(string="Typ (WinVet)", readonly=True,
                          help="Hodnota TYP z WinVetu (rozlišuje vakcinaci a odčervení).")

    _sql_constraints = [
        ("winvet_ref_uniq", "unique(winvet_ref)", "Záznam s tímto ID z WinVetu už existuje."),
    ]
