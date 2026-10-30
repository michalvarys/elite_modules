from odoo import api, fields, models

SEGMENTS = [
    ("aktivni_stali", "Chodí pravidelně"),
    ("jednou_nedavno", "Nový, zatím jednou"),
    ("ohrozeni", "Přestává chodit"),
    ("ztraceni", "Ztracený"),
    ("jednou_davno", "Přišel jen jednou"),
    ("nikdy", "Ještě nehrál"),
]
SEGMENT_HELP = {
    "aktivni_stali": "Byl u nás víckrát a naposledy nedávno.",
    "jednou_nedavno": "Přišel poprvé nedávno, uvidíme, jestli se vrátí.",
    "ohrozeni": "Chodil víckrát, ale už nějakou dobu nepřišel. Teď je čas ho pozvat zpátky.",
    "ztraceni": "Chodil víckrát, ale nepřišel už hodně dlouho.",
    "jednou_davno": "Přišel jednou a už se nevrátil.",
    "nikdy": "Má účet, ale v historii nemá žádnou návštěvu.",
}


class GgleapPlayer(models.Model):
    """A ggLeap user account. Data come from ggLeap only (read-only in Odoo);
    statistics and the segment are recomputed after every sync."""

    _name = "elite.arena.ggleap.player"
    _description = "ggLeap – hráč"
    _order = "last_visit desc nulls last, id desc"
    _rec_name = "display_label"

    uuid = fields.Char(string="ID v ggLeap", required=True, index=True, readonly=True)
    username = fields.Char(string="Přezdívka", readonly=True, index=True)
    first_name = fields.Char(string="Jméno", readonly=True)
    last_name = fields.Char(string="Příjmení", readonly=True)
    full_name = fields.Char(string="Celé jméno", compute="_compute_labels", store=True)
    display_label = fields.Char(string="Hráč", compute="_compute_labels", store=True)
    email = fields.Char(string="E-mail", readonly=True, index=True)
    phone = fields.Char(string="Telefon", readonly=True)
    birthdate = fields.Date(string="Datum narození", readonly=True)
    age = fields.Integer(string="Věk", compute="_compute_age")
    balance = fields.Float(string="Kredit (Kč)", readonly=True)
    time_remaining_hours = fields.Float(string="Zbývající čas (h)", readonly=True)
    group_uuid = fields.Char(string="Skupina v ggLeap", readonly=True)
    locked = fields.Boolean(string="Zablokovaný", readonly=True)
    deleted = fields.Boolean(string="Smazaný v ggLeap", readonly=True)
    registered_at = fields.Datetime(string="Registrace", readonly=True)
    last_seen_ggleap = fields.Datetime(string="Naposledy viděn (ggLeap)", readonly=True,
                                       help="LastSeen z detailu hráče; pokrývá i návštěvy starší než stažená historie.")
    details_synced_at = fields.Datetime(string="Detail stažen", readonly=True)
    partner_id = fields.Many2one("res.partner", string="Kontakt", index=True, ondelete="set null")
    partner_dirty = fields.Boolean(readonly=True, default=True,
                                   help="Kontaktní údaje se v ggLeap změnily a kontakt se má aktualizovat.")
    partner_dirty_fields = fields.Char(readonly=True, help="Které údaje kontaktu se v ggLeap změnily (name,email,phone).")

    # statistics (recomputed by the sync)
    visit_count = fields.Integer(string="Návštěv", readonly=True, help="Počet dní, kdy hráč přišel (víc sezení za den = 1 návštěva).")
    first_visit = fields.Datetime(string="První návštěva", readonly=True)
    last_visit = fields.Datetime(string="Poslední návštěva", readonly=True)
    days_since_visit = fields.Integer(string="Dní od poslední návštěvy", readonly=True)
    hours_played = fields.Float(string="Odehráno (h)", readonly=True)
    total_spent = fields.Float(string="Utratil celkem (Kč)", readonly=True)
    segment = fields.Selection(SEGMENTS, string="Skupina", readonly=True, index=True)
    segment_help = fields.Char(string="Co to znamená", compute="_compute_segment_help")

    visit_ids = fields.One2many("elite.arena.ggleap.visit", "player_id", string="Návštěvy")
    transaction_ids = fields.One2many("elite.arena.ggleap.transaction", "player_id", string="Prodeje")
    booking_ids = fields.One2many("elite.arena.ggleap.booking", "player_id", string="Rezervace")
    gamepass_ids = fields.One2many("elite.arena.ggleap.gamepass", "player_id", string="Herní passy")
    active_gamepass_ids = fields.One2many("elite.arena.ggleap.gamepass", "player_id", string="Platné passy",
                                          domain=[("state", "=", "active")])
    pass_hours_left = fields.Float(string="Zbývá v passech (h)", compute="_compute_pass_hours_left", store=True,
                                   help="Součet nevyčerpaného času v platných passech.")
    gamepasses_synced_at = fields.Datetime(string="Passy načteny", readonly=True)

    _sql_constraints = [("uuid_uniq", "unique(uuid)", "Hráč z ggLeapu už existuje.")]

    @api.depends("username", "first_name", "last_name")
    def _compute_labels(self):
        for rec in self:
            name = " ".join(p.strip() for p in (rec.first_name, rec.last_name) if p and p.strip())
            rec.full_name = name
            if name and rec.username:
                rec.display_label = "%s (%s)" % (name, rec.username)
            else:
                rec.display_label = name or rec.username or rec.uuid

    @api.depends("gamepass_ids.state", "gamepass_ids.hours_left")
    def _compute_pass_hours_left(self):
        for rec in self:
            rec.pass_hours_left = sum(rec.gamepass_ids.filtered(lambda g: g.state == "active").mapped("hours_left"))

    @api.depends("birthdate")
    def _compute_age(self):
        today = fields.Date.context_today(self)
        for rec in self:
            b = rec.birthdate
            rec.age = (today.year - b.year - ((today.month, today.day) < (b.month, b.day))) if b else 0

    @api.depends("segment")
    def _compute_segment_help(self):
        for rec in self:
            rec.segment_help = SEGMENT_HELP.get(rec.segment, "")

    def action_open_visits(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "name": "Herní sezení · %s" % self.display_label,
                "res_model": "elite.arena.ggleap.visit", "view_mode": "list,form",
                "domain": [("player_id", "=", self.id)]}

    def action_open_transactions(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "name": "Prodeje · %s" % self.display_label,
                "res_model": "elite.arena.ggleap.transaction", "view_mode": "list,form",
                "domain": [("player_id", "=", self.id)]}

    def action_open_gamepasses(self):
        return {"type": "ir.actions.act_window", "name": "Herní passy",
                "res_model": "elite.arena.ggleap.gamepass", "view_mode": "list,form",
                "domain": [("player_id", "in", self.ids)], "context": {"search_default_active": 1}}

    def action_refresh_gamepasses(self):
        count = self.env["elite.arena.ggleap.sync"].refresh_gamepasses(self)
        return {"type": "ir.actions.client", "tag": "display_notification",
                "params": {"message": "Passy načteny z ggLeapu (%d)." % count, "type": "success",
                           "next": {"type": "ir.actions.client", "tag": "soft_reload"}}}

    def action_grant_gamepass(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "name": "Přidat herní pass",
                "res_model": "elite.arena.ggleap.gamepass.wizard", "view_mode": "form", "target": "new",
                "context": {"default_player_id": self.id, "default_partner_id": self.partner_id.id}}
