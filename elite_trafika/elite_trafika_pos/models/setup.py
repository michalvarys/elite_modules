import base64
import csv
import hashlib
import logging

from odoo import api, models
from odoo.exceptions import UserError
from odoo.tools import file_open, float_compare
from odoo.tools.misc import file_path

_logger = logging.getLogger(__name__)

MODULE = "elite_trafika_pos"
CHART = "cz"
VAT_RATE = 21.0
REDUCED_VAT_RATE = 12.0
# Sale taxes of l10n_cz by rate (template xmlids, prefixed with the company id by the chart template).
CZ_SALE_TAX_XMLIDS = {
    21.0: "l10n_cz_21_domestic_supplies",
    12.0: "l10n_cz_12_domestic_supplies",
}
CUSTOM_TAX_NAME = "%d %% DPH (cena s DPH)"


class EliteTrafikaPosSetup(models.AbstractModel):
    _name = "elite.trafika.pos.setup"
    _description = "Elite Trafika – nastavení pokladny, skladu a účetnictví"

    # ------------------------------------------------------------------ public API (data/setup.xml)

    @api.model
    def ensure_setup(self, config):
        """Set up the till of one company; safe to call repeatedly.

        The company may be a branch (Elite Trafika is a brand of Elite): the chart of accounts and the
        taxes then belong to its root company, which a branch shares; the warehouse, the products,
        the payment methods and the till belong to the branch.

        Only adds what is missing: values the companies already have (chart of accounts, taxes, price
        settings, warehouse, journals, an existing till) are left as they are; other branches of the
        root company get no chart of their own."""
        company = self.target_company(config["company"])
        root = company.root_id
        self = self.sudo().with_company(company)
        self._block_auto_chart()
        self._ensure_chart(company)
        self.env["res.lang"]._activate_lang("cs_CZ")
        standard, reduced = self.sale_tax(root), self.sale_tax(root, REDUCED_VAT_RATE)
        for accounting_company in root | company:
            if not accounting_company.account_sale_tax_id:
                accounting_company.account_sale_tax_id = standard
        self._ensure_products(company, root, standard, reduced, set(config.get("reduced_vat") or ()))
        self._ensure_barcodes()
        self._ensure_images()
        self._ensure_category_groups(config.get("category_groups") or {})
        self._ensure_pos(company, config.get("pos_name") or company.name)
        self._ensure_pos_groups()

    @api.model
    def target_company(self, name):
        companies = self.env["res.company"].sudo().search([("name", "=", name)])
        if len(companies) != 1:
            raise UserError("Elite Trafika – pokladna: firma „%s“ v databázi %s. Instalace nic nezměnila; "
                            "název firmy je v data/setup.xml." % (name, "není" if not companies else "je víckrát"))
        return companies

    @api.model
    def sale_tax(self, company, rate=VAT_RATE):
        """Sale tax of `rate` % with the price including the tax; `company` is the one that owns the
        taxes, i.e. the root company of a branch.

        The tax of the Czech chart is used when the company has it with prices including tax. When the
        company keeps prices excluding tax, a copy of that tax including tax is created (the copy keeps
        the tax report tags), so the company setting stays as it is."""
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
        _logger.info("Elite Trafika: creating sale tax %s for %s", name, company.name)
        if chart_tax:
            return chart_tax.copy({"name": name, "active": True, "price_include_override": "tax_included"})
        return Tax.create({"name": name, "type_tax_use": "sale", "amount_type": "percent", "amount": rate,
                           "company_id": company.id, "invoice_label": "%d%% DPH" % rate,
                           "price_include_override": "tax_included",
                           "country_id": company.account_fiscal_country_id.id or company.country_id.id})

    # ------------------------------------------------------------------ steps

    def _block_auto_chart(self):
        """Installing `account` queues a chart of accounts for the current company (the main company of
        the database) at the end of the registry load, see ir.module.module._register_hook. That company
        is not the till's company, so it keeps its state; a chart can still be chosen in its settings."""
        pending = getattr(self.env.registry, "_auto_install_template", None)
        if pending and not getattr(pending, "_elite_blocked", False):
            def skip(env):
                _logger.info("Elite Trafika: automatic chart of accounts for %s skipped", env.company.name)
            skip._elite_blocked = True
            self.env.registry._auto_install_template = skip

    def _ensure_chart(self, company):
        """Czech chart for the root company first (it holds the accounts and the taxes), then for the
        branch itself (Odoo copies the root's accounting settings to it, as for a new branch)."""
        root = company.root_id
        for target in (root | company).sorted(lambda c: c != root):
            if target.chart_template:
                if target.chart_template != CHART:
                    _logger.warning("Elite Trafika: company %s keeps its chart %s (not the Czech one).",
                                    target.name, target.chart_template)
                continue
            if target.currency_id != self.env.ref("base.CZK"):
                _logger.warning("Elite Trafika: company %s uses %s, not CZK; left as it is.",
                                target.name, target.currency_id.name)
            # A company without a chart has no accounting yet: these are its first accounting settings.
            if not target.root_id._existing_accounting():
                target.account_price_include = "tax_included"
            _logger.info("Elite Trafika: loading the Czech chart of accounts for %s", target.name)
            self.env["account.chart.template"].sudo().try_loading(CHART, target, install_demo=False)

    def _ensure_products(self, company, tax_company, standard, reduced, reduced_ids):
        for template in self._module_products():
            if not template.company_id:
                template.company_id = company
            tax = reduced if template.id in reduced_ids else standard
            company_taxes = template.taxes_id.filtered(lambda t: t.company_id == tax_company)
            if company_taxes != tax:
                template.taxes_id = [(3, t.id) for t in company_taxes - tax] + [(4, tax.id)]

    def _ensure_barcodes(self):
        """EAN of zbozi.csv on module products without a barcode. The products load only at install
        (noupdate), so a database installed without the barcodes gets them on the module update; a
        barcode set in Odoo is kept, and an EAN another product already has is left out (Odoo allows a
        barcode on one product only)."""
        with open(file_path("%s/zbozi.csv" % MODULE), encoding="utf-8") as f:
            eans = {row["xmlid"]: row["ean"] for row in csv.DictReader(f) if row["ean"]}
        Product = self.env["product.product"].sudo().with_context(active_test=False)
        for xmlid, ean in eans.items():
            template = self.env.ref("%s.%s" % (MODULE, xmlid), raise_if_not_found=False)
            variant = template and template.product_variant_ids[:1]
            if not variant or variant.barcode:
                continue
            if Product.search_count([("barcode", "=", ean)]):
                _logger.warning("Elite Trafika: EAN %s of %s is on another product; left out", ean, variant.name)
                continue
            variant.barcode = ean

    def _ensure_category_groups(self, groups):
        """Subcategories under the main groups. The categories load only at install (noupdate), so this
        also moves them in a database installed before the groups; a category with a parent set in Odoo
        stays where it is."""
        for group, children in groups.items():
            parent = self.env.ref("%s.pos_category_%s" % (MODULE, group))
            for child in children:
                category = self.env.ref("%s.pos_category_%s" % (MODULE, child))
                if not category.parent_id:
                    category.parent_id = parent

    def _ensure_pos_groups(self):
        """The till limited to a list of categories shows only the root ones of that list, so the main
        groups must be in it. Odoo refuses this change on an open session unless told otherwise; an open
        till shows the groups after a reload."""
        config = self.env.ref("%s.pos_config_trafika" % MODULE, raise_if_not_found=False)
        if not config or not config.limit_categories:
            return
        roots = self._module_records("pos.category").filtered(lambda c: not c.parent_id)
        missing = roots - config.iface_available_categ_ids
        if missing:
            config.with_context(bypass_categories_forbidden_change=True).write(
                {"iface_available_categ_ids": [(4, category.id) for category in missing]})

    def _ensure_pos(self, company, pos_name):
        if self.env.ref("%s.pos_config_trafika" % MODULE, raise_if_not_found=False):
            return  # the till exists; its settings belong to the staff now
        warehouse = self._warehouse(company)
        if not warehouse.pos_type_id:
            raise UserError("Elite Trafika – pokladna: sklad „%s“ nemá typ operace pro pokladnu." % warehouse.name)
        Journal = self.env["account.journal"].sudo().with_company(company)
        # journals of the root company serve its branches as well
        bank_journal = Journal.search([("company_id", "parent_of", company.id), ("type", "=", "bank")],
                                      order="sequence, id", limit=1)
        if not bank_journal:
            bank_journal = Journal.create({"name": "Banka", "type": "bank", "code": "ETBNK",
                                           "company_id": company.id})
        methods = self._find_or_create("pos_payment_method_cash", "pos.payment.method", company, "Hotově", lambda: {
            "name": "Hotově", "company_id": company.id, "journal_id": self._free_cash_journal(company).id})
        methods |= self._find_or_create("pos_payment_method_card", "pos.payment.method", company, "Kartou", lambda: {
            "name": "Kartou", "company_id": company.id, "journal_id": bank_journal.id,
            "payment_method_type": "none", "use_payment_terminal": False})
        invoice_journal = Journal.search([("company_id", "parent_of", company.id), ("type", "=", "sale")],
                                         order="sequence, id", limit=1)
        categories = self._module_records("pos.category").filtered(lambda c: not c.parent_id)
        self._find_or_create("pos_config_trafika", "pos.config", company, pos_name, lambda: {
            "name": pos_name, "company_id": company.id, "picking_type_id": warehouse.pos_type_id.id,
            "payment_method_ids": [(6, 0, methods.ids)], "invoice_journal_id": invoice_journal.id,
            "limit_categories": True, "iface_available_categ_ids": [(6, 0, categories.ids)]})

    def _warehouse(self, company):
        """The company's warehouse. Installing `stock` creates one only for the first company of the
        database, so the till's company gets its own when it has none."""
        Warehouse = self.env["stock.warehouse"].sudo().with_company(company)
        warehouse = Warehouse.search([("company_id", "=", company.id)], order="sequence, id", limit=1)
        if warehouse:
            return warehouse
        code = next(c for c in ("TRAF", "ET", "ET1", "ET2", "ET3")
                    if not Warehouse.with_context(active_test=False).search_count(
                        [("company_id", "=", company.id), ("code", "=", c)]))
        _logger.info("Elite Trafika: creating warehouse %s for %s", code, company.name)
        return Warehouse.create({"name": company.name, "code": code, "company_id": company.id,
                                 "partner_id": company.partner_id.id})

    def _free_cash_journal(self, company):
        """A cash journal no other POS payment method uses (Odoo allows one cash method per journal)."""
        Journal = self.env["account.journal"].sudo().with_company(company)
        journal = Journal.search([("company_id", "=", company.id), ("type", "=", "cash"),
                                  ("pos_payment_method_ids", "=", False)], order="sequence, id", limit=1)
        return journal or Journal.create({"name": "Pokladna Elite Trafika", "type": "cash", "code": "ETCSH",
                                          "company_id": company.id})

    # ------------------------------------------------------------------ helpers

    def _ensure_images(self):
        """Images of the module for products and POS categories without one, or with a tile of an
        earlier version of the module (data/old_tiles.txt). Runs on updates too, the data files are
        noupdate; any other image the record already has is kept."""
        old_tiles = self._old_tiles()
        data = self.env["ir.model.data"].sudo().search(
            [("module", "=", MODULE), ("model", "in", ("product.template", "pos.category"))])
        for entry in data:
            is_product = entry.model == "product.template"
            field = "image_1920" if is_product else "image_128"
            record = self.env[entry.model].sudo().with_context(active_test=False).browse(entry.res_id).exists()
            if not record:
                continue
            current = record[field]
            if current and hashlib.sha256(base64.b64decode(current)).hexdigest() not in old_tiles:
                continue
            path = "products/%s.jpg" % entry.name.removeprefix("product_") if is_product \
                else "categories/%s.jpg" % entry.name.removeprefix("pos_category_")
            image = self._module_image(path)
            if image and image != current:
                record[field] = image

    def _old_tiles(self):
        with file_open("%s/data/old_tiles.txt" % MODULE) as hashes:
            return set(hashes.read().split())

    def _module_image(self, path):
        try:
            with file_open("%s/static/img/%s" % (MODULE, path), "rb") as image:
                return base64.b64encode(image.read())
        except FileNotFoundError:
            return False

    def _module_products(self):
        return self._module_records("product.template")

    def _module_records(self, model):
        ids = self.env["ir.model.data"].sudo().search(
            [("module", "=", MODULE), ("model", "=", model)]).mapped("res_id")
        return self.env[model].sudo().with_context(active_test=False).browse(ids).exists()

    def _find_or_create(self, xmlid, model, company, name, vals_factory):
        """Record of `company` known by `elite_trafika_pos.<xmlid>`; an existing record of that name is
        reused unchanged, otherwise one is created."""
        full_xmlid = "%s.%s" % (MODULE, xmlid)
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
