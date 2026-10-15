"""WinVet entities of the clinic (contract v2): bundles, bundle_lines, phrases.

Rules: upsert by WinVet id; a bundle/template changed in Odoo (edited_in_odoo) is never
written, archived or reconciled again, and the lines of such a bundle are not touched.
Deleted (or missing in a full run) bundles/templates are archived, bundle lines deleted.
"""
from odoo import api, models

from odoo.addons.elite_vet_winvet.models.winvet_tools import to_float, to_int, to_str

CLINIC_ENTITIES = ["bundles", "bundle_lines", "phrases"]
CLINIC_MODELS = {
    "bundles": "elite.vet.procedure.bundle",
    "bundle_lines": "elite.vet.procedure.bundle.line",
    "phrases": "elite.vet.text.template",
}
CLINIC_LABELS = {"bundles": "Balíčky výkonů", "bundle_lines": "Položky balíčků", "phrases": "Šablony textů"}
CLINIC_FIXUPS = [
    ("elite.vet.procedure.bundle.line", "bundle_id", "bundle_winvet_ref", "elite.vet.procedure.bundle"),
    ("elite.vet.procedure.bundle.line", "item_id", "item_winvet_ref", "elite.vet.winvet.item"),
]


class WinvetSync(models.AbstractModel):
    _inherit = "elite.vet.winvet.sync"

    @api.model
    def _winvet_entities(self):
        return super()._winvet_entities() + [e for e in CLINIC_ENTITIES if e not in super()._winvet_entities()]

    @api.model
    def _winvet_entity_models(self):
        return dict(super()._winvet_entity_models(), **CLINIC_MODELS)

    @api.model
    def _winvet_entity_labels(self):
        return dict(super()._winvet_entity_labels(), **CLINIC_LABELS)

    @api.model
    def _winvet_master_entities(self):
        return super()._winvet_master_entities() | {"bundles", "phrases"}

    @api.model
    def _winvet_fixups(self):
        return super()._winvet_fixups() + CLINIC_FIXUPS

    def _drop(self, entity, recs, stats):
        if entity in ("bundles", "phrases"):
            recs = recs.filtered(lambda r: not r.edited_in_odoo)
        elif entity == "bundle_lines":
            recs = recs.filtered(lambda r: not r.bundle_id.edited_in_odoo)
        return super()._drop(entity, recs, stats)

    def _push_bundles(self, records, stats, errors, batch, batches):
        vals = {ref: {"name": to_str(r.get("name")) or to_str(r.get("code")) or "Balíček %s" % ref,
                      "code": to_str(r.get("code")), "description": to_str(r.get("description"))}
                for ref, r in records.items()}
        self._upsert("elite.vet.procedure.bundle", vals, stats, errors, skip=lambda rec: rec.edited_in_odoo)

    def _push_bundle_lines(self, records, stats, errors, batch, batches):
        Bundle = self.env["elite.vet.procedure.bundle"]
        bundles = self._ref_map("elite.vet.procedure.bundle", {to_int(r.get("bundle_id")) for r in records.values()})
        edited = set(Bundle.browse(list(bundles.values())).filtered("edited_in_odoo").ids)
        items = self._ref_map("elite.vet.winvet.item", {to_int(r.get("item_id")) for r in records.values()})
        Item = self.env["elite.vet.winvet.item"]
        vals = {}
        for ref, r in records.items():
            bundle, item = to_int(r.get("bundle_id")), to_int(r.get("item_id"))
            if bundles.get(bundle) in edited:
                continue  # the bundle belongs to Odoo now
            item_id = items.get(item, False)
            vals[ref] = {
                "bundle_id": bundles.get(bundle, False), "bundle_winvet_ref": bundle or False,
                "item_id": item_id, "item_winvet_ref": item or False,
                "name": to_str(r.get("item_name")) or (Item.browse(item_id).name if item_id else False)
                or "Položka %s" % (item or ref),
                "quantity": to_float(r.get("quantity")) or 1.0, "unit": to_str(r.get("unit")),
                "sequence": to_int(r.get("sequence")) or 0,
            }
        self._upsert("elite.vet.procedure.bundle.line", vals, stats, errors,
                     skip=lambda rec: rec.bundle_id.edited_in_odoo)

    def _push_phrases(self, records, stats, errors, batch, batches):
        vals = {}
        for ref, r in records.items():
            group = r.get("group")
            vals[ref] = {"name": to_str(r.get("name")) or "Šablona %s" % ref,
                         "body": to_str(r.get("text")) or to_str(r.get("name")) or "-",
                         "group_name": to_str(group) if group not in (None, False) else False}
        # the section is chosen in Odoo; WinVet phrases start as "any"
        self._upsert("elite.vet.text.template", vals, stats, errors, skip=lambda rec: rec.edited_in_odoo,
                     create_extra=lambda v: {"section": "any"})
