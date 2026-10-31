from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import HttpCase, tagged

from odoo.addons.elite_arena_ggleap.models.sync import GgleapSync

from .common import FakeGrant, free_hour_product, make_player


@tagged("post_install", "-at_install")
class TestRewardClaim(HttpCase):

    def setUp(self):
        super().setUp()
        self.partner = self.env["res.partner"].create({"name": "Karel Testovací", "email": "karel@example.com"})
        self.player = make_player(self.env, self.partner)
        self.product = free_hour_product(self.env)
        self.reward = self.env.ref("elite_arena_reward.reward_free_hour")
        self.reward.product_id = self.product

    def test_free_hour_is_the_default_product(self):
        self.reward.product_id = False
        product = self.reward._resolve_product()   # the synced one or the test one
        self.assertEqual((product.kind, product.seconds, product.price), ("free", 3600, 0.0))

    def test_claim_adds_the_pass_once(self):
        claim = self.reward.create_claim(self.partner, "Test")
        self.assertEqual(claim.state, "offered")
        self.assertTrue(claim.url.endswith("/odmena/" + claim.token))
        grant = FakeGrant()
        with patch.object(GgleapSync, "grant_gamepass", grant):
            claim.claim()
            claim.claim()   # double click
        self.assertEqual(len(grant.calls), 1)
        call = grant.calls[0]
        self.assertEqual((call["player"], call["product"], call["seconds"]), (self.player, self.product, 3600))
        self.assertTrue(call["key"].endswith("-claim-%d" % claim.id))
        self.assertEqual(claim.state, "claimed")
        self.assertTrue(claim.gamepass_id)
        days = (call["expires_at"] - fields.Datetime.now()).days
        self.assertIn(days, (14, 15), "pass valid 14 days from the claim")
        self.assertIn("vyzvedl odměnu", self.partner.message_ids[0].body)

    def test_expired_test_and_failed_claims(self):
        claim = self.reward.create_claim(self.partner, "Test")
        claim.expires_at = fields.Datetime.now() - timedelta(minutes=1)
        with patch.object(GgleapSync, "grant_gamepass", FakeGrant()), self.assertRaises(UserError):
            claim.claim()
        self.env["elite.arena.reward.claim"]._cron_expire()
        self.assertEqual(claim.state, "expired")

        test_claim = self.reward.create_claim(self.partner, "Test", test=True)
        with patch.object(GgleapSync, "grant_gamepass", FakeGrant()) as _g, self.assertRaises(UserError):
            test_claim.claim()

        failing = self.reward.create_claim(self.partner, "Test")
        with patch.object(GgleapSync, "grant_gamepass", FakeGrant(fail=True)), self.assertRaises(UserError):
            failing.claim()
        self.assertEqual(failing.state, "offered", "the player can try again")

    def test_claim_page(self):
        claim = self.reward.create_claim(self.partner, "Test")
        page = self.url_open("/odmena/%s" % claim.token)
        self.assertEqual(page.status_code, 200)
        self.assertIn("Vyzvednout odměnu", page.text)
        self.assertIn("noindex", page.text)
        self.assertTrue(claim.visited_at)
        self.assertEqual(self.url_open("/odmena/neexistuje").status_code, 404)

        grant = FakeGrant()
        with patch.object(GgleapSync, "grant_gamepass", grant):
            csrf = page.text.split('name="csrf_token" value="')[1].split('"')[0]
            done = self.url_open("/odmena/%s/vyzvednout" % claim.token, data={"csrf_token": csrf})
        self.assertEqual(done.status_code, 200)
        self.assertIn("Odměnu máš na herním účtu", done.text)
        self.assertEqual(len(grant.calls), 1)
        claim.invalidate_recordset()
        self.assertEqual(claim.state, "claimed")
