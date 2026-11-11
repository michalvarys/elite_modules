import base64
import logging
import uuid
from datetime import timedelta

from odoo import _, api, fields, models, tools
from odoo.exceptions import UserError, ValidationError

from ..eet import cert as eet_cert
from ..eet import fields as eet_fields
from ..eet import message, transport, wssec

_logger = logging.getLogger(__name__)

CERT_FIELDS = ("certificate_file", "certificate_password")
CERT_WARNING_DAYS = 21


class EliteEetDevice(models.Model):
    _name = "elite.eet.device"
    _description = "Nastavení EET pokladny"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "company_id, name"

    name = fields.Char("Název", required=True, tracking=True)
    company_id = fields.Many2one(
        "res.company", "Firma", required=True, default=lambda self: self.env.company, tracking=True
    )
    active_eet = fields.Boolean(
        "Zapnuto", tracking=True, help="Když je vypnuto, tržby této pokladny se nevytvářejí ani neodesílají."
    )
    start_datetime = fields.Datetime(
        "EET od", tracking=True, help="Tržby se evidují jen z plateb po tomto okamžiku."
    )
    environment = fields.Selection(
        [("playground", "Playground (test)"), ("production", "Produkce")],
        "Prostředí", required=True, default="playground", tracking=True,
    )
    eic = fields.Char("EIČ poplatníka", tracking=True, help="CZ a 8 až 10 číslic.")
    id_jednotky = fields.Char("Číslo evidenční jednotky", tracking=True, help="Číslo z portálu MOJE daně.")
    id_pokl = fields.Char("Označení pokladny", tracking=True, help="Nejvýš 20 znaků bez diakritiky.")
    response_timeout = fields.Float(
        "Mezní doba odezvy (s)", default=3.0, required=True, tracking=True,
        help="Jak dlouho se čeká na odpověď EET při zaplacení. Zákon vyžaduje nejméně 2 sekundy.",
    )
    responsible_user_id = fields.Many2one(
        "res.users", "Vedoucí pokladny", required=True, default=lambda self: self.env.user, tracking=True,
        help="Dostává upozornění na chyby, čekající tržby a konec platnosti certifikátu.",
    )
    certificate_file = fields.Binary("Certifikát (.p12)", attachment=True, groups="base.group_system")
    certificate_filename = fields.Char("Soubor certifikátu", groups="base.group_system")
    certificate_password = fields.Char("Heslo certifikátu", groups="base.group_system")
    cert_cn = fields.Char("EIČ v certifikátu", readonly=True)
    cert_issuer = fields.Char("Vydavatel", readonly=True)
    cert_serial = fields.Char("Sériové číslo", readonly=True)
    cert_valid_from = fields.Datetime("Platný od", readonly=True)
    cert_valid_to = fields.Datetime("Platný do", readonly=True)
    cert_environment = fields.Selection(
        [("playground", "Playground (test)"), ("production", "Produkce")], "Certifikát pro", readonly=True
    )
    cert_warning = fields.Char("Upozornění k certifikátu", compute="_compute_cert_warning")
    sale_ids = fields.One2many("elite.eet.sale", "device_id", "Tržby")
    attempt_ids = fields.One2many("elite.eet.attempt", "device_id", "Pokusy")

    @api.depends("cert_cn", "eic")
    def _compute_cert_warning(self):
        for device in self:
            if device.cert_cn and device.eic and device.cert_cn != device.eic:
                device.cert_warning = _(
                    "EIČ v certifikátu (%(cn)s) nesouhlasí s EIČ poplatníka (%(eic)s). EET tržbu přijme "
                    "s varováním; použijte certifikát poplatníka, za kterého pokladna eviduje.",
                    cn=device.cert_cn, eic=device.eic,
                )
            else:
                device.cert_warning = False

    @api.constrains("eic", "id_jednotky", "id_pokl", "response_timeout")
    def _check_values(self):
        for device in self:
            if device.eic and not eet_fields.EIC_RE.fullmatch(device.eic):
                raise ValidationError(_("EIČ musí mít tvar CZ a 8 až 10 číslic."))
            if device.id_jednotky and not eet_fields.ID_JEDNOTKY_RE.fullmatch(device.id_jednotky):
                raise ValidationError(_("Číslo evidenční jednotky je celé číslo bez úvodních nul (nejvýš 9 číslic)."))
            if device.id_pokl and not eet_fields.TEXT20_RE.fullmatch(device.id_pokl):
                raise ValidationError(_(
                    "Označení pokladny smí mít nejvýš 20 znaků: písmena bez diakritiky, číslice, "
                    "mezeru a znaky . , : ; / # - _"
                ))
            if device.response_timeout < 2:
                raise ValidationError(_("Mezní doba odezvy musí být nejméně 2 sekundy."))

    @api.constrains("environment", "cert_environment")
    def _check_environment(self):
        for device in self:
            if device.cert_environment and device.cert_environment != device.environment:
                raise ValidationError(_(
                    "Certifikát je pro prostředí %(cert)s, pokladna je nastavená na %(env)s. "
                    "Produkce potřebuje produkční certifikát, Playground testovací.",
                    cert=dict(self._fields["cert_environment"].selection)[device.cert_environment],
                    env=dict(self._fields["environment"].selection)[device.environment],
                ))

    @api.constrains("active_eet", "eic", "id_jednotky", "id_pokl", "start_datetime")
    def _check_active(self):
        for device in self.filtered("active_eet"):
            missing = [
                label for label, value in [
                    (_("certifikát"), device.sudo().certificate_file),
                    (_("EIČ"), device.eic),
                    (_("číslo evidenční jednotky"), device.id_jednotky),
                    (_("označení pokladny"), device.id_pokl),
                    (_("EET od"), device.start_datetime),
                ] if not value
            ]
            if missing:
                raise ValidationError(_("Pro zapnutí EET chybí: %s.", ", ".join(missing)))

    @api.model_create_multi
    def create(self, vals_list):
        devices = super().create(vals_list)
        for device, vals in zip(devices, vals_list):
            if any(f in vals for f in CERT_FIELDS):
                device._eet_read_certificate()
        return devices

    def write(self, vals):
        res = super().write(vals)
        if any(f in vals for f in CERT_FIELDS):
            for device in self:
                device._eet_read_certificate()
        return res

    def _eet_read_certificate(self):
        """Fill the cert_* fields from the uploaded .p12 (checks the password)."""
        self.ensure_one()
        device = self.sudo()
        if not device.certificate_file:
            device.write({
                "cert_cn": False, "cert_issuer": False, "cert_serial": False,
                "cert_valid_from": False, "cert_valid_to": False, "cert_environment": False,
            })
            return
        try:
            _key, _cert, info = eet_cert.load_p12(
                base64.b64decode(device.certificate_file), (device.certificate_password or "").encode()
            )
        except eet_cert.CertError as e:
            raise UserError(str(e)) from None
        device.write({
            "cert_cn": info.cn,
            "cert_issuer": info.issuer,
            "cert_serial": info.serial,
            "cert_valid_from": info.valid_from,
            "cert_valid_to": info.valid_to,
            "cert_environment": info.environment,
        })

    def _eet_key_and_cert(self):
        """Return (private_key, certificate). Never log the result."""
        self.ensure_one()
        device = self.sudo()
        if not device.certificate_file:
            raise UserError(_("Pokladna %s nemá nahraný certifikát EET.", device.name))
        try:
            key, certificate, _info = eet_cert.load_p12(
                base64.b64decode(device.certificate_file), (device.certificate_password or "").encode()
            )
        except eet_cert.CertError as e:
            raise UserError(str(e)) from None
        return key, certificate

    def _eet_url(self):
        self.ensure_one()
        if self.environment == "production":
            if tools.config["test_enable"]:
                raise UserError(_("Testy nesmějí odesílat do produkčního EET."))
            return transport.URLS["production"]
        override = self.env["ir.config_parameter"].sudo().get_param("elite_eet.playground_url_override")
        return override or transport.URLS["playground"]

    # ------------------------------------------------------------------
    # Transmission (one message per call; the batch-capable entry point is
    # elite.eet.sale._eet_send)
    # ------------------------------------------------------------------

    def _eet_transmit(self, sale_data, first, verification, sale=None):
        """Build, sign and send one message; store and return the attempt."""
        self.ensure_one()
        device = self.sudo()
        now = fields.Datetime.now()
        attempt_vals = {
            "device_id": device.id,
            "sale_id": sale.id if sale else False,
            "uuid": str(uuid.uuid4()),
            "sent_at": now,
            "first_send": first,
            "verification": verification,
        }
        try:
            key, certificate = device._eet_key_and_cert()
            trzba = message.build_trzba(sale_data, attempt_vals["uuid"], now, first, verification)
            envelope = wssec.sign_envelope(trzba, key, certificate)
            url = device._eet_url()
        except (message.MessageError, UserError) as e:
            attempt_vals.update(result="local_error", message=str(e))
            return self.env["elite.eet.attempt"].sudo().create(attempt_vals)
        result = transport.send(url, envelope, device.response_timeout)
        attempt_vals.update(
            request_xml=envelope.decode("ascii"),
            response_xml=result.response_xml.decode("utf-8", "replace") if result.response_xml else False,
            http_status=result.http_status or 0,
            transaction_id=result.transaction_id,
            result=result.kind,
            pok=result.pok,
            is_test=result.test,
            received_at=result.received_at,
            code=result.code or 0,
            message=result.message or (result.pok and "POK %s" % result.pok) or False,
            warnings="\n".join("%s: %s" % w for w in result.warnings) or False,
        )
        return self.env["elite.eet.attempt"].sudo().create(attempt_vals)

    def action_check_connection(self):
        """Send a verification-mode message (nothing is registered)."""
        self.ensure_one()
        now = fields.Datetime.now()
        data = message.SaleData(
            eic_popl=self.eic or "",
            id_jednotky=self.id_jednotky or "",
            id_pokl=self.id_pokl or "",
            porad_cis="OVERENI",
            dat_trzby=now,
            celk_trzba=0,
        )
        attempt = self._eet_transmit(data, first=True, verification=True)
        if attempt.result == "verified":
            ntype, text = "success", _("Spojení s EET funguje.")
        else:
            ntype = "danger"
            label = dict(attempt._fields["result"].selection)[attempt.result]
            text = _("EET spojení neověřilo: %(label)s, kód %(code)s – %(msg)s",
                     label=label, code=attempt.code, msg=attempt.message or "")
        if attempt.warnings:
            text += "\n" + _("Varování: %s", attempt.warnings)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {"title": _("Ověření spojení s EET"), "message": text, "type": ntype, "sticky": ntype != "success"},
        }

    # ------------------------------------------------------------------
    # Warnings
    # ------------------------------------------------------------------

    def _eet_notify(self, summary, note):
        """Schedule a warning activity for the till manager unless one is open."""
        for device in self.sudo():
            if any(a.summary == summary for a in device.activity_ids):
                continue
            device.activity_schedule(
                "mail.mail_activity_data_warning",
                summary=summary,
                note=note,
                user_id=device.responsible_user_id.id,
            )

    @api.model
    def _cron_watch(self):
        now = fields.Datetime.now()
        Sale = self.env["elite.eet.sale"].sudo()
        for device in self.sudo().search([("active_eet", "=", True)]):
            base = [("device_id", "=", device.id)]
            errors = Sale.search_count(base + [("state", "=", "error")])
            if errors:
                device._eet_notify(_("Tržba EET skončila chybou"),
                                   _("%s tržeb je ve stavu Chyba. Opravte příčinu a odešlete je znovu.", errors))
            late = Sale.search_count(base + [("state", "=", "pending"), ("dat_trzby", "<", now - timedelta(hours=24))])
            if late:
                device._eet_notify(_("Tržby EET čekají déle než 24 hodin"),
                                   _("%s tržeb ještě není v EET. Zákon dává na odeslání 48 hodin.", late))
            overdue = Sale.search_count(base + [("state", "=", "pending"), ("deadline", "<", now)])
            if overdue:
                device._eet_notify(_("Tržby EET po lhůtě 48 hodin"),
                                   _("%s tržeb nebylo do 48 hodin evidováno. Odešlete je co nejdřív.", overdue))
            if device.cert_valid_to and device.cert_valid_to <= now + timedelta(days=CERT_WARNING_DAYS):
                device._eet_notify(_("Certifikát EET brzy vyprší"),
                                   _("Certifikát pokladny %(name)s platí do %(date)s. Vydejte nový v portálu MOJE daně.",
                                     name=device.name, date=device.cert_valid_to))
