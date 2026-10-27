"""Printable visit report for the owner ("Zpráva z vyšetření", task 27).

The QWeb template (report/visit_report.xml) prints only what `_visit_report_data` returns: the
medical texts, vitals and the performed items without prices. Internal fields (reception_note,
room_note), pet alerts, prices, tracking and WinVet notes are never put into the data.

Task 28: the same report for a visit imported from WinVet (`elite.vet.visit`, read-only). Its
`_visit_report_data` returns the same shape from what the visit has: date and time, the doctor
(only when the WinVet user is linked to a doctor), the clinical text ("Dekurz", DENNI_ZAZNAM.DEKURS),
the diagnosis / case, the vitals and the WinVet sale lines of the visit without prices. The pet's
WinVet "Poznámka" (winvet_note) is internal and never printed.
"""
import re
import unicodedata

from odoo import api, fields, models

from .clinical_record import TZ
from .patient_card import clinic_today, czech_plural, short_time

REPORT_NAME = "elite_vet_clinic.report_visit"
WINVET_REPORT_NAME = "elite_vet_clinic.report_winvet_visit"
# WinVet sale lines that are money, not care (e.g. "Převod nedoplatku z …", unit "měna").
MONEY_UNITS = ("měna",)


def czech_date(value):
    return value.strftime("%-d. %-m. %Y") if value else ""


def text_blocks(text):
    """Record text -> blocks for printing: {"text": ...} paragraphs and {"rows": [[cell, ...]]} tables.
    A table is a run of lines with tab separated cells (WinVet lab results, see winvet_bridge.rvf;
    a full width title row arrives as an ordinary line above it). The first row of a table is its
    header when none of its cells holds a digit."""
    blocks = []
    for line in (text or "").split("\n"):
        if "\t" in line:
            if not blocks or "rows" not in blocks[-1]:
                blocks.append({"rows": [], "cols": 0, "header": False})
            blocks[-1]["rows"].append(line.split("\t"))
        elif blocks and "text" in blocks[-1]:
            blocks[-1]["text"] += "\n" + line
        else:
            blocks.append({"text": line})
    for block in blocks:
        if "rows" in block:
            block["cols"] = max(len(row) for row in block["rows"])
            first = block["rows"][0]
            block["header"] = len(first) > 1 and not any(ch.isdigit() for cell in first for ch in cell)
        else:
            block["text"] = block["text"].strip("\n")
    return [b for b in blocks if b.get("rows") or b.get("text")]


def czech_number(value, digits):
    """12.50 -> '12,5'; 3.0 -> '3'."""
    return ("%.*f" % (digits, value)).rstrip("0").rstrip(".").replace(".", ",")


def age_long(birth_date, birth_year, on_day):
    """Age on the given day: '3 roky 2 měsíce', '1 rok', '5 měsíců', '2 týdny'; only the year
    known -> 'cca 7 let'."""
    if birth_date:
        months = (on_day.year - birth_date.year) * 12 + on_day.month - birth_date.month - (on_day.day < birth_date.day)
        if months < 0:
            return ""
        years, months = divmod(months, 12)
        parts = []
        if years:
            parts.append("%d %s" % (years, czech_plural(years, "rok", "roky", "let")))
        if months:
            parts.append("%d %s" % (months, czech_plural(months, "měsíc", "měsíce", "měsíců")))
        if parts:
            return " ".join(parts)
        days = (on_day - birth_date).days
        if days >= 7:
            weeks = days // 7
            return "%d %s" % (weeks, czech_plural(weeks, "týden", "týdny", "týdnů"))
        return "%d %s" % (days, czech_plural(days, "den", "dny", "dní"))
    if birth_year and 1900 <= birth_year <= on_day.year:
        years = on_day.year - birth_year
        return "cca %d %s" % (years, czech_plural(years, "rok", "roky", "let")) if years else "méně než rok"
    return ""


def file_part(text):
    """'Ťapka Malá' -> 'Tapka_Mala' (safe in a file name)."""
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")


class ClinicalRecordVisitReport(models.Model):
    _inherit = "elite.vet.clinical.record"

    # ------------------------------------------------------------------ helpers

    def _visit_report_has_content(self):
        """Something to print: the record text, a vital value or a bill line."""
        self.ensure_one()
        return bool((self.record_text or "").strip() or self.temperature or self.weight
                    or self.heart_rate or self.respiratory_rate or self.line_ids)

    def _visit_report_filename(self):
        """Zprava_<pet>_<date> (print_report_name of the report; .pdf is added by Odoo)."""
        self.ensure_one()
        parts = ["Zprava", file_part(self.pet_id.name), self.date.isoformat() if self.date else ""]
        return "_".join(p for p in parts if p)

    @api.model
    def _visit_report_clinic(self):
        """Clinic header: the company first, the website contact settings (elite_vet_web) fill
        what the company lacks. Read only."""
        company = self.env.company.sudo()
        setting = self.env["elite.vet.setting"].sudo().search([], limit=1)
        address = [line for line in (
            company.street, company.street2, " ".join(p for p in (company.zip, company.city) if p)) if line]
        if not address and setting:
            address = [line for line in (setting.address_line1, setting.address_line2) if line]
        place = company.city
        if not place and setting.address_line2:
            # "360 05 Karlovy Vary" -> "Karlovy Vary"
            place = re.sub(r"^[\d\s]+", "", setting.address_line2).strip()
        website = company.website or ""
        return {
            "name": company.name,
            "address": address,
            "ico": company.company_registry or "",
            "dic": company.vat or "",
            "phone": company.phone or setting.phone_display or setting.phone or "",
            "email": company.email or setting.email or "",
            "website": re.sub(r"^https?://", "", website).rstrip("/"),
            "logo": company.logo if company.logo and not company.uses_default_logo else False,
            "place": place or "",
        }

    def _visit_report_patient(self):
        """Filled facts of the pet as (label, value) pairs."""
        return self._visit_report_patient_facts(self.pet_id, self.date or clinic_today())

    @api.model
    def _visit_report_patient_facts(self, pet, on_day):
        if pet.birth_date:
            age = age_long(pet.birth_date, 0, on_day)
            born = czech_date(pet.birth_date) + (" (%s)" % age if age else "")
        elif pet.birth_year:
            age = age_long(False, pet.birth_year, on_day)
            born = "rok %d" % pet.birth_year + (" (%s)" % age if age else "")
        else:
            born = ""
        facts = [
            ("Jméno", pet.name),
            ("Druh", self._species_label(pet) or ""),
            ("Plemeno", pet.breed),
            ("Pohlaví", pet.sex),
            ("Narozen(a)", born),
            ("Barva", pet.color),
            ("Čip", pet.chip),
            ("Tetování", pet.tattoo),
            ("Číslo pasu", pet.passport),
        ]
        return [(label, value) for label, value in facts if value]

    def _visit_report_owner(self):
        return self._visit_report_owner_of(self.pet_id)

    @api.model
    def _visit_report_owner_of(self, pet):
        partner = pet.partner_id.sudo()
        address = ", ".join(p for p in (
            partner.street, partner.street2, " ".join(p for p in (partner.zip, partner.city) if p)) if p)
        phones = []
        for phone in (partner.mobile, partner.phone):
            if phone and phone not in phones:
                phones.append(phone)
        return {"name": partner.name or "", "address": address, "phone": ", ".join(phones)}

    def _visit_report_doctor(self):
        return self._visit_report_doctor_of(self.doctor_id)

    @api.model
    def _visit_report_doctor_of(self, doctor):
        doctor = doctor.sudo()
        if not doctor:
            return {}
        # "Jméno a titul" of the team card when linked (it may carry more titles).
        name = doctor.member_id.name or doctor.name
        return {"name": name, "kvl": doctor.kvl_number or ""}

    def _visit_report_vitals(self):
        parts = []
        if self.temperature:
            parts.append("teplota %s °C" % czech_number(self.temperature, 1))
        if self.weight:
            parts.append("hmotnost %s kg" % czech_number(self.weight, 2))
        if self.heart_rate:
            parts.append("tep %d/min" % self.heart_rate)
        if self.respiratory_rate:
            parts.append("dech %d/min" % self.respiratory_rate)
        return parts

    def _visit_report_lots(self):
        """{bill line id: [(lot name, expiry date or False)]} – lots of the medicines given, when
        known. elite_vet_sale reads them from the stock moves of the paid bill."""
        return {}

    def _visit_report_lines(self):
        lots = self._visit_report_lots()
        lines = []
        for line in self.line_ids.sorted(lambda l: (l.sequence, l.id)):
            quantity = czech_number(line.quantity, 3)
            line_lots = lots.get(line.id) or []
            lines.append({
                "name": line.name,
                "quantity": " ".join(p for p in (quantity, line.unit or "") if p),
                "lots": ", ".join(name for name, _expiry in line_lots),
                "expiry": ", ".join(czech_date(expiry) for _name, expiry in line_lots if expiry),
            })
        return lines

    def _visit_report_data(self):
        """Everything the report prints – and nothing else (see the module docstring)."""
        self.ensure_one()
        rec = self
        start = rec.start and fields.Datetime.context_timestamp(rec.with_context(tz=TZ.zone), rec.start)
        pet = rec.pet_id
        lines = rec._visit_report_lines()
        vitals = rec._visit_report_vitals()
        return {
            "clinic": rec._visit_report_clinic(),
            "patient": rec._visit_report_patient(),
            "owner": rec._visit_report_owner(),
            "doctor": rec._visit_report_doctor(),
            "visit_date": czech_date(rec.date),
            "visit_time": start.strftime("%H:%M") if start else "",
            # task 32: one section "Záznam z vyšetření" – the vitals line and the record text
            # (the deprecated anamnesis / examination / diagnosis are never printed)
            "vitals_rows": [" · ".join(vitals)] if vitals else [],
            "record_text": (rec.record_text or "").strip(),
            "record_blocks": text_blocks((rec.record_text or "").strip()),
            "case": "",
            "diagnosis": "",
            "lines": lines,
            "has_lots": any(line["lots"] or line["expiry"] for line in lines),
            "next_vaccination": czech_date(pet.next_vaccination),
            "next_deworming": czech_date(pet.next_deworming),
            "printed": czech_date(clinic_today()),
        }


class WinvetVisitReport(models.Model):
    """Task 28: "Zpráva z vyšetření" for a visit imported from WinVet – the same template and
    data shape as the clinical record (see the module docstring)."""
    _inherit = "elite.vet.visit"

    def _visit_report_vitals(self):
        """One line per WinVet measurement: '16:52 · teplota 38,6 °C · hmotnost 4,2 kg · TK 120/80'."""
        rows = []
        for vital in self.vital_ids:
            parts = []
            if vital.temperature:
                parts.append("teplota %s °C" % czech_number(vital.temperature, 1))
            if vital.weight:
                parts.append("hmotnost %s kg" % czech_number(vital.weight, 2))
            if vital.heart_rate:
                parts.append("tep %d/min" % vital.heart_rate)
            if vital.respiratory_rate:
                parts.append("dech %d/min" % vital.respiratory_rate)
            if vital.bp_systolic or vital.bp_diastolic:
                parts.append("TK %s/%s" % (vital.bp_systolic or "–", vital.bp_diastolic or "–"))
            if parts:
                if len(self.vital_ids) > 1 and vital.time:
                    parts.insert(0, short_time(vital.time))
                rows.append(" · ".join(parts))
        return rows

    def _visit_report_lines(self):
        """The WinVet sale lines of the visit (read with sudo: the lines and prices are for the
        managers only) – the name and quantity, never a price or amount."""
        lines = []
        for line in self.sudo().line_ids.sorted(lambda l: l.id):
            if (line.unit or "").strip().lower() in MONEY_UNITS or not (line.item_name or "").strip():
                continue
            quantity = czech_number(line.quantity, 3)
            lines.append({
                "name": line.item_name.strip(),
                "quantity": " ".join(p for p in (quantity, line.unit or "") if p),
                "lots": "", "expiry": "",
            })
        return lines

    def _visit_report_has_content(self):
        """Something to print: the clinical text, a diagnosis, a vital value or a line."""
        self.ensure_one()
        return bool((self.notes or "").strip() or (self.diagnosis_name or "").strip()
                    or (self.case_name or "").strip() or self._visit_report_vitals() or self._visit_report_lines())

    def _visit_report_filename(self):
        self.ensure_one()
        parts = ["Zprava", file_part(self.pet_id.name), self.date.isoformat() if self.date else ""]
        return "_".join(p for p in parts if p)

    def _visit_report_data(self):
        """The record's data shape (see ClinicalRecordVisitReport._visit_report_data). The doctor is
        printed only when the WinVet user who entered the visit is linked to a doctor."""
        self.ensure_one()
        Record = self.env["elite.vet.clinical.record"]
        visit = self.sudo()
        pet = self.pet_id
        lines = self._visit_report_lines()
        diagnosis = (visit.diagnosis_name or "").strip()
        case = (visit.case_name or "").strip()
        if not diagnosis:
            diagnosis, case = case, ""
        elif case.lower() == diagnosis.lower():
            case = ""
        notes = (visit.notes or "").strip()
        return {
            "clinic": Record._visit_report_clinic(),
            "patient": Record._visit_report_patient_facts(pet, visit.date or clinic_today()),
            "owner": Record._visit_report_owner_of(pet),
            "doctor": Record._visit_report_doctor_of(visit.doctor_id),
            "visit_date": czech_date(visit.date),
            "visit_time": short_time(visit.time) or "",
            "vitals_rows": self._visit_report_vitals(),
            "record_text": notes,
            "record_blocks": text_blocks(notes),
            "case": case,
            "diagnosis": diagnosis,
            "lines": lines,
            "has_lots": False,
            "next_vaccination": czech_date(pet.next_vaccination),
            "next_deworming": czech_date(pet.next_deworming),
            "printed": czech_date(clinic_today()),
        }
