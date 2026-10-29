from odoo import fields, models


class GgleapMachine(models.Model):
    _name = "elite.arena.ggleap.machine"
    _description = "ggLeap – počítač"
    _order = "name"

    name = fields.Char(string="Název", required=True, readonly=True)
    uuid = fields.Char(string="ID v ggLeap", required=True, index=True, readonly=True)
    group_uuid = fields.Char(string="Skupina PC v ggLeap", readonly=True)
    state = fields.Char(string="Stav", readonly=True)
    last_update = fields.Datetime(string="Poslední hlášení", readonly=True)
    in_catalog = fields.Boolean(string="V ggLeap", readonly=True, default=True)
    visit_ids = fields.One2many("elite.arena.ggleap.visit", "machine_id", string="Návštěvy")
    active = fields.Boolean(default=True)

    _sql_constraints = [("uuid_uniq", "unique(uuid)", "Počítač z ggLeapu už existuje.")]
