"""JSON API of the patient card (OWL client action `elite_vet_clinic.patient_card`).

All methods are model methods of `elite.vet.clinical.record` called over RPC
(`orm.call("elite.vet.clinical.record", "<method>", [args])`). They run with the rights
of the calling user (no sudo): reception reads, nurse/doctor write. Every method returns
plain JSON-serialisable data; the shapes are documented in README.md.
"""
import re
from datetime import datetime

import pytz

from odoo import _, api, models
from odoo.exceptions import AccessError, UserError
from odoo.osv import expression

from odoo.addons.elite_vet_reservation.models.pet import SPECIES, normalize_phone
from odoo.addons.elite_vet_winvet.models.item import KINDS
from odoo.addons.elite_vet_winvet.models.winvet_tools import name_words

from .clinical_record import STATES, SUMMARY_LENGTH, TZ, insert_template_text, record_text_title
from .pet_alert import ALERT_KINDS

# Fields of the record the card may write (save_record).
# Task 32: one text, record_text; the deprecated anamnesis / examination / diagnosis are ignored.
SAVE_FIELDS = ("temperature", "weight", "heart_rate", "respiratory_rate", "record_text", "doctor_id")
NUMBER_FIELDS = {"temperature": float, "weight": float, "heart_rate": int, "respiratory_rate": int}
# Fields of a bill line the card may write (update_line).
LINE_FIELDS = ("quantity", "price_unit", "name", "unit", "kind", "sequence")
TIMELINE_LIMIT = 300


def clinic_today():
    return datetime.now(TZ).date()


def date_str(value):
    return value.isoformat() if value else None


def local_time(dt):
    """Naive UTC datetime -> 'HH:MM' in the clinic timezone."""
    if not dt:
        return None
    return pytz.utc.localize(dt).astimezone(TZ).strftime("%H:%M")


def short_time(text):
    """WinVet 'HH:MM:SS' -> 'HH:MM'."""
    return text[:5] if text else None


def or_none(value):
    """0 / 0.0 / False / '' -> None (an empty measurement is not zero)."""
    return value or None


def to_number(value, kind):
    if value in (None, False, ""):
        return 0
    if isinstance(value, str):
        value = value.strip().replace(",", ".")
        if not value:
            return 0
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise UserError("„%s“ není číslo." % value) from None
    return int(round(number)) if kind is int else number


def czech_plural(n, one, few, many):
    if n == 1:
        return one
    if 2 <= n <= 4:
        return few
    return many


def age_text(birth_date, birth_year, today, end=None):
    """'7 let', '1 rok', '3 roky', '5 měsíců', '2 týdny'; only the year known -> 'cca 7 let'."""
    end = end or today
    if birth_date:
        months = (end.year - birth_date.year) * 12 + end.month - birth_date.month - (end.day < birth_date.day)
        if months < 0:
            return None
        if months >= 12:
            years = months // 12
            return "%d %s" % (years, czech_plural(years, "rok", "roky", "let"))
        if months >= 1:
            return "%d %s" % (months, czech_plural(months, "měsíc", "měsíce", "měsíců"))
        weeks = (end - birth_date).days // 7
        if weeks >= 1:
            return "%d %s" % (weeks, czech_plural(weeks, "týden", "týdny", "týdnů"))
        days = (end - birth_date).days
        return "%d %s" % (days, czech_plural(days, "den", "dny", "dní"))
    if birth_year and 1900 <= birth_year <= end.year:
        years = end.year - birth_year
        return "cca %d %s" % (years, czech_plural(years, "rok", "roky", "let")) if years else "méně než rok"
    return None


class ClinicalRecordCardApi(models.Model):
    _inherit = "elite.vet.clinical.record"

    # ------------------------------------------------------------------ helpers

    @api.model
    def _can_write(self):
        return self.env.user.has_group("elite_vet_clinic.group_clinic_nurse")

    @api.model
    def _check_can_write(self):
        if not self._can_write():
            raise AccessError(_("Záznamy návštěv mohou zapisovat jen sestry a lékařky."))

    @api.model
    def _get_record(self, record_id, editable=True):
        record = self.browse(int(record_id)).exists()
        if not record:
            raise UserError(_("Záznam návštěvy nebyl nalezen."))
        if editable:
            self._check_can_write()
            if record.state != "draft":
                raise UserError(_("Záznam je uzavřený (%s). Pro úpravy ho nejdřív vraťte do rozepsaných.")
                                % dict(STATES)[record.state])
        return record

    @api.model
    def _get_pet(self, pet_id):
        pet = self.env["elite.vet.pet"].browse(int(pet_id)).exists() if pet_id else None
        if not pet:
            raise UserError(_("Pacient nebyl nalezen."))
        return pet

    @api.model
    def _doctor_for_user(self, user=None):
        """Team member of the user: the linked one (elite.vet.doctor.user_id, task 23) first.
        A user without a link falls back to the doctor whose name matches the user's name
        (titles, case, accents and word order ignored, as WinVet users are matched in
        elite_vet_winvet): only a unique match, and none when a doctor of that name is linked
        to another account."""
        user = user or self.env.user
        Doctor = self.env["elite.vet.doctor"]
        linked = Doctor.search([("user_id", "=", user.id)], limit=1) if user else Doctor
        if linked:
            return linked
        key = frozenset(name_words(user.name))
        if not key:
            return Doctor
        matches = Doctor.search([]).filtered(lambda d: frozenset(name_words(d.name)) == key)
        if len(matches) != 1 or matches.user_id:
            return Doctor
        return matches

    @api.model
    def _species_label(self, pet):
        if pet.species == "other" and pet.species_other:
            return pet.species_other
        return dict(SPECIES).get(pet.species) or pet.winvet_species or None

    def _line_data(self, line):
        return {
            "id": line.id, "sequence": line.sequence, "item_id": line.item_id.id or None,
            "code": line.item_id.code or None, "name": line.name, "kind": line.kind,
            "kind_label": dict(KINDS).get(line.kind), "quantity": line.quantity, "unit": line.unit or None,
            "price_unit": line.price_unit, "amount": line.amount,
            "bundle_id": line.bundle_id.id or None, "bundle_name": line.bundle_id.name or None,
        }

    def _record_data(self):
        """The record as the card's center/right columns need it."""
        self.ensure_one()
        rec = self
        return {
            "id": rec.id, "name": rec.display_name, "pet_id": rec.pet_id.id, "partner_id": rec.partner_id.id or None,
            "doctor_id": rec.doctor_id.id or None, "doctor_name": rec.doctor_id.name or None,
            "doctor_auto": rec.doctor_auto, "other_doctors": rec.other_doctor_ids.mapped("name"),
            "user_name": rec.user_id.name or None, "reservation_id": rec.reservation_id.id or None,
            "start": rec.start and rec.start.strftime("%Y-%m-%d %H:%M:%S"), "date": date_str(rec.date),
            "time": local_time(rec.start), "state": rec.state, "state_label": dict(STATES)[rec.state],
            "temperature": or_none(rec.temperature), "weight": or_none(rec.weight),
            "heart_rate": or_none(rec.heart_rate), "respiratory_rate": or_none(rec.respiratory_rate),
            "record_text": rec.record_text or "",
            "reception_note": rec.reception_note or None,
            "room_note": rec.room_note or "",
            "room_note_editable": rec.state != "cancelled" and self._can_write(),
            "lines": [self._line_data(line) for line in rec.line_ids],
            "amount_total": rec.amount_total, "currency": rec.currency_id.symbol,
            "editable": rec.state == "draft" and self._can_write(),
        }

    @api.model
    def _today_record(self, pet, reservation=None):
        """Today's record to continue: the reservation's own record, else today's draft,
        else today's finished one (not linked to another reservation)."""
        if reservation:
            own = self.search([("reservation_id", "=", reservation.id)], limit=1)
            if own:
                return own
        domain = [("pet_id", "=", pet.id), ("date", "=", clinic_today()), ("state", "!=", "cancelled")]
        if reservation:
            domain.append(("reservation_id", "=", False))
        candidates = self.search(domain, order="start desc, id desc")
        return candidates.filtered(lambda r: r.state == "draft")[:1] or candidates[:1]

    @api.model
    def _weight_info(self, pet):
        """Current weight, change against the previous measurement and the date of the last one.
        Measurements: Odoo records (not cancelled) and WinVet vitals."""
        points = []
        for rec in self.search([("pet_id", "=", pet.id), ("state", "!=", "cancelled"), ("weight", ">", 0)]):
            points.append((rec.date, local_time(rec.start) or "", rec.weight))
        for vital in self.env["elite.vet.visit.vital"].search([("pet_id", "=", pet.id), ("weight", ">", 0)]):
            points.append((vital.date or vital.visit_id.date, vital.time or "", vital.weight))
        points = sorted((p for p in points if p[0]), key=lambda p: (p[0], p[1]), reverse=True)
        weight = pet.weight or (points[0][2] if points else 0.0)
        delta = round(points[0][2] - points[1][2], 3) if len(points) > 1 else None
        return {"weight": or_none(weight), "weight_delta": delta,
                "weight_date": date_str(points[0][0]) if points else None}

    @api.model
    def _timeline(self, pet):
        items = []
        for rec in self.search([("pet_id", "=", pet.id), ("state", "!=", "cancelled")], limit=TIMELINE_LIMIT):
            text = rec.record_text or ""
            flat = " ".join(text.split())
            items.append({
                "type": "record", "id": rec.id, "date": date_str(rec.date), "time": local_time(rec.start),
                "doctor": rec.doctor_id.name or rec.user_id.name or None,
                "title": record_text_title(text) or None,
                "summary": flat[:SUMMARY_LENGTH].strip() + ("…" if len(flat) > SUMMARY_LENGTH else ""),
                "record_text": text, "state": rec.state, "state_label": dict(STATES)[rec.state],
                "vitals_summary": self._vitals_summary(rec) or None,
                "items": rec.line_ids.mapped("name"), "amount_total": rec.amount_total,
            })
        Visit = self.env["elite.vet.visit"]
        for visit in Visit.search([("pet_id", "=", pet.id)], limit=TIMELINE_LIMIT):
            vitals = visit.vital_ids
            items.append({
                "type": "visit", "id": visit.id, "date": date_str(visit.date), "time": short_time(visit.time),
                "doctor": visit.doctor_id.name or visit.entered_by_id.name or None,
                "diagnosis": visit.diagnosis_name or visit.case_name or None, "case_name": visit.case_name or None,
                "notes": visit.notes or "",
                "vitals": [{"time": short_time(v.time), "temperature": or_none(v.temperature),
                            "heart_rate": or_none(v.heart_rate), "respiratory_rate": or_none(v.respiratory_rate),
                            "weight": or_none(v.weight), "bp_systolic": or_none(v.bp_systolic),
                            "bp_diastolic": or_none(v.bp_diastolic), "summary": v.summary()} for v in vitals],
                "vitals_summary": " | ".join(s for s in (v.summary() for v in vitals) if s) or None,
                # task 28: the visit report ("Zpráva z vyšetření") can be printed for it too
                "printable": visit._visit_report_has_content(),
            })
        for vac in self.env["elite.vet.vaccination"].search([("pet_id", "=", pet.id)], limit=TIMELINE_LIMIT):
            items.append({
                "type": "vaccination", "id": vac.id, "date": date_str(vac.date), "time": None,
                "item": vac.item_name or vac.item_id.name or None, "next_date": date_str(vac.next_date),
            })
        order = {"record": 0, "visit": 1, "vaccination": 2}
        items.sort(key=lambda i: (i["date"] or "", i["time"] or "", -order[i["type"]], i["id"]), reverse=True)
        return items

    @api.model
    def _vitals_summary(self, rec):
        def num(value, digits):
            return ("%.*f" % (digits, value)).rstrip("0").rstrip(".").replace(".", ",")
        parts = []
        if rec.temperature:
            parts.append("T %s °C" % num(rec.temperature, 1))
        if rec.heart_rate:
            parts.append("P %d/min" % rec.heart_rate)
        if rec.respiratory_rate:
            parts.append("D %d/min" % rec.respiratory_rate)
        if rec.weight:
            parts.append("%s kg" % num(rec.weight, 2))
        return " · ".join(parts)

    # ------------------------------------------------------------------ read API

    @api.model
    def card_data(self, pet_id):
        pet = self._get_pet(pet_id)
        partner = pet.partner_id
        today = clinic_today()
        kinds = dict(ALERT_KINDS)
        header = {
            "pet": dict({
                "id": pet.id, "name": pet.name, "species": pet.species or None,
                "species_label": self._species_label(pet), "breed": pet.breed or None, "sex": pet.sex or None,
                "color": pet.color or None, "birth_date": date_str(pet.birth_date),
                "age_text": age_text(pet.birth_date, pet.birth_year, today,
                                     end=pet.death_date if pet.deceased and pet.death_date else None),
                "chip": pet.chip or None, "tattoo": pet.tattoo or None, "passport": pet.passport or None,
                "deceased": pet.deceased, "active": pet.active, "important_note": pet.important_note or None,
                "note": pet.note or None, "winvet_note": pet.winvet_note or None,
                "next_vaccination": date_str(pet.next_vaccination),
            }, **self._weight_info(pet)),
            "owner": {
                "partner_id": partner.id, "name": partner.name, "phone": partner.phone or None,
                "mobile": partner.mobile or None, "email": partner.email or None,
                "street": partner.street or None, "city": partner.city or None,
                # task 33: balance of the client's WinVet deposits ("2 000 Kč"), None when there is none
                "deposit_text": partner.winvet_deposit_balance_text or None,
            },
            "alerts": [{"id": a.id, "kind": a.kind, "kind_label": kinds.get(a.kind), "note": a.note or None,
                        "label": a.display_name} for a in pet.alert_ids.filtered("active")],
        }
        # task 32: one record text, so every template is offered (the section no longer matters)
        templates = [{"id": tpl.id, "name": tpl.name, "body": tpl.body, "group_name": tpl.group_name or None}
                     for tpl in self.env["elite.vet.text.template"].search([], order="sequence, name, id")]
        bundles = [{"id": b.id, "code": b.code or None, "name": b.name, "description": b.description or None,
                    "line_count": b.line_count, "amount": b.amount}
                   for b in self.env["elite.vet.procedure.bundle"].search([])]
        today_record = self._today_record(pet)
        user = self.env.user
        return {
            "header": header,
            "timeline": self._timeline(pet),
            "today_record": today_record._record_data() if today_record else None,
            "templates": templates,
            "bundles": bundles,
            "doctors": [{"id": d.id, "name": d.name} for d in self.env["elite.vet.doctor"].search([])],
            "permissions": {
                "can_write": self._can_write(),
                "can_edit_templates": user.has_group("elite_vet_clinic.group_clinic_doctor"),
                "is_manager": user.has_group("elite_vet_reservation.group_reservation_manager"),
            },
            "today": date_str(today),
        }

    @api.model
    def get_record(self, record_id):
        return self._get_record(record_id, editable=False)._record_data()

    @api.model
    def search_items(self, term, kind=None, limit=20):
        domain = [("active", "=", True), ("classification", "!=", "group")]
        term = (term or "").strip()
        if term:
            domain += ["|", "|", ("name", "ilike", term), ("code", "ilike", term), ("barcode", "=", term)]
        if kind:
            domain.append(("kind", "=", kind))
        kinds = dict(KINDS)
        return [{"id": i.id, "code": i.code or None, "name": i.name, "kind": i.kind, "kind_label": kinds.get(i.kind),
                 "unit": i.unit or None, "price": i.price, "stock_tracked": i.stock_tracked}
                for i in self.env["elite.vet.winvet.item"].search(domain, limit=int(limit or 20), order="name, id")]

    @api.model
    def search_patients(self, term, limit=20):
        term = (term or "").strip()
        if len(term) < 2:
            return []
        Pet = self.env["elite.vet.pet"]
        domain = ["|", "|", ("name", "ilike", term), ("partner_id.name", "ilike", term), ("chip", "ilike", term)]
        digits = normalize_phone(term)
        if len(digits) >= 4 and len(digits) >= len(re.sub(r"[\s+\-/().]", "", term)):
            # a number: owner phone/mobile or chip compared digits only (stored in various formats)
            self.env["res.partner"].flush_model(["phone", "mobile"])
            Pet.flush_model(["chip"])
            self.env.cr.execute(
                "SELECT id FROM res_partner WHERE regexp_replace(coalesce(phone, ''), '\\D', '', 'g') LIKE %s"
                " OR regexp_replace(coalesce(mobile, ''), '\\D', '', 'g') LIKE %s", ["%" + digits + "%"] * 2)
            partner_ids = [r[0] for r in self.env.cr.fetchall()]
            self.env.cr.execute(
                "SELECT id FROM elite_vet_pet WHERE regexp_replace(coalesce(chip, ''), '\\D', '', 'g') LIKE %s",
                ["%" + digits + "%"])
            pet_ids = [r[0] for r in self.env.cr.fetchall()]
            domain = expression.OR([domain, [("partner_id", "in", partner_ids)], [("id", "in", pet_ids)]])
        pets = Pet.search(domain, limit=int(limit or 20), order="name, id")
        last = self._last_visits(pets)
        return [{
            "id": p.id, "name": p.name, "species": p.species or None, "species_label": self._species_label(p),
            "breed": p.breed or None, "owner": p.partner_id.name, "partner_id": p.partner_id.id,
            "phone": p.partner_id.mobile or p.partner_id.phone or None, "chip": p.chip or None,
            "last_visit": date_str(last.get(p.id)), "deceased": p.deceased, "alerts": p.alert_summary or None,
        } for p in pets]

    @api.model
    def _last_visits(self, pets):
        last = {}
        if not pets:
            return last
        for model in ("elite.vet.clinical.record", "elite.vet.visit"):
            domain = [("pet_id", "in", pets.ids)]
            if model == "elite.vet.clinical.record":
                domain.append(("state", "!=", "cancelled"))
            for pet, day in self.env[model]._read_group(domain, ["pet_id"], ["date:max"]):
                if day and (pet.id not in last or day > last[pet.id]):
                    last[pet.id] = day
        return last

    @api.model
    def my_patients_today(self):
        today = clinic_today()
        A = self.env["elite.vet.availability"]
        Reservation = self.env["elite.vet.reservation"]
        doctor = self._doctor_for_user()
        domain = [("kind", "=", "reservation"), ("state", "in", ("confirmed", "done")),
                  ("start", ">=", A.local_to_utc(today, 0)), ("start", "<", A.local_to_utc(today, 1440))]
        if doctor:
            domain.append(("doctor_id", "=", doctor.id))
        reservations = Reservation.search(domain, order="start, id")
        records = {r.reservation_id.id: r for r in self.search([("reservation_id", "in", reservations.ids)])}
        lang = Reservation._clinic_lang()
        states = dict(Reservation._fields["state"]._description_selection(self.env))
        items = []
        for res in reservations:
            rec = records.get(res.id)
            pet = res.pet_id
            items.append({
                "reservation_id": res.id, "start": res.start.strftime("%Y-%m-%d %H:%M:%S"),
                "time": local_time(res.start), "time_end": local_time(res.stop),
                "room": res.room_id.name or None, "room_color": res.room_id.color_hex or None,
                "doctor": res.doctor_id.name or None,
                "pet_id": pet.id or None, "pet_name": pet.name or res.pet_name or None,
                "species_label": self._species_label(pet) if pet else None,
                "owner": res.partner_id.name or res.contact_name or None, "partner_id": res.partner_id.id or None,
                "phone": res.contact_phone or res.partner_id.mobile or res.partner_id.phone or None,
                "procedure": res.procedure_id.with_context(lang=lang).name or None, "problem": res.problem or None,
                "state": res.state, "state_label": states.get(res.state),
                "record_id": rec.id if rec else None, "record_state": rec.state if rec else None,
                "alerts": pet.alert_summary or None if pet else None,
                "reception_note": rec.reception_note or None if rec and rec.state != "cancelled" else None,
            })
        return {"date": date_str(today), "doctor": {"id": doctor.id, "name": doctor.name} if doctor else None,
                "filtered_by_doctor": bool(doctor), "items": items}

    # ------------------------------------------------------------------ write API

    @api.model
    def open_today_record(self, pet_id, reservation_id=False, force_new=False):
        """Today's record of the pet (see _today_record) or a new draft. force_new=True always
        creates a new draft (second visit on the same day)."""
        self._check_can_write()
        pet = self._get_pet(pet_id)
        reservation = self.env["elite.vet.reservation"].browse(int(reservation_id)).exists() \
            if reservation_id else self.env["elite.vet.reservation"]
        if reservation and reservation.pet_id and reservation.pet_id != pet:
            raise UserError(_("Rezervace patří jinému pacientovi (%s).") % reservation.pet_id.name)
        record = self.browse() if force_new else self._today_record(pet, reservation)
        if record:
            if reservation and not record.reservation_id:
                record.reservation_id = reservation
            if not record.doctor_id and reservation.doctor_id and record.state == "draft":
                record.write({"doctor_id": reservation.doctor_id.id, "doctor_auto": True})
            return record._record_data()
        if reservation and self.search_count([("reservation_id", "=", reservation.id)]):
            reservation = self.env["elite.vet.reservation"]
        doctor = reservation.doctor_id or self._doctor_for_user()
        record = self.create({
            "pet_id": pet.id,
            "reservation_id": reservation.id or False,
            "doctor_id": doctor.id or False,
            "doctor_auto": bool(doctor),   # task 23: a linked doctor's work replaces it
        })
        return record._record_data()

    @api.model
    def save_record(self, record_id, vals):
        """Write the whitelisted fields (others are ignored); returns the record data."""
        record = self._get_record(record_id)
        clean = {}
        for name, value in (vals or {}).items():
            if name not in SAVE_FIELDS:
                continue
            if name in NUMBER_FIELDS:
                clean[name] = to_number(value, NUMBER_FIELDS[name])
            elif name == "doctor_id":
                clean[name] = int(value) if value else False
            else:
                clean[name] = value or False
        if clean:
            record.write(clean)
        return record._record_data()

    @api.model
    def _add_quantity(self, record, item, quantity, bundle=None, name=None, unit=None):
        """Merge into the line of the same price list item, or add a new line."""
        line = record.line_ids.filtered(lambda l: l.item_id == item)[:1] if item else None
        if line:
            line.quantity += quantity
            return line
        sequence = max(record.line_ids.mapped("sequence") or [0]) + 1
        return self.env["elite.vet.clinical.record.line"].create({
            "record_id": record.id, "item_id": item.id if item else False, "quantity": quantity,
            "name": name or (item.name if item else _("Položka")), "unit": unit or (item.unit if item else False),
            "bundle_id": bundle.id if bundle else False, "sequence": sequence,
        })

    @api.model
    def add_item(self, record_id, item_id, quantity=1):
        record = self._get_record(record_id)
        item = self.env["elite.vet.winvet.item"].browse(int(item_id)).exists()
        if not item:
            raise UserError(_("Položka ceníku nebyla nalezena."))
        self._add_quantity(record, item, to_number(quantity, float) or 1.0)
        return record._record_data()

    @api.model
    def add_free_line(self, record_id, name, price_unit=0.0, quantity=1, kind="other"):
        """A line outside the price list (kind 'other' unless given)."""
        record = self._get_record(record_id)
        if not (name or "").strip():
            raise UserError(_("Zadejte název položky."))
        if kind not in dict(KINDS):
            kind = "other"
        self.env["elite.vet.clinical.record.line"].create({
            "record_id": record.id, "name": name.strip(), "kind": kind,
            "quantity": to_number(quantity, float) or 1.0, "price_unit": to_number(price_unit, float),
            "sequence": max(record.line_ids.mapped("sequence") or [0]) + 1,
        })
        return record._record_data()

    @api.model
    def add_bundle(self, record_id, bundle_id):
        record = self._get_record(record_id)
        bundle = self.env["elite.vet.procedure.bundle"].browse(int(bundle_id)).exists()
        if not bundle:
            raise UserError(_("Balíček nebyl nalezen."))
        for bline in bundle.line_ids:
            self._add_quantity(record, bline.item_id, bline.quantity or 1.0, bundle=bundle,
                               name=bline.name, unit=bline.unit)
        return record._record_data()

    @api.model
    def _get_line(self, line_id):
        line = self.env["elite.vet.clinical.record.line"].browse(int(line_id)).exists()
        if not line:
            raise UserError(_("Položka účtu nebyla nalezena."))
        self._get_record(line.record_id.id)
        return line

    @api.model
    def update_line(self, line_id, vals):
        line = self._get_line(line_id)
        clean = {}
        for name, value in (vals or {}).items():
            if name not in LINE_FIELDS:
                continue
            if name in ("quantity", "price_unit"):
                clean[name] = to_number(value, float)
            elif name == "sequence":
                clean[name] = int(to_number(value, int))
            elif name == "kind":
                if value not in dict(KINDS):
                    raise UserError(_("Neznámý druh položky."))
                clean[name] = value
            elif name == "name":
                if not (value or "").strip():
                    raise UserError(_("Zadejte název položky."))
                clean[name] = value.strip()
            else:
                clean[name] = value or False
        if clean:
            line.write(clean)
        return line.record_id._record_data()

    @api.model
    def remove_line(self, line_id):
        line = self._get_line(line_id)
        record = line.record_id
        line.unlink()
        return record._record_data()

    @api.model
    def apply_template(self, record_id, template_id, position=None):
        """Task 32: insert the whole template text into the record text at `position` (the cursor,
        in characters), or append it after a blank line without a cursor – never replaces (see
        insert_template_text). Returns {text, caret}; caret = the position after the inserted text.
        Save what is being typed first (save_record), the template goes into the saved text."""
        record = self._get_record(record_id)
        template = self.env["elite.vet.text.template"].browse(int(template_id)).exists()
        if not template:
            raise UserError(_("Šablona nebyla nalezena."))
        if isinstance(position, bool) or not isinstance(position, (int, float)):
            position = None
        text, caret = insert_template_text(record.record_text or "", template.body, position)
        if text != (record.record_text or ""):
            record.write({"record_text": text})
        return {"text": text, "caret": caret}

    @api.model
    def mark_done(self, record_id):
        record = self._get_record(record_id)
        record.action_done()
        return record._record_data()

    @api.model
    def save_room_note(self, record_id, note):
        """Internal note of the room for the reception (Poznámka pro recepci). Unlike the other
        writes it may change after "Hotovo, k pokladně" too (not on a cancelled record)."""
        record = self._get_record(record_id, editable=False)
        self._check_can_write()
        if record.state == "cancelled":
            raise UserError(_("Zrušený záznam nelze měnit."))
        note = (note or "").strip() or False
        if record.room_note != note:
            record.room_note = note
        return record._record_data()

    @api.model
    def reopen_record(self, record_id):
        """Back to draft (a finished record was closed by mistake). Doctors only."""
        record = self._get_record(record_id, editable=False)
        if not self.env.user.has_group("elite_vet_clinic.group_clinic_doctor"):
            raise AccessError(_("Uzavřený záznam může znovu otevřít jen lékařka."))
        if record.state == "done":
            record.action_reopen()
        return record._record_data()
