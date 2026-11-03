import csv
import logging
from collections import defaultdict

from odoo import api, models
from odoo.exceptions import UserError
from odoo.tools.misc import file_path

_logger = logging.getLogger(__name__)

MODULE = "elite_trafika_dotykacka"
POS_CONFIG = "elite_trafika_pos.pos_config_trafika"
PAYMENT_METHODS = {
    "cash": "elite_trafika_pos.pos_payment_method_cash",
    "card": "elite_trafika_pos.pos_payment_method_card",
}
ORDER_PREFIX = "Dotykačka "
BATCH = 50  # shifts per flush


class EliteTrafikaDotykackaImport(models.AbstractModel):
    _name = "elite.trafika.dotykacka.import"
    _description = "Elite Trafika – historie a sklad z Dotykačky"

    # ------------------------------------------------------------------ public API (data/import.xml)

    @api.model
    def import_history(self):
        """Shifts and receipts of Dotykačka as closed sessions and posted orders of the Trafika till.

        The orders stay outside accounting and stock: the sessions are closed directly, without the
        session closing that would post journal entries and create the stock pickings (the sales
        were booked from Dotykačka already). Safe to call again: shifts already imported are skipped."""
        config = self.env.ref(POS_CONFIG).sudo()
        company = config.company_id
        Session = self.env["pos.session"].sudo().with_company(company)
        Order = self.env["pos.order"].sudo().with_company(company)
        if Session.search_count([("config_id", "=", config.id), ("state", "!=", "closed")]):
            raise UserError("Elite Trafika – Dotykačka: pokladna %s má otevřenou směnu; historii lze nahrát "
                            "jen do pokladny bez otevřené směny." % config.name)
        methods = {key: self.env.ref(xmlid).sudo() for key, xmlid in PAYMENT_METHODS.items()}
        tax = self.env["elite.trafika.pos.setup"].sale_tax(company.root_id)
        user = self.env.ref("base.user_admin")

        receipts = defaultdict(list)
        for row in self._read("uctenky.csv"):
            receipts[row["smena"]].append(row)
        lines, payments = defaultdict(list), defaultdict(list)
        for row in self._read("polozky.csv"):
            lines[row["doklad"]].append(row)
        for row in self._read("platby.csv"):
            payments[row["doklad"]].append(row)
        products = {}

        def product(xmlid):
            if xmlid not in products:
                ref = xmlid if "." in xmlid else "%s.%s" % (MODULE, xmlid)
                template = self.env.ref(ref).sudo().with_context(active_test=False)
                products[xmlid] = template.product_variant_ids[:1]
            return products[xmlid]

        done = set(Order.search([("config_id", "=", config.id), ("name", "=like", ORDER_PREFIX + "%")]).mapped(
            "pos_reference"))
        balance, created = 0.0, 0
        for count, shift in enumerate(self._read("smeny.csv"), 1):
            shift_receipts = [r for r in receipts[shift["smena"]] if r["doklad"] not in done]
            closing_cash = float(shift["hotovost_pri_uzavreni"])
            if not shift_receipts:
                balance = closing_cash
                continue
            session = Session.create({"config_id": config.id, "user_id": user.id})
            session.write({"state": "closed", "start_at": shift["otevreno"], "stop_at": shift["uzavreno"],
                           "cash_register_balance_start": balance,
                           "cash_register_balance_end_real": closing_cash})
            balance = closing_cash
            vals_list = []
            for receipt in shift_receipts:
                order_lines = [(0, 0, {
                    "product_id": product(line["produkt"]).id,
                    "full_product_name": line["nazev"],
                    "qty": float(line["mnozstvi"]),
                    "price_unit": float(line["cena_s_dph"]),
                    "price_subtotal": float(line["celkem_bez_dph"]),
                    "price_subtotal_incl": float(line["celkem_s_dph"]),
                    "tax_ids": [(6, 0, tax.ids)],
                }) for line in lines[receipt["doklad"]]]
                order_payments = [(0, 0, {
                    "payment_method_id": methods[pay["platba"]].id,
                    "amount": float(pay["castka"]),
                    "payment_date": receipt["datum"],
                }) for pay in payments[receipt["doklad"]]]
                total = float(receipt["celkem"])
                untaxed = sum(float(line["celkem_bez_dph"]) for line in lines[receipt["doklad"]])
                vals_list.append({
                    "session_id": session.id,
                    "name": ORDER_PREFIX + receipt["doklad"],
                    "pos_reference": receipt["doklad"],
                    "date_order": receipt["datum"],
                    "user_id": user.id,
                    "amount_total": total,
                    "amount_tax": round(total - untaxed, 2),
                    "amount_paid": sum(float(p["castka"]) for p in payments[receipt["doklad"]]),
                    "amount_return": 0.0,
                    "state": "paid",
                    "general_note": "Dotykačka, obsluha: %s" % receipt["obsluha"],
                    "lines": order_lines,
                    "payment_ids": order_payments,
                })
            orders = Order.create(vals_list)
            orders.write({"state": "done"})
            created += len(orders)
            if count % BATCH == 0:
                self.env.flush_all()
                self.env.invalidate_all()
                _logger.info("Elite Trafika: Dotykačka history, %d orders imported", created)
        _logger.info("Elite Trafika: Dotykačka history imported, %d orders", created)
        return created

    @api.model
    def import_stock(self):
        """Opening stock of the Trafika warehouse from Dotykačka (quantities only: Dotykačka has no
        purchase prices). Products that already have stock in the warehouse are left as they are."""
        config = self.env.ref(POS_CONFIG).sudo()
        company = config.company_id
        location = config.picking_type_id.warehouse_id.lot_stock_id or config.picking_type_id.default_location_src_id
        Quant = self.env["stock.quant"].sudo().with_company(company).with_context(inventory_mode=True)
        quants = Quant
        for row in self._read("sklad.csv"):
            variant = self.env.ref(row["produkt"]).sudo().product_variant_id
            if Quant.search_count([("product_id", "=", variant.id), ("location_id", "child_of", location.id)]):
                continue
            quants |= Quant.create({"product_id": variant.id, "location_id": location.id,
                                    "inventory_quantity": float(row["mnozstvi"])})
        if quants:
            quants.action_apply_inventory()
        _logger.info("Elite Trafika: opening stock from Dotykačka set for %d products", len(quants))
        return len(quants)

    # ------------------------------------------------------------------ helpers

    @api.model
    def _read(self, name):
        with open(file_path("%s/data/dotykacka/%s" % (MODULE, name)), encoding="utf-8") as f:
            return list(csv.DictReader(f))
