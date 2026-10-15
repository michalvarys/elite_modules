"""Structural changes of the WinVet database reported by the bridge (table level)."""

from odoo import fields, models

SEVERITIES = [
    ("breaking", "Blokující"),
    ("journal", "Žurnál změn"),
    ("warning", "Upozornění"),
    ("info", "Informace"),
]
OBJECTS = [
    ("table", "Tabulka"), ("view", "Pohled"), ("column", "Sloupec"), ("primary_key", "Primární klíč"),
    ("unique", "Unikátní klíč"), ("foreign_key", "Cizí klíč"), ("index", "Index"), ("trigger", "Trigger"),
    ("procedure", "Procedura"), ("db_trigger", "Databázový trigger"),
]
CHANGES = [("added", "Přidáno"), ("removed", "Odebráno"), ("changed", "Změněno")]


class WinvetSchemaChange(models.Model):
    """One difference between the live WinVet schema and the baseline approved in the bridge.

    Rows are kept per schema hash (history); the status form shows the rows of the current hash.
    """

    _name = "elite.vet.winvet.schema.change"
    _description = "Změna struktury WinVetu"
    _order = "detected_at desc, severity_rank, table_name, object_name"

    detected_at = fields.Datetime(string="Zjištěno", required=True, readonly=True)
    schema_hash = fields.Char(string="Otisk databáze", readonly=True, index=True)
    baseline_hash = fields.Char(string="Schválený otisk", readonly=True)
    winvet_version = fields.Char(string="Verze WinVetu", readonly=True)
    severity = fields.Selection(SEVERITIES, string="Závažnost", required=True, readonly=True)
    severity_rank = fields.Integer(readonly=True)
    object_type = fields.Selection(OBJECTS, string="Objekt", readonly=True)
    table_name = fields.Char(string="Tabulka", readonly=True)
    object_name = fields.Char(string="Název", readonly=True)
    change = fields.Selection(CHANGES, string="Změna", readonly=True)
    old_value = fields.Char(string="Původně", readonly=True)
    new_value = fields.Char(string="Nově", readonly=True)
    acknowledged = fields.Boolean(string="Prověřeno", help="Změnu někdo zkontroloval.")

    def action_acknowledge(self):
        self.write({"acknowledged": True})
        return True
