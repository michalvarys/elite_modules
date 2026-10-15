import hashlib
import hmac
import secrets

from odoo import api, fields, models

PARAM_HASH = "elite_vet_winvet.api_key_hash"
PARAM_CREATED = "elite_vet_winvet.api_key_created"


def hash_key(key):
    return hashlib.sha256((key or "").encode()).hexdigest()


class WinvetConfig(models.TransientModel):
    """API key settings. Only the SHA-256 hash of the key is stored (ir.config_parameter).
    The plain key travels to the browser in the action context right after generation
    and is never written to the database."""

    _name = "elite.vet.winvet.config"
    _description = "WinVet – nastavení API klíče"

    key_set = fields.Boolean(string="Klíč je nastaven", compute="_compute_key_info")
    key_created = fields.Char(string="Klíč vygenerován", compute="_compute_key_info")
    new_key = fields.Char(string="Nový API klíč", compute="_compute_key_info",
                          help="Zobrazí se jen jednou, hned po vygenerování. Zkopírujte ho do "
                               "nastavení mostu (winvet_bridge). V Odoo se ukládá jen jeho otisk.")

    @api.depends_context("winvet_new_key")
    def _compute_key_info(self):
        params = self.env["ir.config_parameter"].sudo()
        for rec in self:
            rec.key_set = bool(params.get_param(PARAM_HASH))
            rec.key_created = params.get_param(PARAM_CREATED) or False
            rec.new_key = self.env.context.get("winvet_new_key") or False

    @api.model
    def generate_key(self):
        """New random key; stores only its hash and returns the plain key."""
        key = secrets.token_urlsafe(32)
        params = self.env["ir.config_parameter"].sudo()
        params.set_param(PARAM_HASH, hash_key(key))
        params.set_param(PARAM_CREATED, fields.Datetime.to_string(fields.Datetime.now()))
        return key

    def action_generate_key(self):
        key = self.generate_key()
        return {
            "type": "ir.actions.act_window",
            "name": "API klíč pro WinVet",
            "res_model": self._name,
            "view_mode": "form",
            "target": "current",
            "res_id": self.create({}).id,
            "context": {"winvet_new_key": key},
        }

    def action_revoke_key(self):
        params = self.env["ir.config_parameter"].sudo()
        params.set_param(PARAM_HASH, False)
        params.set_param(PARAM_CREATED, False)
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "view_mode": "form",
            "target": "current",
            "res_id": self.create({}).id,
        }

    @api.model
    def check_key(self, key):
        stored = self.env["ir.config_parameter"].sudo().get_param(PARAM_HASH)
        if not stored or not key:
            return False
        return hmac.compare_digest(stored, hash_key(key))
