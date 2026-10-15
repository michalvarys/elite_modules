"""Buttons opening the patient card (client action) from pets, clients and reservations."""
from odoo import _, models
from odoo.exceptions import UserError


class VetPet(models.Model):
    _inherit = "elite.vet.pet"

    def _patient_card_action(self, reservation=None):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("elite_vet_clinic.action_patient_card")
        action["params"] = {"pet_id": self.id, "reservation_id": reservation.id if reservation else False}
        action["name"] = _("Karta pacienta – %s") % self.name
        return action

    def action_open_patient_card(self):
        return self._patient_card_action()


class ResPartner(models.Model):
    _inherit = "res.partner"

    def action_open_patient_card(self):
        """One pet -> its card; several -> list of the client's pets to pick from."""
        self.ensure_one()
        pets = self.pet_ids
        if not pets:
            raise UserError(_("Klient %s nemá žádného mazlíčka.") % self.name)
        if len(pets) == 1:
            return pets._patient_card_action()
        return {
            "type": "ir.actions.act_window", "name": _("Mazlíčci – %s") % self.name,
            "res_model": "elite.vet.pet", "view_mode": "list",
            "views": [(self.env.ref("elite_vet_clinic.view_pet_list_patient_card").id, "list")],
            "domain": [("partner_id", "=", self.id)], "target": "current",
        }


class VetReservation(models.Model):
    _inherit = "elite.vet.reservation"

    def action_open_patient_card(self):
        self.ensure_one()
        if not self.pet_id and self.pet_name:
            self.action_match_client()  # web booking: find or create the client and the pet
        pet = self.pet_id
        if not pet and len(self.partner_id.pet_ids) == 1:
            pet = self.partner_id.pet_ids
        if not pet:
            raise UserError(_("Rezervace nemá přiřazeného mazlíčka – doplňte ho, pak otevřete kartu pacienta."))
        return pet._patient_card_action(reservation=self)
