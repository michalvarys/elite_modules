"""Card index of the reception (Kartotéka dialog in the POS): find, show, create and edit owners
and pets, and link a web reservation to them.

Owners and pets are written with the caller's own rights (reception has create/write on
res.partner and elite.vet.pet); sudo is used only for the clinic-derived data (bills).
"""
import math
import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.osv import expression

from odoo.addons.elite_vet_clinic.models.patient_card import clinic_today, date_str, local_time
from odoo.addons.elite_vet_clinic.models.pet_alert import ALERT_KINDS
from odoo.addons.elite_vet_reservation.models.pet import SPECIES, normalize_phone

OWNER_FIELDS = ("name", "phone", "mobile", "email", "street", "city", "zip")
# Task 22: every pet field reception can fill (none required except name and species).
# `deceased` (bool) and `alerts` (list) are handled apart from these text values.
PET_FIELDS = ("name", "species", "species_other", "breed", "sex", "birth_date", "birth_year", "chip",
              "tattoo", "passport", "color", "weight", "next_vaccination", "next_deworming",
              "important_note", "note", "death_date")
PET_DATE_FIELDS = {
    "birth_date": "datum narození", "next_vaccination": "datum příští vakcinace",
    "next_deworming": "datum příštího odčervení", "death_date": "datum úhynu",
}
MIN_BIRTH_YEAR = 1950
SEARCH_LIMIT = 20
BOOKING_SEARCH_LIMIT = 20


def _clean(vals, allowed):
    """Only the allowed keys, values as stripped strings; empty values -> False."""
    if vals is None:
        vals = {}
    if not isinstance(vals, dict):
        raise UserError(_("Neplatná data formuláře."))
    clean = {}
    for key in allowed:
        if key not in vals:
            continue
        value = vals[key]
        if value is None or value is False:
            value = ""
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            value = str(value)
        elif not isinstance(value, str):
            raise UserError(_("Neplatná hodnota pole %s.") % key)
        clean[key] = value.strip() or False
    return clean


class ReceptionCardIndex(models.AbstractModel):
    _inherit = "elite.vet.reception"

    # ------------------------------------------------------------------ helpers

    @api.model
    def _get_owner(self, partner_id):
        partner = self.env["res.partner"].browse(self._to_id(partner_id)).exists()
        if not partner:
            raise UserError(_("Majitel nebyl nalezen."))
        if self._not_clients(partner):
            raise UserError(_("Tento kontakt není klient kliniky."))
        return partner

    @api.model
    def _not_clients(self, partners):
        """Staff (a user, also archived) and company partners: never an owner of the card index."""
        companies = self.env["res.company"].sudo().search([]).partner_id
        return partners.sudo().with_context(active_test=False).filtered(
            lambda p: p.user_ids or p in companies)

    @api.model
    def _to_id(self, value):
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            raise UserError(_("Neplatné ID: %s") % value) from None

    @api.model
    def _get_owner_pet(self, partner, pet_id):
        pet = self.env["elite.vet.pet"].browse(self._to_id(pet_id)).exists()
        if not pet:
            raise UserError(_("Zvíře nebylo nalezeno."))
        if pet.partner_id != partner:
            raise UserError(_("Zvíře %(pet)s nepatří majiteli %(owner)s.", pet=pet.name, owner=partner.name))
        return pet

    @api.model
    def _owner_ids_by_phone(self, digits):
        Partner = self.env["res.partner"]
        Partner.flush_model(["phone", "mobile"])
        self.env.cr.execute(
            "SELECT id FROM res_partner WHERE regexp_replace(coalesce(phone, ''), '\\D', '', 'g') LIKE %s"
            " OR regexp_replace(coalesce(mobile, ''), '\\D', '', 'g') LIKE %s", ["%" + digits + "%"] * 2)
        return [r[0] for r in self.env.cr.fetchall()]

    @api.model
    def _search_owners(self, term, exclude_ids, limit):
        domain = ["|", ("name", "ilike", term), ("email", "ilike", term)]
        digits = normalize_phone(term)
        # same rule as search_patients: the term is a number (digits and phone separators only)
        if len(digits) >= 4 and len(digits) >= len(re.sub(r"[\s+\-/().]", "", term)):
            domain = expression.OR([domain, [("id", "in", self._owner_ids_by_phone(digits))]])
        domain = expression.AND([domain, [("is_vet_client", "=", True), ("id", "not in", list(exclude_ids))]])
        owners = self.env["res.partner"].search(domain, limit=limit, order="name, id")
        return [{
            "kind": "owner", "id": p.id, "partner_id": p.id, "name": p.name, "owner": p.name,
            "phone": p.mobile or p.phone or None, "email": p.email or None, "pet_count": len(p.pet_ids),
        } for p in owners]

    @api.model
    def _pet_dict(self, pet):
        kinds = dict(ALERT_KINDS)
        return {
            "id": pet.id, "name": pet.name, "species": pet.species or None,
            "species_other": pet.species_other or None,
            "species_label": self.env["elite.vet.clinical.record"]._species_label(pet),
            "breed": pet.breed or None, "sex": pet.sex or None, "birth_date": date_str(pet.birth_date),
            "birth_year": pet.birth_year or None, "chip": pet.chip or None, "tattoo": pet.tattoo or None,
            "passport": pet.passport or None, "color": pet.color or None, "weight": pet.weight or None,
            "note": pet.note or None, "important_note": pet.important_note or None,
            "alerts": pet.alert_summary or None,
            "alert_list": [{"id": a.id, "kind": a.kind, "kind_label": kinds.get(a.kind), "note": a.note or None}
                           for a in pet.alert_ids.filtered("active")],
            "next_vaccination": date_str(pet.next_vaccination), "next_deworming": date_str(pet.next_deworming),
            "deceased": pet.deceased, "death_date": date_str(pet.death_date),
            # request 25. 10.: Nedorazil of the last 12 months (computed from reservations)
            "no_show_count": pet.sudo().no_show_count,
        }

    @api.model
    def _parse_date(self, value, label="datum narození"):
        if not value:
            return False
        try:
            return fields.Date.to_date(value)
        except (TypeError, ValueError):
            raise UserError(_("Neplatné %(label)s: %(value)s (zadejte RRRR-MM-DD).", label=label, value=value)) from None

    @api.model
    def _parse_weight(self, value):
        """'12,5' / '12.5' -> 12.5 kg; empty -> 0 (no weight)."""
        if not value:
            return 0.0
        try:
            weight = float(value.replace(" ", "").replace(",", "."))
        except ValueError:
            raise UserError(_("Hmotnost „%s“ není číslo (např. 12,5).") % value) from None
        if not math.isfinite(weight) or weight < 0:
            raise UserError(_("Hmotnost nesmí být záporná."))
        return weight

    @api.model
    def _parse_birth_year(self, value):
        if not value:
            return 0
        try:
            year = int(value)
        except ValueError:
            raise UserError(_("Rok narození „%s“ není rok (např. 2019).") % value) from None
        if not MIN_BIRTH_YEAR <= year <= clinic_today().year:
            raise UserError(_("Rok narození musí být mezi %(min)s a %(max)s.",
                              min=MIN_BIRTH_YEAR, max=clinic_today().year))
        return year

    @api.model
    def _pet_vals(self, vals):
        """Form values of save_pet -> elite.vet.pet values (text cleaned, dates, numbers parsed)."""
        raw = vals if isinstance(vals, dict) else None
        clean = _clean(vals, PET_FIELDS)
        for key, label in PET_DATE_FIELDS.items():
            if key in clean:
                clean[key] = self._parse_date(clean[key], label)
        if "weight" in clean:
            clean["weight"] = self._parse_weight(clean["weight"])
        if "birth_year" in clean:
            clean["birth_year"] = self._parse_birth_year(clean["birth_year"])
        if "species" in clean and clean["species"] and clean["species"] not in dict(SPECIES):
            raise UserError(_("Neznámý druh zvířete: %s") % clean["species"])
        if raw and "deceased" in raw:
            if not isinstance(raw["deceased"], bool):
                raise UserError(_("Neplatná hodnota pole %s.") % "deceased")
            clean["deceased"] = raw["deceased"]
        return clean

    @api.model
    def _check_pet_dates(self, pet):
        today = clinic_today()
        if pet.birth_date and pet.birth_date > today:
            raise UserError(_("Datum narození nesmí být v budoucnosti."))
        if pet.death_date and pet.death_date > today:
            raise UserError(_("Datum úhynu nesmí být v budoucnosti."))
        if pet.death_date and pet.birth_date and pet.death_date < pet.birth_date:
            raise UserError(_("Datum úhynu nesmí být před datem narození."))

    @api.model
    def _alert_items(self, alerts):
        """List of {id?, kind, note} from the form -> [(id or False, kind, note)]."""
        if not isinstance(alerts, list):
            raise UserError(_("Neplatná upozornění."))
        kinds = dict(ALERT_KINDS)
        items = []
        for alert in alerts:
            if not isinstance(alert, dict):
                raise UserError(_("Neplatná upozornění."))
            kind = alert.get("kind") or "other"
            if kind not in kinds:
                raise UserError(_("Neznámý druh upozornění: %s") % kind)
            note = alert.get("note") or ""
            if not isinstance(note, str):
                raise UserError(_("Neplatná poznámka upozornění."))
            items.append((self._to_id(alert.get("id")) or False, kind, note.strip() or False))
        return items

    @api.model
    def _save_alerts(self, pet, items):
        """Active alerts of the pet become exactly `items`: listed ones are updated, new ones
        created, unlisted ones archived (as the patient card does - nurse has no unlink).

        Reception may only read elite.vet.pet.alert (ACL of elite_vet_clinic), so this checked
        API writes them under sudo, limited to the alerts of this one pet."""
        Alert = self.env["elite.vet.pet.alert"].sudo()
        current = pet.sudo().alert_ids.filtered("active")
        kept = Alert.browse()
        for alert_id, kind, note in items:
            if alert_id:
                alert = current.filtered(lambda a, i=alert_id: a.id == i)
                if not alert:
                    raise UserError(_("Upozornění nepatří zvířeti %s.") % pet.name)
                if (alert.kind, alert.note or False) != (kind, note):
                    alert.write({"kind": kind, "note": note})
                kept |= alert
            else:
                kept |= Alert.create({"pet_id": pet.id, "kind": kind, "note": note})
        (current - kept).write({"active": False})

    # ------------------------------------------------------------------ read API

    @api.model
    def card_search(self, term):
        """Card index search: pets (clinic `search_patients`: name, owner, chip, phone digits)
        plus owners matching name / phone / e-mail that no listed pet shows already
        (e.g. owners without pets)."""
        self._check_reception()
        if not isinstance(term, str):
            raise UserError(_("Zadejte hledaný text."))
        term = term.strip()
        if len(term) < 2:
            return []
        pets = self.env["elite.vet.clinical.record"].search_patients(term, limit=SEARCH_LIMIT)
        results = [dict(p, kind="pet") for p in pets]
        shown = {p["partner_id"] for p in pets}
        return results + self._search_owners(term, shown, SEARCH_LIMIT)

    @api.model
    def booking_search(self, term):
        """Inline client search of Objednat (step 1): the card index search as rows to pick from.

        One row per live pet (`kind` "pet"); an owner found by name / phone / e-mail gets a row
        per live pet (each pet once), and an owner without a live pet one row of `kind` "owner"
        (the dialog adds a pet). Same owner rules as booking:
        no staff and company partners, no deceased pets.
        """
        results = self.card_search(term)
        Pet = self.env["elite.vet.pet"]
        Record = self.env["elite.vet.clinical.record"]
        blocked = set(self._not_clients(self.env["res.partner"].browse({r["partner_id"] for r in results})).ids)
        rows, seen = [], set()

        def pet_row(pet_id, name, species_label, owner, partner_id, phone):
            seen.add(pet_id)
            return {"kind": "pet", "id": pet_id, "name": name, "species_label": species_label or None,
                    "owner": owner, "partner_id": partner_id, "phone": phone or None}

        owners_done = set()
        for result in results:
            partner_id = result["partner_id"]
            if partner_id in blocked:
                continue
            if result["kind"] == "pet" and not result["deceased"]:
                if result["id"] not in seen:
                    rows.append(pet_row(result["id"], result["name"], result["species_label"], result["owner"],
                                        partner_id, result["phone"]))
                continue
            if partner_id in owners_done:
                continue
            owners_done.add(partner_id)
            live = Pet.search([("partner_id", "=", partner_id), ("deceased", "=", False)], order="name, id")
            if result["kind"] == "owner":
                for pet in live.filtered(lambda p: p.id not in seen):
                    rows.append(pet_row(pet.id, pet.name, Record._species_label(pet), result["owner"],
                                        partner_id, result["phone"]))
            if not live:
                # no live pet (none at all, or only a deceased one matched): the dialog adds one
                rows.append({"kind": "owner", "id": partner_id, "partner_id": partner_id,
                             "owner": result["owner"], "phone": result["phone"]})
        return rows[:BOOKING_SEARCH_LIMIT]

    @api.model
    def pet_options(self):
        """Choices for the pet form of the card index dialog."""
        self._check_reception()
        return {
            "species": [{"value": key, "label": label} for key, label in SPECIES],
            # the alert kinds of the patient card (elite.vet.pet.alert)
            "alert_kinds": [{"value": key, "label": label} for key, label in ALERT_KINDS],
        }

    @api.model
    def owner_data(self, partner_id):
        self._check_reception()
        partner = self._get_owner(partner_id)
        pets = self.env["elite.vet.pet"].search([("partner_id", "=", partner.id)], order="deceased, name, id")
        return {
            "owner": {
                "id": partner.id, "name": partner.name, "phone": partner.phone or None,
                "mobile": partner.mobile or None, "email": partner.email or None,
                "street": partner.street or None, "city": partner.city or None, "zip": partner.zip or None,
            },
            "pets": [self._pet_dict(pet) for pet in pets],
            "open_bills": self._to_pay(partner=partner),
            "no_shows": self.env["elite.vet.reservation"].no_show_summary(partner=partner),
        }

    @api.model
    def client_no_shows(self, partner_id):
        """Nedorazil of the client (last 12 months) for the warning in Objednat:
        {count, last_date, last_label, text, items}."""
        self._check_reception()
        return self.env["elite.vet.reservation"].no_show_summary(partner=self._get_owner(partner_id))

    # ------------------------------------------------------------------ write API

    @api.model
    def save_owner(self, vals, partner_id=None, pet_vals=None):
        """Create (no partner_id) or edit an owner. Same phone / e-mail as another owner is
        allowed: nothing is merged.

        Task 31: a new owner can come with their first pet (`pet_vals`, the values of save_pet:
        every pet field and the alerts, never deceased). Both are created in one go: when the
        pet fails validation, the owner is not created either. The result then has `new_pet_id`."""
        self._check_reception()
        vals = _clean(vals, OWNER_FIELDS)
        if pet_vals is not None and (partner_id or not isinstance(pet_vals, dict)):
            raise UserError(_("Zvíře jde se zakládaným klientem jen u nového klienta."))
        if partner_id:
            partner = self._get_owner(partner_id)
            if "name" in vals and not vals["name"]:
                raise UserError(_("Vyplňte jméno majitele."))
            if vals:
                partner.write(vals)
            return self.owner_data(partner.id)
        if not vals.get("name"):
            raise UserError(_("Vyplňte jméno majitele."))
        if pet_vals is None:
            partner = self.env["res.partner"].create(dict(vals, is_vet_client=True))
            return self.owner_data(partner.id)
        # owner and pet together: a savepoint, so a refused pet leaves no owner behind even when
        # the caller's transaction goes on (the RPC itself would roll back as a whole as well)
        with self.env.cr.savepoint():
            partner = self.env["res.partner"].create(dict(vals, is_vet_client=True))
            data = self.save_pet(partner.id, pet_vals)
        new = [p["id"] for p in data["pets"]]
        data["new_pet_id"] = new[0] if new else None
        return data

    @api.model
    def save_pet(self, partner_id, vals, pet_id=None):
        """Create (no pet_id) or edit a pet of the owner.

        Keys of PET_FIELDS (text; dates RRRR-MM-DD; weight with a decimal comma; empty = none),
        `deceased` (bool, only when editing) and `alerts` ([{id?, kind, note}], the full list of
        active alerts). Only name and species are required."""
        self._check_reception()
        partner = self._get_owner(partner_id)
        alerts = vals.get("alerts") if isinstance(vals, dict) else None
        items = self._alert_items(alerts) if alerts is not None else None
        vals = self._pet_vals(vals)
        if pet_id:
            pet = self._get_owner_pet(partner, pet_id)
            if "name" in vals and not vals["name"]:
                raise UserError(_("Vyplňte jméno zvířete."))
            if "species" in vals and not vals["species"]:
                raise UserError(_("Vyberte druh zvířete."))
        else:
            pet = None
            if not vals.get("name"):
                raise UserError(_("Vyplňte jméno zvířete."))
            if not vals.get("species"):
                raise UserError(_("Vyberte druh zvířete."))
            if vals.get("deceased") or vals.get("death_date"):
                raise UserError(_("Nové zvíře nejde založit jako uhynulé."))
            vals.pop("deceased", None)
        species = vals.get("species") or (pet.species if pet else False)
        if species != "other" and ("species" in vals or "species_other" in vals):
            vals["species_other"] = False  # Jiný druh only with Druh = Jiné
        deceased = vals.get("deceased", pet.deceased if pet else False)
        if not deceased and ("deceased" in vals or vals.get("death_date")):
            vals["death_date"] = False  # Datum úhynu only for a deceased pet
        if pet:
            if vals:
                pet.write(vals)
        else:
            pet = self.env["elite.vet.pet"].create(dict(vals, partner_id=partner.id))
        if {"birth_date", "death_date", "deceased"} & set(vals):
            self._check_pet_dates(pet)  # only what this save changes (WinVet data may be odd)
        if items is not None:
            self._save_alerts(pet, items)
        return self.owner_data(partner.id)

    @api.model
    def match_reservation(self, reservation_id, partner_id, pet_id):
        """Link a (web) reservation to an owner and a pet from the card index; its second-room
        copy gets the same client. The board is notified by the reservation write."""
        self._check_reception()
        reservation = self.env["elite.vet.reservation"].browse(self._to_id(reservation_id)).exists()
        if not reservation or reservation.kind != "reservation":
            raise UserError(_("Rezervace nebyla nalezena."))
        if reservation.is_second_room and reservation.linked_reservation_id:
            reservation = reservation.linked_reservation_id  # the client belongs to the main reservation
        if reservation.state in ("cancelled", "no_show"):
            raise UserError(_("Zrušenou rezervaci nelze spárovat."))
        if reservation.state == "done":
            raise UserError(_("Proběhlou rezervaci nelze změnit."))
        partner = self._get_owner(partner_id)
        pet = self._get_owner_pet(partner, pet_id)
        visit = self._records().search([("reservation_id", "=", reservation.id), ("state", "!=", "cancelled")],
                                       limit=1)
        if visit and visit.pet_id != pet:
            raise UserError(_("Rezervace už má návštěvu jiného zvířete."))
        vals = {"partner_id": partner.id, "pet_id": pet.id, "pet_name": pet.name, "pet_species": pet.species}
        if reservation.partner_id and reservation.partner_id != partner:
            # Another client: the contact follows the new partner like in the booking wizard, so the
            # reservation e-mails and the phone on the board do not stay with the previous client.
            vals.update({
                "contact_name": partner.name, "contact_phone": partner.phone or partner.mobile or False,
                "contact_email": partner.email or False, "lang": partner.lang or "cs_CZ",
            })
        reservation.write(vals)
        second = reservation.linked_reservation_id
        if second.is_second_room and second.linked_reservation_id == reservation:
            second.write(vals)
        return {
            "reservation_id": reservation.id, "time": local_time(reservation.start),
            "partner_id": partner.id, "owner": partner.name, "pet_id": pet.id, "pet_name": pet.name,
            "needs_match": False,
        }
