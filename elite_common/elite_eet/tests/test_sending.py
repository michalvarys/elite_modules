from datetime import datetime, timedelta
from unittest.mock import patch

from lxml import etree

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.elite_eet.eet import transport, wssec

from .common import EetCase

SEND = "odoo.addons.elite_eet.eet.transport.send"


def pok(**kw):
    return transport.Result(
        "pok", pok="4425d4b1-329d-4a24-949a-986a62bc308d-ff", test=True,
        received_at=datetime(2027, 1, 15, 8, 0, 1), http_status=200, transaction_id="t1",
        response_xml=b"<ok/>", **kw,
    )


def result(kind, code=None, message="x"):
    return transport.Result(kind, code=code, message=message, http_status=200 if code is not None else None)


class FakeSend:
    def __init__(self, *results):
        self.results = list(results)
        self.calls = []

    def __call__(self, url, envelope, timeout, post=None):
        self.calls.append((url, envelope, timeout))
        return self.results.pop(0) if len(self.results) > 1 else self.results[0]


@tagged("post_install", "-at_install")
class TestEetSending(EetCase):
    def make_sale(self, porad_cis="Arena/0001", device=None, **vals):
        values = {
            "device_id": (device or self.device).id,
            "porad_cis": porad_cis,
            "dat_trzby": fields.Datetime.now() - timedelta(minutes=1),
            "celk_trzba": 250.0,
        }
        values.update(vals)
        return self.env["elite.eet.sale"].create(values)

    def test_pok_registers_sale(self):
        sale = self.make_sale()
        fake = FakeSend(pok(warnings=[(1, "EIC nesouhlasi")]))
        with patch(SEND, fake):
            res = sale._eet_send()
        self.assertEqual(res, {sale.id: "pok"})
        self.assertEqual(sale.state, "registered")
        self.assertTrue(sale.pok.endswith("-ff"))
        self.assertTrue(sale.is_test)
        self.assertIn("EIC nesouhlasi", sale.warning_text)
        self.assertEqual(len(sale.attempt_ids), 1)
        attempt = sale.attempt_ids
        self.assertTrue(attempt.first_send)
        self.assertEqual(attempt.result, "pok")
        self.assertEqual(attempt.transaction_id, "t1")
        self.assertTrue(wssec.verify_envelope(attempt.request_xml.encode()))
        self.assertEqual(fake.calls[0][0], "https://pg.trzbyeet.gov.cz/eet/services/EETServiceSOAP/v4")
        self.assertEqual(fake.calls[0][2], 3.0)

    def test_temporary_stays_pending(self):
        sale = self.make_sale()
        with patch(SEND, FakeSend(result("temporary", -1))):
            sale._eet_send()
        self.assertEqual(sale.state, "pending")
        self.assertEqual(sale.attempt_ids.result, "temporary")

    def test_no_response_stays_pending(self):
        sale = self.make_sale()
        with patch(SEND, FakeSend(result("no_response"))):
            sale._eet_send()
        self.assertEqual(sale.state, "pending")
        self.assertEqual(sale.attempt_ids.result, "no_response")

    def test_critical_sets_error_and_notifies(self):
        sale = self.make_sale()
        with patch(SEND, FakeSend(result("critical", 4, "Neplatny podpis SOAP zpravy"))):
            sale._eet_send()
        self.assertEqual(sale.state, "error")
        self.assertIn("Neplatny podpis", sale.last_error)
        self.assertEqual(len(self.device.activity_ids), 1)

    def test_local_error(self):
        sale = self.make_sale(celk_trzba=100_000_000)
        with patch(SEND, FakeSend(pok())) as fake:
            res = sale._eet_send()
        self.assertEqual(res, {sale.id: "local_error"})
        self.assertEqual(sale.state, "error")
        self.assertEqual(sale.attempt_ids.result, "local_error")
        self.assertFalse(fake.calls)

    def test_resend_new_uuid_same_data(self):
        sale = self.make_sale()
        with patch(SEND, FakeSend(result("no_response"), pok())):
            sale._eet_send()
            sale._eet_send()
        first, second = sale.attempt_ids.sorted("id")
        self.assertNotEqual(first.uuid, second.uuid)
        self.assertTrue(first.first_send)
        self.assertFalse(second.first_send)

        def data_c14n(attempt):
            root = etree.fromstring(attempt.request_xml.encode())
            return etree.tostring(root.find(".//{*}Data"), method="c14n", exclusive=True)

        self.assertEqual(data_c14n(first), data_c14n(second))
        self.assertEqual(sale.state, "registered")

    def test_first_send_override(self):
        sale = self.make_sale()
        with patch(SEND, FakeSend(pok())):
            sale._eet_send(first_send=False)
        self.assertFalse(sale.attempt_ids.first_send)

    def test_data_frozen_after_attempt(self):
        sale = self.make_sale()
        with patch(SEND, FakeSend(result("no_response"))):
            sale._eet_send()
        with self.assertRaises(UserError):
            sale.celk_trzba = 300

    def test_registered_not_resent(self):
        sale = self.make_sale()
        with patch(SEND, FakeSend(pok())) as fake:
            sale._eet_send()
            action = sale.action_send_to_eet()
        self.assertEqual(len(fake.calls), 1)
        self.assertEqual(len(sale.attempt_ids), 1)
        self.assertIn("přeskočeno 1", action["params"]["message"])

    def test_batch_action_resends_pending_and_error(self):
        pending = self.make_sale("A1")
        error = self.make_sale("A2")
        error.state = "error"
        with patch(SEND, FakeSend(pok())):
            action = (pending | error).action_send_to_eet()
        self.assertEqual((pending | error).mapped("state"), ["registered", "registered"])
        self.assertFalse(any((pending | error).attempt_ids.mapped("first_send")))
        self.assertIn("evidováno 2", action["params"]["message"])

    def test_cron_skips_device_after_no_response(self):
        for i in range(3):
            self.make_sale(f"C{i}")
        other_device = self.make_device(eic="CZ683555118")
        other = self.make_sale("D1", device=other_device)
        with patch(SEND, FakeSend(result("no_response"))) as fake:
            self.env["elite.eet.sale"]._cron_send_pending()
        self.assertEqual(len(self.device.attempt_ids), 1)
        self.assertEqual(len(other.attempt_ids), 1)

    def test_inactive_device_not_sent(self):
        sale = self.make_sale()
        self.device.active_eet = False
        with patch(SEND, FakeSend(pok())) as fake:
            sale._eet_send()
            self.env["elite.eet.sale"]._cron_send_pending()
        self.assertFalse(fake.calls)
        self.assertEqual(sale.state, "pending")

    def test_check_connection_verified(self):
        verified = transport.Result("verified", code=0, message="OK", http_status=200)
        with patch(SEND, FakeSend(verified)):
            action = self.device.action_check_connection()
        self.assertEqual(action["params"]["type"], "success")
        attempt = self.device.attempt_ids
        self.assertTrue(attempt.verification)
        self.assertFalse(attempt.sale_id)
        self.assertIn('overeni="true"', attempt.request_xml)

    def test_check_connection_failure(self):
        with patch(SEND, FakeSend(result("critical", 4, "Neplatny podpis"))):
            action = self.device.action_check_connection()
        self.assertEqual(action["params"]["type"], "danger")
        self.assertIn("4", action["params"]["message"])

    def test_watch_notifies_once(self):
        self.make_sale(dat_trzby=fields.Datetime.now() - timedelta(hours=25))
        self.env["elite.eet.device"]._cron_watch()
        self.env["elite.eet.device"]._cron_watch()
        activities = self.device.activity_ids
        self.assertEqual(len(activities), 1)
        self.assertEqual(activities.user_id, self.device.responsible_user_id)
        self.assertIn("24 hodin", activities.summary)

    def test_watch_past_deadline(self):
        self.make_sale(dat_trzby=fields.Datetime.now() - timedelta(hours=49))
        self.env["elite.eet.device"]._cron_watch()
        self.assertTrue(any("48 hodin" in s for s in self.device.activity_ids.mapped("summary")))

    def test_watch_certificate_expiry(self):
        self.device.cert_valid_to = fields.Datetime.now() + timedelta(days=10)
        self.env["elite.eet.device"]._cron_watch()
        self.assertTrue(any("Certifikát" in s for s in self.device.activity_ids.mapped("summary")))

    def test_password_not_in_attempts(self):
        sale = self.make_sale()
        with patch(SEND, FakeSend(result("critical", 4))):
            sale._eet_send()
        attempt = sale.attempt_ids
        for value in (attempt.request_xml, attempt.response_xml or "", attempt.message or "", sale.last_error):
            self.assertNotIn("aaaa1111", value)

    def test_after_commit_registers_callback(self):
        sale = self.make_sale()
        before = len(self.env.cr.postcommit._funcs)
        sale._eet_send_after_commit(first_send=True)
        self.assertEqual(len(self.env.cr.postcommit._funcs), before + 1)
        self.env.cr.postcommit._funcs.pop()
