"""Card index of the reception (Kartotéka dialog in the POS): find, show, create and edit owners
and pets, and link a web reservation to them.

Owners and pets are written with the caller's own rights (reception has create/write on
res.partner and elite.vet.pet); sudo is used only for the clinic-derived data (bills).
"""
import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.osv import expression

from odoo.addons.elite_vet_clinic.models.patient_card import date_str, local_time
from odoo.addons.elite_vet_reservation.models.pet import SPECIES, normalize_phone

OWNER_FIELDS = ("name", "phone", "mobile", "email", "street", "city", "zip")
PET_FIELDS = ("name", "species", "breed", "sex", "birth_date", "chip", "note")
SEARCH_LIMIT = 20


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
        staff = partner.sudo().with_context(active_test=False)
        if staff.user_ids or staff in self.env["res.company"].sudo().search([]).partner_id:
            raise UserError(_("Tento kontakt není klient kliniky."))
        return partner

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
        return {
            "id": pet.id, "name": pet.name, "species": pet.species or None,
            "species_label": self.env["elite.vet.clinical.record"]._species_label(pet),
            "breed": pet.breed or None, "sex": pet.sex or None, "birth_date": date_str(pet.birth_date),
            "chip": pet.chip or None, "alerts": pet.alert_summary or None,
            "next_vaccination": date_str(pet.next_vaccination), "deceased": pet.deceased,
        }

    @api.model
    def _parse_date(self, value):
        if not value:
            return False
        try:
            return fields.Date.to_date(value)
        except (TypeError, ValueError):
            raise UserError(_("Neplatné datum narození: %s (zadejte RRRR-MM-DD).") % value) from None

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
    def pet_options(self):
        """Choices for the pet form of the card index dialog."""
        self._check_reception()
        return {"species": [{"value": key, "label": label} for key, label in SPECIES]}

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
        }

    # ------------------------------------------------------------------ write API

    @api.model
    def save_owner(self, vals, partner_id=None):
        """Create (no partner_id) or edit an owner. Same phone / e-mail as another owner is
        allowed: nothing is merged."""
        self._check_reception()
        vals = _clean(vals, OWNER_FIELDS)
        if partner_id:
            partner = self._get_owner(partner_id)
            if "name" in vals and not vals["name"]:
                raise UserError(_("Vyplňte jméno majitele."))
            if vals:
                partner.write(vals)
        else:
            if not vals.get("name"):
                raise UserError(_("Vyplňte jméno majitele."))
            partner = self.env["res.partner"].create(dict(vals, is_vet_client=True))
        return self.owner_data(partner.id)

    @api.model
    def save_pet(self, partner_id, vals, pet_id=None):
        """Create (no pet_id) or edit a pet of the owner."""
        self._check_reception()
        partner = self._get_owner(partner_id)
        vals = _clean(vals, PET_FIELDS)
        if "birth_date" in vals:
            vals["birth_date"] = self._parse_date(vals["birth_date"])
        if "species" in vals and vals["species"] and vals["species"] not in dict(SPECIES):
            raise UserError(_("Neznámý druh zvířete: %s") % vals["species"])
        if pet_id:
            pet = self._get_owner_pet(partner, pet_id)
            if "name" in vals and not vals["name"]:
                raise UserError(_("Vyplňte jméno zvířete."))
            if "species" in vals and not vals["species"]:
                raise UserError(_("Vyberte druh zvířete."))
            if vals:
                pet.write(vals)
        else:
            if not vals.get("name"):
                raise UserError(_("Vyplňte jméno zvířete."))
            if not vals.get("species"):
                raise UserError(_("Vyberte druh zvířete."))
            self.env["elite.vet.pet"].create(dict(vals, partner_id=partner.id))
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
        partner = self._get_owner(partner_id)
        pet = self._get_owner_pet(partner, pet_id)
        visit = self._records().search([("reservation_id", "=", reservation.id), ("state", "!=", "cancelled")],
                                       limit=1)
        if visit and visit.pet_id != pet:
            raise UserError(_("Rezervace už má návštěvu jiného zvířete."))
        vals = {"partner_id": partner.id, "pet_id": pet.id}
        reservation.write(vals)
        second = reservation.linked_reservation_id
        if second.is_second_room and second.linked_reservation_id == reservation:
            second.write(vals)
        return {
            "reservation_id": reservation.id, "time": local_time(reservation.start),
            "partner_id": partner.id, "owner": partner.name, "pet_id": pet.id, "pet_name": pet.name,
            "needs_match": False,
        }
