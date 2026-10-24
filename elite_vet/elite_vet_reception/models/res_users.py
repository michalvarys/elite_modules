"""Home screen (res.users.action_id) by the highest role of the user (spec "Role a výchozí
obrazovky"). Set automatically when the groups change, only while the user has no home action or
one of the role actions – a custom home action is never overwritten.

Till and stock (task 14): when the highest role changes to Recepce, the user gets
elite_vet_sale.group_till_stock; when it changes to Sestra or Lékařka, the till, sale and stock
groups are removed. Only on a role change: a manual tick or untick afterwards stays."""
from odoo import _, api, models
from odoo.exceptions import AccessError

from odoo.addons.elite_vet_sale.models.res_users import CLINIC_ROLES

# Highest role first.
ROLE_HOME_ACTIONS = (
    ("elite_vet_reservation.group_reservation_manager", "elite_vet_winvet.action_winvet_dashboard"),
    ("elite_vet_clinic.group_clinic_doctor", "elite_vet_clinic.action_patient_card"),
    ("elite_vet_clinic.group_clinic_nurse", "elite_vet_clinic.action_patient_card"),
    ("elite_vet_reservation.group_reservation_reception", "elite_vet_reception.action_open_reception_pos"),
)
MANAGER_GROUP = "elite_vet_reservation.group_reservation_manager"
GROUP_KEYS = ("groups_id",)
REIFIED_GROUP_PREFIXES = ("in_group_", "sel_groups_")


class ResUsers(models.Model):
    _inherit = "res.users"

    @api.model_create_multi
    def create(self, vals_list):
        users = super().create(vals_list)
        users._elite_vet_apply_home_action()
        users._elite_vet_apply_role_till({})
        return users

    def write(self, vals):
        groups_change = any(key in GROUP_KEYS or key.startswith(REIFIED_GROUP_PREFIXES) for key in vals)
        roles_before = {user.id: user._elite_vet_role() for user in self} if groups_change else {}
        res = super().write(vals)
        if groups_change:
            self._elite_vet_apply_home_action()
            self._elite_vet_apply_role_till(roles_before)
        return res

    def _elite_vet_apply_role_till(self, roles_before):
        """Till group by the new role, for users whose highest role changed (roles_before:
        {user id: role before the write}, empty for new users)."""
        for user in self.sudo():
            if user.share:
                continue
            role = user._elite_vet_role()
            if role == roles_before.get(user.id, False):
                continue
            if role == "reception":
                user._elite_vet_grant_till()
            elif role in CLINIC_ROLES:
                user._elite_vet_drop_till_rights()

    def _elite_vet_home_action(self):
        """The role home action of the user (ir.actions record), empty without a role."""
        self.ensure_one()
        for group, xmlid in ROLE_HOME_ACTIONS:
            if self.has_group(group):
                action = self.env.ref(xmlid, raise_if_not_found=False)
                if action:
                    return action.sudo()
        return self.env["ir.actions.actions"]

    @api.model
    def _elite_vet_role_action_ids(self):
        ids = set()
        for _group, xmlid in ROLE_HOME_ACTIONS:
            action = self.env.ref(xmlid, raise_if_not_found=False)
            if action:
                ids.add(action.id)
        return ids

    def _elite_vet_apply_home_action(self):
        """Set the role home action where the user has none or a role one; returns the changed users."""
        role_ids = self._elite_vet_role_action_ids()
        changed = self.browse()
        for user in self.sudo():
            current = user.action_id.id
            if current and current not in role_ids:
                continue
            target = user._elite_vet_home_action().id or False
            if current != target:
                user.write({"action_id": target})
                changed |= user
        return changed

    @api.model
    def _elite_vet_apply_home_actions_all(self):
        """Role home actions of all internal users (custom ones kept); also runs on every module
        update (data/home_actions.xml) and in the post-init hook."""
        return self.sudo().with_context(active_test=False).search(
            [("share", "=", False)])._elite_vet_apply_home_action()

    @api.model
    def action_elite_vet_set_home_actions(self):
        """Button "Nastavit výchozí obrazovky": the role home action for all internal users."""
        if not self.env.user.has_group(MANAGER_GROUP):
            raise AccessError(_("Výchozí obrazovky může nastavit jen vedení."))
        changed = self._elite_vet_apply_home_actions_all()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "title": _("Výchozí obrazovky"),
                "message": _("Nastaveno uživatelům: %(count)s (vlastní výchozí obrazovky zůstaly).",
                             count=len(changed)),
            },
        }
