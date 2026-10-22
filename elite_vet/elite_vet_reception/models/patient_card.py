"""Staged "Moji pacienti dnes" of the patient card (elite_vet_clinic): every item gets its
visit stage and a group of the start screen; walk-ins (today's records with a visit stage and
no reservation) are listed as well. Shapes are documented in README.md."""
from odoo import api, fields, models

from odoo.addons.elite_vet_clinic.models.patient_card import clinic_today, local_time


def item_group(record, reservation_state=None):
    """Group of the start screen: waiting / in_room / arriving / done."""
    if record and record.state == "done":
        return "done"
    if record and record.state == "draft" and record.visit_stage:
        return record.visit_stage
    if not record and reservation_state == "done":
        return "done"   # the visit took place (e.g. recorded in WinVet)
    return "arriving"


class ClinicalRecordPatientList(models.Model):
    _inherit = "elite.vet.clinical.record"

    def _record_data(self):
        data = super()._record_data()
        data["visit_stage"] = self.visit_stage or False
        return data

    def _stage_info(self, now):
        """Stage fields of a list item (self: one record or empty)."""
        rec = self
        since = rec.arrived_at
        until = rec.called_at if rec.visit_stage == "in_room" and rec.called_at else now
        return {
            "visit_stage": rec.visit_stage or False,
            "arrived_time": local_time(since) if since else None,
            "called_time": local_time(rec.called_at) if rec.called_at else None,
            "waiting_minutes": max(0, int((until - since).total_seconds() // 60)) if since else None,
            "payment_state": rec.payment_state if rec else None,
        }

    @api.model
    def my_patients_today(self):
        data = super().my_patients_today()
        now = fields.Datetime.now()
        record_ids = [i["record_id"] for i in data["items"] if i.get("record_id")]
        records = {r.id: r for r in self.browse(record_ids)}
        for item in data["items"]:
            rec = records.get(item.get("record_id")) or self.browse()
            if rec.state == "cancelled":
                rec = self.browse()
            item.update(rec._stage_info(now))
            item.update({"key": "r%s" % item["reservation_id"], "walk_in": False,
                         "group": item_group(rec, item.get("state"))})

        domain = [("date", "=", clinic_today()), ("state", "!=", "cancelled"),
                  ("visit_stage", "!=", False), ("reservation_id", "=", False)]
        if data.get("filtered_by_doctor"):
            domain.append(("doctor_id", "=", data["doctor"]["id"]))
        walk_ins = self.search(domain).sorted(lambda r: (r.arrived_at or r.start, r.id))
        for rec in walk_ins:
            pet = rec.pet_id
            partner = rec.partner_id
            when = rec.arrived_at or rec.start
            item = {
                "key": "w%s" % rec.id, "walk_in": True, "reservation_id": None,
                "start": when.strftime("%Y-%m-%d %H:%M:%S") if when else None,
                "time": local_time(when) if when else None, "time_end": None,
                "room": None, "room_color": None, "doctor": rec.doctor_id.name or None,
                "pet_id": pet.id, "pet_name": pet.name, "species_label": self._species_label(pet),
                "owner": partner.name or None, "partner_id": partner.id or None,
                "phone": partner.mobile or partner.phone or None,
                "procedure": None, "problem": None, "state": None, "state_label": "Bez objednání",
                "record_id": rec.id, "record_state": rec.state, "alerts": pet.alert_summary or None,
                "group": item_group(rec),
            }
            item.update(rec._stage_info(now))
            data["items"].append(item)
        data["items"].sort(key=lambda i: i["start"] or "")
        return data
