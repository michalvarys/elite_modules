import re
import unicodedata

from odoo import api, fields, models


def _kotva_z_nazvu(nazev):
    """Z 'Veterinární lékařky' udela 'veterinarni-lekarky'.

    Kotva jde do adresy (/nas-tym#lekarky), takze v ni nesmi byt diakritika
    ani mezery. Klinika ji nemusi vyplnovat - dopocita se z nazvu, a kdo chce,
    prepise si ji na kratsi.
    """
    bez_diakritiky = unicodedata.normalize("NFKD", nazev or "")
    bez_diakritiky = "".join(z for z in bez_diakritiky if not unicodedata.combining(z))
    kotva = re.sub(r"[^a-zA-Z0-9]+", "-", bez_diakritiky).strip("-").lower()
    return kotva or "sekce"


class VetTeamSection(models.Model):
    """Sekce na strance tymu: lekarky, sestry, recepce, management.

    Sekce je samostatny zaznam, ne pevny seznam v kodu, aby si klinika mohla
    prejmenovat nebo pridat dalsi (treba Externi specialiste) bez zasahu do webu.
    """

    _name = "elite.vet.team.section"
    _description = "Sekce týmu"
    _order = "sequence, id"

    name = fields.Char(string="Název sekce", required=True, translate=True)
    sequence = fields.Integer(string="Pořadí", default=10)
    anchor = fields.Char(
        string="Kotva",
        help="Krátký text bez diakritiky a mezer, například lekarky. Použije se "
             "v odkazu na stránce (/nas-tym#lekarky), takže se dá poslat odkaz "
             "přímo na tuhle část. Když ho necháte prázdný, dopočítá se z názvu.",
    )
    member_ids = fields.One2many("elite.vet.team.member", "section_id", string="Členové")
    member_count = fields.Integer(compute="_compute_member_count", string="Počet lidí")
    na_webu = fields.Boolean(
        string="Na webu",
        compute="_compute_na_webu",
        help="Sekce se na strance ukaze, teprve kdyz do ni patri aspon jeden clovek. "
             "Prazdna sekce by udelala nadpis, pod kterym nic neni, takze se vynecha.",
    )

    @api.depends("member_ids", "active")
    def _compute_na_webu(self):
        for zaznam in self:
            zaznam.na_webu = bool(zaznam.active and zaznam.member_ids)
    active = fields.Boolean(string="Aktivní", default=True)

    def _compute_member_count(self):
        for rec in self:
            rec.member_count = len(rec.member_ids)

    def _volna_kotva(self, zaklad, vlastni_id=None):
        """Dve sekce nesmi mit stejnou kotvu, jinak by odkaz miril jinam."""
        kotva = zaklad
        poradi = 2
        while True:
            domena = [("anchor", "=", kotva)]
            if vlastni_id:
                domena.append(("id", "!=", vlastni_id))
            if not self.sudo().with_context(active_test=False).search_count(domena):
                return kotva
            kotva = "%s-%d" % (zaklad, poradi)
            poradi += 1

    @api.model_create_multi
    def create(self, vals_list):
        # Kotvu necháváme nepovinnou, aby šla sekce založit i rychlým přidáním
        # sloupce v kanbanu, kde se zadává jen název.
        for vals in vals_list:
            if not vals.get("anchor"):
                vals["anchor"] = self._volna_kotva(_kotva_z_nazvu(vals.get("name")))
        return super().create(vals_list)

    def write(self, vals):
        if "anchor" in vals and not vals.get("anchor"):
            del vals["anchor"]
        vysledek = super().write(vals)
        for rec in self:
            if not rec.anchor:
                rec.anchor = rec._volna_kotva(_kotva_z_nazvu(rec.name), rec.id)
        return vysledek
