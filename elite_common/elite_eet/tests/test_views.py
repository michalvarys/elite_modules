from odoo.tests import tagged

from .common import EetCase


@tagged("post_install", "-at_install")
class TestEetViews(EetCase):
    def test_views_load(self):
        manager = self.env["res.users"].create({
            "name": "EET view manager",
            "login": "eet_view_manager",
            "groups_id": [(6, 0, [self.env.ref("base.group_user").id, self.env.ref("elite_eet.group_eet_manager").id])],
        })
        for env in (self.env, self.env(user=manager)):
            for model in ("elite.eet.device", "elite.eet.sale", "elite.eet.attempt"):
                views = env[model].get_views([(False, "list"), (False, "form"), (False, "search")])
                self.assertEqual(set(views["views"]), {"list", "form", "search"}, model)
        form = self.env(user=manager)["elite.eet.device"].get_views([(False, "form")])["views"]["form"]["arch"]
        self.assertNotIn("certificate_password", form)
        self.assertIn("action_check_connection", form)
        admin_form = self.env["elite.eet.device"].get_views([(False, "form")])["views"]["form"]["arch"]
        self.assertIn("certificate_password", admin_form)
        sale_search = self.env["elite.eet.sale"].get_views([(False, "search")])["views"]["search"]["arch"]
        for name in ("filter_pending", "filter_error", "filter_near_deadline", "filter_overdue"):
            self.assertIn(name, sale_search)
        self.assertTrue(self.env.ref("elite_eet.action_eet_sale"))
        self.assertTrue(self.env.ref("elite_eet.action_eet_device"))
        server_action = self.env.ref("elite_eet.action_server_send_to_eet")
        self.assertEqual(server_action.binding_model_id.model, "elite.eet.sale")
