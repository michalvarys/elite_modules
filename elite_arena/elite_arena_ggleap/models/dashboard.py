"""Figures for the client action ``elite_arena_ggleap.dashboard`` (Přehled herny).

Periods are local days (user's time zone, Europe/Prague by default); stored datetimes are
UTC, so the period is converted to UTC bounds once and all queries use them."""

from datetime import date, datetime, time, timedelta

import pytz

from odoo import api, fields, models
from odoo.exceptions import AccessError

from .player import SEGMENT_HELP, SEGMENTS
from .product import KINDS

TOP_LIMIT = 10
KIND_LABELS = dict(KINDS)

# Arrivals: the first session of a player on a (local) day; every guest session counts.
# Parameters: tz, start, end.
ARRIVALS = """
    with s as (select player_id, is_guest, start, (start at time zone 'UTC' at time zone %s) as local
                 from elite_arena_ggleap_visit where start >= %s and start < %s),
    arrivals as (select player_id, min(local) as local from s where player_id is not null
                  group by player_id, local::date
                 union all
                 select null, local from s where player_id is null)
"""


class GgleapDashboard(models.AbstractModel):
    _name = "elite.arena.ggleap.dashboard"
    _description = "Přehled herny (ggLeap)"

    @api.model
    def _check_access(self):
        if not self.env.user.has_group("elite_arena_ggleap.group_ggleap_user"):
            raise AccessError("Přehled herny vidí jen uživatelé s přístupem k datům z ggLeapu.")

    def _tz(self):
        return pytz.timezone(self.env.user.tz or self.env.context.get("tz") or "Europe/Prague")

    def _utc_bounds(self, d_from, d_to):
        tz = self._tz()
        start = tz.localize(datetime.combine(d_from, time.min)).astimezone(pytz.utc).replace(tzinfo=None)
        end = tz.localize(datetime.combine(d_to + timedelta(days=1), time.min)).astimezone(pytz.utc).replace(tzinfo=None)
        return start, end

    def _today(self):
        return datetime.now(pytz.utc).astimezone(self._tz()).date()

    @api.model
    def get_data(self, date_from=None, date_to=None, compare_from=None, compare_to=None, compare=True):
        self._check_access()
        bounds = self._data_bounds()
        today = self._today()
        d_from = fields.Date.to_date(date_from) if date_from else (bounds["first"] or today)
        d_to = fields.Date.to_date(date_to) if date_to else (bounds["last"] or today)
        if d_to < d_from:
            d_from, d_to = d_to, d_from
        length = (d_to - d_from).days + 1
        if compare_from and compare_to:
            p_from, p_to = fields.Date.to_date(compare_from), fields.Date.to_date(compare_to)
        else:
            p_to = d_from - timedelta(days=1)
            p_from = p_to - timedelta(days=length - 1)
        start, end = self._utc_bounds(d_from, d_to)
        p_start, p_end = self._utc_bounds(p_from, p_to)
        status = self.env["elite.arena.ggleap.status"].sudo().search([], limit=1)
        return {
            "period": {"from": fields.Date.to_string(d_from), "to": fields.Date.to_string(d_to), "days": length,
                       "utc_from": fields.Datetime.to_string(start), "utc_to": fields.Datetime.to_string(end)},
            "previous": {"from": fields.Date.to_string(p_from), "to": fields.Date.to_string(p_to)},
            "bounds": {k: fields.Date.to_string(v) if v else False for k, v in bounds.items()},
            "kpi": self._kpi(start, end),
            "kpi_previous": self._kpi(p_start, p_end) if compare else False,
            "daily": self._daily(d_from, d_to),
            "heatmap": self._heatmap(start, end),
            "top_products": self._top_products(start, end),
            "payment_methods": self._payment_methods(start, end),
            "machines": self._machines(start, end),
            "top_players": self._top_players(start, end),
            "segments": self._segments(),
            "sync": {
                "last_success_at": fields.Datetime.to_string(status.last_success_at) if status.last_success_at else False,
                "alert": status.alert or False,
                "backfill_done": bool(status.backfill_done),
            },
        }

    # ------------------------------------------------------------------ helpers
    def _data_bounds(self):
        tz = self._tz().zone
        self.env.cr.execute("""
            select min(d), max(d) from (
                select (start at time zone 'UTC' at time zone %s)::date as d from elite_arena_ggleap_visit
                union all
                select (date at time zone 'UTC' at time zone %s)::date from elite_arena_ggleap_transaction) x""",
                            (tz, tz))
        first, last = self.env.cr.fetchone()
        return {"first": first, "last": last}

    def _kpi(self, start, end):
        cr = self.env.cr
        out = {}
        cr.execute("""select coalesce(sum(amount), 0), count(*), coalesce(sum(paid_cash), 0),
                             coalesce(sum(paid_card), 0), coalesce(sum(paid_balance), 0), coalesce(sum(discount), 0)
                        from elite_arena_ggleap_transaction where is_paid and date >= %s and date < %s""",
                   (start, end))
        (out["revenue"], out["sales"], out["paid_cash"], out["paid_card"], out["paid_balance"],
         out["discount"]) = cr.fetchone()
        cr.execute("""select kind, coalesce(sum(amount), 0), coalesce(sum(hours), 0)
                        from elite_arena_ggleap_transaction_line
                       where is_paid and date >= %s and date < %s group by kind""", (start, end))
        by_kind = {kind: (amount, hours) for kind, amount, hours in cr.fetchall()}
        out["revenue_time"] = by_kind.get("time", (0, 0))[0]
        out["revenue_food"] = by_kind.get("food", (0, 0))[0]
        out["revenue_other"] = by_kind.get("other", (0, 0))[0] + by_kind.get("free", (0, 0))[0]
        out["hours_sold"] = by_kind.get("time", (0, 0))[1]
        out["hours_free"] = by_kind.get("free", (0, 0))[1]
        tz = self._tz().zone
        cr.execute("""select count(*), count(distinct player_id), coalesce(sum(duration_hours), 0),
                             count(*) filter (where duration_hours is not null and duration_hours > 0)
                        from elite_arena_ggleap_visit where start >= %s and start < %s""", (start, end))
        out["sessions"], out["players"], out["hours_played"], out["sessions_with_length"] = cr.fetchone()
        cr.execute(ARRIVALS + "select count(*), count(*) filter (where player_id is null) from arrivals",
                   (tz, start, end))
        out["visits"], out["guest_visits"] = cr.fetchone()
        cr.execute("""select count(*) from elite_arena_ggleap_player
                       where first_visit >= %s and first_visit < %s""", (start, end))
        out["new_players"] = cr.fetchone()[0]
        # new players of the period who came again within 30 days of their first visit
        cr.execute("""select count(distinct p.id) from elite_arena_ggleap_player p
                        join elite_arena_ggleap_visit v on v.player_id = p.id
                       where p.first_visit >= %s and p.first_visit < %s
                         and (v.start at time zone 'UTC' at time zone %s)::date
                             > (p.first_visit at time zone 'UTC' at time zone %s)::date
                         and v.start <= p.first_visit + interval '30 days'""", (start, end, tz, tz))
        out["new_returned"] = cr.fetchone()[0]
        out["new_returned_pct"] = round(100.0 * out["new_returned"] / out["new_players"]) if out["new_players"] else 0
        out["avg_per_player"] = out["revenue"] / out["players"] if out["players"] else 0.0
        out["avg_visit_hours"] = (out["hours_played"] / out["sessions_with_length"]
                                  if out["sessions_with_length"] else 0.0)
        cr.execute("""select count(*), count(*) filter (where state = 'noshow')
                        from elite_arena_ggleap_booking where start >= %s and start < %s""", (start, end))
        out["bookings"], out["bookings_noshow"] = cr.fetchone()
        return {k: (float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else v) for k, v in out.items()}

    def _daily(self, d_from, d_to):
        tz = self._tz().zone
        start, end = self._utc_bounds(d_from, d_to)
        days, day = {}, d_from
        while day <= d_to:
            key = fields.Date.to_string(day)
            days[key] = {"date": key, "time": 0.0, "food": 0.0, "other": 0.0, "visits": 0, "players": 0}
            day += timedelta(days=1)
        cr = self.env.cr
        cr.execute("""select (date at time zone 'UTC' at time zone %s)::date, kind, coalesce(sum(amount), 0)
                        from elite_arena_ggleap_transaction_line
                       where is_paid and date >= %s and date < %s group by 1, 2""", (tz, start, end))
        for day, kind, amount in cr.fetchall():
            row = days.get(fields.Date.to_string(day))
            if row:
                row[kind if kind in ("time", "food") else "other"] += float(amount)
        cr.execute(ARRIVALS + """select local::date, count(*), count(distinct player_id)
                                    from arrivals group by 1""", (tz, start, end))
        for day, visits, players in cr.fetchall():
            row = days.get(fields.Date.to_string(day))
            if row:
                row.update(visits=visits, players=players)
        return list(days.values())

    def _heatmap(self, start, end):
        """Arrivals by weekday (0 = Monday) and hour, local time."""
        tz = self._tz().zone
        self.env.cr.execute(ARRIVALS + """
            select extract(isodow from local)::int - 1, extract(hour from local)::int, count(*)
              from arrivals group by 1, 2""", (tz, start, end))
        grid = [[0] * 24 for _ in range(7)]
        for dow, hour, count in self.env.cr.fetchall():
            grid[dow][hour] = count
        return grid

    def _top_products(self, start, end):
        self.env.cr.execute("""
            select coalesce(l.name, p.name, '—'), l.kind, coalesce(sum(l.quantity), 0), coalesce(sum(l.amount), 0)
              from elite_arena_ggleap_transaction_line l
              left join elite_arena_ggleap_product p on p.id = l.product_id
             where l.is_paid and l.date >= %s and l.date < %s
             group by 1, 2 order by 4 desc, 3 desc limit %s""", (start, end, TOP_LIMIT))
        return [{"name": name, "kind": kind or "other", "kind_label": KIND_LABELS.get(kind, "Ostatní"),
                 "quantity": float(qty), "amount": float(amount)}
                for name, kind, qty, amount in self.env.cr.fetchall()]

    def _payment_methods(self, start, end):
        k = self._kpi_payments(start, end)
        rows = [("cash", "Hotově", k[0]), ("card", "Kartou", k[1]), ("balance", "Z kreditu na účtu", k[2])]
        return [{"method": m, "label": label, "amount": float(v)} for m, label, v in rows if v]

    def _kpi_payments(self, start, end):
        self.env.cr.execute("""select coalesce(sum(paid_cash), 0), coalesce(sum(paid_card), 0),
                                      coalesce(sum(paid_balance), 0)
                                 from elite_arena_ggleap_transaction where is_paid and date >= %s and date < %s""",
                            (start, end))
        return self.env.cr.fetchone()

    def _machines(self, start, end):
        """Hours per PC and per console (consoles have no machine, only a device)."""
        self.env.cr.execute("""
            select coalesce(place, 'Neznámé místo'), min(machine_id), min(device_uuid), count(*),
                   coalesce(sum(duration_hours), 0)
              from elite_arena_ggleap_visit where start >= %s and start < %s
             group by 1 order by 5 desc, 1""", (start, end))
        return [{"name": name, "machine_id": mid or False, "device_uuid": dev or False, "visits": visits,
                 "hours": float(hours)}
                for name, mid, dev, visits, hours in self.env.cr.fetchall()]

    def _top_players(self, start, end):
        self.env.cr.execute("""
            select p.id, p.display_label, p.segment, coalesce(sum(t.amount), 0) as spent,
                   (select count(distinct (v.start at time zone 'UTC' at time zone %s)::date)
                      from elite_arena_ggleap_visit v
                     where v.player_id = p.id and v.start >= %s and v.start < %s)
              from elite_arena_ggleap_transaction t join elite_arena_ggleap_player p on p.id = t.player_id
             where t.is_paid and t.date >= %s and t.date < %s
             group by 1, 2, 3 order by 4 desc limit %s""", (self._tz().zone, start, end, start, end, TOP_LIMIT))
        labels = dict(SEGMENTS)
        return [{"id": pid, "name": name or "—", "segment": seg, "segment_label": labels.get(seg, ""),
                 "amount": float(spent), "visits": visits}
                for pid, name, seg, spent, visits in self.env.cr.fetchall()]

    def _segments(self):
        """Current state (not period-dependent): how many players are in each group and what
        they spent on average (shows what a lapsed group used to be worth)."""
        self.env.cr.execute("""
            select segment, count(*), coalesce(avg(total_spent), 0), count(partner_id),
                   count(*) filter (where email is not null and email != '')
              from elite_arena_ggleap_player
             where not deleted and segment is not null group by segment""")
        rows = {seg: (count, avg, linked, emails) for seg, count, avg, linked, emails in self.env.cr.fetchall()}
        total = sum(r[0] for r in rows.values()) or 1
        out = []
        for key, label in SEGMENTS:
            count, avg, linked, emails = rows.get(key, (0, 0.0, 0, 0))
            out.append({"key": key, "label": label, "help": SEGMENT_HELP[key], "count": count,
                        "share": round(100.0 * count / total), "avg_spent": float(avg), "with_email": emails})
        return out
