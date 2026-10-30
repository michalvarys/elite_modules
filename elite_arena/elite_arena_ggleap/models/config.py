"""Settings of the ggLeap sync, stored in ir.config_parameter (prefix ``elite_arena_ggleap.``).

The AuthToken has to be stored in plain text, because Odoo sends it to ggLeap on every
run; the form never shows it back (only "token is set"), and only system admins can read
ir.config_parameter."""

from odoo import api, fields, models
from odoo.exceptions import UserError

from .ggleap_client import BASES, GgleapClient, GgleapError

PREFIX = "elite_arena_ggleap."
DEFAULTS = {
    "base": "production",
    "rpm": 18,
    "history_days": 365,
    "risk_days": 30,
    "lost_days": 90,
    "create_partners": True,
    "run_seconds": 100,
    "daily_limit": 5000,
    "details_per_run": 30,
    "sessions_per_run": 20,
    "gamepasses_per_run": 10,
    "gamepass_days": 14,
    "bookings_ahead": 14,
}


def get_settings(env):
    """Current settings as a dict with proper types (falls back to DEFAULTS)."""
    params = env["ir.config_parameter"].sudo()
    out = {"auth_token": params.get_param(PREFIX + "auth_token") or ""}
    for key, default in DEFAULTS.items():
        raw = params.get_param(PREFIX + key)
        if raw in (None, False, ""):
            out[key] = default
        elif isinstance(default, bool):
            out[key] = raw not in ("0", "False", "false")
        elif isinstance(default, int):
            try:
                out[key] = int(raw)
            except ValueError:
                out[key] = default
        else:
            out[key] = raw
    if out["base"] not in BASES:
        out["base"] = DEFAULTS["base"]
    return out


class GgleapConfig(models.TransientModel):
    _name = "elite.arena.ggleap.config"
    _description = "ggLeap – nastavení synchronizace"

    auth_token = fields.Char(string="Nový AuthToken",
                             help="ggLeap admin → Settings → API → Public API. Vyplňte jen při změně; "
                                  "uložený token se z bezpečnostních důvodů nezobrazuje.")
    token_set = fields.Boolean(string="AuthToken je uložen", readonly=True)
    base = fields.Selection([("production", "Ostrý provoz"), ("beta", "Beta (testovací)")],
                            string="Prostředí ggLeap", required=True)
    rpm = fields.Integer(string="Nejvýš dotazů za minutu",
                         help="Tarif Basic dovolí 20 za minutu. Nechte rezervu pro jiné nástroje se stejným tokenem.")
    daily_limit = fields.Integer(string="Nejvýš dotazů za den",
                                 help="Tarif Basic dovolí 10 000 denně (pro všechny nástroje dohromady).")
    run_seconds = fields.Integer(string="Délka jednoho běhu (s)",
                                 help="Běh skončí včas a další pokračuje tam, kde přestal. Na serveru s workery "
                                      "musí být menší než limit_time_real_cron (výchozí 120 s).")
    history_days = fields.Integer(string="Stáhnout historii (dní)",
                                  help="Jak daleko do minulosti se stahují návštěvy a prodeje při prvním běhu. "
                                       "ggLeap vrací zhruba posledních 6 měsíců aktivity.")
    details_per_run = fields.Integer(string="Detailů hráčů za běh",
                                     help="Detail hráče (registrace, poslední návštěva před historií, zbývající čas) "
                                          "stojí 1 dotaz. Stahuje se jednou pro každého nového hráče.")
    sessions_per_run = fields.Integer(string="Doplnění délky sezení za běh",
                                      help="Když ggLeap nezapíše odhlášení (došel čas), délka sezení se doplní "
                                           "z přehledu sezení hráče. Stojí 1 dotaz na hráče.")
    gamepasses_per_run = fields.Integer(string="Načtení passů hráčů za běh",
                                        help="Passy hráče stojí 1 dotaz. Načtou se jednou pro každého hráče "
                                             "a pak znovu po každé jeho návštěvě (passy se při hraní odečítají).")
    gamepass_days = fields.Integer(string="Přidaný pass platí (dní)",
                                   help="Výchozí platnost passu přidaného z Odoo. Jde změnit u každého passu.")
    bookings_ahead = fields.Integer(string="Rezervace dopředu (dní)")
    risk_days = fields.Integer(string="„Přestává chodit“ po (dnech)",
                               help="Pravidelný hráč, který nepřišel tolik dní, je ve skupině Přestává chodit.")
    lost_days = fields.Integer(string="„Ztracený“ po (dnech)")
    create_partners = fields.Boolean(string="Zakládat kontakty z hráčů",
                                     help="Hráč s e-mailem nebo jménem dostane kontakt (nebo se spáruje s existujícím "
                                          "podle e-mailu), aby šel použít v e-mailingu.")

    def _compute_display_name(self):
        for rec in self:
            rec.display_name = "Nastavení ggLeap"

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        settings = get_settings(self.env)
        for key in DEFAULTS:
            if key in fields_list:
                res[key] = settings[key]
        res["token_set"] = bool(settings["auth_token"])
        return res

    def _store(self):
        self.ensure_one()
        if self.lost_days <= self.risk_days:
            raise UserError("„Ztracený“ musí být víc dní než „Přestává chodit“.")
        if self.gamepass_days < 1:
            raise UserError("Přidaný pass musí platit aspoň 1 den.")
        if self.rpm < 1 or self.daily_limit < 1 or self.run_seconds < 20:
            raise UserError("Limity musí být kladné a běh aspoň 20 sekund.")
        params = self.env["ir.config_parameter"].sudo()
        for key in DEFAULTS:
            value = self[key]
            params.set_param(PREFIX + key, ("1" if value else "0") if isinstance(value, bool) else str(value))
        if self.auth_token:
            params.set_param(PREFIX + "auth_token", self.auth_token.strip())

    def _reopen(self, message=None, kind="success"):
        action = {
            "type": "ir.actions.act_window", "res_model": self._name, "view_mode": "form",
            # explicit views: the action goes through the notification's "next" param, which the
            # server does not clean up like a normal button result
            "views": [[False, "form"]],
            "target": "main", "res_id": self.create({}).id, "name": "Nastavení ggLeap",
        }
        if not message:
            return action
        return {"type": "ir.actions.client", "tag": "display_notification",
                "params": {"message": message, "type": kind, "sticky": kind != "success", "next": action}}

    def action_save(self):
        self._store()
        return self._reopen("Nastavení uloženo.")

    def action_test(self):
        """Saves and checks the token with two cheap calls (JWT + list of PCs)."""
        self._store()
        settings = get_settings(self.env)
        try:
            client = GgleapClient(BASES[settings["base"]], settings["auth_token"], rpm=settings["rpm"], max_calls=3)
            machines = client.get("/machines/get-all").get("Machines") or []
        except GgleapError as err:
            return self._reopen("Spojení s ggLeap nefunguje: %s" % err, "danger")
        return self._reopen("Spojení funguje. ggLeap hlásí %d počítačů." % len(machines))

    def action_sync_now(self):
        self._store()
        self.env["elite.arena.ggleap.sync"].trigger()
        return self._reopen("Synchronizace se spustí na pozadí během chvíle. Průběh je ve Stavu synchronizace.")

    def action_forget_token(self):
        self.env["ir.config_parameter"].sudo().set_param(PREFIX + "auth_token", False)
        return self._reopen("AuthToken smazán, synchronizace se zastaví.", "warning")
