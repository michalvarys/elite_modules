from odoo import fields, models


class VetPet(models.Model):
    _inherit = "elite.vet.pet"

    winvet_ref = fields.Integer(string="ID ve WinVetu", index=True, readonly=True, copy=False)
    winvet_owner_ref = fields.Integer(
        string="ID majitele ve WinVetu", index=True, readonly=True, copy=False,
        help="Když majitel ještě není v Odoo, pacient patří dočasně k archivovanému kontaktu "
             "„WinVet – neznámý majitel“ a po příchodu majitele se k němu sám přepojí.")
    winvet_species = fields.Char(string="Druh ve WinVetu", readonly=True)
    chip = fields.Char(string="Čip", index=True)
    tattoo = fields.Char(string="Tetování")
    passport = fields.Char(string="Číslo pasu")
    birth_date = fields.Date(string="Datum narození")
    birth_year = fields.Integer(string="Rok narození")
    sex = fields.Char(string="Pohlaví")
    color = fields.Char(string="Barva")
    weight = fields.Float(string="Hmotnost (kg)")
    deceased = fields.Boolean(string="Uhynulý")
    death_date = fields.Date(string="Datum úhynu / eutanazie")
    registered_date = fields.Date(string="Registrován")
    next_vaccination = fields.Date(string="Příští vakcinace")
    next_deworming = fields.Date(string="Příští odčervení")
    important_note = fields.Char(string="Důležité")
    winvet_note = fields.Text(string="Poznámka z WinVetu", readonly=True)
    winvet_created = fields.Date(string="Založen ve WinVetu", readonly=True)
    winvet_modified = fields.Datetime(string="Změněn ve WinVetu", readonly=True)
    vaccination_ids = fields.One2many("elite.vet.vaccination", "pet_id", string="Očkování", readonly=True)
    visit_ids = fields.One2many("elite.vet.visit", "pet_id", string="Návštěvy", readonly=True)

    def init(self):
        super().init()
        # Partial unique index: pets created in Odoo have no WinVet id (NULL or 0).
        self.env.cr.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS elite_vet_pet_winvet_ref_uniq ON elite_vet_pet (winvet_ref)"
            " WHERE winvet_ref IS NOT NULL AND winvet_ref <> 0")
