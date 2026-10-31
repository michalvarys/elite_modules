import secrets
from datetime import timedelta

import pytz

from odoo import api, fields, models

from .sequence import DEFAULT_EMAIL_FROM, PARAM

RETURN_WINDOW = timedelta(days=120)   # a visit this long after joining still counts as "came back"


class MailSequenceEnrollment(models.Model):
    """One contact in one series: which step comes next and when."""

    _name = "elite.arena.mail.sequence.enrollment"
    _description = "Elite Arena – zařazení do automatických e-mailů"
    _order = "enrolled_at desc, id desc"
    _rec_name = "partner_id"

    sequence_id = fields.Many2one("elite.arena.mail.sequence", string="Série", required=True, index=True,
                                  ondelete="cascade", readonly=True)
    partner_id = fields.Many2one("res.partner", string="Kontakt", required=True, index=True, ondelete="cascade",
                                 readonly=True)
    state = fields.Selection([
        ("running", "Probíhá"),
        ("done", "Dokončeno"),
        ("returned", "Vrátil se"),
        ("stopped", "Zastaveno"),
        ("unsubscribed", "Odhlásil se"),
    ], string="Stav", default="running", required=True, index=True, readonly=True)
    enrolled_at = fields.Datetime(string="Zařazen", required=True, readonly=True)
    last_visit_at_enroll = fields.Datetime(string="Poslední návštěva při zařazení", readonly=True)
    next_step_id = fields.Many2one("elite.arena.mail.sequence.step", string="Další krok", readonly=True,
                                   ondelete="set null")
    next_at = fields.Datetime(string="Další e-mail", readonly=True, index=True)
    returned_at = fields.Datetime(string="Přišel znovu", readonly=True,
                                  help="První návštěva po zařazení (do 120 dní).")
    mail_ids = fields.One2many("elite.arena.mail.sequence.mail", "enrollment_id", string="E-maily")
    claimed = fields.Boolean(string="Vyzvedl odměnu", compute="_compute_claimed")
    note = fields.Char(string="Poznámka", readonly=True)

    def _compute_claimed(self):
        for rec in self:
            rec.claimed = any(m.claim_id.state == "claimed" for m in rec.mail_ids)

    def action_stop(self):
        self.filtered(lambda e: e.state == "running").write({"state": "stopped", "next_at": False,
                                                              "note": "Zastaveno ručně."})

    @api.model
    def _check_returned(self, now):
        """Marks who came after joining; the series stops for them where it should."""
        candidates = self.search([("returned_at", "=", False), ("enrolled_at", ">=", now - RETURN_WINDOW),
                                  ("state", "!=", "unsubscribed")])
        for rec in candidates:
            last = rec.partner_id.ggleap_last_visit
            if last and last > rec.enrolled_at:
                vals = {"returned_at": last}
                if rec.state == "running" and rec.sequence_id.stop_when_back:
                    vals.update(state="returned", next_at=False)
                rec.write(vals)

    def _open_claim(self):
        claims = self.mail_ids.mapped("claim_id").filtered(lambda c: not c.is_test)
        return claims.sorted("id", reverse=True)[:1]

    def _process(self, now, settings):
        """Sends the next step if it is due. Returns 1 when an e-mail went out."""
        self.ensure_one()
        partner = self.partner_id
        if not partner.email or partner.is_blacklisted:
            self.write({"state": "unsubscribed" if partner.is_blacklisted else "stopped", "next_at": False,
                        "note": "Kontakt je odhlášený z e-mailů." if partner.is_blacklisted else "Kontakt nemá e-mail."})
            return 0
        step = self.next_step_id
        if not step:
            self.write({"state": "done", "next_at": False})
            return 0
        gap = timedelta(days=settings["gap_days"])
        last = self.env["elite.arena.mail.sequence.mail"].search(
            [("partner_id", "=", partner.id), ("state", "=", "sent"), ("is_test", "=", False),
             ("enrollment_id", "!=", self.id), ("sent_at", ">", now - gap)], order="sent_at desc", limit=1)
        if last:   # another series wrote recently: wait
            self.write({"next_at": last.sent_at + gap})
            return 0
        sent = 0
        if step.skip_if_claimed and self.claimed:
            self.env["elite.arena.mail.sequence.mail"].create({
                "enrollment_id": self.id, "step_id": step.id, "state": "skipped", "sent_at": now})
        else:
            mail = self.env["elite.arena.mail.sequence.mail"].create(self._mail_vals(step, now))
            mail._send()
            sent = 1
        self._advance(step, now)
        return sent

    def _mail_vals(self, step, now):
        claim = False
        if step.reward_id:
            claim = step.reward_id.create_claim(self.partner_id, "%s · %s" % (self.sequence_id.name, step.name))
        else:
            claim = self._open_claim().filtered(lambda c: c.state == "offered")
        return {"enrollment_id": self.id, "step_id": step.id, "claim_id": claim.id if claim else False}

    def _advance(self, step, now):
        steps = self.sequence_id.step_ids
        later = steps.filtered(lambda s: (s.delay_days, s.sequence, s.id) > (step.delay_days, step.sequence, step.id))
        nxt = later[:1]
        if nxt:
            self.write({"next_step_id": nxt.id, "next_at": max(now, self.enrolled_at + timedelta(days=nxt.delay_days))})
        else:
            self.write({"next_step_id": False, "next_at": False, "state": "done"})


class MailSequenceMail(models.Model):
    """One sent e-mail. Its fields are what the e-mail templates use."""

    _name = "elite.arena.mail.sequence.mail"
    _description = "Elite Arena – odeslaný automatický e-mail"
    _order = "sent_at desc, id desc"

    enrollment_id = fields.Many2one("elite.arena.mail.sequence.enrollment", string="Zařazení", index=True,
                                    ondelete="cascade", readonly=True)
    step_id = fields.Many2one("elite.arena.mail.sequence.step", string="Krok", readonly=True, ondelete="set null")
    sequence_id = fields.Many2one("elite.arena.mail.sequence", string="Série", readonly=True, index=True,
                                  compute="_compute_sequence", store=True)
    partner_id = fields.Many2one("res.partner", string="Kontakt", index=True, readonly=True,
                                 compute="_compute_partner", store=True)
    claim_id = fields.Many2one("elite.arena.reward.claim", string="Odměna", readonly=True, ondelete="set null")
    claim_state = fields.Selection(related="claim_id.state", string="Odměna – stav")
    mail_id = fields.Many2one("mail.mail", string="Zpráva", readonly=True, ondelete="set null")
    state = fields.Selection([("draft", "Připraveno"), ("sent", "Odesláno"), ("skipped", "Vynecháno"),
                              ("failed", "Chyba")], string="Stav", default="draft", readonly=True)
    sent_at = fields.Datetime(string="Odesláno", readonly=True)
    is_test = fields.Boolean(string="Zkušební", readonly=True)
    token = fields.Char(readonly=True, copy=False, index=True, default=lambda self: secrets.token_urlsafe(18))

    # values for the templates
    first_name = fields.Char(compute="_compute_texts")
    claim_url = fields.Char(compute="_compute_texts")
    reward_name = fields.Char(compute="_compute_texts")
    claim_until = fields.Char(compute="_compute_texts", help="Do kdy jde odměnu vyzvednout, např. 30. 11. 2026.")
    pass_days = fields.Integer(compute="_compute_texts")
    unsubscribe_url = fields.Char(compute="_compute_texts")

    @api.depends("enrollment_id.sequence_id", "step_id.sequence_id")
    def _compute_sequence(self):
        for rec in self:
            rec.sequence_id = rec.enrollment_id.sequence_id or rec.step_id.sequence_id or rec.sequence_id

    @api.depends("enrollment_id.partner_id")
    def _compute_partner(self):
        for rec in self:
            rec.partner_id = rec.enrollment_id.partner_id or rec.partner_id

    def _compute_texts(self):
        base = self.env["ir.config_parameter"].sudo().get_param("web.base.url", "")
        tz = pytz.timezone("Europe/Prague")
        for rec in self:
            name = (rec.partner_id.name or "").strip()
            rec.first_name = name.split(" ")[0] if name else "hráči"
            claim = rec.claim_id
            rec.claim_url = claim.url if claim else False
            reward = claim.reward_id.name or ""
            rec.reward_name = reward
            rec.claim_until = (pytz.utc.localize(claim.expires_at).astimezone(tz).strftime("%-d. %-m. %Y")
                               if claim and claim.expires_at else "")
            rec.pass_days = claim.reward_id.pass_valid_days if claim else 0
            rec.unsubscribe_url = "%s/arena/odhlasit/%s" % (base, rec.token)

    def _send(self, email_to=None):
        """Renders the step's template and queues the e-mail (the mail queue cron sends it)."""
        for rec in self:
            template = rec.step_id.mail_template_id
            values = {"headers": repr({"List-Unsubscribe": "<%s>" % rec.unsubscribe_url})}
            if not template.email_from:   # sender of all automatic e-mails unless the template says otherwise
                values["email_from"] = self.env["ir.config_parameter"].sudo().get_param(
                    PARAM + "email_from") or DEFAULT_EMAIL_FROM
            if email_to:
                values.update(email_to=email_to, recipient_ids=[])
            mail_id = template.send_mail(rec.id, force_send=False, email_values=values)
            rec.write({"mail_id": mail_id, "state": "sent", "sent_at": fields.Datetime.now()})
