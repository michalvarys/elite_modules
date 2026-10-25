from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


SETTING_MANAGER_GROUP = "elite_vet_reservation.group_reservation_manager"
# Menus and server actions of elite_vet_web that open the settings record: Správce rezervací only.
# The leaf menus and the actions have no groups in elite_vet_web's XML, so an update of elite_vet_web
# alone keeps what is set here; the root "Nastavení kontaktu" gets the calendar manager back from
# that update, but without a visible item it stays hidden for that group.
SETTING_MENUS = (
    "elite_vet_web.menu_nastaveni_root",
    "elite_vet_web.menu_nastaveni_web",
    "elite_vet_web.menu_rezervace_nastaveni",
)
SETTING_ACTIONS = (
    "elite_vet_web.action_setting_otevrit",
    "elite_vet_web.action_setting_rezervace",
)


class EliteVetSetting(models.Model):
    """Booking settings live on the same record as the rest of the website
    settings, so the clinic does not have to look in two places."""

    _inherit = "elite.vet.setting"

    booking_slot_step = fields.Integer("Krok slotů (min)", default=15,
                                       help="Po kolika minutách se nabízejí začátky termínů.")
    booking_min_hours_before = fields.Integer("Nejdříve za (hodin)", default=24)
    booking_max_days_ahead = fields.Integer("Nejdál dopředu (dní)", default=60)
    booking_cancel_hours_before = fields.Integer("Klient může zrušit do (hodin před)", default=12,
                                                 help="0 = klient nemůže rušit odkazem z e-mailu.")
    booking_notify_email = fields.Char("E-mail pro upozornění", default="info@elite-vet.cz",
                                       help="Sem chodí zpráva o každé nové rezervaci z webu.")
    booking_email_from = fields.Char(
        "Odesílatel e-mailů", default="rezervace@elite-vet.cz",
        help="Adresa, ze které chodí klientům e-maily k rezervacím (potvrzení, změna, zrušení, "
             "připomínka). Musí to být schránka, přes kterou Odoo odesílá (odchozí poštovní "
             "server), jinak e-maily skončí ve spamu nebo je server odmítne. Jde zadat i se "
             "jménem: Elite Vet Karlovy Vary <rezervace@elite-vet.cz>.")
    booking_email_reply_to = fields.Char(
        "Odpovědi klientů na", default="info@elite-vet.cz",
        help="Kam dojde odpověď, když klient na e-mail k rezervaci odpoví. Prázdné = na odesílatele.")
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

    # ---------- rights (task 16) ----------
    # Only Správce rezervací changes the settings (booking and the contact data of the website);
    # a calendar manager of elite_vet_web who is not Správce rezervací only reads them. The record
    # rules in security/rules.xml say the same; this check gives the clear message first.
    # Reading (website, public) and sudo (nastaveni() creating the record) are not affected.
    def _check_setting_rights(self):
        if not self.env.su and not self.env.user.has_group(SETTING_MANAGER_GROUP):
            raise AccessError(_("Nastavení může měnit jen správce rezervací."))

    @api.model_create_multi
    def create(self, vals_list):
        self._check_setting_rights()
        return super().create(vals_list)

    def write(self, vals):
        self._check_setting_rights()
        return super().write(vals)

    def unlink(self):
        self._check_setting_rights()
        return super().unlink()

    @api.model
    def _elite_vet_apply_setting_groups(self):
        """Called by <function> in views/menus.xml on every install / update of this module."""
        manager = self.env.ref(SETTING_MANAGER_GROUP)
        for xmlid in SETTING_MENUS + SETTING_ACTIONS:
            record = self.env.ref(xmlid, raise_if_not_found=False)
            if record and record.groups_id != manager:
                record.groups_id = [(6, 0, manager.ids)]
