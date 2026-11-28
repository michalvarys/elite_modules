import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


class PosPaymentMethod(models.Model):
    _inherit = "pos.payment.method"

    pos_button_color = fields.Char(
        "Barva tlačítka v pokladně",
        help="Pozadí tlačítka této platby na obrazovce platby v pokladně (např. #2e7d32). "
             "Prázdné = běžné šedé tlačítko.",
    )

    @api.constrains("pos_button_color")
    def _check_pos_button_color(self):
        for method in self:
            if method.pos_button_color and not HEX_COLOR.match(method.pos_button_color):
                raise ValidationError(_("Barva tlačítka „%s“ musí být ve tvaru #rrggbb, např. #2e7d32.")
                                      % method.pos_button_color)

    def _is_write_forbidden(self, fields):
        # The colour only changes the look of the button, so it can be changed while a till is open.
        return super()._is_write_forbidden(fields - {"pos_button_color"})

    @api.model
    def _load_pos_data_fields(self, config_id):
        return super()._load_pos_data_fields(config_id) + ["pos_button_color"]
