"""Where a web reservation came from (request 26. 11.): UTM parameters and ad click ids.

Odoo's `utm` module already keeps utm_source / utm_medium / utm_campaign of the landing URL in
cookies (odoo_utm_*). The rest - utm_content, utm_term and the click ids of Google Ads (gclid) and
Meta (fbclid) - is kept the same way here. Like Odoo's, the cookies are "optional": the visitor
gets them only after allowing optional cookies in the cookie bar, so a visitor who allowed only
the essential ones books without a source.

The public booking API (controllers/booking.py, form and chat) copies them onto the reservation.
"""
import uuid

from odoo import api, fields, models
from odoo.http import Response, request

# (URL parameter, reservation field, cookie)
EXTRA_TRACKING = [
    ("utm_content", "utm_content", "ev_utm_content"),
    ("utm_term", "utm_term", "ev_utm_term"),
    ("gclid", "gclid", "ev_gclid"),
    ("fbclid", "fbclid", "ev_fbclid"),
]
COOKIE_AGE = 90 * 24 * 3600   # an ad click is usually attributed up to 90 days back
MAX_LEN = 255


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    @classmethod
    def _set_utm(cls, response):
        super()._set_utm(response)
        response = Response.load(response)
        domain = cls.get_utm_domain_cookies()
        for param, _field, cookie in EXTRA_TRACKING:
            value = (request.params.get(param) or "")[:MAX_LEN]
            if value and isinstance(value, str) and request.cookies.get(cookie) != value:
                response.set_cookie(cookie, value, max_age=COOKIE_AGE, domain=domain, cookie_type="optional")


class VetReservation(models.Model):
    _inherit = "elite.vet.reservation"

    # Not utm.mixin: its default_get would read the cookies of whoever creates the record,
    # so a receptionist who once opened a link with ?utm_source= would tag her own reservations.
    campaign_id = fields.Many2one("utm.campaign", string="Kampaň", index="btree_not_null", readonly=True)
    source_id = fields.Many2one("utm.source", string="Zdroj (UTM)", index="btree_not_null", readonly=True)
    medium_id = fields.Many2one("utm.medium", string="Médium", index="btree_not_null", readonly=True)
    utm_content = fields.Char(string="Obsah (utm_content)", readonly=True)
    utm_term = fields.Char(string="Klíčové slovo (utm_term)", readonly=True)
    gclid = fields.Char(string="Google Ads klik (gclid)", readonly=True)
    fbclid = fields.Char(string="Meta klik (fbclid)", readonly=True)
    # Id of the "Lead" event sent by the browser to GA4 / Meta; the same id lets a later
    # server-side send (Meta Conversions API) be deduplicated. Not the cancel token - that is secret.
    lead_event_id = fields.Char(readonly=True, copy=False)
    has_tracking = fields.Boolean(compute="_compute_has_tracking")

    @api.depends("campaign_id", "source_id", "medium_id", "utm_content", "utm_term", "gclid", "fbclid")
    def _compute_has_tracking(self):
        for rec in self:
            rec.has_tracking = any(rec[f] for f in ("campaign_id", "source_id", "medium_id", "utm_content",
                                                     "utm_term", "gclid", "fbclid"))

    @api.model
    def _web_tracking_values(self):
        """Tracking values of the current website request (its cookies), for a new web reservation."""
        if not request:
            return {}
        vals = {"lead_event_id": uuid.uuid4().hex}
        Mixin = self.env["utm.mixin"].sudo()
        for _param, field, cookie in Mixin.tracking_fields():
            name = (request.cookies.get(cookie) or "").strip()[:MAX_LEN]
            if name and field in self._fields:
                vals[field] = Mixin._find_or_create_record(self._fields[field].comodel_name, name).id
        for _param, field, cookie in EXTRA_TRACKING:
            value = (request.cookies.get(cookie) or "").strip()[:MAX_LEN]
            if value:
                vals[field] = value
        return vals
