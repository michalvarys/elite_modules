from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class EliteVetSetting(models.Model):
    """Nastavení rezervací visí na stejném záznamu jako zbytek webu,
    aby klinika nehledala dvě různá nastavení."""

    _inherit = "elite.vet.setting"

    booking_slot_step = fields.Integer("Krok slotů (min)", default=15,
                                       help="Po kolika minutách se nabízejí začátky termínů.")
    booking_min_hours_before = fields.Integer("Nejdříve za (hodin)", default=24)
    booking_max_days_ahead = fields.Integer("Nejdál dopředu (dní)", default=60)
    booking_cancel_hours_before = fields.Integer("Klient může zrušit do (hodin před)", default=12,
                                                 help="0 = klient nemůže rušit odkazem z e-mailu.")
    booking_notify_email = fields.Char("E-mail pro upozornění", default="info@elite-vet.cz",
                                       help="Sem chodí zpráva o každé nové rezervaci z webu.")
    booking_require_doctor = fields.Boolean("Online jen tam, kde slouží lékař", default=False,
                                            help="Zapnuté = termín se nabídne jen v čase, kdy má ordinace zapsanou službu lékaře.")
    booking_block_weekends = fields.Boolean(
        "Víkendy jen ručně (web neobjednává)", default=True,
        help="Zapnuté = web v sobotu a neděli nenabízí žádné termíny. Recepce objednává dál "
             "(i ručním časem mimo ordinační dobu).")
    booking_block_holidays = fields.Boolean(
        "Státní svátky jen ručně (web neobjednává)", default=True,
        help="Zapnuté = web ve státní svátek (včetně Velkého pátku a Velikonočního pondělí) nenabízí "
             "žádné termíny. Svátky se počítají samy, nic se nezadává. Recepce objednává dál.")
    booking_reminder_enabled = fields.Boolean("Posílat připomínku", default=False)
    booking_reminder_hours_before = fields.Integer("Připomínka (hodin před)", default=24)
    booking_deposits_enabled = fields.Boolean("Zálohy zapnuté", default=False,
                                              help="Dokud je vypnuté, záloha se nikde neukazuje.")
    booking_consent_text = fields.Html("Text souhlasu pod formulářem", translate=True, sanitize=False)
    booking_intro = fields.Html("Text nad rezervací", translate=True, sanitize=False)

    @api.constrains("booking_slot_step", "booking_min_hours_before", "booking_max_days_ahead", "booking_cancel_hours_before")
    def _check_booking_numbers(self):
        for rec in self:
            if rec.booking_slot_step <= 0 or rec.booking_slot_step % 5:
                raise ValidationError(_("Krok slotů musí být kladný násobek 5 minut."))
            if min(rec.booking_min_hours_before, rec.booking_max_days_ahead, rec.booking_cancel_hours_before) < 0:
                raise ValidationError(_("Hodnoty časových limitů nesmí být záporné."))
