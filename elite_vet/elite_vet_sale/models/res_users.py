"""Till and stock rights by role (task 14): only Recepce (group_till_stock) and Vedení have the
POS, sale orders and the stock; Sestra and Lékařka do not. The role change itself is handled in
elite_vet_reception (res.users.write), the one-off cleanup of the old chain is here."""
import logging

from odoo import api, models

_logger = logging.getLogger(__name__)

TILL_GROUP = "elite_vet_sale.group_till_stock"
# Highest role first (the chain Recepce < Sestra < Lékařka < Správce rezervací).
ROLES = (
    ("manager", "elite_vet_reservation.group_reservation_manager"),
    ("doctor", "elite_vet_clinic.group_clinic_doctor"),
    ("nurse", "elite_vet_clinic.group_clinic_nurse"),
    ("reception", "elite_vet_reservation.group_reservation_reception"),
)
# Roles without the till and the stock.
CLINIC_ROLES = ("nurse", "doctor")
# What a nurse or a doctor loses (the old chain gave the first four, Vedení-like rights were
# sometimes ticked by hand); nothing else is touched.
TILL_RIGHTS = (
    TILL_GROUP,
    "point_of_sale.group_pos_user",
    "point_of_sale.group_pos_manager",
    "sales_team.group_sale_salesman",
    "sales_team.group_sale_salesman_all_leads",
    "stock.group_stock_user",
    "stock.group_stock_manager",
)


class ResGroupsTill(models.Model):
    _inherit = "res.groups"

    @api.model
    def _elite_vet_unlink_role_till_rights(self):
        """Remove the POS / sale / stock groups from the implied groups of Recepce, Sestra and
        Lékařka (an earlier version linked them). Users keep their groups; see
        res.users._elite_vet_split_till_rights. Runs on every update (security/groups.xml)."""
        rights = self.env["res.users"]._elite_vet_till_rights()
        for role, xmlid in ROLES:
            group = self.env.ref(xmlid, raise_if_not_found=False)
            if role == "manager" or not group:
                continue
            linked = group.implied_ids & rights
            if linked:
                group.sudo().write({"implied_ids": [(3, g.id) for g in linked]})
                _logger.info("Elite Vet till rights: %s no longer implies %s", xmlid,
                             list(linked.get_external_id().values()))


class ResUsersTill(models.Model):
    _inherit = "res.users"

    def _elite_vet_role(self):
        """Highest Elite Vet role of the user: manager / doctor / nurse / reception, or False.
        Read from groups_id (it holds the implied groups too), not from the has_group cache."""
        self.ensure_one()
        groups = self.sudo().groups_id
        for role, xmlid in ROLES:
            group = self.env.ref(xmlid, raise_if_not_found=False)
            if group and group in groups:
                return role
        return False

    @api.model
    def _elite_vet_till_rights(self):
        groups = self.env["res.groups"]
        for xmlid in TILL_RIGHTS:
            groups |= self.env.ref(xmlid, raise_if_not_found=False) or self.env["res.groups"]
        return groups

    def _elite_vet_drop_till_rights(self):
        """Remove the till, sale and stock groups (TILL_RIGHTS only); returns the changed users."""
        rights = self._elite_vet_till_rights()
        changed = self.browse()
        for user in self.sudo():
            drop = user.groups_id & rights
            if drop:
                user.write({"groups_id": [(3, group.id) for group in drop]})
                changed |= user
        return changed

    def _elite_vet_grant_till(self):
        """Add the till group; returns the changed users."""
        till = self.env.ref(TILL_GROUP)
        users = self.sudo().filtered(lambda u: till not in u.groups_id)
        if users:
            users.write({"groups_id": [(4, till.id)]})
        return self.browse(users.ids)

    @api.model
    def _elite_vet_split_till_rights(self):
        """One-off cleanup of the users of the old chain (migration 18.0.1.0.2, post-init hook):
        a nurse or a doctor (not Vedení, not an administrator) loses the till/sale/stock groups,
        a Recepce user gets group_till_stock. Users without a role, administrators and
        portal/public users are not touched. Idempotent; returns {"dropped": users, "granted": users}."""
        admin = self.env.ref("base.group_system")
        users = self.sudo().with_context(active_test=False).search([("share", "=", False)])
        dropped = granted = self.browse()
        for user in users:
            if admin in user.groups_id:
                continue
            role = user._elite_vet_role()
            if role in CLINIC_ROLES:
                dropped |= user._elite_vet_drop_till_rights()
            elif role == "reception":
                granted |= user._elite_vet_grant_till()
        _logger.info("Elite Vet till rights: removed from %s nurse/doctor user(s) %s, granted to %s "
                     "reception user(s) %s", len(dropped), dropped.mapped("login"),
                     len(granted), granted.mapped("login"))
        return {"dropped": dropped, "granted": granted}
