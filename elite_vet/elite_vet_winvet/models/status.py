import json

from odoo import api, fields, models

from .schema_change import OBJECTS, SEVERITIES

SEVERITY_LABELS = SEVERITIES
SEVERITY_ORDER = {key: i for i, (key, _label) in enumerate(SEVERITIES)}
OBJECT_KEYS = {key for key, _label in OBJECTS}

# Areas of the bridge (keys of `fingerprints` / values of `blocked`) besides entity names.
AREA_LABELS = {"owners": "majitelé", "patients": "pacienti", "clinical": "klinická data",
               "sales": "tržby", "catalog": "ceník", "journal": "žurnál změn"}


class WinvetStatus(models.Model):
    """One record (singleton) with the state of the WinVet bridge."""

    _name = "elite.vet.winvet.status"
    _description = "Stav synchronizace WinVet"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char(string="Název", default="Synchronizace WinVet", readonly=True)
    bridge_version = fields.Char(string="Verze mostu", readonly=True)
    source = fields.Char(string="Zdroj dat", readonly=True, help="live = živá databáze, backup = záloha")
    winvet_version = fields.Char(string="Verze WinVetu", readonly=True)
    previous_winvet_version = fields.Char(string="Předchozí verze WinVetu", readonly=True)
    ods = fields.Char(string="ODS databáze", readonly=True)
    engine = fields.Char(string="Firebird", readonly=True)
    fingerprints = fields.Text(string="Otisky struktury", readonly=True)
    blocked = fields.Char(string="Zablokované oblasti", readonly=True,
                          help="Oblasti, které most odmítl číst, protože verze WinVetu nebo struktura "
                               "databáze není ověřená.")
    journal_cursor = fields.Integer(string="Pozice v žurnálu", readonly=True)
    message = fields.Text(string="Zpráva mostu", readonly=True)
    last_status_at = fields.Datetime(string="Poslední hlášení stavu", readonly=True)
    last_push_at = fields.Datetime(string="Poslední příjem dat", readonly=True)
    last_error = fields.Text(string="Poslední chyba", readonly=True)
    alert = fields.Char(string="Upozornění", readonly=True)
    last_alert_text = fields.Char(readonly=True, help="Blocked areas already announced.")
    entity_ids = fields.One2many("elite.vet.winvet.status.entity", "status_id", string="Oblasti", readonly=True)
    schema_hash = fields.Char(string="Otisk struktury databáze", readonly=True)
    schema_baseline_hash = fields.Char(string="Schválený otisk struktury", readonly=True)
    schema_change_summary = fields.Char(string="Změny struktury", readonly=True)
    schema_change_ids = fields.Many2many("elite.vet.winvet.schema.change", compute="_compute_schema_changes",
                                         string="Aktuální změny struktury")

    @api.depends("schema_hash", "schema_baseline_hash")
    def _compute_schema_changes(self):
        Change = self.env["elite.vet.winvet.schema.change"]
        for rec in self:
            rec.schema_change_ids = Change.search([("schema_hash", "=", rec.schema_hash)]) \
                if rec.schema_hash and rec.schema_hash != rec.schema_baseline_hash else Change

    @api.model
    def get_status(self):
        rec = self.sudo().search([], limit=1)
        if not rec:
            rec = self.sudo().create({})
        return rec

    def record_status(self, payload):
        """Store a /status call. Raises an alert when the WinVet version changed or
        some areas are blocked."""
        self.ensure_one()
        blocked = payload.get("blocked") or []
        if isinstance(blocked, str):
            blocked = [blocked]
        blocked_txt = ", ".join(str(b) for b in blocked)
        new_version = payload.get("winvet_version")
        new_version = str(new_version) if new_version not in (None, "") else False
        old_version = self.winvet_version
        fingerprints = payload.get("fingerprints")
        vals = {
            "bridge_version": payload.get("bridge_version") or False,
            "source": payload.get("source") or False,
            "winvet_version": new_version,
            "ods": str(payload["ods"]) if payload.get("ods") is not None else False,
            "engine": payload.get("engine") or False,
            "fingerprints": json.dumps(fingerprints, indent=1, sort_keys=True) if fingerprints else False,
            "blocked": blocked_txt or False,
            "journal_cursor": int(payload.get("journal_cursor") or 0),
            "message": payload.get("message") or False,
            "last_status_at": fields.Datetime.now(),
            "last_error": False,
        }
        parts = []
        if old_version and new_version and old_version != new_version:
            vals["previous_winvet_version"] = old_version
            parts.append("WinVet byl aktualizován z verze %s na %s." % (old_version, new_version))
        # The bridge runs often: the same set of blocked areas is announced only once (also
        # after it was acknowledged); again only when it changes or comes back later.
        if blocked_txt and blocked_txt != self.last_alert_text:
            block_labels = dict(self.env["elite.vet.winvet.sync"]._winvet_entity_labels(), **AREA_LABELS)
            labels = ", ".join(block_labels.get(b, b) for b in blocked)
            parts.append("Oblasti %s jsou zablokované – most je nečte, dokud nebude ověřená "
                         "nová verze WinVetu." % labels)
        vals["last_alert_text"] = blocked_txt or False
        parts += self._record_schema(payload, vals, new_version)
        text = " ".join(parts)
        if text:
            vals["alert"] = text
        self.write(vals)
        if text:
            self._notify_managers(text)
        return True

    def _record_schema(self, payload, vals, winvet_version):
        """Store table-level schema changes; return alert texts for new serious ones."""
        if "schema_hash" not in payload:
            return []
        new_hash = payload.get("schema_hash") or False
        vals["schema_hash"] = new_hash
        vals["schema_baseline_hash"] = payload.get("schema_baseline_hash") or False
        counts = payload.get("schema_change_counts") or {}
        labels = dict(SEVERITY_LABELS)
        vals["schema_change_summary"] = ", ".join(
            "%s %s" % (labels.get(k, k), v) for k, v in sorted(counts.items(), key=lambda kv: SEVERITY_ORDER.get(kv[0], 9))
        ) or False
        if not new_hash or new_hash == self.schema_hash:
            return []  # nothing new since the last report
        changes = payload.get("schema_changes") or []
        Change = self.env["elite.vet.winvet.schema.change"]
        now = fields.Datetime.now()
        if not Change.search_count([("schema_hash", "=", new_hash)]):
            Change.create([{
                "detected_at": now, "schema_hash": new_hash, "baseline_hash": vals["schema_baseline_hash"],
                "winvet_version": winvet_version, "severity": c.get("severity") if c.get("severity") in SEVERITY_ORDER else "info",
                "severity_rank": SEVERITY_ORDER.get(c.get("severity"), 9),
                "object_type": c.get("object") if c.get("object") in OBJECT_KEYS else False,
                "table_name": c.get("table") or False, "object_name": c.get("name") or False,
                "change": c.get("change") if c.get("change") in ("added", "removed", "changed") else False,
                "old_value": c.get("old") or False, "new_value": c.get("new") or False,
            } for c in changes])
        if not changes:
            if self.schema_hash:
                self.message_post(body="Struktura databáze WinVetu je opět shodná se schváleným stavem.",
                                  message_type="comment", subtype_xmlid="mail.mt_note")
            return []
        serious = [c for c in changes if c.get("severity") in ("breaking", "journal")]
        if serious:
            tables = sorted({c.get("table") or "-" for c in serious})
            return ["Ve WinVetu se změnila struktura tabulek, které most čte (%s): %s. Zkontrolujte "
                    "„Změny struktury“ a po ověření je v mostu schvalte." % (vals["schema_change_summary"], ", ".join(tables))]
        self.message_post(body="WinVet: změny struktury databáze bez dopadu na synchronizaci (%s)."
                          % vals["schema_change_summary"], message_type="comment", subtype_xmlid="mail.mt_note")
        return []

    def action_open_schema_changes(self):
        return {
            "type": "ir.actions.act_window", "name": "Změny struktury WinVetu",
            "res_model": "elite.vet.winvet.schema.change", "view_mode": "list,form",
            "domain": [("schema_hash", "=", self.schema_hash)],
        }

    def _notify_managers(self, text):
        self.message_post(body=text, subject="WinVet – upozornění", message_type="comment",
                          subtype_xmlid="mail.mt_note")
        group = self.env.ref("elite_vet_reservation.group_reservation_manager")
        users = group.users.filtered(lambda u: u.active and not u.share and u.id != self.env.ref("base.user_root").id)
        activity_type = self.env.ref("mail.mail_activity_data_warning", raise_if_not_found=False) \
            or self.env.ref("mail.mail_activity_data_todo")
        for user in users:
            self.activity_schedule(activity_type_id=activity_type.id, summary="WinVet – zkontrolujte synchronizaci",
                                   note=text, user_id=user.id)

    def action_acknowledge(self):
        self.write({"alert": False})
        self.activity_ids.action_feedback(feedback="Upozornění potvrzeno.")
        return True

    def record_push(self, entity, mode, run_id, result, error=None):
        self.ensure_one()
        line = self.entity_ids.filtered(lambda e: e.entity == entity)
        now = fields.Datetime.now()
        vals = {"mode": mode, "run_id": run_id or False, "last_push_at": now}
        if not line or line.run_id != run_id:
            # first batch of this run: restart the counters
            vals.update({k: result.get(k, 0) for k in ("created", "updated", "deleted", "skipped")})
        else:
            vals.update({k: getattr(line, k) + result.get(k, 0) for k in ("created", "updated", "deleted", "skipped")})
        if line:
            line.write(vals)
        else:
            vals.update({"status_id": self.id, "entity": entity})
            self.env["elite.vet.winvet.status.entity"].create(vals)
        status_vals = {"last_push_at": now}
        if error:
            status_vals["last_error"] = "%s %s: %s" % (fields.Datetime.to_string(now), entity, error)
        self.write(status_vals)


class WinvetStatusEntity(models.Model):
    _name = "elite.vet.winvet.status.entity"
    _description = "Stav synchronizace WinVet – oblast"
    _order = "sequence"

    status_id = fields.Many2one("elite.vet.winvet.status", required=True, ondelete="cascade")
    entity = fields.Selection(selection="_selection_entity", string="Oblast", required=True)
    sequence = fields.Integer(compute="_compute_sequence", store=True)
    mode = fields.Selection([("full", "Plná"), ("incremental", "Změny")], string="Režim")
    run_id = fields.Char(string="Běh")
    last_push_at = fields.Datetime(string="Naposledy")
    created = fields.Integer(string="Nové")
    updated = fields.Integer(string="Změněné")
    deleted = fields.Integer(string="Smazané/archivované")
    skipped = fields.Integer(string="Přeskočené")

    @api.model
    def _selection_entity(self):
        """Entities of the sync engine (extensible by other modules), in push order."""
        sync = self.env["elite.vet.winvet.sync"]
        labels = sync._winvet_entity_labels()
        return [(e, labels.get(e, e)) for e in sync._winvet_entities()]

    @api.depends("entity")
    def _compute_sequence(self):
        entities = self.env["elite.vet.winvet.sync"]._winvet_entities()
        for rec in self:
            rec.sequence = entities.index(rec.entity) if rec.entity in entities else 99
