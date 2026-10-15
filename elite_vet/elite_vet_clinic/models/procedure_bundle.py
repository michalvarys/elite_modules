from odoo import api, fields, models


class VetProcedureBundle(models.Model):
    """Bundle of price list items added to the bill with one click (WinVet SABLONA_VYKONU)."""

    _name = "elite.vet.procedure.bundle"
    _description = "Balíček výkonů"
    _order = "name, id"

    name = fields.Char(string="Název", required=True)
    code = fields.Char(string="Kód")
    description = fields.Text(string="Popis")
    line_ids = fields.One2many("elite.vet.procedure.bundle.line", "bundle_id", string="Položky")
    line_count = fields.Integer(string="Počet položek", compute="_compute_totals")
    currency_id = fields.Many2one("res.currency", compute="_compute_totals")
    amount = fields.Monetary(string="Cena celkem", compute="_compute_totals", currency_field="currency_id",
                             help="Součet aktuálních cen položek z ceníku.")
    active = fields.Boolean(string="Aktivní", default=True)
    winvet_ref = fields.Integer(string="ID ve WinVetu", index=True, readonly=True, copy=False)
    edited_in_odoo = fields.Boolean(
        string="Upraveno v Odoo", readonly=True, copy=False,
        help="Balíček z WinVetu změněný v Odoo (název, kód, popis nebo položky). Most ho už nepřepisuje.")

    def init(self):
        super().init()
        self.env.cr.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS elite_vet_procedure_bundle_winvet_ref_uniq"
            " ON elite_vet_procedure_bundle (winvet_ref) WHERE winvet_ref IS NOT NULL AND winvet_ref <> 0")

    @api.depends("line_ids.quantity", "line_ids.item_id.price")
    def _compute_totals(self):
        czk = self.env.ref("base.CZK")
        for rec in self:
            rec.currency_id = czk
            rec.line_count = len(rec.line_ids)
            rec.amount = sum(line.quantity * line.item_id.price for line in rec.line_ids)

    def _mark_edited(self):
        if self.env.context.get("winvet_sync"):
            return
        todo = self.filtered(lambda b: b.winvet_ref and not b.edited_in_odoo)
        if todo:
            super(VetProcedureBundle, todo).write({"edited_in_odoo": True})

    def write(self, vals):
        if {"name", "code", "description", "line_ids"} & set(vals):
            self._mark_edited()
        return super().write(vals)


class VetProcedureBundleLine(models.Model):
    _name = "elite.vet.procedure.bundle.line"
    _description = "Položka balíčku výkonů"
    _order = "bundle_id, sequence, id"

    bundle_id = fields.Many2one("elite.vet.procedure.bundle", string="Balíček", index=True, ondelete="cascade")
    bundle_winvet_ref = fields.Integer(string="ID balíčku ve WinVetu", index=True, readonly=True)
    sequence = fields.Integer(string="Pořadí", default=10)
    item_id = fields.Many2one("elite.vet.winvet.item", string="Položka ceníku", ondelete="set null")
    item_winvet_ref = fields.Integer(string="ID položky ve WinVetu", index=True, readonly=True)
    name = fields.Char(string="Název", required=True)
    quantity = fields.Float(string="Množství", default=1.0, digits=(10, 3))
    unit = fields.Char(string="Jednotka")
    winvet_ref = fields.Integer(string="ID ve WinVetu", index=True, readonly=True, copy=False)

    def init(self):
        super().init()
        self.env.cr.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS elite_vet_procedure_bundle_line_winvet_ref_uniq"
            " ON elite_vet_procedure_bundle_line (winvet_ref) WHERE winvet_ref IS NOT NULL AND winvet_ref <> 0")

    @api.onchange("item_id")
    def _onchange_item_id(self):
        if self.item_id:
            self.name = self.item_id.name
            self.unit = self.item_id.unit

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines.bundle_id._mark_edited()
        return lines

    def write(self, vals):
        self.bundle_id._mark_edited()
        res = super().write(vals)
        if "bundle_id" in vals:
            self.bundle_id._mark_edited()
        return res

    def unlink(self):
        self.bundle_id._mark_edited()
        return super().unlink()
