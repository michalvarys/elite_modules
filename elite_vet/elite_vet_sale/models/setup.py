import logging

from odoo import api, models
from odoo.tools import float_compare

_logger = logging.getLogger(__name__)

MODULE = "elite_vet_sale"
CHART = "cz"
WINVET_MASTER_PARAM = "elite_vet_sale.winvet_master"
# The single place that maps a VAT rate of a price list item to a sale tax of l10n_cz
# (template xmlids, prefixed with the company id by the chart template).
CZ_SALE_TAX_XMLIDS = {
    21.0: "l10n_cz_21_domestic_supplies",
    12.0: "l10n_cz_12_domestic_supplies",
    0.0: "l10n_cz_other_transaction_deduction",
}
UNIT_ROUNDING = 0.001
CUSTOM_TAX_NAME = "%d %% DPH (cena s DPH)"


class EliteVetSaleSetup(models.AbstractModel):
    _name = "elite.vet.sale.setup"
    _description = "Elite Vet – nastavení prodeje, pokladny a skladu"

    # ------------------------------------------------------------------ public API

    @api.model
    def ensure_setup(self, company=None):
        """Bring the company to the state the clinic needs; safe to call repeatedly."""
        company = (company or self.env.company).sudo()
        self = self.sudo().with_company(company)
        self._ensure_country_currency(company)
        self._ensure_chart(company)
        self._ensure_price_include(company)
        self._ensure_lots_and_expiry()
        self._ensure_units()
        self._ensure_fefo(company)
        self._ensure_pos(company)
        self._ensure_free_product(company)

    @api.model
    def tax_for_rate(self, rate, company=None):
        """Sale tax (price including tax) for a VAT rate in percent; created when l10n_cz has none."""
        company = (company or self.env.company).sudo()
        rate = round(float(rate), 4)
        Tax = self.env["account.tax"].sudo().with_company(company)
        xmlid = CZ_SALE_TAX_XMLIDS.get(rate)
        if xmlid:
            tax = self.env["account.chart.template"].sudo().with_company(company).ref(
                xmlid, raise_if_not_found=False)
            if tax and tax.active and tax.company_id == company and tax.type_tax_use == "sale" \
                    and float_compare(tax.amount, rate, precision_digits=4) == 0:
                return tax
        name = CUSTOM_TAX_NAME % rate
        tax = Tax.search([("company_id", "=", company.id), ("type_tax_use", "=", "sale"),
                          ("amount_type", "=", "percent"), ("amount", "=", rate), ("name", "=", name)],
                         limit=1)
        if tax:
            return tax
        vals = {"name": name, "type_tax_use": "sale", "amount_type": "percent", "amount": rate,
                "company_id": company.id, "country_id": company.account_fiscal_country_id.id
                or company.country_id.id, "invoice_label": "%d%% DPH" % rate}
        if company.account_price_include != "tax_included":
            vals["price_include_override"] = "tax_included"
        _logger.info("Elite Vet: creating sale tax %s for %s", name, company.name)
        return Tax.create(vals)

    @api.model
    def pos_config(self):
        config = self.env.ref("%s.pos_config_reception" % MODULE, raise_if_not_found=False)
        if not config:
            self.sudo().ensure_setup()
            config = self.env.ref("%s.pos_config_reception" % MODULE)
        return config

    @api.model
    def free_product(self):
        return self.env.ref("%s.product_free_line" % MODULE)

    @api.model
    def is_winvet_master(self):
        """True while WinVet leads the price list, prices and stock and Odoo only mirrors them."""
        value = self.env["ir.config_parameter"].sudo().get_param(WINVET_MASTER_PARAM, "1")
        return (value or "").strip().lower() not in ("0", "false", "no", "")

    # ------------------------------------------------------------------ steps

    def _has_posted_moves(self, company):
        return bool(self.env["account.move"].sudo().search_count(
            [("company_id", "child_of", company.id), ("state", "=", "posted")], limit=1))

    def _ensure_country_currency(self, company):
        country, currency = self.env.ref("base.cz"), self.env.ref("base.CZK")
        if company.country_id == country and company.currency_id == currency:
            return
        if self._has_posted_moves(company):
            _logger.warning("Elite Vet: company %s has posted journal entries, country/currency left "
                            "as %s/%s (expected CZ/CZK).", company.name, company.country_id.code,
                            company.currency_id.name)
            return
        vals = {}
        if company.country_id != country:
            vals["country_id"] = country.id
        if company.currency_id != currency:
            if company.root_id._existing_accounting():
                # Draft journal items exist; Odoo forbids the currency change.
                _logger.warning("Elite Vet: company %s has journal items, currency left as %s "
                                "(expected CZK).", company.name, company.currency_id.name)
            else:
                currency.active = True
                vals["currency_id"] = currency.id
        if vals:
            company.write(vals)

    def _ensure_chart(self, company):
        if company.chart_template != CHART:
            if company.chart_template and company.root_id._existing_accounting():
                _logger.warning("Elite Vet: company %s uses chart %s with journal items, Czech chart "
                                "not loaded.", company.name, company.chart_template)
                return
            self.env["account.chart.template"].sudo().try_loading(CHART, company, install_demo=False)
        # Installing `account` on a company without a chart queues the generic chart for the end
        # of the registry load (ir.module.module._register_hook). It would replace the Czech chart
        # loaded just now, so it may only run for a company still without a chart.
        pending = getattr(self.env.registry, "_auto_install_template", None)
        if pending and not getattr(pending, "_elite_vet_guarded", False):
            def guarded(env, pending=pending):
                if not env.company.chart_template:
                    pending(env)
            guarded._elite_vet_guarded = True
            self.env.registry._auto_install_template = guarded

    def _ensure_price_include(self, company):
        if company.account_price_include == "tax_included":
            return
        if company.root_id._existing_accounting():
            _logger.warning("Elite Vet: company %s has journal items, prices stay tax excluded; "
                            "new clinic taxes override it.", company.name)
            return
        company.account_price_include = "tax_included"

    def _ensure_lots_and_expiry(self):
        """Same as enabling "Lots & Serial Numbers" in the settings: the group is implied by internal
        users. product_expiry has no group of its own for expiration dates, they follow the lot group."""
        group_user = self.env.ref("base.group_user")
        lots = self.env.ref("stock.group_production_lot")
        if lots not in group_user.implied_ids:
            group_user.write({"implied_ids": [(4, lots.id)]})

    def _ensure_units(self):
        """Medicines are sold by ml and tablets: Units accept three decimals."""
        precision = self.env.ref("product.decimal_product_uom")
        if precision.digits < 3:
            precision.digits = 3
        unit = self.env.ref("uom.product_uom_unit")
        if unit.rounding != UNIT_ROUNDING:
            unit.rounding = UNIT_ROUNDING

    def _warehouses(self, company):
        return self.env["stock.warehouse"].sudo().search([("company_id", "=", company.id)], order="sequence, id")

    def _ensure_fefo(self, company):
        fefo = self.env.ref("product_expiry.removal_fefo")
        for location in self._warehouses(company).lot_stock_id:
            if location.removal_strategy_id != fefo:
                location.removal_strategy_id = fefo

    def _ensure_pos(self, company):
        warehouse = self._warehouses(company)[:1]
        if not warehouse.pos_type_id:
            self.env["stock.warehouse"].sudo()._create_missing_pos_picking_types()
        picking_type = warehouse.pos_type_id
        # No lot prompt in the POS: the outgoing move reserves lots itself (FEFO), see
        # point_of_sale/models/stock_picking.py::_add_mls_related_to_order.
        if picking_type.use_existing_lots or picking_type.use_create_lots:
            picking_type.write({"use_existing_lots": False, "use_create_lots": False})

        Journal = self.env["account.journal"].sudo()
        bank_journal = Journal.search([("company_id", "=", company.id), ("type", "=", "bank")],
                                      order="sequence, id", limit=1)
        if not bank_journal:
            bank_journal = Journal.create({"name": "Banka", "type": "bank", "code": "EVBNK",
                                           "company_id": company.id})
        methods = self._find_or_create("pos_payment_method_cash", "pos.payment.method", company, "Hotově",
                                       lambda: {"name": "Hotově", "company_id": company.id,
                                                "journal_id": self._free_cash_journal(company).id})
        for xmlid, name in (("pos_payment_method_card", "Kartou"), ("pos_payment_method_transfer", "Převodem")):
            methods |= self._find_or_create(xmlid, "pos.payment.method", company, name, lambda name=name: {
                "name": name, "company_id": company.id, "journal_id": bank_journal.id,
                "payment_method_type": "none", "use_payment_terminal": False})

        invoice_journal = Journal.search([("company_id", "=", company.id), ("type", "=", "sale")],
                                         order="sequence, id", limit=1)
        config = self._find_or_create("pos_config_reception", "pos.config", company, "Recepce", lambda: {
            "name": "Recepce", "company_id": company.id, "picking_type_id": picking_type.id,
            "payment_method_ids": [(6, 0, methods.ids)], "invoice_journal_id": invoice_journal.id})
        vals = {}
        if methods - config.payment_method_ids:
            vals["payment_method_ids"] = [(4, method.id) for method in methods - config.payment_method_ids]
        if not config.invoice_journal_id and invoice_journal:
            vals["invoice_journal_id"] = invoice_journal.id
        if config.picking_type_id != picking_type and not config.current_session_id:
            vals["picking_type_id"] = picking_type.id
        pricelist = self._ensure_pricelist(company, config)
        if config.pricelist_id != pricelist:
            vals["pricelist_id"] = pricelist.id
        if pricelist not in config.available_pricelist_ids:
            vals["available_pricelist_ids"] = [(4, pricelist.id)]
        if vals:
            config.write(vals)

    def _ensure_pricelist(self, company, config):
        """The pricelist of the Recepce till, in the company currency (CZK). Visit quotations use it, so
        they always match the till's currency. The default pricelist is switched to CZK while nothing
        uses it yet, otherwise "Ceník Kč" is created."""
        Pricelist = self.env["product.pricelist"].sudo().with_context(active_test=False)
        currency = company.currency_id
        current = config.pricelist_id
        if current and current.currency_id == currency:
            return current
        known = self.env.ref("%s.pricelist_czk" % MODULE, raise_if_not_found=False)
        if known and known.currency_id == currency:
            return known
        pricelist = Pricelist.search([("name", "=", "Ceník Kč"), ("currency_id", "=", currency.id),
                                      ("company_id", "in", (False, company.id))], limit=1)
        if not pricelist:
            default = self.env.ref("product.list0", raise_if_not_found=False)
            used = default and (self.env["sale.order"].sudo().search_count([("pricelist_id", "=", default.id)])
                                or self.env["pos.order"].sudo().search_count([("pricelist_id", "=", default.id)])
                                or self.env["res.partner"].sudo().with_context(active_test=False).search_count(
                                    [("specific_property_product_pricelist", "=", default.id)]))
            if default and not used:
                default.write({"currency_id": currency.id, "name": "Ceník Kč"})
                pricelist = default
            else:
                pricelist = Pricelist.create({"name": "Ceník Kč", "currency_id": currency.id,
                                              "company_id": company.id})
        if not known:
            self.env["ir.model.data"].sudo()._update_xmlids([{
                "xml_id": "%s.pricelist_czk" % MODULE, "record": pricelist, "noupdate": True}])
        return pricelist

    def _free_cash_journal(self, company):
        """A cash journal no other POS payment method uses (Odoo allows one cash method per journal)."""
        Journal = self.env["account.journal"].sudo()
        journal = Journal.search([("company_id", "=", company.id), ("type", "=", "cash"),
                                  ("pos_payment_method_ids", "=", False)], order="sequence, id", limit=1)
        return journal or Journal.create({"name": "Pokladna Recepce", "type": "cash", "code": "EVCSH",
                                          "company_id": company.id})

    def _ensure_free_product(self, company):
        product = self.free_product().sudo()
        tax = self.tax_for_rate(21, company)
        company_taxes = product.taxes_id.filtered(lambda t: t.company_id == company)
        if company_taxes != tax:
            product.taxes_id = [(3, t.id) for t in company_taxes - tax] + [(4, tax.id)]

    # ------------------------------------------------------------------ helpers

    def _find_or_create(self, xmlid, model, company, name, vals_factory):
        """Record of `company` known by `elite_vet_sale.<xmlid>`; created (and named) when missing."""
        full_xmlid = "%s.%s" % (MODULE, xmlid)
        Model = self.env[model].sudo().with_company(company).with_context(active_test=False)
        record = self.env.ref(full_xmlid, raise_if_not_found=False)
        if record and record.company_id == company:
            return record.sudo()
        found = Model.search([("company_id", "=", company.id), ("name", "=", name)], limit=1)
        created = found or Model.create(vals_factory())
        if not record:
            self.env["ir.model.data"].sudo()._update_xmlids(
                [{"xml_id": full_xmlid, "record": created, "noupdate": True}])
        return created
