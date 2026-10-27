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


WEB_BOOKING_SOURCES = [
    ("winvet", "WinVet (podle adresy)"),
    ("elite", "Elite Vet (náš kalendář)"),
]


class EliteVetSetting(models.Model):
    """Booking settings live on the same record as the rest of the website
    settings, so the clinic does not have to look in two places."""

    _inherit = "elite.vet.setting"

    # Which calendar the website offers on /rezervacni-system. The default is WinVet: a fresh
    # install and an upgrade of a database that does not have the column yet (the ORM fills the
    # new required column with the default) both show the WinVet form first. The clinic sets up
    # rooms, procedures and the roster, then switches to Elite Vet.
    web_booking_source = fields.Selection(
        WEB_BOOKING_SOURCES, string="Rezervace na webu", required=True, default="winvet",
        help="WinVet (podle adresy) = na stránce /rezervacni-system je formulář WinVet z adresy "
             "níže, jako dřív. Náš webový rezervační systém (stránka i chat) pak žádné rezervace "
             "nepřijímá. Elite Vet (náš kalendář) = na stejném místě je náš rezervační průvodce "
             "a žádosti z webu chodí do Odoo (Rezervace › Čekající). Recepce, tabule a pokladna "
             "objednávají v obou režimech stejně.")

    booking_slot_step = fields.Integer("Krok slotů (min)", default=15,
                                       help="Po kolika minutách se nabízejí začátky termínů.")
    booking_min_hours_before = fields.Integer("Nejdříve za (hodin)", default=24)
    booking_max_days_ahead = fields.Integer("Nejdál dopředu (dní)", default=60)
    booking_cancel_hours_before = fields.Integer("Klient může zrušit do (hodin před)", default=12,
                                                 help="0 = klient nemůže rušit odkazem z e-mailu.")
    booking_notify_enabled = fields.Boolean(
        "Posílat klinice upozornění", default=True,
        help="Zapnuté = klinika dostane e-mail o každé nové rezervaci z webu a o zrušení rezervace "
             "klientem. Vypnuté = klinice nechodí nic; e-maily klientům (potvrzení, změna, zrušení, "
             "připomínka) chodí dál.")
    booking_notify_email = fields.Char("E-mail pro upozornění", default="rezervace@elite-vet.cz",
                                       help="Sem chodí zpráva o každé nové rezervaci z webu a o zrušení "
                                            "rezervace klientem.")
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

    def _check_web_booking_source(self):
        for rec in self:
            if rec.web_booking_source == "winvet" and not (rec.booking_url or "").strip():
                raise ValidationError(_(
                    "Rezervace přes WinVet potřebují adresu formuláře WinVet. Vyplňte ji, "
                    "nebo přepněte rezervace na webu na Elite Vet (náš kalendář)."))

    # ---------- rights (task 16) ----------
    # Only Správce rezervací changes the settings (booking and the contact data of the website);
    # a calendar manager of elite_vet_web who is not Správce rezervací only reads them. The record
    # rules in security/rules.xml say the same; this check gives the clear message first.
    # Reading (website, public) and sudo (nastaveni() creating the record) are not affected.
    def _check_setting_rights(self):
        if not self.env.su and not self.env.user.has_group(SETTING_MANAGER_GROUP):
            raise AccessError(_("Nastavení může měnit jen správce rezervací."))

    # The WinVet address is checked only when somebody chooses WinVet or changes the address:
    # the record created by nastaveni() (or an old record without the address) is not refused.
    @api.model_create_multi
    def create(self, vals_list):
        self._check_setting_rights()
        records = super().create(vals_list)
        for rec, vals in zip(records, vals_list):
            if "web_booking_source" in vals:
                rec._check_web_booking_source()
        return records

    def write(self, vals):
        self._check_setting_rights()
        res = super().write(vals)
        if "web_booking_source" in vals or "booking_url" in vals:
            self._check_web_booking_source()
        return res

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
