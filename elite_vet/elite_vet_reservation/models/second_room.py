"""Zákrok, který potřebuje dvě lékařky: rezervace se zduplikuje do druhé ordinace.

Obě rezervace jsou propojené (linked_reservation_id na obou stranách):
- přesun času jedné posune i druhou (ordinace zůstávají),
- zrušení / proběhla / nedorazil hlavní rezervace platí i pro druhou,
- zrušení jen druhé ordinace hlavní rezervaci nechá (druhá lékařka už není potřeba),
- klientovi chodí e-maily jen z hlavní rezervace.
"""
from odoo import _, api, models
from odoo.exceptions import UserError

from .reservation import INACTIVE_STATES

FINAL_STATES = ("cancelled", "done", "no_show")


class VetReservationSecondRoom(models.Model):
    _inherit = "elite.vet.reservation"

    def _linked_label(self):
        """„Ordinace 2 · MVDr. X“ pro tabuli, nebo False."""
        self.ensure_one()
        druha = self.linked_reservation_id
        if not druha or druha.state in INACTIVE_STATES:
            return False
        return " · ".join(p for p in (druha.room_id.name, druha.doctor_id.name) if p)

    def add_second_room(self, room, doctor=None):
        self.ensure_one()
        if self.kind != "reservation" or self.state != "confirmed":
            raise UserError(_("Do druhé ordinace jde přidat jen potvrzená rezervace."))
        if self.is_second_room:
            raise UserError(_("Tato rezervace už je druhou ordinací jiné rezervace."))
        if self.linked_reservation_id and self.linked_reservation_id.state not in INACTIVE_STATES:
            raise UserError(_("Rezervace už druhou ordinaci má: %s.") % self._linked_label())
        if not room or room == self.room_id:
            raise UserError(_("Vyberte jinou ordinaci, než ve které rezervace je."))
        druha = self.with_context(ev_no_mail=True, ev_linked_sync=True).copy({
            "room_id": room.id, "doctor_id": doctor.id if doctor else False,
            "start": self.start, "stop": self.stop, "state": "confirmed", "source": "internal",
            "is_second_room": True, "linked_reservation_id": self.id,
            "deposit_state": "none", "transaction_id": False,
        })
        self.with_context(ev_linked_sync=True).write({"linked_reservation_id": druha.id})
        # Bez pomocného kontextu: další přesuny a zrušení kopie se musí propojovat.
        return druha.with_env(self.env)

    def _send_template(self, xmlid, email_to=None):
        # Klient dostane e-mail jednou – z hlavní rezervace. E-maily pro kliniku
        # (email_to) se taky posílají jen jednou.
        return super(VetReservationSecondRoom, self.filtered(lambda r: not r.is_second_room))._send_template(
            xmlid, email_to=email_to)

    def write(self, vals):
        res = super().write(vals)
        if self.env.context.get("ev_linked_sync") or not ({"start", "stop", "state"} & set(vals)):
            return res
        for rec in self.filtered("linked_reservation_id"):
            druha = rec.linked_reservation_id
            upd = {}
            if {"start", "stop"} & set(vals) and rec.state not in INACTIVE_STATES \
                    and druha.state not in INACTIVE_STATES and (druha.start, druha.stop) != (rec.start, rec.stop):
                upd.update(start=rec.start, stop=rec.stop)
            if vals.get("state") in FINAL_STATES:
                if not rec.is_second_room and druha.state not in FINAL_STATES:
                    upd["state"] = vals["state"]
                    if vals.get("cancel_reason"):
                        upd["cancel_reason"] = vals["cancel_reason"]
                elif rec.is_second_room and vals["state"] == "cancelled" and druha.linked_reservation_id == rec:
                    # Zrušená druhá ordinace: hlavní rezervace jde znovu rozšířit.
                    upd["linked_reservation_id"] = False
            if upd:
                druha.with_context(ev_linked_sync=True).write(upd)
        return res

    def action_add_second_room(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window", "res_model": "elite.vet.reservation.second.room.wizard",
            "name": _("Přidat druhou ordinaci"), "view_mode": "form", "views": [[False, "form"]],
            "target": "new", "context": {"default_reservation_id": self.id},
        }
