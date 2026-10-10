from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class VetShift(models.Model):
    """Jeden radek rozpisu: jeden den, jedna lekarka, jedna smena.

    Vyjimkou jsou typy s priznakem "celodenni poznamka" (zavreno, statni
    svatek, den otevrenych dveri). Ty nejsou sluzba lekarky, takze se u nich
    nevybira lekarka ani cas a na webu se vypisou pres celou bunku.
    """

    _name = "elite.vet.shift"
    _description = "Směna v rozpisu"
    _order = "date, type_id"

    date = fields.Date(
        string="Datum",
        required=True,
        index=True,
        default=fields.Date.context_today,
    )
    doctor_id = fields.Many2one(
        "elite.vet.doctor",
        string="Lékařka",
        ondelete="restrict",
    )
    type_id = fields.Many2one(
        "elite.vet.shift.type",
        string="Směna",
        required=True,
        ondelete="restrict",
        default=lambda self: self.env["elite.vet.shift.type"].search(
            [("is_note", "=", False)], limit=1
        ),
    )
    is_note = fields.Boolean(related="type_id.is_note")
    note = fields.Char(
        string="Poznámka",
        translate=True,
        help="Text, který se vypíše na webu přes celou buňku — například "
             "Státní svátek. Vyplňuje se jen u typů s celodenní poznámkou; "
             "když zůstane prázdný, použije se název typu.",
    )

    @api.depends("date", "doctor_id", "type_id", "note")
    def _compute_display_name(self):
        for shift in self:
            if shift.type_id.is_note:
                shift.display_name = shift.note or shift.type_id.name
            else:
                shift.display_name = "%s — %s" % (
                    shift.doctor_id.name or _("Nezadáno"),
                    shift.type_id.name or "",
                )

    @api.onchange("type_id")
    def _onchange_type_id(self):
        """U celodenni poznamky nema lekarka smysl, tak ji rovnou vyhodime."""
        if self.type_id.is_note:
            self.doctor_id = False

    @api.constrains("doctor_id", "type_id")
    def _check_doctor(self):
        for shift in self:
            if not shift.type_id.is_note and not shift.doctor_id:
                raise ValidationError(_(
                    "U služby vyberte lékařku.\n\n"
                    "Bez lékařky jde uložit jen typ, který má v Typech směn "
                    "zaškrtnutou Celodenní poznámku — zavřeno, státní svátek, "
                    "den otevřených dveří a podobně."
                ))
