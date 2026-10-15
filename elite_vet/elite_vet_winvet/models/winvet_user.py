from odoo import api, fields, models

from .winvet_tools import name_words


class WinvetUser(models.Model):
    _name = "elite.vet.winvet.user"
    _description = "Uživatel WinVetu"
    _order = "name"

    winvet_ref = fields.Integer(string="ID ve WinVetu", required=True, index=True, readonly=True)
    name = fields.Char(string="Jméno", required=True, readonly=True)
    code = fields.Char(string="Zkratka", readonly=True)
    active = fields.Boolean(string="Aktivní", default=True)
    doctor_id = fields.Many2one(
        "elite.vet.doctor", string="Lékařka v Odoo", ondelete="set null",
        help="Propojení na lékařku z Rozpisu služeb. Doplní se samo podle jména (tituly se "
             "ignorují, pořadí jména a příjmení nehraje roli); ručně zadané propojení se nepřepisuje.")

    _sql_constraints = [
        ("winvet_ref_uniq", "unique(winvet_ref)", "Uživatel s tímto ID z WinVetu už existuje."),
    ]

    def match_doctors(self):
        """Fill doctor_id for users without it: the set of name words (without titles)
        of the WinVet name ('Nováková Jana') must equal the doctor's ('MVDr. Jana Nováková').
        Only a unique match is used."""
        todo = self.filtered(lambda u: not u.doctor_id)
        if not todo:
            return
        doctors = self.env["elite.vet.doctor"].with_context(active_test=False).search([])
        by_words = {}
        for doc in doctors:
            key = frozenset(name_words(doc.name))
            if key:
                by_words.setdefault(key, []).append(doc)
        for user in todo:
            key = frozenset(name_words(user.name))
            match = by_words.get(key) or []
            if len(match) == 1:
                user.doctor_id = match[0]

    @api.model
    def action_match_doctors(self):
        self.with_context(active_test=False).search([]).match_doctors()
        return True
