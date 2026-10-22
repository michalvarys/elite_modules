from odoo.tests import tagged

from .common import BASE, ClinicCase


@tagged("post_install", "-at_install")
class TestClinicSync(ClinicCase):
    """Contract v2 entities of the clinic fed straight into the sync engine."""

    def find(self, model, n):
        return self.env[model].with_context(active_test=False).search([("winvet_ref", "=", BASE + n)])

    def bundle(self, n, **over):
        rec = {"id": BASE + n, "code": "VAK%s" % n, "name": "Vakcinace psa %s" % n, "description": "Roční"}
        rec.update(over)
        return rec

    def bline(self, n, bundle_n, item_n, **over):
        rec = {"id": BASE + n, "bundle_id": BASE + bundle_n, "item_id": BASE + item_n, "item_name": None,
               "quantity": 1, "unit": "ks", "sequence": n}
        rec.update(over)
        return rec

    def phrase(self, n, **over):
        rec = {"id": BASE + n, "name": "Bez nálezu %s" % n, "group": 3, "text": "Celkový stav dobrý."}
        rec.update(over)
        return rec

    def test_entities_registered(self):
        entities = self.sync._winvet_entities()
        # after the base entities (modules installed later, e.g. elite_vet_sale, append their own)
        start = entities.index("payments") + 1
        self.assertEqual(entities[start:start + 3], ["bundles", "bundle_lines", "phrases"])
        self.assertEqual(entities.index("vitals"), entities.index("visits") + 1)
        self.push_ok("phrases", [self.phrase(1)])
        line = self.env["elite.vet.winvet.status"].get_status().entity_ids.filtered(lambda e: e.entity == "phrases")
        self.assertEqual(line.sequence, entities.index("phrases"))
        self.assertEqual(dict(line._fields["entity"]._description_selection(self.env))["phrases"], "Šablony textů")

    def test_bundles_and_lines(self):
        res = self.push_ok("bundles", [self.bundle(100)])
        self.assertEqual(res["created"], 1)
        # a line before its bundle (another bundle id) is stored and linked later
        self.push_ok("bundle_lines", [self.bline(110, 100, 1, item_name="Vyšetření"), self.bline(111, 100, 2, quantity=2),
                                      self.bline(112, 101, 3)])
        bundle = self.find("elite.vet.procedure.bundle", 100)
        self.assertEqual((bundle.code, bundle.name, bundle.description), ("VAK100", "Vakcinace psa 100", "Roční"))
        self.assertEqual(bundle.line_ids.mapped("name"), ["Vyšetření", "Vakcína testovací DHPPi"])
        self.assertEqual(bundle.line_ids[1].quantity, 2)
        self.assertEqual(bundle.line_ids[1].item_id, self.vaccine)
        orphan = self.find("elite.vet.procedure.bundle.line", 112)
        self.assertFalse(orphan.bundle_id)
        self.push_ok("bundles", [self.bundle(101)])
        self.assertEqual(orphan.bundle_id, self.find("elite.vet.procedure.bundle", 101))
        self.assertFalse(bundle.edited_in_odoo, "sync writes are not Odoo edits")
        # idempotent
        self.assertEqual(self.push_ok("bundles", [self.bundle(100)])["updated"], 0)
        self.assertEqual(self.push_ok("bundle_lines", [self.bline(111, 100, 2, quantity=2)])["updated"], 0)
        # WinVet change written; deletions: bundle archived, line deleted
        self.push_ok("bundles", [self.bundle(100, name="Vakcinace psa – nová")])
        self.assertEqual(bundle.name, "Vakcinace psa – nová")
        self.push_ok("bundle_lines", [], deleted=[BASE + 110])
        self.assertFalse(self.find("elite.vet.procedure.bundle.line", 110))
        self.push_ok("bundles", [], deleted=[BASE + 101])
        self.assertFalse(self.find("elite.vet.procedure.bundle", 101).active)

    def test_edited_bundle_protected(self):
        self.push_ok("bundles", [self.bundle(100)])
        self.push_ok("bundle_lines", [self.bline(110, 100, 1), self.bline(111, 100, 2)])
        bundle = self.find("elite.vet.procedure.bundle", 100)
        bundle.with_user(self.doctor_user).write({"name": "Naše vakcinace"})
        self.assertTrue(bundle.edited_in_odoo)
        own_line = self.env["elite.vet.procedure.bundle.line"].create(
            {"bundle_id": bundle.id, "item_id": self.dewormer.id, "name": "Tableta"})
        self.push_ok("bundles", [self.bundle(100, name="Z WinVetu")])
        self.assertEqual(bundle.name, "Naše vakcinace")
        self.push_ok("bundle_lines", [self.bline(110, 100, 1, quantity=5), self.bline(120, 100, 3)])
        self.assertEqual(self.find("elite.vet.procedure.bundle.line", 110).quantity, 1)
        self.assertFalse(self.find("elite.vet.procedure.bundle.line", 120), "no new lines in an edited bundle")
        # full runs and deletions leave the edited bundle and its lines alone
        self.push_ok("bundle_lines", [], mode="full", run_id="bl-full")
        self.assertEqual(len(bundle.line_ids), 3)
        self.assertTrue(own_line.exists())
        self.push_ok("bundles", [], mode="full", run_id="b-full")
        self.assertTrue(bundle.active)

    def test_full_run_archives_bundles_deletes_lines(self):
        self.push_ok("bundles", [self.bundle(100), self.bundle(101)])
        self.push_ok("bundle_lines", [self.bline(110, 100, 1), self.bline(111, 101, 2)])
        own = self.env["elite.vet.procedure.bundle"].create({"name": "Jen v Odoo"})
        self.push_ok("bundles", [self.bundle(100)], mode="full", run_id="b-full-2")
        self.push_ok("bundle_lines", [self.bline(110, 100, 1)], mode="full", run_id="bl-full-2")
        self.assertTrue(self.find("elite.vet.procedure.bundle", 100).active)
        self.assertFalse(self.find("elite.vet.procedure.bundle", 101).active)
        self.assertFalse(self.find("elite.vet.procedure.bundle.line", 111))
        self.assertTrue(own.active)

    def test_phrases(self):
        res = self.push_ok("phrases", [self.phrase(200), self.phrase(201, text=None, group=None)])
        self.assertEqual(res["created"], 2)
        tpl, empty = self.find("elite.vet.text.template", 200), self.find("elite.vet.text.template", 201)
        self.assertEqual((tpl.name, tpl.body, tpl.section, tpl.group_name),
                         ("Bez nálezu 200", "Celkový stav dobrý.", "any", "3"))
        self.assertEqual(empty.body, "Bez nálezu 201", "a phrase without text falls back to its name")
        # the section chosen in Odoo survives a WinVet change of the text
        tpl.section = "examination"
        self.push_ok("phrases", [self.phrase(200, text="Celkový stav velmi dobrý.")])
        self.assertEqual((tpl.body, tpl.section), ("Celkový stav velmi dobrý.", "examination"))
        # edited in Odoo -> never overwritten nor archived
        tpl.with_user(self.doctor_user).body = "Náš text"
        self.push_ok("phrases", [self.phrase(200, text="WinVet zase jinak")])
        self.assertEqual(tpl.body, "Náš text")
        self.push_ok("phrases", [], deleted=[BASE + 200, BASE + 201])
        self.assertTrue(tpl.active)
        self.assertFalse(empty.active)
        own = self.env["elite.vet.text.template"].create({"name": "Vlastní", "body": "x"})
        self.push_ok("phrases", [], mode="full", run_id="ph-full")
        self.assertTrue(own.active)
