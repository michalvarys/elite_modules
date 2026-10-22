"""Goods receipt by barcode scanner (API of the OWL client action elite_vet_sale.goods_receipt).

The nurse picks a supplier, scans the goods (GS1 DataMatrix: product + lot + expiry; EAN or
another code: product, lot and expiry from the last receipt) and stocks them in: one incoming
picking on the main warehouse, done with lots, and one expense (elite.vet.expense) for it.
"""
from collections import OrderedDict, defaultdict
from datetime import datetime, time

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import float_round

from . import gs1

NURSE_GROUP = "elite_vet_clinic.group_clinic_nurse"
EXPENSE_RATES = (0, 12, 21)   # elite.vet.expense.vat_rate keys


class GoodsReceipt(models.AbstractModel):
    _name = "elite.vet.goods.receipt"
    _description = "Příjem zboží"

    # helpers --------------------------------------------------------------
    def _check_access(self):
        if not (self.env.su or self.env.user.has_group(NURSE_GROUP)):
            raise AccessError(_("Příjem zboží smí dělat jen sestra, lékařka nebo správce."))

    def _find_product(self, parsed):
        codes = gs1.lookup_codes(parsed["gtin"], parsed["raw"])
        if not codes:
            return self.env["product.product"]
        Product = self.env["product.product"]
        found = Product.search([("barcode", "in", codes), ("type", "=", "consu")])
        if not found:
            found = self.env["elite.vet.product.code"].sudo().search([("code", "in", codes)]).product_id
            found = Product.browse(found.filtered("active").ids)
        # the first form in lookup order wins (GTIN-14 before its EAN-13 form)
        for code in codes:
            for product in found:
                if product.barcode == code:
                    return product
        return found[:1]

    def _last_lot(self, product):
        """Lot of the last receipt of the product; without receipts the lot expiring last."""
        line = self.env["stock.move.line"].search([
            ("product_id", "=", product.id), ("lot_id", "!=", False), ("state", "=", "done"),
            ("picking_code", "=", "incoming")], order="date desc, id desc", limit=1)
        if line:
            return line.lot_id
        lots = self.env["stock.lot"].search([("product_id", "=", product.id)], order="id desc")
        return max(lots, key=lambda lot: lot.expiration_date or datetime.min, default=lots)

    def _purchase_tax(self, product):
        """Purchase VAT of the product. Its own supplier tax when one was set; the company
        default purchase tax every new product gets (21 %) does not count, the sale tax (the
        WinVet item rate, same rate for buying the goods) is closer for drugs at 12 %."""
        company = self.env.company
        product = product.sudo()
        supplier = product.supplier_taxes_id.filtered(lambda t: t.company_id == company)
        sale = product.taxes_id.filtered(lambda t: t.company_id == company)
        return (supplier - company.account_purchase_tax_id)[:1] or sale[:1] or supplier[:1]

    def _vat_rate(self, product):
        tax = self._purchase_tax(product)
        return float(tax.amount) if tax and tax.amount_type == "percent" else 0.0

    def _product_data(self, product):
        return {"id": product.id, "name": product.name, "code": product.default_code or "",
                "tracking": product.tracking}

    def _scan_result(self, parsed, product):
        lot, expiry = parsed["lot"], parsed["expiry"]
        res = {"product": None, "lot": lot, "expiry": expiry.isoformat() if expiry else None,
               "known": bool(product), "suggested_cost": 0.0, "vat_rate": 0.0,
               "expired": bool(expiry and expiry < fields.Date.context_today(self))}
        if not product:
            return res
        if product.tracking == "none":
            lot = None
        elif lot:
            if not expiry:
                existing = self.env["stock.lot"].search([("product_id", "=", product.id), ("name", "=", lot)],
                                                        limit=1)
                expiry = existing.expiration_date and existing.expiration_date.date()
        else:
            last = self._last_lot(product)
            lot = last.name or None
            expiry = expiry or (last.expiration_date and last.expiration_date.date())
        res.update({
            "product": self._product_data(product), "lot": lot,
            "expiry": expiry.isoformat() if expiry else None,
            "suggested_cost": product.sudo().with_company(self.env.company).standard_price,
            "vat_rate": self._vat_rate(product),
            "expired": bool(expiry and expiry < fields.Date.context_today(self)),
        })
        return res

    # API ------------------------------------------------------------------
    @api.model
    def init_data(self):
        """Start of the screen: {winvet_master} (trial run banner, ruling R14)."""
        self._check_access()
        return {"winvet_master": self.env["elite.vet.sale.setup"].is_winvet_master()}

    @api.model
    def scan(self, code):
        """Scanned code -> {product, lot, expiry, known, suggested_cost, vat_rate}."""
        self._check_access()
        parsed = gs1.parse(code)
        return self._scan_result(parsed, self._find_product(parsed))

    @api.model
    def assign_code(self, code, product_id):
        """Remember an unknown code for a product (the GTIN of a GS1 code) -> scan(code)."""
        self._check_access()
        parsed = gs1.parse(code)
        key = parsed["gtin"] or parsed["raw"]
        product = self.env["product.product"].browse(int(product_id)).exists()
        if not key or not product:
            raise UserError(_("Chybí kód nebo produkt."))
        Code = self.env["elite.vet.product.code"].sudo()
        existing = Code.search([("code", "=", key)], limit=1)
        if existing:
            existing.product_id = product
        else:
            Code.create({"code": key, "product_id": product.id})
        return self._scan_result(parsed, product)

    @api.model
    def search_products(self, term, limit=20):
        """Goods for assigning an unknown code: by name, internal reference or barcode."""
        self._check_access()
        term = (term or "").strip()
        domain = [("type", "=", "consu")]
        if term:
            domain += ["|", "|", ("name", "ilike", term), ("default_code", "ilike", term),
                       ("barcode", "ilike", term)]
        products = self.env["product.product"].search(domain, limit=limit, order="name, id")
        return [dict(self._product_data(p), barcode=p.barcode or "") for p in products]

    @api.model
    def suppliers(self, term="", limit=20):
        """Suppliers, recent first: partners of done receipts (last receipt first), then
        partners named like the suppliers of the WinVet receipts (most used first); with a
        term also any other company whose name contains it."""
        self._check_access()
        term = (term or "").strip()
        Partner = self.env["res.partner"]
        groups = self.env["stock.picking"]._read_group(
            [("picking_type_code", "=", "incoming"), ("state", "=", "done"), ("partner_id", "!=", False),
             ("company_id", "=", self.env.company.id)],
            ["partner_id"], ["date_done:max"], order="date_done:max desc", limit=50)
        recent = OrderedDict((partner.commercial_partner_id.id, True) for partner, _date in groups)
        layers = self.env["elite.vet.winvet.stock.layer"].sudo()._read_group(
            [("supplier", "!=", False)], ["supplier"], ["__count"], order="__count desc", limit=30)
        for name, _count in layers:
            partner = Partner.search([("name", "=ilike", name.strip())], order="is_company desc, id", limit=1)
            if partner:
                recent.setdefault(partner.id, True)
        result = []
        for partner in Partner.browse(list(recent)).exists().filtered("active"):
            if not term or term.casefold() in (partner.name or "").casefold():
                result.append({"id": partner.id, "name": partner.name, "recent": True})
        if term and len(result) < limit:
            others = Partner.search([("is_company", "=", True), ("name", "ilike", term),
                                     ("id", "not in", list(recent))], limit=limit - len(result), order="name")
            result += [{"id": p.id, "name": p.name, "recent": False} for p in others]
        return result[:limit]

    @api.model
    def create_supplier(self, name):
        """Quick supplier by name only (an existing company of that name is reused)."""
        self._check_access()
        name = " ".join((name or "").split())
        if not name:
            raise UserError(_("Zadejte název dodavatele."))
        Partner = self.env["res.partner"].sudo()
        partner = Partner.search([("name", "=ilike", name), ("is_company", "=", True)], limit=1)
        if not partner:
            partner = Partner.create({"name": name, "is_company": True, "supplier_rank": 1})
        return {"id": partner.id, "name": partner.name, "recent": False}

    @api.model
    def validate(self, supplier_id, lines, document_number=None):
        """Stock the lines in -> {picking_id, picking_name, expense_id}.

        lines: [{product_id, lot, expiry ("YYYY-MM-DD" or None), quantity, unit_cost (untaxed)}].
        Lines of the same product and lot are added up."""
        self._check_access()
        company = self.env.company
        supplier = self.env["res.partner"].browse(int(supplier_id or 0)).exists()
        if not supplier:
            raise UserError(_("Vyberte dodavatele."))
        groups = self._group_lines(lines)
        if not groups:
            raise UserError(_("Není co naskladnit."))
        warehouse = self.env["stock.warehouse"].search([("company_id", "=", company.id)], limit=1)
        picking_type = warehouse.in_type_id
        if not picking_type:
            raise UserError(_("Sklad nemá typ operace pro příjem."))
        src = picking_type.default_location_src_id or self.env.ref("stock.stock_location_suppliers")
        dest = picking_type.default_location_dest_id or warehouse.lot_stock_id
        document_number = (document_number or "").strip() or False

        # One move per product (Odoo merges moves of the same product on confirm anyway),
        # one move line per lot.
        by_product, last_cost = OrderedDict(), {}
        for (product, lot_name), group in groups.items():
            lot = self._ensure_lot(product, lot_name, group["expiry"], company) if lot_name else False
            entry = by_product.setdefault(product, {"quantity": 0.0, "cost": 0.0, "lots": []})
            entry["quantity"] += group["quantity"]
            entry["cost"] += group["cost"]
            entry["lots"].append((lot, group["quantity"]))
            if group["last_cost"] > 0:
                last_cost[product] = group["last_cost"]  # free goods keep the cost
        # Standard cost: the receipt is valued at standard_price, so it is set first (AVCO/FIFO
        # categories compute it from the move price themselves).
        for product, cost in last_cost.items():
            product = product.sudo().with_company(company)
            if product.cost_method == "standard" and abs(product.standard_price - cost) > 1e-6:
                product.standard_price = cost
        picking = self.env["stock.picking"].create({
            "picking_type_id": picking_type.id, "partner_id": supplier.id, "origin": document_number,
            "location_id": src.id, "location_dest_id": dest.id, "company_id": company.id,
            "move_ids": [(0, 0, {
                "name": product.display_name, "product_id": product.id, "product_uom": product.uom_id.id,
                "product_uom_qty": entry["quantity"], "price_unit": entry["cost"] / entry["quantity"],
                "location_id": src.id, "location_dest_id": dest.id, "company_id": company.id,
            }) for product, entry in by_product.items()],
        })
        picking.action_confirm()
        for product, entry in by_product.items():
            move = picking.move_ids.filtered(lambda m, p=product: m.product_id == p)
            move.move_line_ids.unlink()
            move[:1].write({"move_line_ids": [(0, 0, {
                "product_id": product.id, "product_uom_id": move[:1].product_uom.id,
                "lot_id": lot.id if lot else False, "quantity": quantity,
                "location_id": src.id, "location_dest_id": dest.id, "picking_id": picking.id,
            }) for lot, quantity in entry["lots"]]})
        picking.move_ids.picked = True
        res = picking.with_context(skip_backorder=True, skip_expired=True, skip_sms=True,
                                   picking_ids_not_to_backorder=picking.ids).button_validate()
        if picking.state != "done":
            raise UserError(_("Příjemku %(name)s se nepodařilo dokončit (%(res)s).", name=picking.name, res=res))
        # Trial run (ruling R14): WinVet still leads the stock, the next mirror run overwrites this
        # receipt and the purchase is in WinVet's books -> no expense.
        winvet_master = self.env["elite.vet.sale.setup"].is_winvet_master()
        expense = self.env["elite.vet.expense"]
        if not winvet_master:
            expense = self._create_expense(supplier, groups, picking, document_number)
        return {"picking_id": picking.id, "picking_name": picking.name, "expense_id": expense.id or False,
                "winvet_master": winvet_master}

    def _group_lines(self, lines):
        Product = self.env["product.product"]
        groups = OrderedDict()
        for line in lines or []:
            quantity = float(line.get("quantity") or 0.0)
            if quantity <= 0:
                continue
            product = Product.browse(int(line.get("product_id") or 0)).exists()
            if not product:
                raise UserError(_("Řádek bez produktu."))
            lot_name = (line.get("lot") or "").strip() if product.tracking != "none" else ""
            if product.tracking != "none" and not lot_name:
                raise UserError(_("Produkt %s vyžaduje šarži.", product.display_name))
            expiry = fields.Date.to_date(line.get("expiry")) if line.get("expiry") else None
            cost = max(float(line.get("unit_cost") or 0.0), 0.0)
            group = groups.setdefault((product, lot_name), {"quantity": 0.0, "cost": 0.0, "expiry": None,
                                                            "last_cost": 0.0})
            group["quantity"] += quantity
            group["cost"] += quantity * cost
            group["expiry"] = expiry or group["expiry"]
            if cost > 0:
                group["last_cost"] = cost
        return groups

    def _ensure_lot(self, product, name, expiry, company):
        Lot = self.env["stock.lot"]
        expiration = datetime.combine(expiry, time(12, 0)) if expiry else False
        lot = Lot.search([("product_id", "=", product.id), ("name", "=", name),
                          ("company_id", "in", [company.id, False])], limit=1)
        if not lot:
            return Lot.create({"name": name, "product_id": product.id, "company_id": company.id,
                               "expiration_date": expiration})
        if expiration and lot.expiration_date != expiration:
            lot.expiration_date = expiration
        return lot

    def _create_expense(self, supplier, groups, picking, document_number):
        currency = self.env.ref("base.CZK")
        by_rate = defaultdict(float)
        for (product, _lot), group in groups.items():
            rate = self._vat_rate(product)
            by_rate[rate] += group["cost"] * (1 + rate / 100.0)
        amount = currency.round(sum(by_rate.values()))
        if amount <= 0:
            return self.env["elite.vet.expense"]  # free goods (samples): nothing paid
        main_rate = max(by_rate.items(), key=lambda item: (float_round(item[1], 2), item[0]))[0]
        vat_key = str(min(EXPENSE_RATES, key=lambda r: abs(r - main_rate)))
        today = fields.Date.context_today(self)
        return self.env["elite.vet.expense"].sudo().create({
            "name": _("Příjem zboží %(supplier)s %(date)s", supplier=supplier.name,
                      date="%d. %d. %d" % (today.day, today.month, today.year)),
            "date": today,
            "category_id": self.env.ref("elite_vet_winvet.expense_category_drugs").id,
            "amount": amount,
            "vat_rate": vat_key,
            "supplier_id": supplier.id,
            "document_number": document_number,
            "picking_id": picking.id,
        })
