from datetime import timedelta

import pytz

from odoo import api, fields, models

TZ = pytz.timezone("Europe/Prague")


class VetReservationMailing(models.Model):
    """E-maily a vse kolem nich drzime stranou od stavu a prekryvu, at je reservation.py citelny."""

    _inherit = "elite.vet.reservation"

    start_display = fields.Char(compute="_compute_start_display")
    cancel_url = fields.Char(compute="_compute_cancel_url")
    reminder_sent = fields.Boolean(default=False, copy=False)

    @api.depends("start")
    def _compute_start_display(self):
        for rec in self:
            if not rec.start:
                rec.start_display = ""
                continue
            local = pytz.utc.localize(rec.start).astimezone(TZ)
            rec.start_display = "%d. %d. %d %d:%02d" % (local.day, local.month, local.year, local.hour, local.minute)

    @api.depends("cancel_token")
    def _compute_cancel_url(self):
        for rec in self:
            rec.cancel_url = "%s/rezervace/zruseni/%s" % (rec.get_base_url(), rec.cancel_token)

    def _poslat(self, xmlid, email_to=None):
        template = self.env.ref("elite_vet_reservation." + xmlid, raise_if_not_found=False)
        if not template:
            return
        for rec in self:
            to = email_to or rec.contact_email
            if not to:
                continue
            template.with_context(lang=rec.lang or "cs_CZ").sudo().send_mail(
                rec.id, force_send=False, email_values={"email_to": to})

    def muze_zrusit_klient(self):
        self.ensure_one()
        hours = self.env["elite.vet.setting"].nastaveni().booking_cancel_hours_before
        if hours <= 0 or self.state not in ("web_new", "confirmed"):
            return False
        return self.start - timedelta(hours=hours) > fields.Datetime.now()

    # ---------- napojeni na akce ----------
    def _po_prijeti_z_webu(self):
        self._poslat("mail_web_received")
        notify = self.env["elite.vet.setting"].nastaveni().booking_notify_email
        if notify:
            self._poslat("mail_new_for_clinic", email_to=notify)
        return True

    def action_confirm(self):
        res = super().action_confirm()
        self.filtered(lambda r: r.kind == "reservation" and not self.env.context.get("ev_bez_mailu"))._poslat("mail_confirmed")
        return res

    def action_cancel(self, reason="clinic"):
        res = super().action_cancel(reason)
        self.filtered(lambda r: r.kind == "reservation")._poslat("mail_cancelled")
        if reason == "client":
            notify = self.env["elite.vet.setting"].nastaveni().booking_notify_email
            if notify:
                self._poslat("mail_cancelled", email_to=notify)
        return res

    def action_send_confirmation(self):
        self.filtered(lambda r: r.kind == "reservation" and r.state == "confirmed" and r.contact_email)._poslat("mail_confirmed")
        return True

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if not self.env.context.get("ev_bez_mailu"):
            records.filtered(lambda r: r.kind == "reservation" and r.source == "internal"
                             and r.state == "confirmed" and r.contact_email).action_send_confirmation()
        return records

    def write(self, vals):
        if self.env.context.get("ev_skip_mail") or not ({"start", "room_id"} & set(vals)):
            return super().write(vals)
        before = {r.id: (r.start, r.room_id.id) for r in self if r.kind == "reservation" and r.state == "confirmed"}
        res = super().write(vals)
        moved = self.filtered(lambda r: r.id in before and r.state == "confirmed"
                              and before[r.id] != (r.start, r.room_id.id))
        if moved:
            moved.with_context(ev_skip_mail=True).write({"reminder_sent": False})
            moved._poslat("mail_rescheduled")
        return res

    @api.model
    def _cron_pripominky(self):
        s = self.env["elite.vet.setting"].nastaveni()
        if not s.booking_reminder_enabled:
            return
        now = fields.Datetime.now()
        due = self.search([("kind", "=", "reservation"), ("state", "=", "confirmed"), ("reminder_sent", "=", False),
                           ("start", ">", now), ("start", "<=", now + timedelta(hours=s.booking_reminder_hours_before))])
        due._poslat("mail_reminder")
        due.write({"reminder_sent": True})
