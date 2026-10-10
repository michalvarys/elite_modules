from odoo import fields, models


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
    booking_reminder_enabled = fields.Boolean("Posílat připomínku", default=False)
    booking_reminder_hours_before = fields.Integer("Připomínka (hodin před)", default=24)
    booking_deposits_enabled = fields.Boolean("Zálohy zapnuté", default=False,
                                              help="Dokud je vypnuté, záloha se nikde neukazuje.")
    booking_consent_text = fields.Html("Text souhlasu pod formulářem", translate=True, sanitize=False)
    booking_intro = fields.Html("Text nad rezervací", translate=True, sanitize=False)
