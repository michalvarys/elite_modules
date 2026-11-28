import base64
import csv
import datetime
import json
import logging
import zoneinfo

from odoo import api, models
from odoo.exceptions import UserError
from odoo.tools import float_compare
from odoo.tools.misc import file_path

_logger = logging.getLogger(__name__)

MODULE = "elite_restaurant_pos"
CHART = "cz"
STANDARD_RATE = 21.0
REDUCED_RATE = 12.0
# Sale taxes of l10n_cz by rate (template xmlids, prefixed with the company id by the chart template).
CZ_SALE_TAX_XMLIDS = {
    21.0: "l10n_cz_21_domestic_supplies",
    12.0: "l10n_cz_12_domestic_supplies",
}
CUSTOM_TAX_NAME = "%d %% DPH (cena s DPH)"
# Non-alcoholic drinks served in a restaurant: 21 % until 31. 12. 2026, 12 % from 1. 1. 2027 (law 180/2026 Sb.).
SOFT_DRINK_REDUCED_FROM = datetime.date(2027, 1, 1)
PRAGUE = zoneinfo.ZoneInfo("Europe/Prague")
TABLES_PER_ROW = 4


class EliteRestaurantPosSetup(models.AbstractModel):
    _name = "elite.restaurant.pos.setup"
    _description = "Elite – nastavení restaurační pokladny, skladu a účetnictví"

    # ------------------------------------------------------------------ public API (data/setup.xml of a restaurant)

    @api.model
    def ensure_setup(self, config):
        """Set up the till of one restaurant from its module; safe to call repeatedly.

        config: module (the restaurant module, holds zbozi.csv), company, parent (name of the company the
        restaurant is a branch of, or False), pos_name, code (short code for the warehouse and journals),
        floor (name of the dining room), tables (number of tables created with the till); or floors = True
        for the floors, tables and floor plans of floors.json in the restaurant module.

        Only adds what is missing: values the companies already have (chart of accounts, price settings,
        warehouse, journals, an existing till) are left as they are; other companies are not touched."""
        module = config["module"]
        company = self._ensure_company(config["company"], config.get("parent"))
        root = company.root_id
        self = self.sudo().with_company(company)
        self._block_auto_chart()
        self._ensure_chart(company)
        self.env["res.lang"]._activate_lang("cs_CZ")
        standard = self.sale_tax(root)
        for accounting_company in root | company:
            if not accounting_company.account_sale_tax_id:
                accounting_company.account_sale_tax_id = standard
        self._ensure_products(module, company)
        self._ensure_pos(module, company, config)

    @api.model
    def sale_tax(self, company, rate=STANDARD_RATE):
        """Sale tax of `rate` % with the price including the tax; `company` owns the taxes (the root
        company of a branch). A copy including tax is made when the company's tax excludes it."""
        company = company.sudo()
        Tax = self.env["account.tax"].sudo().with_company(company).with_context(active_test=False)
        chart_tax = self.env["account.chart.template"].sudo().with_company(company).ref(
            CZ_SALE_TAX_XMLIDS[rate], raise_if_not_found=False)
        if chart_tax and (chart_tax.company_id != company or chart_tax.type_tax_use != "sale"
                          or float_compare(chart_tax.amount, rate, precision_digits=4)):
            chart_tax = Tax
        if chart_tax and chart_tax.active and chart_tax.price_include:
            return chart_tax
        name = CUSTOM_TAX_NAME % rate
        tax = Tax.search([("company_id", "=", company.id), ("type_tax_use", "=", "sale"),
                          ("amount_type", "=", "percent"), ("amount", "=", rate), ("name", "=", name)], limit=1)
        if tax:
            if not tax.active:
                tax.active = True
            return tax
        _logger.info("Elite restaurace: creating sale tax %s for %s", name, company.name)
        if chart_tax:
            return chart_tax.copy({"name": name, "active": True, "price_include_override": "tax_included"})
        return Tax.create({"name": name, "type_tax_use": "sale", "amount_type": "percent", "amount": rate,
                           "company_id": company.id, "invoice_label": "%d%% DPH" % rate,
                           "price_include_override": "tax_included",
                           "country_id": company.account_fiscal_country_id.id or company.country_id.id})

    @api.model
    def soft_drink_rate(self, day=None):
        day = day or datetime.datetime.now(PRAGUE).date()
        return REDUCED_RATE if day >= SOFT_DRINK_REDUCED_FROM else STANDARD_RATE

    @api.model
    def _cron_soft_drink_vat(self):
        """On 1. 1. 2027 non-alcoholic drinks served on site move from 21 % to 12 %. Products tagged by a
        restaurant module get the reduced tax of their company; the job then switches itself off."""
        if self.soft_drink_rate() != REDUCED_RATE:
            return
        tag = self.env.ref("%s.tag_soft_drink" % MODULE)
        templates = self.env["product.template"].sudo().with_context(active_test=False).search(
            [("product_tag_ids", "in", tag.ids)])
        for template in templates:
            if template.company_id:
                self._set_tax(template, template.company_id.root_id, REDUCED_RATE)
        _logger.info("Elite restaurace: %d non-alcoholic drinks moved to %d %% VAT", len(templates), REDUCED_RATE)
        self.env.ref("%s.cron_soft_drink_vat" % MODULE).sudo().active = False

    # ------------------------------------------------------------------ steps

    def _ensure_company(self, name, parent_name):
        """The restaurant's company; created (as a branch of `parent_name` when given) when missing.
        The admin and the installing user get access to it."""
        Company = self.env["res.company"].sudo()
        companies = Company.search([("name", "=", name)])
        if len(companies) > 1:
            raise UserError("Restaurace: firma „%s“ je v databázi víckrát. Instalace nic nezměnila." % name)
        if companies:
            return companies
        parent = Company
        if parent_name:
            parent = Company.search([("name", "=", parent_name)])
            if len(parent) != 1:
                raise UserError("Restaurace: mateřská firma „%s“ v databázi %s. Instalace nic nezměnila; název "
                                "je v data/setup.xml." % (parent_name, "není" if not parent else "je víckrát"))
        _logger.info("Elite restaurace: creating company %s%s", name, " (branch of %s)" % parent.name if parent else "")
        company = Company.create({
            "name": name, "parent_id": parent.id, "country_id": self.env.ref("base.cz").id,
            "currency_id": self.env.ref("base.CZK").id,
        })
        users = self.env.ref("base.user_admin") | self.env.user
        users.sudo().write({"company_ids": [(4, company.id)]})
        return company

    def _block_auto_chart(self):
        """Installing `account` queues a chart of accounts for the main company of the database at the end
        of the registry load; that company is not the restaurant's, so it keeps its state."""
        pending = getattr(self.env.registry, "_auto_install_template", None)
        if pending and not getattr(pending, "_elite_blocked", False):
            def skip(env):
                _logger.info("Elite restaurace: automatic chart of accounts for %s skipped", env.company.name)
            skip._elite_blocked = True
            self.env.registry._auto_install_template = skip

    def _ensure_chart(self, company):
        """Czech chart for the root company first (it holds the accounts and the taxes), then for the branch."""
        root = company.root_id
        for target in (root | company).sorted(lambda c: c != root):
            if target.chart_template:
                if target.chart_template != CHART:
                    _logger.warning("Elite restaurace: company %s keeps its chart %s (not the Czech one).",
                                    target.name, target.chart_template)
                continue
            if not target.root_id._existing_accounting():
                target.account_price_include = "tax_included"
            _logger.info("Elite restaurace: loading the Czech chart of accounts for %s", target.name)
            self.env["account.chart.template"].sudo().try_loading(CHART, target, install_demo=False)

    def _ensure_products(self, module, company):
        """Company and VAT of the menu items: food 12 %, alcohol 21 %, non-alcoholic drinks by
        soft_drink_rate(). Rates follow zbozi.csv on every module update."""
        root = company.root_id
        tag = self.env.ref("%s.tag_soft_drink" % MODULE)
        for row in self._menu(module):
            template = self.env.ref("%s.product_%s" % (module, row["kod"])).sudo()
            if not template.company_id:
                template.company_id = company
            kind = row["dph"]
            rate = REDUCED_RATE if kind == "jidlo" else self.soft_drink_rate() if kind == "nealko" else STANDARD_RATE
            self._set_tax(template, root, rate)
            if kind == "nealko" and tag not in template.product_tag_ids:
                template.product_tag_ids = [(4, tag.id)]

    def _set_tax(self, template, tax_company, rate):
        """`rate` % of `tax_company` on the product. Taxes of companies outside it go too: a product
        created during the install gets the default tax of the installing user's company."""
        tax = self.sale_tax(tax_company, rate)
        stale = template.taxes_id.filtered(lambda t: t.company_id.root_id != tax_company or t.company_id == tax_company)
        if template.taxes_id.filtered(lambda t: t.company_id == tax_company) != tax or stale - tax:
            template.taxes_id = [(3, t.id) for t in stale - tax] + [(4, tax.id)]

    def _ensure_pos(self, module, company, config):
        pos_name = config.get("pos_name") or company.name
        floors, new_floors = self._floors(module, config, pos_name)
        till = self.env.ref("%s.pos_config" % module, raise_if_not_found=False)
        if till:
            # the till's settings belong to the staff now; only floors added to floors.json are added to it
            if new_floors:
                till.sudo().floor_ids = [(4, floor.id) for floor in new_floors]
            return
        code = config["code"]
        warehouse = self._warehouse(company, code, pos_name)
        if not warehouse.pos_type_id:
            self.env["stock.warehouse"].sudo()._create_missing_pos_picking_types()
        Journal = self.env["account.journal"].sudo().with_company(company)
        # journals of the root company serve its branches as well
        bank_journal = Journal.search([("company_id", "parent_of", company.id), ("type", "=", "bank")],
                                      order="sequence, id", limit=1)
        if not bank_journal:
            bank_journal = Journal.create({"name": "Banka", "type": "bank", "code": self._journal_code(code, "B"),
                                           "company_id": company.id})
        methods = self._find_or_create(module, "pos_payment_method_cash", "pos.payment.method", company, "Hotově",
                                       lambda: {"name": "Hotově", "company_id": company.id,
                                                "journal_id": self._free_cash_journal(company, code, pos_name).id})
        methods |= self._find_or_create(module, "pos_payment_method_card", "pos.payment.method", company, "Kartou",
                                        lambda: {"name": "Kartou", "company_id": company.id,
                                                 "journal_id": bank_journal.id, "payment_method_type": "none",
                                                 "use_payment_terminal": False})
        invoice_journal = Journal.search([("company_id", "parent_of", company.id), ("type", "=", "sale")],
                                         order="sequence, id", limit=1)
        categories = self._module_records(module, "pos.category").filtered(lambda c: not c.parent_id)
        self._find_or_create(module, "pos_config", "pos.config", company, pos_name, lambda: {
            "name": pos_name, "company_id": company.id, "picking_type_id": warehouse.pos_type_id.id,
            "payment_method_ids": [(6, 0, methods.ids)], "invoice_journal_id": invoice_journal.id,
            "module_pos_restaurant": True, "floor_ids": [(6, 0, floors.ids)],
            "iface_printbill": True, "iface_splitbill": True,
            "limit_categories": True, "iface_available_categ_ids": [(6, 0, categories.ids)]})

    def _warehouse(self, company, code, name):
        """The restaurant's own warehouse (each restaurant stocks its floor separately)."""
        Warehouse = self.env["stock.warehouse"].sudo().with_company(company)
        warehouse = Warehouse.search([("company_id", "=", company.id)], order="sequence, id", limit=1)
        if warehouse:
            return warehouse
        _logger.info("Elite restaurace: creating warehouse %s for %s", code, company.name)
        return Warehouse.create({"name": name, "code": code[:5], "company_id": company.id,
                                 "partner_id": company.partner_id.id})

    def _floors(self, module, config, pos_name):
        """Floors of the till and those of them created now. Each floor is created once (known by its
        xml id); tables moved or added in Odoo stay as they are."""
        if not config.get("floors"):
            floor = self.env.ref("%s.restaurant_floor" % module, raise_if_not_found=False)
            if floor:
                return floor, floor.browse()
            floor = self._create_floor(module, "restaurant_floor", {"name": config.get("floor") or pos_name}, [{
                "table_number": number, "seats": 4, "shape": "square",
                "position_h": 50 + ((number - 1) % TABLES_PER_ROW) * 180,
                "position_v": 50 + ((number - 1) // TABLES_PER_ROW) * 180,
                "width": 120, "height": 120,
            } for number in range(1, int(config.get("tables") or 0) + 1)])
            return floor, floor
        with open(file_path("%s/floors.json" % module), encoding="utf-8") as f:
            layout = json.load(f)
        Floor = self.env["restaurant.floor"].sudo()
        floors = new_floors = Floor.browse()
        for sequence, plan in enumerate(layout["floors"], start=1):
            xmlid = "restaurant_floor_%s" % plan["key"]
            floor = self.env.ref("%s.%s" % (module, xmlid), raise_if_not_found=False)
            if not floor:
                floor = self._create_floor(module, xmlid, {
                    "name": plan["name"], "sequence": sequence, "background_color": plan.get("background"),
                    "floor_background_image": self._module_file(module, "static/img/floor_%s.png" % plan["key"]),
                }, [{
                    "table_number": table["number"], "seats": table.get("seats", 4),
                    "shape": table.get("shape", "square"), "color": layout.get("table_color", "#35D374"),
                    "position_h": table["box"][0], "position_v": table["box"][1],
                    "width": table["box"][2], "height": table["box"][3],
                } for table in plan["tables"]])
                new_floors |= floor
            floors |= floor
        return floors, new_floors

    def _create_floor(self, module, xmlid, vals, tables):
        floor = self.env["restaurant.floor"].sudo().create(vals)
        self.env["restaurant.table"].sudo().create([dict(table, floor_id=floor.id) for table in tables])
        self.env["ir.model.data"].sudo()._update_xmlids(
            [{"xml_id": "%s.%s" % (module, xmlid), "record": floor, "noupdate": True}])
        return floor

    def _module_file(self, module, path):
        try:
            with open(file_path("%s/%s" % (module, path)), "rb") as f:
                return base64.b64encode(f.read())
        except FileNotFoundError:
            return False

    def _free_cash_journal(self, company, code, pos_name):
        """A cash journal no other POS payment method uses (Odoo allows one cash method per journal)."""
        Journal = self.env["account.journal"].sudo().with_company(company)
        journal = Journal.search([("company_id", "=", company.id), ("type", "=", "cash"),
                                  ("pos_payment_method_ids", "=", False)], order="sequence, id", limit=1)
        return journal or Journal.create({"name": "Pokladna %s" % pos_name, "type": "cash",
                                          "code": self._journal_code(code, "H"), "company_id": company.id})

    def _journal_code(self, code, suffix):
        Journal = self.env["account.journal"].sudo().with_context(active_test=False)
        base = code[:4].upper() + suffix
        candidate, number = base, 1
        while Journal.search_count([("code", "=", candidate)]):
            candidate, number = "%s%d" % (base[:4], number), number + 1
        return candidate

    # ------------------------------------------------------------------ helpers

    def _menu(self, module):
        with open(file_path("%s/zbozi.csv" % module), encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def _module_records(self, module, model):
        ids = self.env["ir.model.data"].sudo().search(
            [("module", "=", module), ("model", "=", model)]).mapped("res_id")
        return self.env[model].sudo().with_context(active_test=False).browse(ids).exists()

    def _find_or_create(self, module, xmlid, model, company, name, vals_factory):
        """Record of `company` known by `<module>.<xmlid>`; an existing record of that name is reused
        unchanged, otherwise one is created."""
        full_xmlid = "%s.%s" % (module, xmlid)
        Model = self.env[model].sudo().with_company(company).with_context(active_test=False)
        record = self.env.ref(full_xmlid, raise_if_not_found=False)
        if record and record.company_id == company:
            return record.sudo()
        found = Model.search([("company_id", "=", company.id), ("name", "=", name)], limit=1)
        created = found or Model.create(vals_factory())
        if not record:
            # noupdate, otherwise the module update would delete the record as not loaded from data.
            self.env["ir.model.data"].sudo()._update_xmlids(
                [{"xml_id": full_xmlid, "record": created, "noupdate": True}])
        return created
