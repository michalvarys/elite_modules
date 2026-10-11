"""Zákrok, který potřebuje dvě lékařky: rezervace se zduplikuje do druhé ordinace.

Obě rezervace jsou propojené (spojena_id na obou stranách):
- přesun času jedné posune i druhou (ordinace zůstávají),
- zrušení / proběhla / nedorazil hlavní rezervace platí i pro druhou,
- zrušení jen druhé ordinace hlavní rezervaci nechá (druhá lékařka už není potřeba),
- klientovi chodí e-maily jen z hlavní rezervace.
"""
from odoo import _, api, models
from odoo.exceptions import UserError

from .reservation import INACTIVE_STATES

KONCOVE_STAVY = ("cancelled", "done", "no_show")


class VetReservationDruhaOrdinace(models.Model):
    _inherit = "elite.vet.reservation"

    def _popisek_spojene(self):
        """„Ordinace 2 · MVDr. X“ pro tabuli, nebo False."""
        self.ensure_one()
        druha = self.spojena_id
        if not druha or druha.state in INACTIVE_STATES:
            return False
        return " · ".join(p for p in (druha.room_id.name, druha.doctor_id.name) if p)

    def pridat_druhou_ordinaci(self, room, doctor=None):
        self.ensure_one()
        if self.kind != "reservation" or self.state != "confirmed":
            raise UserError(_("Do druhé ordinace jde přidat jen potvrzená rezervace."))
        if self.druha_ordinace:
            raise UserError(_("Tato rezervace už je druhou ordinací jiné rezervace."))
        if self.spojena_id and self.spojena_id.state not in INACTIVE_STATES:
            raise UserError(_("Rezervace už druhou ordinaci má: %s.") % self._popisek_spojene())
        if not room or room == self.room_id:
            raise UserError(_("Vyberte jinou ordinaci, než ve které rezervace je."))
        druha = self.with_context(ev_bez_mailu=True, ev_spojena_sync=True).copy({
            "room_id": room.id, "doctor_id": doctor.id if doctor else False,
            "start": self.start, "stop": self.stop, "state": "confirmed", "source": "internal",
            "druha_ordinace": True, "spojena_id": self.id,
            "deposit_state": "none", "transaction_id": False,
        })
        self.with_context(ev_spojena_sync=True).write({"spojena_id": druha.id})
        # Bez pomocného kontextu: další přesuny a zrušení kopie se musí propojovat.
        return druha.with_env(self.env)

    def _poslat(self, xmlid, email_to=None):
        # Klient dostane e-mail jednou – z hlavní rezervace. E-maily pro kliniku
        # (email_to) se taky posílají jen jednou.
        return super(VetReservationDruhaOrdinace, self.filtered(lambda r: not r.druha_ordinace))._poslat(
            xmlid, email_to=email_to)

    def write(self, vals):
        res = super().write(vals)
        if self.env.context.get("ev_spojena_sync") or not ({"start", "stop", "state"} & set(vals)):
            return res
        for rec in self.filtered("spojena_id"):
            druha = rec.spojena_id
            upd = {}
            if {"start", "stop"} & set(vals) and rec.state not in INACTIVE_STATES \
                    and druha.state not in INACTIVE_STATES and (druha.start, druha.stop) != (rec.start, rec.stop):
                upd.update(start=rec.start, stop=rec.stop)
            if vals.get("state") in KONCOVE_STAVY:
                if not rec.druha_ordinace and druha.state not in KONCOVE_STAVY:
                    upd["state"] = vals["state"]
                    if vals.get("cancel_reason"):
                        upd["cancel_reason"] = vals["cancel_reason"]
                elif rec.druha_ordinace and vals["state"] == "cancelled" and druha.spojena_id == rec:
                    # Zrušená druhá ordinace: hlavní rezervace jde znovu rozšířit.
                    upd["spojena_id"] = False
            if upd:
                druha.with_context(ev_spojena_sync=True).write(upd)
        return res

    def action_druha_ordinace(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window", "res_model": "elite.vet.reservation.druha.wizard",
            "name": _("Přidat druhou ordinaci"), "view_mode": "form", "views": [[False, "form"]],
            "target": "new", "context": {"default_reservation_id": self.id},
        }
