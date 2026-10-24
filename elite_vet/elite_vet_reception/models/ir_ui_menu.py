"""Menus by role (spec "Role a výchozí obrazovky"). The menus belong to other modules and are not
noupdate, so their groups are set by data/menus.xml (<function>) on every update of this module;
an update of the owning module alone restores its own groups until the next update of this one."""
from odoo import api, models

NURSE = "elite_vet_clinic.group_clinic_nurse"
DOCTOR = "elite_vet_clinic.group_clinic_doctor"
MANAGER = "elite_vet_reservation.group_reservation_manager"
# Pokladna and the stock (task 14): the till group of Recepce (and Vedení, which implies it).
TILL = "elite_vet_sale.group_till_stock"

# App roots only Vedení (and the system administrator, who implies it) sees.
MANAGER_ROOTS = (
    "sale.sale_menu_root",
    "account.menu_finance",
    "hr.menu_hr_root",
    "elite_vet_winvet.menu_winvet_root",
    "elite_vet_calendar.menu_rozpis_root",
    "website.menu_website_configuration",
    "spreadsheet_dashboard.spreadsheet_dashboard_menu_root",
)
# Menus for the system administrator only. Apps is base.group_system in base, but
# base_install_request (auto-installed) opens it to every user, and an earlier version of this
# module gave it to Vedení.
ADMIN_ROOTS = ("base.menu_management",)
# Ordinace from the nurse up (ruling R11); its copies of Příjem zboží and Přehled skladu are for
# the till group (elite_vet_sale), so only Vedení sees them there.
NURSE_ROOTS = ("elite_vet_clinic.menu_clinic_root",)
TILL_ROOTS = ("point_of_sale.menu_point_root",)
STOCK_ROOT = "stock.menu_stock_root"
# The two stock items of the till group (Příjem zboží is moved up from Operations); the root and
# these two are for the till group and Vedení, the rest of the stock for Vedení only.
STOCK_KEPT = ("elite_vet_sale.menu_stock_overview", "elite_vet_sale.menu_goods_receipt_stock")


class IrUiMenu(models.Model):
    _inherit = "ir.ui.menu"

    @api.model
    def _elite_vet_apply_role_menus(self):
        manager, till = self.env.ref(MANAGER), self.env.ref(TILL)
        Menu = self.with_context(**{"ir.ui.menu.full_list": True, "active_test": False})
        for xmlid in MANAGER_ROOTS:
            self._elite_vet_set_groups(self.env.ref(xmlid, raise_if_not_found=False), manager)
        for xmlid in ADMIN_ROOTS:
            self._elite_vet_set_groups(self.env.ref(xmlid, raise_if_not_found=False), self.env.ref("base.group_system"))
        for xmlid in NURSE_ROOTS:
            self._elite_vet_set_groups(self.env.ref(xmlid, raise_if_not_found=False), self.env.ref(NURSE))
        for xmlid in TILL_ROOTS:
            self._elite_vet_set_groups(self.env.ref(xmlid, raise_if_not_found=False), till)

        stock_root = self.env.ref(STOCK_ROOT, raise_if_not_found=False)
        if not stock_root:
            return
        kept = Menu.browse()
        for xmlid in STOCK_KEPT:
            kept |= self.env.ref(xmlid, raise_if_not_found=False) or Menu.browse()
        for menu in stock_root | kept:
            self._elite_vet_set_groups(menu, till | manager)
        for menu in kept.filtered(lambda m: m.parent_id != stock_root):
            menu.parent_id = stock_root
        # Příjem zboží right after Přehled skladu.
        overview, receipt = (self.env.ref(xmlid, raise_if_not_found=False) for xmlid in STOCK_KEPT)
        if overview and receipt and receipt.sequence != overview.sequence + 1:
            receipt.sequence = overview.sequence + 1
        # Every other stock item a doctor or the till group (the non-manager roles) would see
        # becomes manager only; items already limited to other groups (stock manager, debug
        # mode, ...) keep them.
        doctor = self.env.ref(DOCTOR)
        role_groups = doctor | doctor.trans_implied_ids | till | till.trans_implied_ids
        for menu in Menu.search([("parent_id", "=", stock_root.id), ("id", "not in", kept.ids)]):
            if not menu.groups_id or menu.groups_id & role_groups:
                self._elite_vet_set_groups(menu, manager)

    @api.model
    def _elite_vet_set_groups(self, menu, groups):
        if menu and menu.groups_id != groups:
            menu.groups_id = [(6, 0, groups.ids)]
