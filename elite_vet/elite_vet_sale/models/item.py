import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class WinvetItem(models.Model):
    _inherit = "elite.vet.winvet.item"

    product_id = fields.Many2one("product.product", string="Produkt", readonly=True, copy=False,
                                 ondelete="set null", index="btree_not_null",
                                 help="Produkt v Odoo (pokladna, nabídky, sklad) vytvořený z této položky ceníku.")

    # ------------------------------------------------------------------ product sync

    def write(self, vals):
        res = super().write(vals)
        if "active" in vals and self.env["elite.vet.sale.setup"].is_winvet_master():
            for item in self.filtered("product_id"):
                if item.product_id.active != item.active:
                    item.product_id.sudo().with_context(active_test=False).active = item.active
        return res

    def _sync_products(self, errors=None):
        """Create or update the product of every item; one bad item never stops the others."""
        for item in self:
            try:
                with self.env.cr.savepoint():
                    item._sync_product()
            except Exception as exc:  # noqa: BLE001 - keep the batch going
                self.env.invalidate_all()
                _logger.warning("Elite Vet: product of price list item %s (%s) not synced: %s",
                                item.code, item.winvet_ref, exc)
                if errors is not None:
                    errors.append("elite.vet.winvet.item %s (%s): %s" % (item.winvet_ref, item.code, exc))

    def _sync_product(self):
        self.ensure_one()
        if self.kind not in ("service", "product"):
            return  # groups, aliases and the like are not sold
        Product = self.env["product.product"].sudo().with_context(active_test=False)
        product = self.product_id.sudo().with_context(active_test=False)
        if not product:
            if not self.active:
                return
            product = Product.create(self._product_vals(Product))
            self.sudo().write({"product_id": product.id})
            return
        if not self.env["elite.vet.sale.setup"].is_winvet_master():
            return  # Odoo leads now: price, tax and the rest are no longer overwritten
        vals = self._product_vals(product)
        company = self.env.company
        tax_ids = vals.pop("taxes_id")
        categ_ids = vals.pop("pos_categ_ids")
        diff = {}
        # The name is translatable: keep every installed language in step with WinVet.
        name = vals.pop("name")
        for lang, _label in self.env["res.lang"].get_installed():
            if product.with_context(lang=lang).name != name:
                product.with_context(lang=lang).write({"name": name})
        for name, value in vals.items():
            current = product[name]
            current = current.id if hasattr(current, "id") else current
            if current != value:
                diff[name] = value
        current_taxes = product.taxes_id.filtered(lambda t: t.company_id == company)
        if set(current_taxes.ids) != set(tax_ids):
            diff["taxes_id"] = [(3, t.id) for t in current_taxes if t.id not in tax_ids] \
                + [(4, t_id) for t_id in tax_ids if t_id not in current_taxes.ids]
        if set(product.pos_categ_ids.ids) != set(categ_ids):
            diff["pos_categ_ids"] = [(6, 0, categ_ids)]
        if diff:
            product.write(diff)

    def _product_vals(self, product):
        """Values of the product for this item; `product` is the existing one or an empty recordset."""
        self.ensure_one()
        setup = self.env["elite.vet.sale.setup"]
        category = self.env.ref("elite_vet_sale.pos_category_%s" % ("services" if self.kind == "service"
                                                                     else "products"))
        unit = self.env.ref("uom.product_uom_unit")
        storable = self.kind == "product" and self.stock_tracked
        vals = {
            "name": self.name,
            "default_code": self.code or False,
            "type": "service" if self.kind == "service" else "consu",
            "is_storable": storable,
            "tracking": "lot" if storable else "none",
            "use_expiration_date": storable,
            "list_price": self.price or 0.0,
            "sale_ok": True,
            "available_in_pos": True,
            "uom_id": unit.id,
            "uom_po_id": unit.id,
            "active": bool(self.active),
            "pos_categ_ids": [category.id],
            "taxes_id": [setup.tax_for_rate(self.vat_rate or 0.0).id],
        }
        barcode = self.barcode
        if barcode and product.barcode != barcode:
            clash = self.env["product.product"].sudo().with_context(active_test=False).search_count(
                [("barcode", "=", barcode), ("id", "!=", product.id)], limit=1)
            if clash:
                _logger.info("Elite Vet: barcode %s of item %s is used by another product", barcode, self.code)
            else:
                vals["barcode"] = barcode
        if not product:
            vals["taxes_id"] = [(6, 0, vals["taxes_id"])]
            vals["pos_categ_ids"] = [(6, 0, vals["pos_categ_ids"])]
        return vals
