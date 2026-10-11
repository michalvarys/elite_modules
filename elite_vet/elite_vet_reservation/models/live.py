"""Živá aktualizace tabule přes bus.bus.

Kanál: skupina Recepce (res.groups). Odoo 18 přihlašuje každého uživatele
k odběru všech jeho skupin (ir.websocket._build_bus_channel_list přidává
self.env.user.groups_id) a Správce rezervací Recepci implikuje - jedna zpráva
tak dojde všem, kdo s rezervacemi pracují, bez úprav cizích modulů.

Zprávy se sbírají za celou transakci a odešlou se jednou před commitem:
hromadný zápis (kopírování rozpisu, opakovaná blokace) = jedna obnova tabule.
"""
import pytz

from odoo import api, models

from .reservation import DNY_KRATCE, TZ

ZPRAVA = "elite_vet_reservation/changed"
KLIC = "elite_vet_reservation.zmeny"


def oznamit_tabuli(env, nove_z_webu=()):
    """Poznamená změnu; zprávu pošle jednou za transakci (precommit)."""
    data = env.cr.precommit.data
    if KLIC not in data:
        data[KLIC] = []

        @env.cr.precommit.add
        def _poslat():
            nove = env.cr.precommit.data.pop(KLIC, [])
            group = env.ref("elite_vet_reservation.group_reservation_reception", raise_if_not_found=False)
            if not group:
                return
            env["bus.bus"].sudo()._sendone(group.sudo(), ZPRAVA, {"new_web": bool(nove), "web": nove})
    data[KLIC].extend(nove_z_webu)


class VetReservationLive(models.Model):
    _inherit = "elite.vet.reservation"

    def _popisek_zadosti(self):
        local = pytz.utc.localize(self.start).astimezone(TZ)
        return "%s · %s %d. %d. %s" % (self.name, DNY_KRATCE[local.weekday()], local.day, local.month,
                                      local.strftime("%H:%M"))

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        nove = records.filtered(lambda r: r.kind == "reservation" and r.state == "web_new")
        if records:
            oznamit_tabuli(self.env, [r._popisek_zadosti() for r in nove])
        return records

    def write(self, vals):
        res = super().write(vals)
        if self:
            oznamit_tabuli(self.env)
        return res

    def unlink(self):
        if self:
            oznamit_tabuli(self.env)
        return super().unlink()


class VetDoctorAssignmentLive(models.Model):
    _inherit = "elite.vet.doctor.assignment"

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if records:
            oznamit_tabuli(self.env)
        return records

    def write(self, vals):
        res = super().write(vals)
        if self:
            oznamit_tabuli(self.env)
        return res

    def unlink(self):
        if self:
            oznamit_tabuli(self.env)
        return super().unlink()
