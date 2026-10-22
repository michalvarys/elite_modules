import importlib.util
import os

from odoo.tests import tagged

from .common import SaleCase


@tagged("post_install", "-at_install")
class TestBoardData(SaleCase):
    """Payment state of the visit record on the reservation board (spec section 4)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.room = cls.env["elite.vet.room"].create({"name": "Ordinace test platba"})
        cls.day = "2030-03-04"

    def reservation(self, start, stop):
        return self.env["elite.vet.reservation"].create({
            "kind": "reservation", "state": "confirmed", "room_id": self.room.id,
            "start": "%s %s" % (self.day, start), "stop": "%s %s" % (self.day, stop),
            "partner_id": self.owner.id, "pet_id": self.pet.id})

    def event(self, reservation):
        events = self.env["elite.vet.reservation"].board_data(self.day)["events"]
        return next(e for e in events if e["id"] == reservation.id)

    def test_payment_state_follows_the_record(self):
        res = self.reservation("09:00:00", "09:30:00")
        self.assertIs(self.event(res)["payment_state"], False, "no record, no state")
        api = self.as_user(self.nurse)
        data = api.open_today_record(self.pet.id, reservation_id=res.id)
        record = self.Record.browse(data["id"])
        self.assertEqual(record.reservation_id, res)
        self.assertEqual(self.event(res)["payment_state"], "none", "a draft has no bill yet")
        api.add_free_line(record.id, "Stříhání drápků", 100.0)
        api.mark_done(record.id)
        self.assertEqual(self.event(res)["payment_state"], "waiting")
        self.settle(record.sale_order_id)
        self.assertEqual(self.event(res)["payment_state"], "paid")

    def test_reservation_without_record_is_false(self):
        res = self.reservation("11:00:00", "11:30:00")
        self.assertIs(self.event(res)["payment_state"], False)


@tagged("post_install", "-at_install")
class TestQuotationPricelist(SaleCase):
    """Visit quotations always use the till's CZK pricelist (ruling R11)."""

    def test_quotation_uses_till_pricelist_despite_usd_client_pricelist(self):
        usd = self.env.ref("base.USD")
        usd_list = self.env["product.pricelist"].create({"name": "TEST USD", "currency_id": usd.id})
        self.owner.property_product_pricelist = usd_list
        api = self.as_user(self.nurse)
        data = api.open_today_record(self.pet.id, force_new=True)
        api.add_free_line(data["id"], "Služba v Kč", 100.0)
        api.mark_done(data["id"])
        order = self.Record.browse(data["id"]).sale_order_id
        till_list = self.setup.pos_config().pricelist_id
        self.assertEqual(order.pricelist_id, till_list)
        self.assertEqual(order.currency_id.name, "CZK")
        self.settle(order)
        self.assertEqual(self.Record.browse(data["id"]).payment_state, "paid")

    def test_ensure_setup_twice_creates_no_second_pricelist(self):
        self.setup.ensure_setup()
        before = self.env["product.pricelist"].with_context(active_test=False).search_count([])
        self.setup.ensure_setup()
        self.assertEqual(self.env["product.pricelist"].with_context(active_test=False).search_count([]), before)
        config = self.setup.pos_config()
        self.assertEqual(config.pricelist_id.currency_id, self.company.currency_id)
        self.assertIn(config.pricelist_id, config.available_pricelist_ids)


@tagged("post_install", "-at_install")
class TestTillPricelistOnUpdate(SaleCase):
    """Module update re-runs the setup, so an upgraded DB gets a CZK till pricelist (ruling R12)."""

    def usd_pricelist(self, name):
        return self.env["product.pricelist"].create({"name": name, "currency_id": self.env.ref("base.USD").id})

    def force_till_pricelist(self, pricelist):
        """The state of a DB installed before R11; the ORM constraint forbids it, hence SQL."""
        config = self.setup.pos_config()
        self.env.flush_all()
        self.env.cr.execute("UPDATE pos_config SET pricelist_id = %s WHERE id = %s", (pricelist.id, config.id))
        self.env.cr.execute("DELETE FROM pos_config_product_pricelist_rel WHERE pos_config_id = %s", (config.id,))
        self.env.cr.execute("INSERT INTO pos_config_product_pricelist_rel (pos_config_id, product_pricelist_id) "
                            "VALUES (%s, %s)", (config.id, pricelist.id))
        self.env.invalidate_all()
        self.assertEqual(config.pricelist_id, pricelist)
        return config

    def test_migration_switches_till_to_czk(self):
        config = self.force_till_pricelist(self.usd_pricelist("TEST USD till"))
        path = os.path.join(os.path.dirname(__file__), "..", "migrations", "18.0.1.0.1", "post-migrate.py")
        spec = importlib.util.spec_from_file_location("ev_sale_migration_1_0_1", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.migrate(self.env.cr, "18.0.1.0.0")
        self.env.invalidate_all()
        self.assertEqual(config.pricelist_id.currency_id.name, "CZK")
        self.assertIn(config.pricelist_id, config.available_pricelist_ids)

    def test_used_default_pricelist_is_not_switched(self):
        usd = self.env.ref("base.USD")
        default = self.env.ref("product.list0", raise_if_not_found=False)
        if default:
            default.write({"currency_id": usd.id, "name": "Default"})
        else:  # a DB without demo data may lack it
            default = self.usd_pricelist("Default")
            self.env["ir.model.data"]._update_xmlids([{"xml_id": "product.list0", "record": default}])
        self.env["ir.model.data"].search([("module", "=", "elite_vet_sale"), ("name", "=", "pricelist_czk")]).unlink()
        self.env["product.pricelist"].with_context(active_test=False).search(
            [("name", "=", "Ceník Kč")]).write({"name": "TEST old Kč list"})
        self.owner.specific_property_product_pricelist = default
        config = self.force_till_pricelist(self.usd_pricelist("TEST USD till 2"))
        self.setup.ensure_setup()
        self.env.invalidate_all()
        self.assertEqual(default.currency_id, usd, "a used default pricelist keeps its currency")
        self.assertEqual(default.name, "Default")
        till_list = config.pricelist_id
        self.assertNotEqual(till_list, default)
        self.assertEqual(till_list.name, "Ceník Kč")
        self.assertEqual(till_list.currency_id, self.company.currency_id)
        self.assertEqual(self.env.ref("elite_vet_sale.pricelist_czk"), till_list)
