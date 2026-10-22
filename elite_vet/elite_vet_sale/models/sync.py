import logging

from odoo import api, models

from odoo.addons.elite_vet_winvet.models.winvet_tools import to_bool, to_date, to_float, to_int, to_str

_logger = logging.getLogger(__name__)

STOCK_ENTITIES = ["stock_lots", "stock_totals"]
STOCK_MODELS = {
    "stock_lots": "elite.vet.winvet.stock.layer",
    "stock_totals": "elite.vet.winvet.stock.total",
}
STOCK_LABELS = {"stock_lots": "Sklad – šarže", "stock_totals": "Sklad – stavy"}
STOCK_FIXUPS = [
    ("elite.vet.winvet.stock.layer", "item_id", "item_winvet_ref", "elite.vet.winvet.item"),
    ("elite.vet.winvet.stock.total", "item_id", "item_winvet_ref", "elite.vet.winvet.item"),
]


class WinvetSync(models.AbstractModel):
    _inherit = "elite.vet.winvet.sync"

    @api.model
    def _winvet_entities(self):
        entities = super()._winvet_entities()
        return entities + [e for e in STOCK_ENTITIES if e not in entities]

    @api.model
    def _winvet_entity_models(self):
        return dict(super()._winvet_entity_models(), **STOCK_MODELS)

    @api.model
    def _winvet_entity_labels(self):
        return dict(super()._winvet_entity_labels(), **STOCK_LABELS)

    @api.model
    def _winvet_fixups(self):
        return super()._winvet_fixups() + STOCK_FIXUPS

    def _push_items(self, records, stats, errors, batch, batches):
        super()._push_items(records, stats, errors, batch, batches)
        items = self.env["elite.vet.winvet.item"].search([("winvet_ref", "in", [to_int(r) for r in records])])
        items._sync_products(errors)

    def _stock_item_vals(self, records):
        """{ref: (item_id, item ref)} for records with an item; rows without one are skipped."""
        items = self._ref_map("elite.vet.winvet.item", {to_int(r.get("item_id")) for r in records.values()})
        out = {}
        for ref, r in records.items():
            item = to_int(r.get("item_id"))
            if item and item > 0:
                out[ref] = {"item_id": items.get(item, False), "item_winvet_ref": item}
        return out

    def _push_stock_lots(self, records, stats, errors, batch, batches):
        vals = self._stock_item_vals(records)
        stats["skipped"] += len(records) - len(vals)
        for ref, v in vals.items():
            r = records[ref]
            # the quantity is stored as WinVet has it (an over-issued receipt is negative)
            v.update({"lot_name": to_str(r.get("lot")), "expiry": to_date(r.get("expiry")),
                      "received": to_date(r.get("received")), "quantity": to_float(r.get("quantity")),
                      "unit_cost": to_float(r.get("unit_cost")), "vat_rate": to_float(r.get("vat_rate")),
                      "cost_includes_vat": to_bool(r.get("cost_includes_vat")), "supplier": to_str(r.get("supplier"))})
        self._upsert("elite.vet.winvet.stock.layer", vals, stats, errors)

    def _push_stock_totals(self, records, stats, errors, batch, batches):
        vals = self._stock_item_vals(records)
        stats["skipped"] += len(records) - len(vals)
        for ref, v in vals.items():
            v["total"] = to_float(records[ref].get("total"))
        self._upsert("elite.vet.winvet.stock.total", vals, stats, errors)

    def _after_full_run(self, entity, stats, errors):
        super()._after_full_run(entity, stats, errors)
        if entity != "stock_totals" or not self.env["elite.vet.sale.setup"].is_winvet_master():
            return
        # the warnings are stored on the status (stock_mirror_warnings), not in `errors`: they
        # would overwrite last_error after every cycle and hide real errors of other entities
        result = self.env["elite.vet.winvet.stock.layer"]._apply_mirror()
        _logger.info("Elite Vet: stock mirrored from WinVet – %(products)s products, %(adjusted)s quants "
                     "adjusted, %(n)s warnings", dict(result, n=len(result["warnings"])))
