from odoo import api, fields, models


class ProductProduct(models.Model):
    _inherit = "product.product"

    stock_below_minimum = fields.Boolean(
        string="Dochází", compute="_compute_stock_below_minimum", search="_search_stock_below_minimum",
        help="Stav na skladě je pod minimem z pravidla doplnění, nebo je záporný (prodáno bez stavu).")

    @api.model
    def _below_minimum_ids(self):
        """Products whose on-hand quantity in an orderpoint's location is below its minimum, and
        products with a negative quantity in an internal location (sold without stock)."""
        ids = set()
        orderpoints = self.env["stock.warehouse.orderpoint"].sudo().search(
            [("product_id.active", "=", True)])
        for orderpoint in orderpoints:
            if orderpoint.qty_on_hand < orderpoint.product_min_qty:
                ids.add(orderpoint.product_id.id)
        negative = self.env["stock.quant"].sudo()._read_group(
            [("location_id.usage", "=", "internal")], ["product_id"], having=[("quantity:sum", "<", 0)])
        ids.update(product.id for (product,) in negative)
        return ids

    def _compute_stock_below_minimum(self):
        ids = self._below_minimum_ids() if self else set()
        for product in self:
            product.stock_below_minimum = product.id in ids

    def _search_stock_below_minimum(self, operator, value):
        ids = list(self._below_minimum_ids())
        positive = (operator in ("=", "in")) == bool(value)
        return [("id", "in" if positive else "not in", ids)]
