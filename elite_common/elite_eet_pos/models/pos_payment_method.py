from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class PosPaymentMethod(models.Model):
    _inherit = "pos.payment.method"

    eet_register = fields.Boolean(
        "Evidovat v EET",
        compute="_compute_eet_register", store=True, readonly=False, precompute=True,
        help="Platby tímto způsobem se evidují v EET. Vypněte u interních záznamů, za které se nic neplatí, "
             "a u odložené platby na účet zákazníka.",
    )
    eet_voucher_redemption = fields.Boolean(
        "Čerpání předplaceného kreditu/voucheru",
        help="Platba uplatněním dříve prodaného voucheru nebo kreditu na blíže neurčené zboží. "
             "Jde do EET jako čerpání (cerp_zuct) a je součástí celkové tržby.",
    )

    @api.depends("type")
    def _compute_eet_register(self):
        for method in self:
            method.eet_register = method.type != "pay_later"

    @api.constrains("eet_register", "eet_voucher_redemption")
    def _check_eet_voucher_redemption(self):
        for method in self:
            if method.eet_voucher_redemption and not method.eet_register:
                raise ValidationError(_("Čerpání voucheru musí mít zapnuté Evidovat v EET."))
