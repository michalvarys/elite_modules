from odoo import api, fields, models

CLASSIFICATIONS = [
    ("group", "Skupina"), ("product", "Výrobek / lék"), ("set", "Sada"), ("kit", "Souprava"),
    ("service", "Služba"), ("operation", "Operace"), ("alias", "Alias"), ("other", "Jiné"),
]
KINDS = [("service", "Úkon"), ("product", "Lék / zboží"), ("other", "Jiné")]


def kind_of(classification):
    if classification in ("service", "operation"):
        return "service"
    if classification in ("product", "set", "kit"):
        return "product"
    return "other"


class WinvetItem(models.Model):
    _name = "elite.vet.winvet.item"
    _description = "Položka ceníku WinVet"
    _order = "name"

    winvet_ref = fields.Integer(string="ID ve WinVetu", required=True, index=True, readonly=True)
    code = fields.Char(string="Kód", index=True, readonly=True)
    name = fields.Char(string="Název", required=True, readonly=True)
    classification = fields.Selection(CLASSIFICATIONS, string="Klasifikace", readonly=True)
    kind = fields.Selection(KINDS, string="Druh", compute="_compute_kind", store=True,
                            help="Úkon = služba nebo operace, Lék / zboží = výrobek, sada nebo souprava.")
    stock_tracked = fields.Boolean(string="Skladová", readonly=True)
    tracked_drug = fields.Boolean(string="Sledované léčivo", readonly=True)
    unit = fields.Char(string="Jednotka", readonly=True)
    barcode = fields.Char(string="Čárový kód", readonly=True)
    active = fields.Boolean(string="Aktivní", default=True)

    _sql_constraints = [
        ("winvet_ref_uniq", "unique(winvet_ref)", "Položka s tímto ID z WinVetu už existuje."),
    ]

    @api.depends("classification")
    def _compute_kind(self):
        for rec in self:
            rec.kind = kind_of(rec.classification)

    @api.depends("code", "name")
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = "[%s] %s" % (rec.code, rec.name) if rec.code else rec.name
