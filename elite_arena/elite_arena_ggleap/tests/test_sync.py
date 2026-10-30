from datetime import datetime, timedelta
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

from ..models.config import DEFAULTS
from ..models.ggleap_client import GgleapClient, GgleapError
from ..models.sync import parse_dt, parse_duration, segment

NOW = datetime(2026, 10, 28, 12, 0, 0)
U1, U2, U3, U4 = ("u1-0000-test", "u2-0000-test", "u3-0000-test", "u4-0000-test")
PC1, PC2 = "pc1-0000-test", "pc2-0000-test"
HOUR3, FREE1, COLA, PS5 = "offer-3h-test", "offer-free-test", "prod-cola-test", "offer-ps5-test"


def ts(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S.123Z")


class FakeClient(GgleapClient):
    """Answers like ggLeap from in-memory data; filters time ranges like the API."""

    def __init__(self, data, fail=()):
        self.data = data
        self.fail = set(fail)
        self.calls = 0
        self.log = []
        self.posts = []

    def get(self, path, params=None):
        self.calls += 1
        self.log.append((path, dict(params or {})))
        if path in self.fail:
            raise GgleapError("simulovaná chyba %s" % path)
        params = params or {}
        if path == "/machines/get-all":
            return {"Machines": self.data["machines"]}
        if path == "/pos/products/get-all":
            return {"Products": self.data["products"], "Offers": self.data["offers"], "ComboDeals": []}
        if path == "/users/summaries":
            return {"Users": self.data["users"]}
        if path == "/users/user-details":
            return {"User": self.data["details"].get(params["Uuid"], {})}
        if path in ("/activity-logs/search", "/transactions/search"):
            start, end = parse_dt(params["Start"]), parse_dt(params["End"])
            key, field = ("activity", "DateTime") if path.startswith("/activity") else ("transactions", None)
            out = []
            for row in self.data[key]:
                when = parse_dt(row["DateTime"] if field else row["Details"]["DateTime"])
                if start <= when < end:
                    out.append(row)
            return {"Entries" if key == "activity" else "Transactions": out}
        if path == "/sessions/get-user-sessions":
            start, end = parse_dt(params["Start"]), parse_dt(params["End"])
            return {"Sessions": [x for x in self.data["sessions"].get(params["UserUuid"], [])
                                 if start <= parse_dt(x["StartDateTime"]) < end]}
        if path == "/bookings/get-bookings":
            day = datetime.strptime(params["Date"], "%Y-%m-%d")
            return {"Bookings": [b for b in self.data["bookings"]
                                 if day <= parse_dt(b["Start"]) < day + timedelta(days=params["Days"])]}
        if path == "/users/gamepasses/list":
            return {"Offers": list(self.data["gamepasses"].get(params["UserUuid"], []))}
        raise AssertionError("neočekávaný dotaz %s" % path)

    def post(self, path, body, correlation_id=None):
        self.calls += 1
        self.posts.append((path, body, correlation_id))
        if path in self.fail:
            raise GgleapError("simulovaná chyba %s" % path)
        if path == "/users/gamepasses/add":
            dto = dict(body, Uuid="gp-new-%d" % len(self.posts), AddedAt=ts(NOW), SecondsUsed=0)
            self.data["gamepasses"].setdefault(body["UserUuid"], []).append(dto)
            return {"Offer": dto}
        raise AssertionError("neočekávaný zápis %s" % path)


def user(uuid, email, first, last, username, **over):
    row = {"Uuid": uuid, "Username": username, "Email": email, "Phone": None, "FirstName": first,
           "LastName": last, "Balance": 0.0, "GroupUuid": "grp", "Locked": False}
    row.update(over)
    return row


def login(uuid, user_uuid, machine, when, guest=False):
    return {"Uuid": uuid, "DateTime": ts(when), "Action": "LoggedIn", "UserUuid": user_uuid,
            "MachineUuid": machine, "IsGuest": guest, "Data": {}}


def logout(uuid, user_uuid, machine, when, duration, guest=False):
    return {"Uuid": uuid, "DateTime": ts(when), "Action": "LoggedOut", "UserUuid": user_uuid,
            "MachineUuid": machine, "IsGuest": guest, "Data": {"Duration": duration}}


def sale(uuid, user_uuid, when, items, status="Paid", cash=0.0, card=0.0):
    total = sum(i["GrossTotalValue"] for i in items)
    return {"TransactionUuid": uuid, "TransactionId": "T-" + uuid[:6], "Type": "Sale", "Status": status,
            "Source": "Employee",
            "Details": {"DateTime": ts(when), "TotalGross": total, "TotalDiscount": 0.0, "PaidWithCash": cash,
                        "PaidWithCard": card, "PaidWithBalance": 0.0, "Employee": {"Name": "obsluha"},
                        "User": {"Uuid": user_uuid} if user_uuid else {}},
            "Items": {str(n): i for n, i in enumerate(items)}}


def gamepass(uuid, offer, name, seconds, used=0, added=None, consumed=None, expires=None):
    return {"Uuid": uuid, "OfferUuid": offer, "Name": name, "Seconds": seconds, "SecondsUsed": used,
            "Type": "StartOnFirstUse", "Priority": "Normal", "AddedAt": ts(added or NOW - timedelta(days=5)),
            "ConsumedAt": ts(consumed) if consumed else None,
            "ExpiresAt": ts(expires or NOW + timedelta(days=365)), "EligibleDays": [], "EligiblePcGroups": []}


def item(product, name, qty, amount):
    return {"ProductUuid": product, "Name": name, "Quantity": qty, "GrossTotalValue": amount}


def dataset():
    d1 = NOW - timedelta(days=45)
    d2 = NOW - timedelta(days=40)
    d3 = NOW - timedelta(days=5)
    return {
        "machines": [{"Uuid": PC1, "Name": "PC1", "GroupUuid": "g", "State": "ReadyForUser",
                      "LastUpdate": ts(NOW)},
                     {"Uuid": PC2, "Name": "PC2", "GroupUuid": "g", "State": "InUse", "LastUpdate": ts(NOW)}],
        "products": [{"ProductUuid": COLA, "Name": "Coca Cola 330ML", "ProductType": "Generic", "Price": 45.0}],
        "offers": [{"OfferUuid": HOUR3, "Name": "3 Hodiny", "Price": 210.0, "Seconds": 10800,
                    "OfferType": "StartOnFirstUse", "Priority": "Normal", "EligibleDays": [0, 1, 2, 3, 4, 5, 6],
                    "EligiblePcGroups": []},
                   {"OfferUuid": FREE1, "Name": "1 HODINA FREE", "Price": 0.0, "Seconds": 3600,
                    "OfferType": "StartOnFirstUse", "Priority": "Highest", "EligibleDays": [0, 1, 2, 3, 4, 5, 6],
                    "EligiblePcGroups": []},
                   {"OfferUuid": PS5, "Name": "PS5 1 Hodina", "Price": 130.0, "Seconds": 3600,
                    "OfferType": "StartOnAllocation", "Priority": "High", "EligibleDays": [6, 0],
                    "EligiblePcGroups": ["grp-ps5"]}],
        "users": [
            user(U1, "Karel.Novak@Example.com", "karel", "novák", "kaja"),
            user(U2, "jana@example.com", "Jana", "Dvořáková", "janca"),
            user(U3, "petr@example.com", "Petr", "Svoboda", "peta"),
            user(U4, None, None, None, "anon"),
        ],
        "details": {
            U1: {"RegisteredAt": ts(d1 - timedelta(days=1)), "LastSeen": ts(d3), "Birthdate": "2005-05-15T00:00:00Z",
                 "TimeRemaining": 1800},
            U2: {"RegisteredAt": ts(d1), "LastSeen": ts(d2)},
            U3: {"RegisteredAt": ts(d1), "LastSeen": None},
            U4: {"RegisteredAt": ts(d1), "LastSeen": ts(NOW - timedelta(days=200))},
        },
        "activity": [
            {"Uuid": "a-created-u1", "DateTime": ts(d1 - timedelta(days=1)), "Action": "CreatedUser",
             "UserUuid": U1, "MachineUuid": None, "IsGuest": False, "Data": {}},
            login("a-in-1", U1, PC1, d1),
            logout("a-out-1", U1, PC1, d1 + timedelta(hours=2), "02:00:00"),
            login("a-in-2", U2, PC2, d2),
            logout("a-out-2", U2, PC2, d2 + timedelta(hours=1, minutes=30), "01:30:00"),
            login("a-in-3", U1, PC2, d3),
            logout("a-out-3", U1, PC2, d3 + timedelta(hours=3), "03:00:00"),
            # remote login (phone / QR): plain logout without duration, then remote logout
            dict(login("a-rin-4", U2, PC1, d2 + timedelta(days=1)), Action="RemoteLoggedIn"),
            logout("a-out-4", U2, PC1, d2 + timedelta(days=1, hours=2), "00:00:00"),
            # console (PS5 "L"): device instead of a PC, remote logout without duration
            dict(login("a-rin-5", U2, None, d2 + timedelta(days=3)), Action="RemoteLoggedIn",
                 DeviceUuid="dev-ps5-l", Data={"DeviceName": "L"}),
            dict(logout("a-rout-5", U2, None, d2 + timedelta(days=3, hours=1), None), Action="RemoteLoggedOut",
                 DeviceUuid="dev-ps5-l", Data={"DeviceName": "L"}),
            # second session the same evening = the same visit
            login("a-in-3b", U1, PC1, d3 + timedelta(hours=4)),
            logout("a-out-3b", U1, PC1, d3 + timedelta(hours=5), "01:00:00"),
            # time ran out: no logout in the activity log, the end comes from the sessions endpoint
            dict(login("a-rin-6", U1, PC1, d3 - timedelta(days=1)), Action="RemoteLoggedIn"),
            login("a-in-guest", None, PC1, d3, guest=True),
            logout("a-out-guest", None, PC1, d3 + timedelta(minutes=45), "00:45:00", guest=True),
        ],
        "transactions": [
            sale("t1-test", U1, d1 + timedelta(minutes=1), [item(HOUR3, "3 Hodiny", 1, 210.0),
                                                            item(COLA, "Coca Cola 330ML", 2, 90.0)], cash=300.0),
            dict(sale("t2-test", U1, d3, [item(FREE1, "1 HODINA FREE", 1, 1000.0)]),
                 Details=dict(sale("x", U1, d3, [])["Details"], TotalGross=0.0)),  # paid with coins
            sale("t3-test", U2, d2, [item(HOUR3, "3 Hodiny", 1, 210.0)], status="Refunded", card=210.0),
            sale("t4-test", None, d3, [item("unknown-prod", "Guest session (PC) - 1h", 1, 75.0)], card=75.0),
        ],
        "sessions": {U1: [{"StartDateTime": ts(d3 - timedelta(days=1) + timedelta(seconds=1)), "Seconds": 7200,
                           "Ended": True}]},
        "gamepasses": {
            U1: [gamepass("gp-u1-active", HOUR3, "3 Hodiny", 10800, used=3600),
                 gamepass("gp-u1-used", HOUR3, "3 Hodiny", 10800, used=10800, consumed=NOW - timedelta(days=40)),
                 gamepass("gp-u1-old", FREE1, "1 HODINA FREE", 3600, expires=NOW - timedelta(days=1))],
            U2: [gamepass("gp-u2-active", PS5, "PS5 1 Hodina", 3600, used=900)],
        },
        "bookings": [
            {"BookingUuid": "b1-test", "Name": "Pařba", "UserUuid": U1, "Start": ts(NOW + timedelta(days=2)),
             "Duration": 120, "Machines": [PC1, PC2], "Paid": False, "Deleted": False},
            {"BookingUuid": "b2-test", "Name": "Nedorazil", "UserUuid": U2, "Start": ts(NOW - timedelta(days=1)),
             "Duration": 60, "Machines": [PC1], "Paid": False, "Deleted": True, "DeleteReason": "NoShow"},
        ],
    }


@tagged("post_install", "-at_install")
class TestGgleapSync(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # start from an empty state even in a database that already holds synced data
        # (everything is rolled back after the tests)
        for model in ("elite.arena.ggleap.gamepass", "elite.arena.ggleap.transaction", "elite.arena.ggleap.visit", "elite.arena.ggleap.booking",
                      "elite.arena.ggleap.player", "elite.arena.ggleap.product", "elite.arena.ggleap.machine"):
            cls.env[model].with_context(active_test=False).search([]).unlink()
        status = cls.env["elite.arena.ggleap.status"].get_status()
        status.entity_ids.unlink()
        status.write({"activity_cursor": False, "transaction_cursor": False, "history_from": False,
                      "backfill_done": False, "last_error": False, "last_error_at": False,
                      "last_success_at": False, "calls_today": 0})
        cls.sync = cls.env["elite.arena.ggleap.sync"]
        cls.Player = cls.env["elite.arena.ggleap.player"]
        cls.settings = dict(DEFAULTS, auth_token="test", history_days=60, run_seconds=600, details_per_run=50)
        cls.partner_existing = cls.env["res.partner"].create({"name": "Jana z CRM", "email": "JANA@example.com"})
        cls.partner_survey = cls.env["res.partner"].create({"name": "Petr ze survey", "email": "jiny@example.com",
                                                            "ref": U3})

    def run_sync(self, data, now=NOW, **kw):
        client = FakeClient(data, **kw)
        message = self.sync.run(client=client, now=now, settings=self.settings)
        return client, message

    def player(self, uuid):
        return self.Player.search([("uuid", "=", uuid)])

    def test_helpers(self):
        self.assertEqual(parse_dt("2026-10-27T20:12:06.22Z"), datetime(2026, 10, 27, 20, 12, 6, 220000))
        self.assertEqual(parse_dt("2026-10-27T22:12:06+02:00"), datetime(2026, 10, 27, 20, 12, 6))
        self.assertIsNone(parse_dt("0218-01-01T00:00:00Z"))
        self.assertEqual(parse_duration("08:37:34"), timedelta(hours=8, minutes=37, seconds=34))
        self.assertEqual(parse_duration("1.02:00:00"), timedelta(days=1, hours=2))
        self.assertEqual(segment(0, None, NOW, 30, 90), "nikdy")
        self.assertEqual(segment(1, NOW - timedelta(days=10), NOW, 30, 90), "jednou_nedavno")
        self.assertEqual(segment(1, NOW - timedelta(days=40), NOW, 30, 90), "jednou_davno")
        self.assertEqual(segment(3, NOW - timedelta(days=40), NOW, 30, 90), "ohrozeni")
        self.assertEqual(segment(3, NOW - timedelta(days=100), NOW, 30, 90), "ztraceni")

    def test_full_run(self):
        client, message = self.run_sync(dataset())
        self.assertTrue(message.startswith("Hotovo"), message)
        status = self.env["elite.arena.ggleap.status"].get_status()
        self.assertFalse(status.last_error)
        self.assertTrue(status.backfill_done)
        self.assertEqual(status.activity_cursor, NOW)

        # players and their statistics
        u1, u2, u3, u4 = (self.player(u) for u in (U1, U2, U3, U4))
        self.assertEqual(u1.email, "karel.novak@example.com")
        self.assertEqual(u1.visit_count, 3, "days with sessions, not sessions")
        self.assertAlmostEqual(u1.hours_played, 8.0, places=3)
        self.assertEqual(u1.total_spent, 300.0)  # free hour = 0, refund of u2 not counted
        self.assertEqual(u1.segment, "aktivni_stali")
        self.assertEqual(u1.birthdate.isoformat(), "2005-05-15")
        self.assertAlmostEqual(u1.time_remaining_hours, 0.5)
        self.assertEqual(u2.visit_count, 3, "remote logins are visits too")
        self.assertAlmostEqual(u2.hours_played, 4.5, places=3)
        self.assertEqual(u2.segment, "ohrozeni")
        self.assertEqual(u2.total_spent, 0.0)
        self.assertEqual(u3.segment, "nikdy")
        self.assertEqual(u4.segment, "jednou_davno", "LastSeen from details counts as a visit before the history")
        self.assertTrue(u1.registered_at)

        # contacts: new one with a tidy name, existing one by e-mail keeps its name, survey one by ref
        self.assertEqual(u1.partner_id.name, "Karel Novák")
        self.assertEqual(u1.partner_id.ggleap_uuid, U1)
        self.assertEqual(u1.partner_id.ggleap_segment, "aktivni_stali")
        self.assertEqual(u1.partner_id.ggleap_visit_count, 3)
        self.assertEqual(u2.partner_id, self.partner_existing)
        self.assertEqual(self.partner_existing.name, "Jana z CRM")
        self.assertEqual(u3.partner_id, self.partner_survey)
        self.assertEqual(self.partner_survey.email, "jiny@example.com", "an existing e-mail is not overwritten")
        self.assertFalse(u4.partner_id, "no e-mail and no name: no contact")
        tag = self.env.ref("elite_arena_ggleap.partner_category_player")
        self.assertIn(tag, u1.partner_id.category_id)

        # visits: login + logout paired, guest kept
        Visit = self.env["elite.arena.ggleap.visit"]
        self.assertEqual(Visit.search_count([]), 8)
        closed = Visit.search([("login_uuid", "=", "a-rin-6")])
        self.assertEqual(closed.end_source, "session")
        self.assertAlmostEqual(closed.duration_hours, 2.0, places=3)
        guest = Visit.search([("is_guest", "=", True)])
        self.assertEqual(len(guest), 1)
        self.assertAlmostEqual(guest.duration_hours, 0.75, places=3)
        self.assertFalse(Visit.search([("end", "=", False)]))
        console = Visit.search([("device_uuid", "=", "dev-ps5-l")])
        self.assertEqual(console.place, "Konzole L")
        self.assertAlmostEqual(console.duration_hours, 1.0, places=3)

        # sales
        Tx = self.env["elite.arena.ggleap.transaction"]
        t1 = Tx.search([("uuid", "=", "t1-test")])
        self.assertTrue(t1.is_paid)
        self.assertEqual(t1.paid_cash, 300.0)
        kinds = {l.name: (l.kind, l.hours) for l in t1.line_ids}
        self.assertEqual(kinds["3 Hodiny"], ("time", 3.0))
        self.assertEqual(kinds["Coca Cola 330ML"][0], "food")
        free_line = Tx.search([("uuid", "=", "t2-test")]).line_ids
        self.assertEqual(free_line.kind, "free")
        self.assertEqual(free_line.amount, 0.0, "coins are not money")
        self.assertEqual(free_line.list_amount, 1000.0)
        self.assertFalse(Tx.search([("uuid", "=", "t3-test")]).is_paid)
        guest_sale = Tx.search([("uuid", "=", "t4-test")])
        self.assertFalse(guest_sale.player_id)
        self.assertEqual(guest_sale.line_ids.kind, "time")
        stub = self.env["elite.arena.ggleap.product"].search([("uuid", "=", "unknown-prod")])
        self.assertFalse(stub.in_catalog)

        # bookings
        Booking = self.env["elite.arena.ggleap.booking"]
        self.assertEqual(Booking.search([("uuid", "=", "b1-test")]).state, "planned")
        self.assertEqual(Booking.search([("uuid", "=", "b2-test")]).state, "noshow")

    def test_second_run_is_idempotent_and_copies_changes(self):
        data = dataset()
        self.run_sync(data)
        u1 = self.player(U1)
        u1.partner_id.name = "Karel Novák (upraveno v Odoo)"
        counts = {m: self.env[m].search_count([]) for m in (
            "elite.arena.ggleap.visit", "elite.arena.ggleap.transaction", "elite.arena.ggleap.transaction.line",
            "elite.arena.ggleap.player", "res.partner")}
        data["users"][0]["Email"] = "karel.novy@example.com"
        data["users"] = [u for u in data["users"] if u["Uuid"] != U3]   # deleted in ggLeap
        client, _message = self.run_sync(data)
        for model, count in counts.items():
            self.assertEqual(self.env[model].search_count([]), count, model)
        self.assertEqual(u1.partner_id.email, "karel.novy@example.com")
        self.assertEqual(u1.partner_id.name, "Karel Novák (upraveno v Odoo)", "only the changed field is copied")
        self.assertTrue(self.player(U3).deleted)
        details_calls = [c for c in client.log if c[0] in ("/users/user-details", "/sessions/get-user-sessions",
                                                            "/users/gamepasses/list")]
        self.assertFalse(details_calls, "details, session ends and passes are fetched only once")
        activity = [c for c in client.log if c[0] == "/activity-logs/search"]
        self.assertEqual(len(activity), 1, "the second run continues from the cursor")

    def test_error_in_one_area_does_not_stop_others(self):
        with self.assertLogs("odoo.addons.elite_arena_ggleap.models.sync", level="ERROR"):
            self.run_sync(dataset(), fail={"/transactions/search"})
        status = self.env["elite.arena.ggleap.status"].get_status()
        self.assertIn("transactions", status.last_error)
        self.assertTrue(status.alert)
        self.assertEqual(self.env["elite.arena.ggleap.transaction"].search_count([]), 0)
        self.assertEqual(self.env["elite.arena.ggleap.visit"].search_count([]), 8)
        self.assertFalse(status.transaction_cursor)
        # next run catches up
        self.run_sync(dataset())
        self.assertEqual(self.env["elite.arena.ggleap.transaction"].search_count([]), 4)
        self.assertFalse(status.last_error and status.last_error_at > status.last_success_at)

    def test_manual_product_kind_is_kept(self):
        self.run_sync(dataset())
        cola = self.env["elite.arena.ggleap.product"].search([("uuid", "=", COLA)])
        cola.kind = "other"
        self.assertTrue(cola.kind_manual)
        self.run_sync(dataset())
        self.assertEqual(cola.kind, "other")

    def test_dashboard(self):
        self.run_sync(dataset())
        dash = self.env["elite.arena.ggleap.dashboard"].with_context(tz="Europe/Prague")
        data = dash.get_data((NOW - timedelta(days=60)).date().isoformat(), NOW.date().isoformat())
        k = data["kpi"]
        self.assertEqual(k["revenue"], 375.0)        # t1 300 + t4 75 (refund and free hour excluded)
        self.assertEqual(k["revenue_time"], 285.0)
        self.assertEqual(k["revenue_food"], 90.0)
        self.assertEqual(k["visits"], 7)      # u1 3 days, u2 3 days, 1 guest
        self.assertEqual(k["sessions"], 8)
        self.assertEqual(k["guest_visits"], 1)
        self.assertEqual(k["new_players"], 2)
        self.assertAlmostEqual(k["hours_free"], 1.0)
        self.assertEqual(sum(sum(r) for r in data["heatmap"]), 7)
        self.assertEqual(sum(r["visits"] for r in data["daily"]), 7)
        segments = {s["key"]: s["count"] for s in data["segments"]}
        self.assertEqual(segments["aktivni_stali"], 1)
        self.assertEqual(segments["ohrozeni"], 1)
        self.assertEqual(segments["jednou_davno"], 1)
        self.assertEqual(data["top_players"][0]["amount"], 300.0)
        self.assertEqual({m["name"] for m in data["machines"]}, {"PC1", "PC2", "Konzole L"})
        self.assertTrue(data["payment_methods"])

    # ------------------------------------------------------------------ game passes
    def test_gamepasses(self):
        self.run_sync(dataset())
        u1, u2 = self.player(U1), self.player(U2)
        states = {g.uuid: (g.state, g.hours_left) for g in u1.gamepass_ids}
        self.assertEqual(states["gp-u1-active"], ("active", 2.0))
        self.assertEqual(states["gp-u1-used"], ("used", 0.0))
        self.assertEqual(states["gp-u1-old"], ("expired", 0.0))
        self.assertEqual(u1.pass_hours_left, 2.0)
        self.assertEqual(u1.partner_id.ggleap_pass_hours_left, 2.0)
        self.assertEqual(u1.partner_id.ggleap_active_gamepass_ids.mapped("uuid"), ["gp-u1-active"])
        self.assertEqual(u2.partner_id.ggleap_pass_hours_left, 0.75)
        hour3 = self.env["elite.arena.ggleap.product"].search([("uuid", "=", HOUR3)])
        self.assertEqual(u1.gamepass_ids.filtered(lambda g: g.uuid == "gp-u1-active").product_id, hour3)
        self.assertTrue(u1.gamepasses_synced_at)

        ps5 = self.env["elite.arena.ggleap.product"].search([("uuid", "=", PS5)])
        self.assertEqual(ps5.eligible_days, "Sunday,Saturday")
        self.assertEqual(ps5.eligible_pc_groups, '["grp-ps5"]')
        self.assertEqual(ps5.offer_type, "StartOnAllocation")
        self.assertFalse(hour3.eligible_days, "every day = no restriction")

    def test_gamepass_after_visit_and_removal(self):
        data = dataset()
        self.run_sync(data)
        u1 = self.player(U1)
        # the player came today and used up the pass; ggLeap also removed the old free hour
        data["activity"].append(login("a-in-today", U1, PC1, NOW + timedelta(minutes=30)))
        data["gamepasses"][U1] = [gamepass("gp-u1-active", HOUR3, "3 Hodiny", 10800, used=10800,
                                           consumed=NOW + timedelta(hours=2)),
                                  data["gamepasses"][U1][1]]
        self.run_sync(data, now=NOW + timedelta(hours=1))   # the visit is counted, passes are not due yet
        client, _message = self.run_sync(data, now=NOW + timedelta(hours=3))
        self.assertIn("/users/gamepasses/list", [c[0] for c in client.log], "reloaded after the visit")
        states = {g.uuid: g.state for g in u1.gamepass_ids}
        self.assertEqual(states["gp-u1-active"], "used")
        self.assertEqual(states["gp-u1-old"], "removed")
        self.assertEqual(u1.partner_id.ggleap_pass_hours_left, 0.0)

    def test_grant_gamepass(self):
        data = dataset()
        self.run_sync(data)
        self.env["ir.config_parameter"].sudo().set_param("elite_arena_ggleap.auth_token", "test")
        u1 = self.player(U1)
        partner = u1.partner_id
        client = FakeClient(data)
        Wizard = self.env["elite.arena.ggleap.gamepass.wizard"]
        with patch.object(type(self.sync), "_make_client", return_value=client):
            wizard = Wizard.with_context(**partner.action_grant_ggleap_gamepass()["context"]).create(
                {"note": "dotazník"})
            self.assertEqual(wizard.player_id, u1)
            self.assertEqual(wizard.product_id.uuid, FREE1, "1 free hour is the default")
            wizard._onchange_product_id()
            self.assertEqual(wizard.hours, 1.0)
            wizard.action_grant()
            wizard.action_grant()   # double click: the same idempotency key
        (path, body, key), second = client.posts
        self.assertEqual(path, "/users/gamepasses/add")
        self.assertEqual(second[2], key)
        self.assertTrue(key.startswith("odoo-"))
        self.assertEqual(body["UserUuid"], U1)
        self.assertEqual(body["OfferUuid"], FREE1)
        self.assertEqual(body["Seconds"], 3600)
        self.assertEqual(body["Priority"], "Highest")
        self.assertEqual(len(body["EligibleDays"]), 7)
        self.assertEqual(body["EligiblePcGroups"], [])
        self.assertTrue(body["ExpiresAt"].endswith("Z"))

        granted = u1.gamepass_ids.filtered("granted_in_odoo")
        self.assertEqual(len(granted), 2, "the fake adds twice; ggLeap would add once")
        self.assertEqual(granted[0].grant_note, "dotazník")
        self.assertEqual(granted[0].granted_by_id, self.env.user)
        self.assertEqual(partner.ggleap_pass_hours_left, 4.0)
        self.assertIn("Přidán herní pass", partner.message_ids[0].body)

        # restrictions of the product go with the pass
        with patch.object(type(self.sync), "_make_client", return_value=client):
            ps5 = self.env["elite.arena.ggleap.product"].search([("uuid", "=", PS5)])
            self.sync.grant_gamepass(u1, ps5, 1800, "PS5 dárek", NOW + timedelta(days=14), "StartOnFirstUse")
        body = client.posts[-1][1]
        self.assertEqual(body["EligibleDays"], ["Sunday", "Saturday"])
        self.assertEqual(body["EligiblePcGroups"], ["grp-ps5"])
        self.assertEqual(body["Type"], "StartOnFirstUse")

        # a later full reload keeps the passes added from Odoo
        with patch.object(type(self.sync), "_make_client", return_value=client):
            u1.action_refresh_gamepasses()
        self.assertEqual(len(u1.gamepass_ids.filtered("granted_in_odoo")), 3)
        self.assertFalse(u1.gamepass_ids.filtered(lambda g: g.granted_in_odoo and g.state != "active"))

    def test_grant_error_is_shown(self):
        self.run_sync(dataset())
        self.env["ir.config_parameter"].sudo().set_param("elite_arena_ggleap.auth_token", "test")
        u1 = self.player(U1)
        free = self.env["elite.arena.ggleap.product"].search([("uuid", "=", FREE1)])
        client = FakeClient(dataset(), fail={"/users/gamepasses/add"})
        with patch.object(type(self.sync), "_make_client", return_value=client), self.assertRaises(UserError):
            self.sync.grant_gamepass(u1, free, 3600, "Hodina", NOW + timedelta(days=14), "StartOnFirstUse")
        self.assertFalse(u1.gamepass_ids.filtered("granted_in_odoo"))
