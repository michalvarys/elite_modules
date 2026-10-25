import re
import time

from werkzeug.exceptions import NotFound

from odoo import _, fields, http
from odoo.http import request

from ..models.holidays import czech_holidays
from ..models.pet import SPECIES

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")
# Simple per-process limit: 5 submissions per 10 minutes from one IP. With more workers
# it is looser, but the honeypot and validation keep spam out anyway.
_SUBMITS = {}
RATE_LIMIT, RATE_WINDOW = 5, 600


def _rate_ok(ip):
    now = time.time()
    hits = [t for t in _SUBMITS.get(ip, []) if now - t < RATE_WINDOW]
    if len(hits) >= RATE_LIMIT:
        return False
    hits.append(now)
    _SUBMITS[ip] = hits
    return True


def validate_submit(data):
    """Return (errors, cleaned data). Errors are {field: message} for the form."""
    errors, clean = {}, {}
    name = (data.get("contact_name") or "").strip()
    if len(name) < 3 or " " not in name:
        errors["contact_name"] = _("Vyplňte jméno a příjmení.")
    clean["contact_name"] = name
    email = (data.get("contact_email") or "").strip()
    if not EMAIL_RE.match(email):
        errors["contact_email"] = _("Zadejte platný e-mail.")
    clean["contact_email"] = email
    digits = re.sub(r"\D", "", data.get("contact_phone") or "")
    if len(digits) == 9:
        digits = "420" + digits
    if len(digits) < 11 or len(digits) > 13:
        errors["contact_phone"] = _("Zadejte telefon, například +420 777 111 222.")
    clean["contact_phone"] = "+" + digits
    pet = (data.get("pet_name") or "").strip()
    if not pet:
        errors["pet_name"] = _("Vyplňte jméno mazlíčka.")
    clean["pet_name"] = pet
    clean["pet_species"] = data.get("pet_species") if data.get("pet_species") in dict(SPECIES) else "other"
    problem = (data.get("problem") or "").strip()
    if len(problem) < 3:
        errors["problem"] = _("Popište prosím, s čím přicházíte.")
    clean["problem"] = problem
    if not data.get("consent"):
        errors["consent"] = _("Bez souhlasu se zpracováním údajů rezervaci nepřijmeme.")
    return errors, clean


class BookingController(http.Controller):

    def _env(self):
        return request.env

    def _setting(self):
        return request.env["elite.vet.setting"].sudo().nastaveni()

    def _web_booking_off(self):
        """None when the website books into Odoo; otherwise the answer of every public booking
        call. With "Rezervace na webu" = WinVet the clinic books through the WinVet form on
        /rezervacni-system, so our API neither offers dates nor creates reservations. The chat
        widget shows the message and a link to that page."""
        if self._setting().web_booking_source == "elite":
            return None
        return {"ok": False, "error": "web_booking_off", "fields": {},
                "message": _("Online rezervace najdete na stránce Rezervační systém."),
                "url": request.env["ir.http"]._url_for("/rezervacni-system")}

    def _procedure(self, procedure_id):
        proc = request.env["elite.vet.procedure"].sudo().browse(int(procedure_id or 0)).exists()
        return proc if proc and proc.online else None

    def _filters(self, kw):
        doctor = request.env["elite.vet.doctor"].sudo().browse(int(kw.get("doctor_id") or 0)).exists() or None
        spec = request.env["elite.vet.team.specialization"].sudo().browse(int(kw.get("specialization_id") or 0)).exists() or None
        return doctor, spec

    @http.route("/rezervace/api/options", type="json", auth="public", website=True, methods=["POST"], csrf=False)
    def options(self, **kw):
        off = self._web_booking_off()
        if off:
            return off
        env = request.env
        s = self._setting()
        today = fields.Date.context_today(env["elite.vet.setting"].sudo())
        horizon = fields.Date.add(today, days=s.booking_max_days_ahead)
        assignments = env["elite.vet.doctor.assignment"].sudo().search([("date", ">=", today), ("date", "<=", horizon)])
        doctors = assignments.mapped("doctor_id").filtered("accepts_bookings").sorted("name")
        # Offer only specializations that at least one doctor has - otherwise the
        # client could pick a field nobody can be booked for.
        all_doctors = env["elite.vet.doctor"].sudo().search([("accepts_bookings", "=", True)])
        specs = all_doctors.mapped("specialization_ids").sorted(lambda s: (s.sequence, s.name))
        procs = env["elite.vet.procedure"].sudo().search([("online", "=", True)])
        return {
            "procedures": [{"id": p.id, "name": p.name, "duration": p.duration, "client_note": p.client_note or "",
                            "deposit": p.deposit_amount if (s.booking_deposits_enabled and p.deposit_required) else 0,
                            "specialization_ids": p.specialization_ids.ids,
                            "doctor_ids": p.doctors_for_booking().ids} for p in procs],
            "doctors": [{"id": d.id, "name": d.name,
                         "photo": "/web/image/elite.vet.team.member/%s/image_128" % d.member_id.id if d.member_id else "",
                         "specialization_ids": d.specialization_ids.ids} for d in doctors],
            "specializations": [{"id": sp.id, "name": sp.name,
                                 "icon": "/web/image/elite.vet.team.icon/%s/image/24x24" % sp.icon_id.id if sp.icon_id else ""}
                                for sp in specs],
            "settings": {"step": s.booking_slot_step, "min_hours_before": s.booking_min_hours_before,
                         "max_days_ahead": s.booking_max_days_ahead, "consent_html": s.booking_consent_text or "",
                         "deposits": s.booking_deposits_enabled, "phone": s.phone_display or s.phone or ""},
        }

    @http.route("/rezervace/api/days", type="json", auth="public", website=True, methods=["POST"], csrf=False)
    def days(self, procedure_id=None, year=None, month=None, with_holidays=False, **kw):
        """Free days of the month: a list of ISO dates (unchanged response).

        With `with_holidays` (the booking page sends it) the response is
        {"days": [...], "holidays": {"YYYY-MM-DD": name}, "holidays_closed": bool}:
        the Czech public holidays of the month are marked in the calendar, also when the
        website books on them; `holidays_closed` = setting booking_block_holidays (the day is
        unavailable). Older callers (the chat widget) keep getting the plain list."""
        off = self._web_booking_off()
        if off:
            return off
        proc = self._procedure(procedure_id)
        if not proc:
            free = []
        else:
            doctor, spec = self._filters(kw)
            free = request.env["elite.vet.availability"].sudo().days(proc, int(year), int(month), doctor, spec)
        if not with_holidays:
            return free
        return {"days": free, "holidays": self._month_holidays(year, month),
                "holidays_closed": bool(self._setting().booking_block_holidays)}

    def _month_holidays(self, year, month):
        try:
            year, month = int(year), int(month)
            holidays = czech_holidays(year)
        except (TypeError, ValueError, OverflowError):
            return {}
        return {day.isoformat(): name for day, name in sorted(holidays.items()) if day.month == month}

    @http.route("/rezervace/api/slots", type="json", auth="public", website=True, methods=["POST"], csrf=False)
    def slots(self, procedure_id=None, date=None, **kw):
        off = self._web_booking_off()
        if off:
            return off
        proc = self._procedure(procedure_id)
        if not proc:
            return []
        doctor, spec = self._filters(kw)
        day = fields.Date.from_string(date)
        return request.env["elite.vet.availability"].sudo().slots(proc, day, doctor, spec, scope="web")

    @http.route("/rezervace/api/submit", type="json", auth="public", website=True, methods=["POST"], csrf=False)
    def submit(self, **data):
        off = self._web_booking_off()
        if off:
            return off
        if data.get("hp"):
            return {"ok": True, "token": "", "deposit": False}   # bot: pretend it went through
        ip = request.httprequest.remote_addr or "?"
        proc = self._procedure(data.get("procedure_id"))
        if not proc:
            return {"ok": False, "error": "validation", "fields": {"procedure_id": _("Vyberte důvod návštěvy.")}}
        errors, clean = validate_submit(data)
        try:
            day = fields.Date.from_string(data.get("date"))
            hh, mm = [int(x) for x in (data.get("time") or "").split(":")]
            minute = hh * 60 + mm
        except (ValueError, TypeError):
            errors["time"] = _("Vyberte termín.")
            day, minute = None, None
        if errors:
            return {"ok": False, "error": "validation", "fields": errors}
        doctor, spec = self._filters(data)
        A = request.env["elite.vet.availability"].sudo()
        # Room lock: two simultaneous submissions for the same time are serialized and the
        # second one already sees the first request (it holds the slot, see availability.pending_holds).
        request.env["elite.vet.reservation"].sudo()._lock_rooms(proc.rooms_for_booking().ids)
        slot = next((sl for sl in A.slots(proc, day, doctor, spec, scope="web") if sl["minute"] == minute), None)
        if not slot:
            return {"ok": False, "error": "slot_taken", "fields": {}}
        # The limit counts only submissions that actually create a record (failed attempts do not count).
        if not _rate_ok(ip):
            return {"ok": False, "error": "rate_limit", "fields": {}}
        s = self._setting()
        vals = dict(clean, **{
            "kind": "reservation", "state": "web_new", "source": "web",
            "procedure_id": proc.id, "doctor_id": doctor.id if doctor else False, "room_id": False,
            "start": A.local_to_utc(day, minute), "lang": request.env.lang or "cs_CZ",
            "deposit_state": "pending" if (s.booking_deposits_enabled and proc.deposit_required) else "none",
        })
        rec = request.env["elite.vet.reservation"].sudo().create(vals)
        rec._after_web_submit()
        return {"ok": True, "token": rec.cancel_token, "deposit": rec.deposit_state == "pending"}

    # csrf=False: the action is authorized by the random token in the URL (link from the e-mail); the client has no session with a CSRF token.
    @http.route("/rezervace/zruseni/<string:token>", type="http", auth="public", website=True,
                methods=["GET", "POST"], sitemap=False, csrf=False)
    def cancel_booking(self, token, **post):
        reservation = request.env["elite.vet.reservation"].sudo().search([("cancel_token", "=", token)], limit=1)
        if not reservation or reservation.kind != "reservation":
            raise NotFound()
        s = self._setting()
        status = "ask"
        if reservation.state in ("cancelled", "no_show", "done"):
            status = "already_cancelled"
        elif not reservation.client_can_cancel():
            status = "too_late"
        elif request.httprequest.method == "POST" and post.get("confirm"):
            reservation.action_cancel("client")
            status = "cancelled"
        return request.render("elite_vet_reservation.cancel_page", {
            "reservation": reservation, "status": status, "phone": s.phone_display or s.phone or "",
        })

    @http.route("/rezervace/platba/<string:token>", type="http", auth="public", website=True, methods=["GET"], sitemap=False)
    def deposit_payment(self, token, **kw):
        reservation = request.env["elite.vet.reservation"].sudo().search([("cancel_token", "=", token)], limit=1)
        if not reservation or reservation.kind != "reservation":
            raise NotFound()
        return request.render("elite_vet_reservation.deposit_page", {"reservation": reservation})
