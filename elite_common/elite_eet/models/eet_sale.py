import logging
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.modules import module as odoo_module

from ..eet import message

_logger = logging.getLogger(__name__)

NEAR_DEADLINE = timedelta(hours=6)
FROZEN_FIELDS = ("device_id", "porad_cis", "dat_trzby", "celk_trzba", "urceno_cerp_zuct", "cerp_zuct")


class EliteEetSale(models.Model):
    _name = "elite.eet.sale"
    _description = "Tržba EET"
    _order = "dat_trzby desc, id desc"
    _rec_name = "porad_cis"

    device_id = fields.Many2one("elite.eet.device", "Pokladna EET", required=True, ondelete="restrict", index=True)
    company_id = fields.Many2one(related="device_id.company_id", store=True, string="Firma")
    currency_id = fields.Many2one(related="company_id.currency_id", string="Měna")
    source_ref = fields.Char("Doklad")
    porad_cis = fields.Char("Pořadové číslo", required=True)
    dat_trzby = fields.Datetime("Čas tržby", required=True)
    celk_trzba = fields.Monetary("Celková tržba", required=True)
    urceno_cerp_zuct = fields.Monetary("Určeno k čerpání")
    cerp_zuct = fields.Monetary("Čerpání")
    state = fields.Selection(
        [("pending", "Čeká"), ("registered", "Evidováno"), ("error", "Chyba")],
        "Stav", default="pending", required=True, index=True,
    )
    pok = fields.Char("POK", readonly=True)
    received_at = fields.Datetime("Přijato", readonly=True)
    is_test = fields.Boolean("Testovací POK", readonly=True)
    warning_text = fields.Text("Varování", readonly=True)
    last_error = fields.Text("Poslední chyba", readonly=True)
    deadline = fields.Datetime("Lhůta 48 h", compute="_compute_deadline", store=True)
    is_near_deadline = fields.Boolean(
        "Blíží se 48 h", compute="_compute_deadline_flags", search="_search_near_deadline"
    )
    is_overdue = fields.Boolean("Po lhůtě", compute="_compute_deadline_flags", search="_search_overdue")
    attempt_ids = fields.One2many("elite.eet.attempt", "sale_id", "Pokusy")
    attempt_count = fields.Integer("Počet pokusů", compute="_compute_attempt_count")

    _sql_constraints = [
        ("porad_cis_unique", "unique(device_id, porad_cis)", "Pořadové číslo musí být v pokladně jedinečné."),
    ]

    @api.depends("dat_trzby")
    def _compute_deadline(self):
        for sale in self:
            sale.deadline = sale.dat_trzby and sale.dat_trzby + timedelta(hours=48)

    @api.depends("deadline", "state")
    def _compute_deadline_flags(self):
        now = fields.Datetime.now()
        for sale in self:
            open_sale = sale.state != "registered" and sale.deadline
            sale.is_overdue = bool(open_sale and sale.deadline < now)
            sale.is_near_deadline = bool(open_sale and now <= sale.deadline < now + NEAR_DEADLINE)

    def _search_near_deadline(self, operator, value):
        now = fields.Datetime.now()
        domain = [("state", "!=", "registered"), ("deadline", ">=", now), ("deadline", "<", now + NEAR_DEADLINE)]
        return domain if (operator == "=") == bool(value) else ["!", "&", "&"] + domain

    def _search_overdue(self, operator, value):
        domain = [("state", "!=", "registered"), ("deadline", "<", fields.Datetime.now())]
        return domain if (operator == "=") == bool(value) else ["!", "&"] + domain

    def _compute_attempt_count(self):
        for sale in self:
            sale.attempt_count = len(sale.attempt_ids)

    def write(self, vals):
        if any(f in vals for f in FROZEN_FIELDS) and self.filtered("attempt_ids"):
            raise UserError(_("Údaje tržby, která už byla odeslána do EET, se nesmí měnit."))
        return super().write(vals)

    # ------------------------------------------------------------------
    # Sending. _eet_send is the single entry point that turns sales into
    # messages; when EET supports batches, only this method and
    # eet/transport.py change.
    # ------------------------------------------------------------------

    def _eet_sale_data(self):
        self.ensure_one()
        device = self.device_id
        return message.SaleData(
            eic_popl=device.eic or "",
            id_jednotky=device.id_jednotky or "",
            id_pokl=device.id_pokl or "",
            porad_cis=self.porad_cis,
            dat_trzby=self.dat_trzby,
            celk_trzba=self.celk_trzba,
            urceno_cerp_zuct=self.urceno_cerp_zuct or None,
            cerp_zuct=self.cerp_zuct or None,
        )

    def _eet_send(self, first_send=None):
        """Send the sales (skipping registered and locked ones). Return {sale_id: result}."""
        sales = self.sudo()
        if not sales:
            return {}
        self.env.cr.execute(
            "SELECT id FROM elite_eet_sale WHERE id IN %s AND state != 'registered' FOR UPDATE SKIP LOCKED",
            [tuple(sales.ids)],
        )
        locked = {row[0] for row in self.env.cr.fetchall()}
        results = {}
        for sale in sales.filtered(lambda s: s.id in locked):
            if not sale.device_id.active_eet:
                continue
            first = (not sale.attempt_ids) if first_send is None else first_send
            attempt = sale.device_id._eet_transmit(sale._eet_sale_data(), first, False, sale=sale)
            sale._eet_apply(attempt)
            results[sale.id] = attempt.result
        return results

    def _eet_apply(self, attempt):
        self.ensure_one()
        if attempt.result == "pok":
            self.write({
                "state": "registered",
                "pok": attempt.pok,
                "received_at": attempt.received_at or attempt.sent_at,
                "is_test": attempt.is_test,
                "warning_text": attempt.warnings or False,
                "last_error": False,
            })
        elif attempt.result in ("critical", "local_error"):
            error = "%s%s" % (f"{attempt.code}: " if attempt.code else "", attempt.message or "")
            self.write({"state": "error", "last_error": error})
            self.device_id._eet_notify(
                _("Tržba EET skončila chybou"),
                _("Tržbu %(ref)s EET odmítlo: %(err)s", ref=self.source_ref or self.porad_cis, err=error),
            )
        else:
            self.write({"last_error": attempt.message or False})

    def _eet_send_after_commit(self, first_send=None):
        """Send right after the current transaction commits (never inside it)."""
        ids = self.ids
        if not ids:
            return
        registry, uid, context = self.env.registry, self.env.uid, dict(self.env.context)

        @self.env.cr.postcommit.add
        def _send():
            try:
                with registry.cursor() as cr:
                    env = api.Environment(cr, uid, context)
                    env["elite.eet.sale"].browse(ids)._eet_send(first_send)
            except Exception:
                _logger.exception("EET: sending sales %s after commit failed; the queue will retry", ids)

    @api.model
    def _cron_send_pending(self, limit=50):
        sales = self.sudo().search(
            [("state", "=", "pending"), ("device_id.active_eet", "=", True)], order="dat_trzby, id", limit=limit
        )
        unreachable = set()
        for sale in sales:
            if sale.device_id.id in unreachable:
                continue
            if sale._eet_send().get(sale.id) == "no_response":
                unreachable.add(sale.device_id.id)
            if not odoo_module.current_test:
                self.env.cr.commit()

    def action_send_to_eet(self):
        to_send = self.filtered(lambda s: s.state in ("pending", "error"))
        skipped = len(self) - len(to_send)
        results = to_send._eet_send(first_send=False)
        registered = sum(1 for r in results.values() if r == "pok")
        errors = sum(1 for r in results.values() if r in ("critical", "local_error"))
        text = _(
            "Odesláno %(sent)s, evidováno %(ok)s, chyba %(err)s, přeskočeno %(skip)s.",
            sent=len(results), ok=registered, err=errors, skip=skipped + len(to_send) - len(results),
        )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Odeslání do EET"),
                "message": text,
                "type": "success" if registered == len(results) else "warning",
                "sticky": False,
                "next": {"type": "ir.actions.act_window_close"},
            },
        }
