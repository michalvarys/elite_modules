"""Stock mirrored from WinVet (contract v3: stock_lots, stock_totals).

WinVet keeps stock as receipt layers (one per receipt line, minus the issues linked to it)
and a total per item. While WinVet leads the stock (`is_winvet_master()`), every full run
sets the Odoo stock on the warehouse stock location exactly to the mirrored state:
one lot per layer (its lot number, or `WV-<layer id>` without one), quantities set by an
inventory adjustment. See README, section "Stav skladu ze WinVetu".
"""
import logging
from collections import defaultdict
from datetime import date, datetime, time

from odoo import fields, models
from odoo.tools import float_compare, float_is_zero, float_round

_logger = logging.getLogger(__name__)

PRECISION = 0.001  # rounding of the unit (uom.product_uom_unit, see setup._ensure_units)


def _fmt(value):
    return ("%.3f" % value).rstrip("0").rstrip(".")


class WinvetStockLayer(models.Model):
    _name = "elite.vet.winvet.stock.layer"
    _description = "WinVet – skladová vrstva (příjem)"
    _order = "item_id, expiry, id"

    winvet_ref = fields.Integer(string="WinVet ID", required=True, index=True, readonly=True)
    item_id = fields.Many2one("elite.vet.winvet.item", string="Položka", index=True, ondelete="set null",
                              readonly=True)
    item_winvet_ref = fields.Integer(string="WinVet ID položky", readonly=True)
    lot_name = fields.Char(string="Šarže", readonly=True)
    expiry = fields.Date(string="Expirace", readonly=True)
    received = fields.Date(string="Přijato", readonly=True)
    quantity = fields.Float(string="Zůstatek", digits="Product Unit of Measure", readonly=True,
                            help="Množství příjmu mínus výdeje navázané na tento příjem (jak je ve WinVetu, "
                                 "i záporné).")
    unit_cost = fields.Float(string="Nákupní cena za MJ", readonly=True)
    vat_rate = fields.Float(string="Sazba DPH (%)", readonly=True)
    cost_includes_vat = fields.Boolean(string="Cena s DPH", readonly=True)
    supplier = fields.Char(string="Dodavatel", readonly=True)

    _sql_constraints = [("winvet_ref_unique", "unique(winvet_ref)", "Vrstva WinVetu už existuje.")]

    # ------------------------------------------------------------------ mirror

    def _untaxed_cost(self):
        self.ensure_one()
        if self.cost_includes_vat and self.vat_rate:
            return self.unit_cost / (1.0 + self.vat_rate / 100.0)
        return self.unit_cost

    def _apply_mirror(self):
        """Set lots, quants and cost of every storable WinVet product to the mirrored state.

        Returns {"products": n, "adjusted": n, "warnings": [str]}; never raises for one product.
        """
        self = self.sudo()
        env = self.env
        Layer, Total = env["elite.vet.winvet.stock.layer"], env["elite.vet.winvet.stock.total"]
        Quant, Lot = env["stock.quant"], env["stock.lot"].with_context(active_test=False)
        company = env.company
        location = env["stock.warehouse"].search([("company_id", "=", company.id)], limit=1).lot_stock_id
        result = {"products": 0, "adjusted": 0, "warnings": []}
        if not location:
            result["warnings"].append("zrcadlo skladu: společnost nemá sklad")
            return result

        Item = env["elite.vet.winvet.item"].with_context(active_test=False)
        stocked = Total.search([("total", "!=", 0), ("item_id", "!=", False)]).item_id
        # goods WinVet holds stock for but whose product is missing or not storable yet
        stocked.filtered(lambda i: i.active and i.kind == "product" and not i.product_id.is_storable) \
            ._sync_products(result["warnings"])
        inactive = stocked.filtered(lambda i: not i.active and not i.product_id.is_storable)
        if inactive:
            result["warnings"].append("%d neaktivních položek se stavem skladu se nepřenáší" % len(inactive))
        items = Item.search([("product_id", "!=", False)])
        items = items.filtered(lambda i: i.product_id.is_storable)
        layers_by_item, totals_by_item = defaultdict(list), defaultdict(float)
        has_total = set()
        for layer in Layer.search([("item_id", "in", items.ids)]):
            layers_by_item[layer.item_id.id].append(layer)
        for total in Total.search([("item_id", "in", items.ids)]):
            totals_by_item[total.item_id.id] += total.total
            has_total.add(total.item_id.id)
        products = items.product_id
        quants_by_product = defaultdict(lambda: Quant)
        for quant in Quant.search([("product_id", "in", products.ids), ("location_id", "child_of", location.id)]):
            quants_by_product[quant.product_id.id] |= quant
        lots = {(lot.product_id.id, lot.name): lot for lot in Lot.search([("product_id", "in", products.ids)])}

        to_apply = Quant
        for item in items:
            product = item.product_id
            layers = layers_by_item.get(item.id, [])
            if not layers and item.id not in has_total and not quants_by_product.get(product.id):
                continue
            result["products"] += 1
            try:
                with env.cr.savepoint():
                    targets = self._mirror_targets(item, layers, totals_by_item.get(item.id), item.id in has_total,
                                                   result["warnings"])
                    self._mirror_cost(product, layers, company)
                    to_apply |= self._mirror_quants(product, location, targets, lots,
                                                    quants_by_product.get(product.id, Quant), company)
            except Exception as exc:  # noqa: BLE001 - one bad product must not stop the mirror
                env.invalidate_all()
                _logger.warning("Elite Vet: stock of item %s not mirrored: %s", item.winvet_ref, exc)
                result["warnings"].append("Položka %s: stav skladu nenastaven (%s)" % (self._label(item), exc))
        result["adjusted"] = self._apply_quants(to_apply, result["warnings"])
        env["elite.vet.winvet.status"].get_status().write({
            "stock_mirror_warnings": "\n".join(result["warnings"]) or False,
            "stock_mirror_date": fields.Datetime.now(),
        })
        return result

    def _label(self, item):
        return item.code or item.name or str(item.winvet_ref)

    def _mirror_targets(self, item, layers, total, has_total, warnings):
        """{lot name: (quantity, expiry)} the stock of the item should have."""
        targets = {}
        for layer in layers:
            name = layer.lot_name or "WV-%d" % layer.winvet_ref
            qty, expiry = targets.get(name, (0.0, False))
            targets[name] = (qty + max(layer.quantity, 0.0), max(filter(None, [expiry, layer.expiry]), default=False))
        if not has_total:
            return targets
        label = self._label(item)
        # WinVet itself disagrees (layers vs. total): reported. An over-issued layer (negative,
        # counted as 0) is no disagreement, its excess is only taken from the other lots below.
        raw_diff = float_round(total - sum(la.quantity for la in layers), precision_rounding=PRECISION)
        if not float_is_zero(raw_diff, precision_rounding=PRECISION):
            warnings.append("Položka %s: rozdíl %s proti stavu WinVetu" % (label, _fmt(raw_diff)))
        diff = float_round(total - sum(q for q, _e in targets.values()), precision_rounding=PRECISION)
        if float_is_zero(diff, precision_rounding=PRECISION):
            return targets

        def latest(layer):
            return (layer.expiry or date.min, layer.received or date.min, layer.winvet_ref)
        # lots from the latest expiry down (a lot ranks by its latest layer)
        rank = {}
        for layer in layers:
            name = layer.lot_name or "WV-%d" % layer.winvet_ref
            rank[name] = max(rank.get(name, latest(layer)), latest(layer))
        order = sorted(rank, key=rank.get, reverse=True)
        if diff > 0:
            stocked = [n for n in order if targets[n][0] > 0]
            # a total without any receipt layer gets a lot of its own
            name = (stocked or order or ["WV-P%d" % item.winvet_ref])[0]
            qty, expiry = targets.get(name, (0.0, False))
            targets[name] = (qty + diff, expiry)
            return targets
        missing = -diff
        for name in order:
            qty, expiry = targets[name]
            take = min(qty, missing)
            if take > 0:
                targets[name] = (float_round(qty - take, precision_rounding=PRECISION), expiry)
                missing = float_round(missing - take, precision_rounding=PRECISION)
        if not float_is_zero(missing, precision_rounding=PRECISION):
            warnings.append("Položka %s: záporný stav WinVetu %s oříznut na 0" % (label, _fmt(-missing)))
        return targets

    def _mirror_cost(self, product, layers, company):
        priced = [la for la in layers if la.unit_cost > 0]
        if not priced:
            return
        newest = max(priced, key=lambda la: (la.received or date.min, la.winvet_ref))
        cost = round(newest._untaxed_cost(), 4)
        product = product.with_company(company)
        if abs(product.standard_price - cost) > 1e-4:
            product.standard_price = cost

    def _mirror_quants(self, product, location, targets, lots, quants, company):
        """Set inventory_quantity on the quants of the product; returns the quants to apply."""
        Quant, Lot = self.env["stock.quant"].sudo(), self.env["stock.lot"].sudo()
        wanted = {}  # lot id -> quantity
        for name, (qty, expiry) in targets.items():
            lot = lots.get((product.id, name))
            expiration = datetime.combine(expiry, time(12, 0)) if expiry else False
            if not lot:
                if float_is_zero(qty, precision_rounding=PRECISION):
                    continue  # no empty lots for fully issued layers
                lot = Lot.create({"name": name, "product_id": product.id, "company_id": company.id,
                                  "expiration_date": expiration})
                lots[(product.id, name)] = lot
            elif lot.expiration_date != expiration:
                lot.expiration_date = expiration  # also cleared when WinVet has no expiry any more
            wanted[lot.id] = wanted.get(lot.id, 0.0) + qty
        changed = Quant
        for quant in quants:
            target = 0.0
            if quant.location_id == location and quant.lot_id.id in wanted:
                target = wanted.pop(quant.lot_id.id)
            if float_compare(quant.quantity, target, precision_rounding=PRECISION):
                quant.inventory_quantity = target
                changed |= quant
        for lot_id, qty in wanted.items():
            if float_is_zero(qty, precision_rounding=PRECISION):
                continue
            quant = Quant.create({"product_id": product.id, "location_id": location.id, "lot_id": lot_id})
            quant.inventory_quantity = qty
            changed |= quant
        return changed

    def _apply_quants(self, quants, warnings):
        """Apply the inventory of all quants at once; product by product when that fails."""
        if not quants:
            return 0
        ctx = {"inventory_mode": True, "set_inventory_quantity_auto_apply": True,
               "inventory_name": "Stav skladu z WinVetu"}
        try:
            with self.env.cr.savepoint():
                quants.with_context(**ctx).action_apply_inventory()
            return len(quants)
        except Exception:  # noqa: BLE001 - retry per product to keep the good ones
            self.env.invalidate_all()
        applied = 0
        for product in quants.product_id:
            group = quants.filtered(lambda q, p=product: q.product_id == p)
            try:
                with self.env.cr.savepoint():
                    group.with_context(**ctx).action_apply_inventory()
                applied += len(group)
            except Exception as exc:  # noqa: BLE001
                self.env.invalidate_all()
                _logger.warning("Elite Vet: inventory of product %s not applied: %s", product.id, exc)
                warnings.append("Produkt %s: stav skladu nenastaven (%s)" % (product.default_code or product.id,
                                                                             exc))
        return applied


class WinvetStockTotal(models.Model):
    _name = "elite.vet.winvet.stock.total"
    _description = "WinVet – stav skladu položky"
    _order = "item_id"

    winvet_ref = fields.Integer(string="WinVet ID", required=True, index=True, readonly=True)
    item_id = fields.Many2one("elite.vet.winvet.item", string="Položka", index=True, ondelete="set null",
                              readonly=True)
    item_winvet_ref = fields.Integer(string="WinVet ID položky", readonly=True)
    total = fields.Float(string="Stav celkem", digits="Product Unit of Measure", readonly=True)

    _sql_constraints = [("winvet_ref_unique", "unique(winvet_ref)", "Stav WinVetu už existuje.")]
