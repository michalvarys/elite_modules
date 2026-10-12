"""Live board updates via bus.bus.

Channel: the Reception group (res.groups). Odoo 18 subscribes every user to
all of their groups (ir.websocket._build_bus_channel_list adds
self.env.user.groups_id) and Reservation Manager implies Reception, so a single
message reaches everyone working with reservations without patching other modules.

Changes are collected for the whole transaction and sent once before commit:
a bulk write (copying the schedule, a repeated block) = one board refresh.
"""
import pytz

from odoo import api, models

from .reservation import WEEKDAY_ABBR, TZ

BUS_MESSAGE = "elite_vet_reservation/changed"
PRECOMMIT_KEY = "elite_vet_reservation.changes"


def notify_board(env, new_web_requests=()):
    """Record a change; the message is sent once per transaction (precommit)."""
    data = env.cr.precommit.data
    if PRECOMMIT_KEY not in data:
        data[PRECOMMIT_KEY] = []

        @env.cr.precommit.add
        def _send_notification():
            new_requests = env.cr.precommit.data.pop(PRECOMMIT_KEY, [])
            group = env.ref("elite_vet_reservation.group_reservation_reception", raise_if_not_found=False)
            if not group:
                return
            # web_ids: lets the browser recognise a request it already announced (after
            # a page load the bus re-delivers recent messages as well).
            env["bus.bus"].sudo()._sendone(group.sudo(), BUS_MESSAGE, {
                "new_web": bool(new_requests), "web": [label for _id, label in new_requests],
                "web_ids": [rid for rid, _label in new_requests]})
    data[PRECOMMIT_KEY].extend(new_web_requests)


class VetReservationLive(models.Model):
    _inherit = "elite.vet.reservation"

    def _request_label(self):
        local = pytz.utc.localize(self.start).astimezone(TZ)
        return "%s · %s %d. %d. %s" % (self.name, WEEKDAY_ABBR[local.weekday()], local.day, local.month,
                                      local.strftime("%H:%M"))

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        new_requests = records.filtered(lambda r: r.kind == "reservation" and r.state == "web_new")
        if records:
            notify_board(self.env, [(r.id, r._request_label()) for r in new_requests])
        return records

    def write(self, vals):
        res = super().write(vals)
        if self:
            notify_board(self.env)
        return res

    def unlink(self):
        if self:
            notify_board(self.env)
        return super().unlink()


class VetDoctorAssignmentLive(models.Model):
    _inherit = "elite.vet.doctor.assignment"

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if records:
            notify_board(self.env)
        return records

    def write(self, vals):
        res = super().write(vals)
        if self:
            notify_board(self.env)
        return res

    def unlink(self):
        if self:
            notify_board(self.env)
        return super().unlink()
