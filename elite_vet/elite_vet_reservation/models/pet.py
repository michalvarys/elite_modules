import re

from odoo import api, fields, models
from odoo.osv import expression

SPECIES = [
    ("dog", "Pes"), ("cat", "Kočka"), ("rabbit", "Králík"), ("rodent", "Hlodavec"),
    ("bird", "Pták"), ("reptile", "Plaz"), ("other", "Jiné"),
]


def normalizuj_telefon(text):
    """'+420 722-599 699' -> '420722599699'. Porovnava se posledních 9 cislic."""
    return re.sub(r"\D", "", text or "")


class VetPet(models.Model):
    _name = "elite.vet.pet"
    _description = "Mazlíček"
    _order = "name"

    name = fields.Char(string="Jméno", required=True)
    partner_id = fields.Many2one("res.partner", string="Majitel", required=True, ondelete="cascade")
    species = fields.Selection(SPECIES, string="Druh", default="dog")
    species_other = fields.Char(string="Jiný druh")
    breed = fields.Char(string="Plemeno")
    note = fields.Text(string="Poznámka")
    active = fields.Boolean(string="Aktivní", default=True)

    @api.model
    def find_or_create(self, partner, name, species=None):
        """Mazlicek stejneho majitele se stejnym jmenem (bez ohledu na velikost pismen)."""
        name = (name or "").strip()
        if not name:
            return self.browse()
        pet = self.search([("partner_id", "=", partner.id), ("name", "=ilike", name)], limit=1)
        if pet:
            return pet
        return self.create({"name": name, "partner_id": partner.id, "species": species or "other"})


class ResPartner(models.Model):
    _inherit = "res.partner"

    is_vet_client = fields.Boolean(string="Klient kliniky", index=True)
    pet_ids = fields.One2many("elite.vet.pet", "partner_id", string="Mazlíčci")
    # Misto pro budouci export z WinVetu. Ted se nikde nevyplnuje.
    winvet_ref = fields.Char(string="ID ve WinVetu", index=True)
    reservation_ids = fields.One2many("elite.vet.reservation", "partner_id", string="Rezervace")

    @api.model
    def _search_display_name(self, operator, value):
        """V průvodci rezervací (kontext ev_search_phone) se klient hledá i podle
        telefonu - jen podle číslic, telefony jsou v bázi zapsané různě."""
        domain = super()._search_display_name(operator, value)
        digits = normalizuj_telefon(value) if isinstance(value, str) else ""
        if self.env.context.get("ev_search_phone") and operator == "ilike" and len(digits) >= 4:
            self.flush_model(["phone", "mobile", "active"])
            self.env.cr.execute(
                "SELECT id FROM res_partner WHERE regexp_replace(coalesce(phone, ''), '\\D', '', 'g') LIKE %s"
                " OR regexp_replace(coalesce(mobile, ''), '\\D', '', 'g') LIKE %s",
                ["%" + digits + "%"] * 2,
            )
            ids = [r[0] for r in self.env.cr.fetchall()]
            if ids:
                domain = expression.OR([domain, [("id", "in", ids)]])
        return domain

    @api.model
    def find_or_create_client(self, name, email, phone):
        """Parovani z webu: e-mail, pak telefon, jinak novy klient."""
        email = (email or "").strip()
        digits = normalizuj_telefon(phone)
        partner = self.browse()
        if email:
            # email_normalized (male pismena) misto =ilike: ten bere % a _ jako zastupne
            # znaky a verejny formular by tak mohl "trefit" cizi kontakt.
            partner = self.search([("email_normalized", "=", email.lower())], limit=1)
        if not partner and len(digits) >= 9:
            tail = digits[-9:]
            # Telefony jsou v bazi zapsane ruzne ("+420 722 599 699"), proto se
            # porovnava jen cislice; ilike na cast cisla by mezery rozbily.
            # Raw SQL nevidi necommitnute ORM zapisy, proto je predtim flushneme.
            self.flush_model(["phone", "active"])
            self.env.cr.execute(
                "SELECT id FROM res_partner WHERE active"
                " AND regexp_replace(phone, '\\D', '', 'g') LIKE %s ORDER BY id LIMIT 1",
                ["%" + tail],
            )
            partner = self.browse([r[0] for r in self.env.cr.fetchall()])
        if not partner:
            partner = self.create({"name": (name or email or phone or "Klient").strip(),
                                   "email": email or False, "phone": phone or False})
        if not partner.is_vet_client:
            partner.is_vet_client = True
        return partner
