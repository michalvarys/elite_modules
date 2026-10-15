import json
from datetime import timedelta

from odoo import api, fields, models


class WinvetRun(models.Model):
    """WinVet ids seen in one batch of a full push. On the last batch of a run the
    union of all batches tells which Odoo rows disappeared from WinVet.
    Rows are deleted once the run is reconciled (and stale ones after two days)."""

    _name = "elite.vet.winvet.run"
    _description = "WinVet – plná synchronizace (dávka)"

    run_id = fields.Char(required=True, index=True)
    entity = fields.Char(required=True)
    batch = fields.Integer()
    batches = fields.Integer()
    refs = fields.Text(help="JSON list of WinVet ids of the batch")

    _sql_constraints = [
        ("run_entity_batch_uniq", "unique(run_id, entity, batch)", "Dávka běhu už je uložená."),
    ]

    @api.model
    def store_batch(self, run_id, entity, batch, batches, refs):
        existing = self.search([("run_id", "=", run_id), ("entity", "=", entity), ("batch", "=", batch)])
        vals = {"batches": batches, "refs": json.dumps(sorted(set(refs)))}
        if existing:
            existing.write(vals)
        else:
            self.create(dict(vals, run_id=run_id, entity=entity, batch=batch))

    @api.model
    def collect(self, run_id, entity, batches):
        """Seen ids of the whole run, or None when some batch is missing."""
        rows = self.search([("run_id", "=", run_id), ("entity", "=", entity)])
        if set(range(1, batches + 1)) - set(rows.mapped("batch")):
            return None
        seen = set()
        for row in rows:
            seen.update(json.loads(row.refs or "[]"))
        return seen

    @api.model
    def cleanup(self, run_id, entity):
        old = fields.Datetime.now() - timedelta(days=2)
        self.search(["|", "&", ("run_id", "=", run_id), ("entity", "=", entity),
                     ("create_date", "<", old)]).unlink()
