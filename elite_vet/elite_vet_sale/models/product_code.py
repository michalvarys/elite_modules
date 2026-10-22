from odoo import fields, models


class ProductCode(models.Model):
    """Extra codes of a product for the scanner (supplier codes, GTINs the product has no
    barcode for). Assigned once in the goods receipt, a product may have several."""
    _name = "elite.vet.product.code"
    _description = "Kód produktu pro čtečku"
    _order = "product_id, code"
    _rec_name = "code"

    code = fields.Char(string="Kód", required=True, index=True,
                       help="GTIN z kódu GS1 (bez šarže a expirace) nebo jiný naskenovaný kód.")
    product_id = fields.Many2one("product.product", string="Produkt", required=True, index=True,
                                 ondelete="cascade")

    _sql_constraints = [("code_uniq", "unique(code)", "Tento kód už je přiřazený jinému produktu.")]
