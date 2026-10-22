"""Menus by role (spec "Role a výchozí obrazovky"). The menus belong to other modules and are not
noupdate, so their groups are set by data/menus.xml (<function>) on every update of this module;
an update of the owning module alone restores its own groups until the next update of this one."""
from odoo import api, models

RECEPTION = "elite_vet_reservation.group_reservation_reception"
NURSE = "elite_vet_clinic.group_clinic_nurse"
DOCTOR = "elite_vet_clinic.group_clinic_doctor"
MANAGER = "elite_vet_reservation.group_reservation_manager"

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
# Stock menus an earlier version of this module gave to Vedení: their stock groups are restored
# (only while they still carry exactly the Vedení group, i.e. nobody changed them since).
RESTORED_STOCK = {"base.menu_management": "base.group_system"}
# Ordinace (with its copies of Příjem zboží and Přehled skladu) from the nurse up (ruling R11).
NURSE_ROOTS = ("elite_vet_clinic.menu_clinic_root",)
RECEPTION_ROOTS = ("point_of_sale.menu_point_root",)
STOCK_ROOT = "stock.menu_stock_root"
# The two stock items nurses and doctors keep (Příjem zboží is moved up from Operations).
STOCK_KEPT = ("elite_vet_sale.menu_stock_overview", "elite_vet_sale.menu_goods_receipt_stock")


class IrUiMenu(models.Model):
    _inherit = "ir.ui.menu"

    @api.model
    def _elite_vet_apply_role_menus(self):
        manager, reception = self.env.ref(MANAGER), self.env.ref(RECEPTION)
        Menu = self.with_context(**{"ir.ui.menu.full_list": True, "active_test": False})
        for xmlid in MANAGER_ROOTS:
            self._elite_vet_set_groups(self.env.ref(xmlid, raise_if_not_found=False), manager)
        for xmlid, group_xmlid in RESTORED_STOCK.items():
            menu = self.env.ref(xmlid, raise_if_not_found=False)
            if menu and menu.groups_id == manager:
                self._elite_vet_set_groups(menu, self.env.ref(group_xmlid))
        for xmlid in NURSE_ROOTS:
            self._elite_vet_set_groups(self.env.ref(xmlid, raise_if_not_found=False), self.env.ref(NURSE))
        for xmlid in RECEPTION_ROOTS:
            self._elite_vet_set_groups(self.env.ref(xmlid, raise_if_not_found=False), reception)

        stock_root = self.env.ref(STOCK_ROOT, raise_if_not_found=False)
        if not stock_root:
            return
        kept = Menu.browse()
        for xmlid in STOCK_KEPT:
            kept |= self.env.ref(xmlid, raise_if_not_found=False) or Menu.browse()
        for menu in kept.filtered(lambda m: m.parent_id != stock_root):
            menu.parent_id = stock_root
        # Příjem zboží right after Přehled skladu.
        overview, receipt = (self.env.ref(xmlid, raise_if_not_found=False) for xmlid in STOCK_KEPT)
        if overview and receipt and receipt.sequence != overview.sequence + 1:
            receipt.sequence = overview.sequence + 1
        # Every other stock item a doctor (the highest non-manager role) would see becomes manager
        # only; items already limited to other groups (stock manager, debug mode, ...) keep them.
        doctor = self.env.ref(DOCTOR)
        doctor_groups = doctor | doctor.trans_implied_ids
        for menu in Menu.search([("parent_id", "=", stock_root.id), ("id", "not in", kept.ids)]):
            if not menu.groups_id or menu.groups_id & doctor_groups:
                self._elite_vet_set_groups(menu, manager)

    @api.model
    def _elite_vet_set_groups(self, menu, groups):
        if menu and menu.groups_id != groups:
            menu.groups_id = [(6, 0, groups.ids)]
