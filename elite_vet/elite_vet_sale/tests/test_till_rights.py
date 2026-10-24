from odoo.exceptions import AccessError
from odoo.tests import HttpCase, tagged

from odoo.addons.elite_vet_clinic.models.patient_card import clinic_today

from .common import SaleCase

TILL = "elite_vet_sale.group_till_stock"
OLD_RIGHTS = ("point_of_sale.group_pos_user", "sales_team.group_sale_salesman_all_leads", "stock.group_stock_user")


@tagged("post_install", "-at_install")
class TestTillRights(SaleCase):
    """Task 14: doctors and nurses without POS and stock; the upgrade cleanup of the old chain."""

    def old_way_user(self, login, role, *extra):
        """A user as the old chain left it: the role plus the POS/sale/stock groups it implied."""
        Users = self.env["res.users"].with_context(no_reset_password=True)
        user = Users.create({"name": "T18 %s" % login, "login": login, "email": "%s@example.invalid" % login,
                             "groups_id": [(6, 0, [self.env.ref("base.group_user").id] + ([self.env.ref(role).id] if role else []))]})
        # added after the create: the role-change automation of elite_vet_reception (if installed)
        # runs on the create only
        groups = [self.env.ref(g).id for g in extra]
        if groups:
            self.env.cr.execute("INSERT INTO res_groups_users_rel (gid, uid) SELECT g, %s FROM unnest(%s) g "
                                "ON CONFLICT DO NOTHING", [user.id, groups])
            user.invalidate_recordset(["groups_id"])
            self.env.registry.clear_cache()
        return user

    def groups_of(self, user):
        user.invalidate_recordset(["groups_id"])
        return set(user.groups_id.get_external_id().values())

    # ------------------------------------------------------------------ upgrade cleanup

    def test_split_till_rights_of_old_chain_users(self):
        nurse = self.old_way_user("t18_old_nurse", "elite_vet_clinic.group_clinic_nurse", *OLD_RIGHTS)
        doctor = self.old_way_user("t18_old_doctor", "elite_vet_clinic.group_clinic_doctor",
                                   *OLD_RIGHTS, "point_of_sale.group_pos_manager", "stock.group_stock_manager",
                                   "sales_team.group_sale_salesman", "account.group_account_invoice")
        reception = self.old_way_user("t18_old_reception", "elite_vet_reservation.group_reservation_reception",
                                      "point_of_sale.group_pos_user", "sales_team.group_sale_salesman_all_leads")
        reception.groups_id = [(3, self.env.ref(TILL).id)]
        no_role = self.old_way_user("t18_old_norole", None, "point_of_sale.group_pos_user", "stock.group_stock_user")
        manager = self.old_way_user("t18_old_manager", "elite_vet_reservation.group_reservation_manager")
        before_no_role, before_manager = self.groups_of(no_role), self.groups_of(manager)

        result = self.env["res.users"]._elite_vet_split_till_rights()

        self.assertIn(nurse, result["dropped"])
        self.assertIn(doctor, result["dropped"])
        self.assertIn(reception, result["granted"])
        for user in (nurse, doctor):
            groups = self.groups_of(user)
            for xmlid in OLD_RIGHTS + ("point_of_sale.group_pos_manager", "stock.group_stock_manager",
                                       "sales_team.group_sale_salesman", TILL):
                self.assertNotIn(xmlid, groups, (user.login, xmlid))
                self.assertFalse(user.has_group(xmlid), (user.login, xmlid))
        # only the listed groups are removed
        self.assertIn("account.group_account_invoice", self.groups_of(doctor))
        self.assertIn("elite_vet_clinic.group_clinic_doctor", self.groups_of(doctor))
        self.assertIn(TILL, self.groups_of(reception))
        self.assertTrue(reception.has_group("stock.group_stock_user"))
        # users without a role and Vedení are not touched
        self.assertEqual(self.groups_of(no_role), before_no_role)
        self.assertEqual(self.groups_of(manager), before_manager)
        self.assertNotIn(no_role, result["dropped"] | result["granted"])
        self.assertNotIn(manager, result["dropped"] | result["granted"])

        # idempotent
        again = self.env["res.users"]._elite_vet_split_till_rights()
        self.assertFalse((again["dropped"] | again["granted"]) & (nurse | doctor | reception))

    def test_split_skips_admins_and_portal(self):
        admin = self.env.ref("base.user_admin")
        portal = self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "T18 portal", "login": "t18_portal", "email": "t18_portal@example.invalid",
            "groups_id": [(6, 0, [self.env.ref("base.group_portal").id])]})
        before_admin, before_portal = self.groups_of(admin), self.groups_of(portal)
        result = self.env["res.users"]._elite_vet_split_till_rights()
        self.assertNotIn(admin, result["dropped"] | result["granted"])
        self.assertNotIn(portal, result["dropped"] | result["granted"])
        self.assertEqual(self.groups_of(admin), before_admin)
        self.assertEqual(self.groups_of(portal), before_portal)

    # ------------------------------------------------------------------ doctor access

    def test_doctor_and_nurse_have_no_pos_or_stock(self):
        session = self.pos_session()
        warehouse = self.env["stock.warehouse"].search([("company_id", "=", self.env.company.id)], limit=1)
        picking = self.env["stock.picking"].create({
            "picking_type_id": warehouse.in_type_id.id, "location_id": self.env.ref("stock.stock_location_suppliers").id,
            "location_dest_id": warehouse.lot_stock_id.id})
        product = self.env["product.product"].create({"name": "T18 lék přístup", "is_storable": True})
        self.env["stock.quant"]._update_available_quantity(product, warehouse.lot_stock_id, 2)
        quant = self.env["stock.quant"].search([("product_id", "=", product.id)], limit=1)
        for user in (self.doctor_user, self.nurse):
            with self.subTest(user=user.login):
                for model, record in (("pos.session", session), ("pos.config", self.pos_config),
                                      ("stock.picking", picking)):
                    with self.assertRaises(AccessError, msg=model):
                        self.env[model].with_user(user).browse(record.id).read(["display_name"])
                with self.assertRaises(AccessError):
                    self.env["pos.order"].with_user(user).search([])
                with self.assertRaises(AccessError):
                    self.env["sale.order"].with_user(user).search([])
                with self.assertRaises(AccessError):
                    self.env["stock.picking"].with_user(user).search([])
                # stock.quant: Odoo grants read to every internal user, the Elite Vet rule hides all
                with self.assertRaises(AccessError):
                    self.env["stock.quant"].with_user(user).browse(quant.id).read(["quantity"])
                self.assertFalse(self.env["stock.quant"].with_user(user).search([]))

    def test_till_users_read_all_quants(self):
        product = self.env["product.product"].create({"name": "T18 lék sklad", "is_storable": True})
        stock = self.env["stock.warehouse"].search([("company_id", "=", self.env.company.id)], limit=1).lot_stock_id
        self.env["stock.quant"]._update_available_quantity(product, stock, 3)
        quant = self.env["stock.quant"].search([("product_id", "=", product.id)])
        self.assertTrue(quant)
        for user in (self.reception, self.manager):
            self.assertEqual(self.env["stock.quant"].with_user(user).search([("product_id", "=", product.id)]), quant)
        self.assertEqual(product.with_user(self.reception).qty_available, 3)

    def test_doctor_workflow_still_works(self):
        """Bill lines, "Hotovo, k pokladně", payment state on the record, the form and the board."""
        api = self.as_user(self.doctor_user)
        # bill line search on the card (price list items)
        found = api.search_items("Vakcína testovací")
        self.assertIn(self.vaccine.id, [i["id"] for i in found])
        room = self.env["elite.vet.room"].create({"name": "Ordinace T18 lékařka"})
        reservation = self.env["elite.vet.reservation"].create({
            "kind": "reservation", "state": "confirmed", "room_id": room.id,
            "start": self.today_utc(7, 0), "stop": self.today_utc(7, 20),
            "partner_id": self.owner.id, "pet_id": self.pet.id})
        data = api.open_today_record(self.pet.id, reservation_id=reservation.id)
        api.add_item(data["id"], self.vaccine.id)
        data = api.mark_done(data["id"])
        record = self.Record.browse(data["id"])
        self.assertTrue(record.sale_order_id)
        self.assertEqual(data["payment_state"], "waiting")
        self.assertEqual(data["sale_order_name"], record.sale_order_id.name)
        as_doctor = record.with_user(self.doctor_user)
        values = as_doctor.web_read({"sale_order_id": {"fields": {"display_name": {}}}, "payment_state": {}})[0]
        self.assertEqual(values["sale_order_id"]["display_name"], record.sale_order_id.name)
        self.assertEqual(values["payment_state"], "waiting")
        self.settle(record.sale_order_id)
        record.invalidate_recordset(["payment_state"])
        self.assertEqual(api.get_record(record.id)["payment_state"], "paid")
        # reopening a paid record is refused with a message, not an access error
        with self.assertRaisesRegex(Exception, "zaplacen"):
            as_doctor.action_reopen()
        # the board as the doctor carries the payment state
        events = self.env["elite.vet.reservation"].with_user(self.doctor_user).board_data(
            str(clinic_today()))["events"]
        self.assertEqual(next(e for e in events if e["id"] == reservation.id)["payment_state"], "paid")


@tagged("post_install", "-at_install")
class TestPosRoute(HttpCase):
    """Task 14: Odoo's /pos/ui opens a session under sudo for any internal user; Elite Vet allows it
    only with the POS rights."""

    def test_doctor_cannot_open_the_till(self):
        config = self.env["elite.vet.sale.setup"].pos_config()
        doctor = self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "T18 lékařka route", "login": "t18_route_doctor", "password": "t18_route_doctor",
            "email": "t18_route_doctor@example.invalid",
            "groups_id": [(6, 0, [self.env.ref("base.group_user").id,
                                  self.env.ref("elite_vet_clinic.group_clinic_doctor").id])]})
        self.assertFalse(doctor.has_group("point_of_sale.group_pos_user"))
        sessions_before = self.env["pos.session"].search_count([("user_id", "=", doctor.id)])
        self.authenticate("t18_route_doctor", "t18_route_doctor")
        response = self.url_open("/pos/ui?config_id=%d" % config.id, allow_redirects=False)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.env["pos.session"].search_count([("user_id", "=", doctor.id)]), sessions_before)
