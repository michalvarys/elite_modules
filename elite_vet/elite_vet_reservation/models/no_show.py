"""Request 25. 10.: no-shows on the client and the pet.

Computed from reservations in the state Nedorazil (no_show) of the last 12 months - nothing is
stored twice. The second-room copy of a two-doctor procedure is not counted (it shares the state
of its main reservation). Shown on the partner / pet form (smart button), in the till's Kartotéka
and as a warning when booking (POS Objednat, backend wizard).
"""
import pytz
from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models

from .reservation import TZ

NO_SHOW_MONTHS = 12
NO_SHOW_ITEMS = 10


def short_date(day):
    return "%d. %d." % (day.day, day.month) if day else ""


class ReservationNoShow(models.Model):
    _inherit = "elite.vet.reservation"

    @api.model
    def _no_show_domain(self):
        since = fields.Datetime.now() - relativedelta(months=NO_SHOW_MONTHS)
        return [("kind", "=", "reservation"), ("state", "=", "no_show"), ("is_second_room", "=", False),
                ("start", ">=", since)]

    @api.model
    def no_show_summary(self, partner=None, pet=None):
        """{count, last_date, last_label, text, items: [{date, date_label, procedure, pet}]} of the
        client (or of the pet), newest first; count 0 = nothing to warn about."""
        domain = self._no_show_domain()
        if pet:
            domain.append(("pet_id", "=", pet.id))
        elif partner:
            domain.append(("partner_id", "=", partner.id))
        else:
            return {"count": 0, "last_date": None, "last_label": None, "text": None, "items": []}
        Reservation = self.sudo()
        found = Reservation.search(domain, order="start desc, id desc")
        lang = Reservation._clinic_lang()
        items = []
        for res in found[:NO_SHOW_ITEMS]:
            day = pytz.utc.localize(res.start).astimezone(TZ).date()
            items.append({"id": res.id, "date": day.isoformat(), "date_label": "%s %d" % (short_date(day), day.year),
                          "procedure": res.procedure_id.with_context(lang=lang).name or None,
                          "pet": res.pet_id.name or res.pet_name or None})
        count = len(found)
        last = fields.Date.from_string(items[0]["date"]) if items else None
        text = None
        if count:
            if pet:
                text = _("Zvíře %(count)d× nedorazilo, naposledy %(day)s", count=count, day=short_date(last))
            else:
                text = _("Klient %(count)d× nedorazil, naposledy %(day)s", count=count, day=short_date(last))
        return {"count": count, "last_date": last.isoformat() if last else None,
                "last_label": short_date(last) or None, "text": text, "items": items}

    @api.model
    def _no_show_counts(self, field, ids):
        """{partner_id or pet_id: count} for the smart buttons (one query)."""
        groups = self.sudo()._read_group(self._no_show_domain() + [(field, "in", list(ids))], [field], ["__count"])
        return {record.id: count for record, count in groups}

    @api.model
    def _no_show_action(self, domain, name):
        return {
            "type": "ir.actions.act_window", "name": name, "res_model": "elite.vet.reservation",
            "view_mode": "list,form",
            "views": [[self.env.ref("elite_vet_reservation.view_reservation_history_list").id, "list"], [False, "form"]],
            "domain": self._no_show_domain() + domain, "context": {"create": False},
        }


class PartnerNoShow(models.Model):
    _inherit = "res.partner"

    no_show_count = fields.Integer(string="Nedorazil", compute="_compute_no_show_count",
                                   help="Kolikrát klient nedorazil za posledních 12 měsíců (rezervace ve stavu Nedorazil).")

    def _compute_no_show_count(self):
        counts = self.env["elite.vet.reservation"]._no_show_counts("partner_id", self.ids) if self.ids else {}
        for partner in self:
            partner.no_show_count = counts.get(partner.id, 0)

    def action_view_no_shows(self):
        self.ensure_one()
        return self.env["elite.vet.reservation"]._no_show_action(
            [("partner_id", "=", self.id)], _("Nedorazil – %s") % self.name)


class PetNoShow(models.Model):
    _inherit = "elite.vet.pet"

    no_show_count = fields.Integer(string="Nedorazil", compute="_compute_no_show_count",
                                   help="Kolikrát zvíře nedorazilo za posledních 12 měsíců (rezervace ve stavu Nedorazil).")

    def _compute_no_show_count(self):
        counts = self.env["elite.vet.reservation"]._no_show_counts("pet_id", self.ids) if self.ids else {}
        for pet in self:
            pet.no_show_count = counts.get(pet.id, 0)

    def action_view_no_shows(self):
        self.ensure_one()
        return self.env["elite.vet.reservation"]._no_show_action(
            [("pet_id", "=", self.id)], _("Nedorazil – %s") % self.name)
