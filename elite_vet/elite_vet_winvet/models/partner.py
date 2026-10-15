from odoo import fields, models

OWNER_KINDS = [("company", "Firma"), ("person", "Osoba"), ("group", "Skupina")]


class ResPartner(models.Model):
    _inherit = "res.partner"

    winvet_kind = fields.Selection(OWNER_KINDS, string="Druh ve WinVetu", readonly=True)
    winvet_title = fields.Char(string="Titul (WinVet)", readonly=True)
    winvet_first_name = fields.Char(string="Jméno (WinVet)", readonly=True)
    winvet_last_name = fields.Char(string="Příjmení (WinVet)", readonly=True)
    winvet_vat = fields.Char(string="DIČ (WinVet)", readonly=True)
    winvet_note = fields.Text(string="Poznámka z WinVetu", readonly=True)
    winvet_important_note = fields.Boolean(string="Důležitá poznámka", readonly=True)
    winvet_created = fields.Date(string="Založen ve WinVetu", readonly=True)
    winvet_modified = fields.Datetime(string="Změněn ve WinVetu", readonly=True)
    winvet_contact_ids = fields.One2many("elite.vet.winvet.contact", "partner_id", string="Kontakty z WinVetu",
                                         readonly=True)
    # Set when the sync creates a person owner. The first contacts push of the run may
    # then link the owner to an existing web client with the same e-mail/phone.
    winvet_merge_pending = fields.Boolean(readonly=True, copy=False)

    def init(self):
        super().init()
        # Partial unique index: partners without a WinVet id have NULL or ''.
        self.env.cr.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS res_partner_winvet_ref_uniq ON res_partner (winvet_ref)"
            " WHERE winvet_ref IS NOT NULL AND winvet_ref <> ''")
