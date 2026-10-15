import json

from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestAuth(HttpCase):

    def rpc(self, path, params, key=None):
        headers = {"Content-Type": "application/json"}
        if key is not None:
            headers["Authorization"] = "Bearer %s" % key
        resp = self.url_open(path, data=json.dumps({"jsonrpc": "2.0", "method": "call", "params": params}),
                             headers=headers)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertNotIn("error", body, body.get("error"))
        return body["result"]

    def test_key_is_stored_only_as_hash(self):
        key = self.env["elite.vet.winvet.config"].generate_key()
        stored = self.env["ir.config_parameter"].sudo().get_param("elite_vet_winvet.api_key_hash")
        self.assertNotEqual(stored, key)
        self.assertEqual(len(stored), 64)
        self.assertNotIn(key, json.dumps(self.env["ir.config_parameter"].sudo().search([]).mapped("value")))

    def test_generate_button_shows_key_once(self):
        Config = self.env["elite.vet.winvet.config"]
        action = Config.create({}).action_generate_key()
        key = action["context"]["winvet_new_key"]
        shown = Config.with_context(action["context"]).browse(action["res_id"])
        self.assertEqual(shown.new_key, key)
        self.assertTrue(shown.key_set)
        self.assertFalse(Config.browse(action["res_id"]).with_context(winvet_new_key=False).new_key)
        self.assertTrue(Config.check_key(key))

    def test_no_key_configured(self):
        self.env["ir.config_parameter"].sudo().set_param("elite_vet_winvet.api_key_hash", False)
        res = self.rpc("/winvet/api/v1/status", {"winvet_version": "2603"}, key="anything")
        self.assertEqual(res, {"ok": False, "error": "unauthorized"})

    def test_missing_and_wrong_key(self):
        self.env["elite.vet.winvet.config"].generate_key()
        self.assertEqual(self.rpc("/winvet/api/v1/status", {}), {"ok": False, "error": "unauthorized"})
        self.assertEqual(self.rpc("/winvet/api/v1/push", {"entity": "users", "records": []}, key="wrong"),
                         {"ok": False, "error": "unauthorized"})

    def test_correct_key(self):
        key = self.env["elite.vet.winvet.config"].generate_key()
        res = self.rpc("/winvet/api/v1/status", {
            "bridge_version": "1.0.0", "source": "live", "winvet_version": "2603", "ods": "13.1",
            "engine": "5.0.1", "fingerprints": {"owners": "abc"}, "blocked": [], "journal_cursor": 5,
            "message": None}, key=key)
        self.assertEqual(res, {"ok": True})
        status = self.env["elite.vet.winvet.status"].get_status()
        self.assertEqual(status.bridge_version, "1.0.0")
        self.assertEqual(status.journal_cursor, 5)
        res = self.rpc("/winvet/api/v1/push", {
            "entity": "users", "mode": "incremental", "batch": 1, "batches": 1, "run_id": "r1", "deleted": [],
            "records": [{"id": 9_100_001, "name": "Testová Alena", "code": "TA", "active": True}]}, key=key)
        self.assertEqual(res, {"ok": True, "created": 1, "updated": 0, "deleted": 0, "skipped": 0})
        self.assertTrue(self.env["elite.vet.winvet.user"].search([("winvet_ref", "=", 9_100_001)]))

    def test_unknown_entity(self):
        key = self.env["elite.vet.winvet.config"].generate_key()
        res = self.rpc("/winvet/api/v1/push", {"entity": "dekurs", "records": []}, key=key)
        self.assertFalse(res["ok"])
