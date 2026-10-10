from odoo import api, fields, models

# Predvolene barvy. Vyber misto psani hexu, aby se v tom nedalo udelat preklep.
COLORS = {
    "green": "#16a34a",
    "orange": "#ea580c",
    "purple": "#6d28d9",
    "pink": "#db2777",
    "red": "#b91c1c",
    "blue": "#2563eb",
    "teal": "#2b7870",
    "grey": "#64748b",
}


class VetShiftType(models.Model):
    """Typ smeny: nazev, cas od-do a barva.

    Diky tomu jde cas smeny zmenit v Odoo a projevi se to na webu vsude
    najednou - ve vysvetlivkach i v bublinach u jmen.
    """

    _name = "elite.vet.shift.type"
    _description = "Typ směny"
    _order = "sequence, id"

    name = fields.Char(string="Název", required=True, translate=True)
    sequence = fields.Integer(string="Pořadí", default=10)
    time_from = fields.Float(string="Od", default=8.0)
    time_to = fields.Float(string="Do", default=14.0)
    color = fields.Selection(
        [
            ("green", "Zelená"),
            ("orange", "Oranžová"),
            ("purple", "Fialová"),
            ("pink", "Růžová"),
            ("red", "Červená"),
            ("blue", "Modrá"),
            ("teal", "Tyrkysová"),
            ("grey", "Šedá"),
        ],
        string="Barva na webu",
        required=True,
        default="green",
    )
    is_note = fields.Boolean(
        string="Celodenní poznámka",
        help="Zaškrtněte u typu, který není služba lékařky — zavřeno, státní "
             "svátek, sanitární den, den otevřených dveří. Nevybírá se u něj "
             "lékařka ani čas; na webu se přes celou buňku vypíše text "
             "z pole Poznámka, a když je prázdné, název typu.",
    )
    active = fields.Boolean(string="Aktivní", default=True)

    time_display = fields.Char(string="Čas", compute="_compute_time_display")
    color_hex = fields.Char(compute="_compute_color_hex")

    @api.depends("time_from", "time_to", "is_note")
    def _compute_time_display(self):
        for rec in self:
            if rec.is_note:
                rec.time_display = ""
            else:
                rec.time_display = "%s–%s" % (
                    rec._format_hour(rec.time_from),
                    rec._format_hour(rec.time_to),
                )

    @api.depends("color")
    def _compute_color_hex(self):
        for rec in self:
            rec.color_hex = COLORS.get(rec.color, COLORS["grey"])

    @staticmethod
    def _format_hour(value):
        """8.0 -> '8:00', 14.5 -> '14:30'."""
        hours = int(value)
        minutes = int(round((value - hours) * 60))
        if minutes == 60:
            hours, minutes = hours + 1, 0
        return "%d:%02d" % (hours, minutes)
