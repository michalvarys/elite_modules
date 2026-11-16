"""PDF of the month plan (request 16. 11.: the browser's print to PDF gave a file that would not open).

Rendered on the server by wkhtmltopdf from the same data as the planner screen (load_month)."""
from odoo import api, fields, models

from .planner import fmt_time, month_bounds


class RosterReport(models.AbstractModel):
    _name = "report.elite_vet_planning.report_roster"
    _description = "Shift roster PDF"

    @api.model
    def _get_report_values(self, docids, data=None):
        month = (data or {}).get("month") or fields.Date.context_today(self)
        first, _last = month_bounds(month)
        planner = self.env["elite.vet.planner"]
        plan = planner.load_month(first)   # checks the manager right
        staff = {m["id"]: m for m in plan["staff"]}
        shifts_by_cell = {}
        for s in plan["shifts"]:
            shifts_by_cell.setdefault((s["slot_id"], s["date"]), []).append(s)
        role_order = {r["key"]: i for i, r in enumerate(plan["roles"])}
        for items in shifts_by_cell.values():
            items.sort(key=lambda s: (role_order.get(s["role"], 9), s["hour_from"]))

        def chips(slot, day):
            out = []
            for s in shifts_by_cell.get((slot["id"], day["date"]), []):
                member = staff.get(s["member_id"]) or {}
                custom = (s["hour_from"], s["hour_to"]) != (slot["hour_from"], slot["hour_to"])
                out.append({"label": member.get("initials") or s["helper_name"], "color": member.get("color") or "#94a3b8",
                            "doctor": s["role"] == "doctor",
                            "time": "%s–%s" % (fmt_time(s["hour_from"]), fmt_time(s["hour_to"])) if custom else ""})
            return out

        groups = []
        for role in plan["roles"]:
            members = [m for m in plan["staff"] if m["role"] == role["key"]]
            if members:
                groups.append({"label": role["label"], "members": members})
        weekday_abbr = ["Po", "Út", "St", "Čt", "Pá", "So", "Ne"]
        return {
            "doc_ids": docids,
            "plan": plan,
            "month_label": "%s %s" % (MONTHS[first.month - 1], first.year),
            "chips": chips,
            "groups": groups,
            "wd": lambda day: weekday_abbr[day["weekday"]],
            "people": lambda member, day: plan["people"].get(member["id"], {}).get(day["date"], []),
            "text_on": text_on,
            "short": {c["key"]: c["short"] for c in plan["codes"]},
            "hours": lambda v: ("%.1f" % v).rstrip("0").rstrip(".").replace(".", ","),
            "printed": fields.Datetime.context_timestamp(self, fields.Datetime.now()).strftime("%d. %m. %Y %H:%M"),
        }


MONTHS = ["Leden", "Únor", "Březen", "Duben", "Květen", "Červen", "Červenec", "Srpen", "Září", "Říjen",
          "Listopad", "Prosinec"]


def text_on(hex_color):
    """Dark or white text on a coloured chip (same rule as the planner screen)."""
    value = (hex_color or "").lstrip("#")
    if len(value) != 6:
        return "#fff"
    n = int(value, 16)
    lum = (0.299 * ((n >> 16) & 255) + 0.587 * ((n >> 8) & 255) + 0.114 * (n & 255)) / 255
    return "#1e293b" if lum > 0.62 else "#fff"
