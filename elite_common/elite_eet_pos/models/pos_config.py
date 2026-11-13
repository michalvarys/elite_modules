import base64
import binascii
from datetime import datetime
from zoneinfo import ZoneInfo

from odoo import _, api, fields, models
from odoo.tools import format_datetime

EET_GO_LIVE = datetime(2027, 1, 1, tzinfo=ZoneInfo("Europe/Prague"))
CERT_WARNING_DAYS = 21

EET_DATA_FIELDS = {"eet_id_jednotky": "id_jednotky", "eet_start_datetime": "start_datetime", "eet_eic": "eic"}
EET_CERT_FIELDS = {
    "eet_certificate_file": "certificate_file",
    "eet_certificate_filename": "certificate_filename",
    "eet_certificate_password": "certificate_password",
}
EET_SETTINGS_FIELDS = set(EET_DATA_FIELDS) | set(EET_CERT_FIELDS) | {"eet_enabled", "eet_cert_source_config_id"}


def default_start():
    """1. 1. 2027 0:00 in Prague, or now once that has passed (naive UTC like fields.Datetime)."""
    go_live = EET_GO_LIVE.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
    return max(go_live, fields.Datetime.now().replace(microsecond=0))


def p12_bytes(value):
    """Base64 content as bytes, or None for an empty value or the size label a form may send back."""
    if not value:
        return None
    value = value.encode() if isinstance(value, str) else value
    try:
        return value if len(base64.b64decode(value, validate=True)) > 100 else None
    except (binascii.Error, ValueError):
        return None


class PosConfig(models.Model):
    _inherit = "pos.config"

    eet_device_ids = fields.One2many("elite.eet.device", "pos_config_id", "Nastavení EET (vazba)")
    eet_device_id = fields.Many2one("elite.eet.device", "Nastavení EET", compute="_compute_eet_device_id")

    # Shown and edited in Point of Sale → Configuration → Settings; stored on the till's EET device
    # (see write / _eet_apply_settings).
    eet_enabled = fields.Boolean("Evidovat tržby v EET", compute="_compute_eet_settings")
    eet_eic = fields.Char("EIČ", compute="_compute_eet_settings")
    eet_id_jednotky = fields.Char("Číslo evidenční jednotky", compute="_compute_eet_settings")
    eet_start_datetime = fields.Datetime("EET od", compute="_compute_eet_settings")
    eet_environment = fields.Selection(
        [("playground", "Zkušební (Playground)"), ("production", "Ostré")], "Prostředí",
        compute="_compute_eet_settings",
    )
    eet_cert_valid_to = fields.Datetime("Certifikát platí do", compute="_compute_eet_settings")
    eet_status = fields.Char("Stav EET", compute="_compute_eet_settings")
    eet_status_level = fields.Selection(
        [("none", "Nenastaveno"), ("ok", "V pořádku"), ("warning", "Upozornění"), ("danger", "Chyba")],
        "Úroveň stavu EET", compute="_compute_eet_settings",
    )
    eet_certificate_file = fields.Binary(
        "Certifikát (.p12)", compute="_compute_eet_certificate", groups="base.group_system"
    )
    eet_certificate_filename = fields.Char(
        "Soubor certifikátu", compute="_compute_eet_certificate", groups="base.group_system"
    )
    eet_certificate_password = fields.Char(
        "Heslo certifikátu", compute="_compute_eet_certificate", groups="base.group_system"
    )
    eet_cert_source_config_id = fields.Many2one(
        "pos.config", "Převzít certifikát z pokladny", compute="_compute_eet_certificate",
        groups="base.group_system",
        help="Pokladny stejného poplatníka mohou mít jeden certifikát. Vyberte pokladnu, ze které se převezme.",
    )

    @api.depends("eet_device_ids")
    def _compute_eet_device_id(self):
        for config in self:
            config.eet_device_id = config.eet_device_ids[:1]

    @api.depends(
        "eet_device_ids.active_eet", "eet_device_ids.eic", "eet_device_ids.id_jednotky",
        "eet_device_ids.start_datetime", "eet_device_ids.environment", "eet_device_ids.cert_valid_to",
        "eet_device_ids.attempt_ids", "eet_device_ids.sale_ids.state",
    )
    def _compute_eet_settings(self):
        for config in self:
            device = config.eet_device_ids[:1]
            config.eet_enabled = device.active_eet
            config.eet_eic = device.eic
            config.eet_id_jednotky = device.id_jednotky
            config.eet_start_datetime = device.start_datetime or default_start()
            config.eet_environment = device.environment or "playground"
            config.eet_cert_valid_to = device.cert_valid_to
            config.eet_status_level, config.eet_status = config._eet_status(device)

    @api.depends("eet_device_ids")
    def _compute_eet_certificate(self):
        for config in self:
            device = config.eet_device_ids[:1].sudo()
            config.eet_certificate_file = device.certificate_file
            config.eet_certificate_filename = device.certificate_filename or (
                device.certificate_file and "certifikat.p12")
            config.eet_certificate_password = device.certificate_password
            config.eet_cert_source_config_id = False

    def _eet_status(self, device):
        """(level, text) for the status line in the settings."""
        if not device:
            return "none", _("EET není nastavené. Vyplňte číslo evidenční jednotky a nahrajte certifikát.")
        missing = [
            label for label, value in [
                (_("certifikát"), device.cert_valid_to),
                (_("číslo evidenční jednotky"), device.id_jednotky),
                (_("EIČ"), device.eic),
            ] if not value
        ]
        if missing:
            return "warning", _("Chybí: %s.", ", ".join(missing))
        if device.cert_warning:
            return "warning", device.cert_warning
        now = fields.Datetime.now()
        if device.cert_valid_to < now:
            return "danger", _("Certifikát vypršel. Vydejte nový v portálu MOJE daně a nahrajte ho.")
        open_sales = device.sale_ids.filtered(lambda s: s.state in ("pending", "error"))
        if open_sales:
            return "danger", _("%s tržeb ještě není v EET. Podívejte se do Pokladna → EET → Tržby EET.",
                               len(open_sales))
        env = dict(self._fields["eet_environment"].selection)[device.environment]
        if device.active_eet:
            text = _("EET je zapnuté, prostředí %(env)s, tržby od %(start)s.",
                     env=env, start=format_datetime(self.env, device.start_datetime))
        else:
            text = _("EET je vypnuté, prostředí %s.", env)
        level = "ok"
        check = device.attempt_ids.filtered("verification").sorted("sent_at", reverse=True)[:1]
        if not check:
            level = "warning"
            text += " " + _("Spojení zatím není ověřené, klikněte na Ověřit spojení.")
        elif check.result != "verified":
            level = "danger"
            text += " " + _("Poslední ověření spojení selhalo: %s", check.message or check.result)
        else:
            text += " " + _("Spojení ověřeno %s.", format_datetime(self.env, check.sent_at))
        if (device.cert_valid_to - now).days < CERT_WARNING_DAYS:
            level = "warning" if level == "ok" else level
            text += " " + _("Certifikát platí jen do %s.", format_datetime(self.env, device.cert_valid_to))
        return level, text

    def write(self, vals):
        eet_vals = {key: vals.pop(key) for key in list(vals) if key in EET_SETTINGS_FIELDS}
        res = super().write(vals) if vals else True
        if eet_vals:
            for config in self:
                config._eet_apply_settings(eet_vals)
        return res

    def _eet_apply_settings(self, eet_vals):
        """Create or update the till's EET device from the settings form.

        The form sends every field back, so only changed values are written. Order: data, then the
        certificate (it may fill the EIČ and switch the environment), switching on last.
        """
        self.ensure_one()
        device = self.eet_device_ids[:1]
        current = device.sudo()

        cert_vals = {}
        source = self.browse(eet_vals.get("eet_cert_source_config_id") or [])
        new_file = p12_bytes(eet_vals.get("eet_certificate_file"))
        if source and source != self:
            src = source.eet_device_ids[:1].sudo()
            if src.certificate_file:
                cert_vals = {
                    "certificate_file": src.certificate_file,
                    "certificate_filename": src.certificate_filename,
                    "certificate_password": src.certificate_password,
                }
        elif new_file and new_file != current.certificate_file:
            cert_vals = {dev: eet_vals.get(key) for key, dev in EET_CERT_FIELDS.items() if key in eet_vals}
            cert_vals["certificate_file"] = new_file
        elif "eet_certificate_password" in eet_vals and (
                (eet_vals["eet_certificate_password"] or False) != (current.certificate_password or False)):
            cert_vals = {"certificate_password": eet_vals["eet_certificate_password"]}

        data_vals = {}
        for key, dev in EET_DATA_FIELDS.items():
            value = eet_vals.get(key) or False
            if key not in eet_vals or (device and value == device[dev]):
                continue
            if key == "eet_eic" and not value:
                continue  # an empty EIČ is filled from the certificate
            data_vals[dev] = value
        enabled = bool(eet_vals.get("eet_enabled"))

        if not device:
            if not (enabled or cert_vals or data_vals.get("eic") or data_vals.get("id_jednotky")):
                return
            device = self.env["elite.eet.device"].create({
                "pos_config_id": self.id,
                "start_datetime": data_vals.pop("start_datetime", False) or default_start(),
            })
        if data_vals:
            device.write(data_vals)
        if cert_vals:
            device.sudo().write(cert_vals)
        if "eet_enabled" in eet_vals and enabled != device.active_eet:
            device.write({"active_eet": enabled})
