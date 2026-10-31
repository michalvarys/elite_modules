import logging
from datetime import timedelta

import pytz

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

PARAM = "elite_arena_mail_sequence."
DEFAULT_EMAIL_FROM = "Elite Arena <no-reply@elite-arena.cz>"
SETTINGS = {
    "send_hour_from": 9,     # e-mails go out only in the daytime (Prague time)
    "send_hour_to": 20,
    "mails_per_run": 40,     # the cron runs every hour
    "gap_days": 3,           # two automatic e-mails to one person at least this far apart
    "enroll_per_run": 300,
}
TRIGGERS = [
    ("lost", "Dlouho u nás nebyl"),
    ("first_visit", "Po první návštěvě"),
]


def get_settings(env):
    params = env["ir.config_parameter"].sudo()
    out = {}
    for key, default in SETTINGS.items():
        try:
            out[key] = int(params.get_param(PARAM + key) or default)
        except ValueError:
            out[key] = default
    return out


class MailSequence(models.Model):
    """An automatic series of e-mails. A contact joins it once it meets the conditions
    (e.g. has not been here for 45 days) and then gets the steps on the given days."""

    _name = "elite.arena.mail.sequence"
    _description = "Elite Arena – automatické e-maily"
    _order = "sequence, id"

    name = fields.Char(string="Název", required=True)
    sequence = fields.Integer(default=10)
    state = fields.Selection([("draft", "Vypnuto"), ("running", "Běží"), ("paused", "Pozastaveno")],
                             string="Stav", default="draft", required=True, readonly=True, copy=False)
    activated_at = fields.Datetime(string="Spuštěno", readonly=True, copy=False)
    trigger = fields.Selection(TRIGGERS, string="Kdy se hráč zařadí", required=True, default="lost")
    min_days = fields.Integer(string="Od (dní)", required=True, default=45)
    max_days = fields.Integer(string="Do (dní)", required=True, default=180,
                              help="Kdo je za touto hranicí, se už nezařadí (např. hráči, kteří nepřišli přes půl roku).")
    min_visits = fields.Integer(string="Aspoň návštěv", default=1)
    max_visits = fields.Integer(string="Nejvýš návštěv", default=0, help="0 = bez omezení.")
    include_existing = fields.Boolean(
        string="Zařadit i ty, kdo podmínku splňují už teď",
        help="Vypnuté: zařadí se jen ti, kdo podmínku splní až po spuštění (e-maily chodí postupně). "
             "Zapnuté: po spuštění se zařadí i všichni, kdo ji splňují už teď (jednorázově víc e-mailů).")
    stop_when_back = fields.Boolean(string="Ukončit, když hráč přijde", default=True,
                                    help="Další e-maily už nedostane, protože se vrátil.")
    reenroll_days = fields.Integer(string="Znovu zařadit nejdřív po (dnech)", default=0,
                                   help="0 = každý hráč dostane sérii jen jednou.")
    step_ids = fields.One2many("elite.arena.mail.sequence.step", "sequence_id", string="Kroky", copy=True)
    enrollment_ids = fields.One2many("elite.arena.mail.sequence.enrollment", "sequence_id", string="Zařazení")
    explanation = fields.Text(string="Jak to funguje", compute="_compute_explanation")
    enrolled_count = fields.Integer(string="Zařazeno", compute="_compute_stats")
    running_count = fields.Integer(string="Právě v sérii", compute="_compute_stats")
    returned_count = fields.Integer(string="Vrátili se", compute="_compute_stats")
    claimed_count = fields.Integer(string="Vyzvedli odměnu", compute="_compute_stats")
    mail_count = fields.Integer(string="Odesláno e-mailů", compute="_compute_stats")
    result = fields.Char(string="Výsledek", compute="_compute_stats")

    _sql_constraints = [
        ("days", "CHECK (min_days >= 0 AND max_days > min_days)", "„Do“ musí být víc dní než „Od“."),
    ]

    # ------------------------------------------------------------------ texts and numbers
    @api.depends("trigger", "min_days", "max_days", "min_visits", "max_visits", "stop_when_back", "step_ids",
                 "step_ids.delay_days", "step_ids.reward_id", "step_ids.skip_if_claimed", "include_existing")
    def _compute_explanation(self):
        for rec in self:
            if rec.trigger == "lost":
                who = "Hráč se zařadí, když u nás nebyl %d dní (a ne víc než %d dní)" % (rec.min_days, rec.max_days)
            else:
                who = "Hráč se zařadí %d dní po své první návštěvě (nejpozději po %d dnech)" % (rec.min_days,
                                                                                              rec.max_days)
            visits = []
            if rec.min_visits > 1:
                visits.append("byl tu aspoň %dx" % rec.min_visits)
            if rec.max_visits:
                visits.append("byl tu nejvýš %dx" % rec.max_visits)
            lines = [who + (" a " + " a ".join(visits) if visits else "") + "."]
            for step in rec.step_ids:
                text = "Den %d: %s" % (step.delay_days, step.name or step.mail_template_id.name or "e-mail")
                if step.reward_id:
                    text += " + odměna „%s“" % step.reward_id.name
                if step.skip_if_claimed:
                    text += " (jen když odměnu ještě nevyzvedl)"
                lines.append(text)
            if rec.stop_when_back:
                lines.append("Jakmile hráč přijde, další e-maily už nedostane.")
            if not rec.include_existing:
                lines.append("Zařazují se jen ti, kdo podmínku splní po spuštění, takže e-maily chodí postupně.")
            rec.explanation = "\n".join(lines)

    def _compute_stats(self):
        Enrollment = self.env["elite.arena.mail.sequence.enrollment"]
        Mail = self.env["elite.arena.mail.sequence.mail"]
        for rec in self:
            enrollments = Enrollment.search([("sequence_id", "=", rec.id)])
            rec.enrolled_count = len(enrollments)
            rec.running_count = len(enrollments.filtered(lambda e: e.state == "running"))
            rec.returned_count = len(enrollments.filtered("returned_at"))
            rec.claimed_count = len(enrollments.filtered("claimed"))
            rec.mail_count = Mail.search_count([("sequence_id", "=", rec.id), ("state", "=", "sent"),
                                                ("is_test", "=", False)])
            if rec.enrolled_count:
                rec.result = "Z %d zařazených se %d vrátilo (%d %%) a %d vyzvedlo odměnu (%d %%)." % (
                    rec.enrolled_count, rec.returned_count, round(100.0 * rec.returned_count / rec.enrolled_count),
                    rec.claimed_count, round(100.0 * rec.claimed_count / rec.enrolled_count))
            else:
                rec.result = "Zatím nikdo zařazený."

    # ------------------------------------------------------------------ buttons
    def action_start(self):
        for rec in self:
            if not rec.step_ids:
                raise UserError("Série „%s“ nemá žádný krok." % rec.name)
            for step in rec.step_ids:
                step._check_ready()
            rec.write({"state": "running", "activated_at": rec.activated_at or fields.Datetime.now()})
        return True

    def action_pause(self):
        self.write({"state": "paused"})

    def action_open_enrollments(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "name": "Zařazení · %s" % self.name,
                "res_model": "elite.arena.mail.sequence.enrollment", "view_mode": "list,form",
                "domain": [("sequence_id", "=", self.id)]}

    def action_open_mails(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "name": "E-maily · %s" % self.name,
                "res_model": "elite.arena.mail.sequence.mail", "view_mode": "list,form",
                "domain": [("sequence_id", "=", self.id)]}

    def action_preview_candidates(self):
        """Who would join now (without "only new ones"), to check the conditions."""
        self.ensure_one()
        partners = self._candidates(fields.Datetime.now(), only_new=False, limit=None)
        return {"type": "ir.actions.act_window", "name": "Splňují podmínky · %s" % self.name,
                "res_model": "res.partner", "view_mode": "list,form", "domain": [("id", "in", partners.ids)]}

    # ------------------------------------------------------------------ who joins
    def _base_partner_domain(self):
        return [("email", "!=", False), ("is_blacklisted", "=", False), ("ggleap_player_ids", "!=", False),
                ("ggleap_player_ids.deleted", "=", False)]

    def _candidates(self, now, only_new=None, limit=None):
        """Partners that meet the conditions now and may join (not in the series already)."""
        self.ensure_one()
        only_new = (not self.include_existing) if only_new is None else only_new
        oldest, newest = now - timedelta(days=self.max_days), now - timedelta(days=self.min_days)
        if only_new and self.activated_at:
            oldest = max(oldest, self.activated_at - timedelta(days=self.min_days))
        Partner = self.env["res.partner"]
        if self.trigger == "lost":
            domain = self._base_partner_domain() + [("ggleap_last_visit", ">=", oldest),
                                                    ("ggleap_last_visit", "<=", newest),
                                                    ("ggleap_visit_count", ">=", max(self.min_visits, 1))]
            if self.max_visits:
                domain.append(("ggleap_visit_count", "<=", self.max_visits))
            partners = Partner.search(domain, order="ggleap_last_visit desc")
        else:
            self.env.cr.execute("""
                select partner_id from elite_arena_ggleap_player
                 where partner_id is not null and not coalesce(deleted, false)
                 group by partner_id
                having min(first_visit) >= %s and min(first_visit) <= %s
                   and sum(visit_count) >= %s and (%s = 0 or sum(visit_count) <= %s)""",
                                (oldest, newest, max(self.min_visits, 1), self.max_visits, self.max_visits))
            ids = [r[0] for r in self.env.cr.fetchall()]
            partners = Partner.search(self._base_partner_domain() + [("id", "in", ids)])
        if not partners:
            return partners
        Enrollment = self.env["elite.arena.mail.sequence.enrollment"]
        blocked = [("sequence_id", "=", self.id), ("partner_id", "in", partners.ids)]
        if self.reenroll_days:
            blocked += ["|", ("state", "=", "running"),
                        ("enrolled_at", ">", now - timedelta(days=self.reenroll_days))]
        taken = set(Enrollment.search(blocked).mapped("partner_id").ids)
        partners = partners.filtered(lambda p: p.id not in taken)
        return partners[:limit] if limit else partners

    def _enroll(self, now, limit):
        Enrollment = self.env["elite.arena.mail.sequence.enrollment"]
        created = Enrollment
        for rec in self.filtered(lambda s: s.state == "running" and s.step_ids):
            first = rec.step_ids[0]
            vals = [{"sequence_id": rec.id, "partner_id": p.id, "enrolled_at": now, "next_step_id": first.id,
                     "next_at": now + timedelta(days=first.delay_days),
                     "last_visit_at_enroll": p.ggleap_last_visit}
                    for p in rec._candidates(now, limit=limit)]
            if vals:
                created |= Enrollment.create(vals)
        return created

    # ------------------------------------------------------------------ cron
    @api.model
    def _in_send_hours(self, now, settings):
        local = pytz.utc.localize(now).astimezone(pytz.timezone("Europe/Prague"))
        return settings["send_hour_from"] <= local.hour < settings["send_hour_to"]

    @api.model
    def _cron_run(self, now=None):
        now = now or fields.Datetime.now()
        settings = get_settings(self.env)
        sequences = self.search([("state", "=", "running")])
        sequences._enroll(now, settings["enroll_per_run"])
        Enrollment = self.env["elite.arena.mail.sequence.enrollment"]
        Enrollment._check_returned(now)
        if not self._in_send_hours(now, settings):
            return 0
        due = Enrollment.search([("state", "=", "running"), ("next_at", "<=", now),
                                 ("sequence_id.state", "=", "running")],
                                order="next_at, id", limit=settings["mails_per_run"])
        sent = 0
        for enrollment in due:
            try:
                with self.env.cr.savepoint():
                    sent += enrollment._process(now, settings)
            except Exception:
                _logger.exception("Automatický e-mail pro zařazení %s selhal", enrollment.id)
                enrollment.write({"note": "Chyba při odesílání, zkusí se znovu za hodinu.",
                                  "next_at": now + timedelta(hours=1)})
        return sent


class MailSequenceStep(models.Model):
    _name = "elite.arena.mail.sequence.step"
    _description = "Elite Arena – krok automatických e-mailů"
    _order = "sequence_id, delay_days, sequence, id"

    sequence_id = fields.Many2one("elite.arena.mail.sequence", string="Série", required=True, ondelete="cascade")
    sequence = fields.Integer(default=10)
    name = fields.Char(string="Krok", required=True)
    delay_days = fields.Integer(string="Den", required=True, default=0,
                                help="Kolik dní po zařazení do série se e-mail pošle (0 = hned).")
    step_type = fields.Selection([("mail", "E-mail")], string="Druh", required=True, default="mail")
    mail_template_id = fields.Many2one("mail.template", string="E-mail", required=True,
                                       domain=[("model", "=", "elite.arena.mail.sequence.mail")])
    reward_id = fields.Many2one("elite.arena.reward", string="Odměna",
                                help="E-mail bude obsahovat osobní odkaz na tuto odměnu. Prázdné = bez nové odměny "
                                     "(e-mail může připomenout odměnu z dřívějšího kroku).")
    skip_if_claimed = fields.Boolean(string="Jen když odměnu ještě nevyzvedl",
                                     help="Připomínka: kdo už odměnu vyzvedl, tenhle e-mail nedostane.")

    def _check_ready(self):
        self.ensure_one()
        if self.reward_id:
            self.reward_id._resolve_product()

    def action_send_test(self):
        """Sends this step to the current user (with a test reward link that adds nothing)."""
        self.ensure_one()
        user = self.env.user
        if not user.email:
            raise UserError("Váš uživatel nemá e-mail, kam zkušební e-mail poslat.")
        partner = self.sequence_id.enrollment_ids[:1].partner_id or user.partner_id
        Mail = self.env["elite.arena.mail.sequence.mail"]
        claim = self.reward_id.create_claim(partner, "Zkouška: %s" % self.name, test=True) if self.reward_id else False
        mail = Mail.create({"step_id": self.id, "sequence_id": self.sequence_id.id, "partner_id": partner.id,
                            "claim_id": claim.id if claim else False, "is_test": True})
        mail._send(email_to=user.email)
        return {"type": "ir.actions.client", "tag": "display_notification",
                "params": {"type": "success", "message": "Zkušební e-mail odešel na %s (text jako pro %s)." % (
                    user.email, partner.name)}}
