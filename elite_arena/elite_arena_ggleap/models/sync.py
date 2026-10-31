"""ggLeap → Odoo sync engine (polling; ggLeap has no webhooks).

One run (cron every 15 min, or "Synchronizovat teď") goes through the areas in a fixed
order and stops in time (``run_seconds``); cursors are stored after every chunk, so the
next run continues where this one ended. The first run walks the history window
(``history_days``) in chunks. Every area runs in its own savepoint: an error in one area
is recorded on the status and does not undo the others.

The sync only reads. The one thing Odoo writes to ggLeap is a game pass that a user adds
on purpose (``grant_gamepass``).
"""
import hashlib
import json
import logging
import re
import threading
import time
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone

import requests

from odoo import api, fields, models
from odoo.exceptions import UserError

from .config import get_settings
from .ggleap_client import BASES, GgleapAuthError, GgleapBudgetError, GgleapClient, GgleapError
from .game import guess_is_game
from .gamepass import pass_state
from .product import DAY_NAMES, guess_kind

_logger = logging.getLogger(__name__)

LOCK_KEY = 74210551
ACTIVITY_WINDOW = timedelta(days=7)
ACTIVITY_OVERLAP = timedelta(minutes=15)
TRANSACTION_WINDOW = timedelta(days=14)
TRANSACTION_OVERLAP = timedelta(days=3)   # refunds change older transactions
LOGOUT_SLACK = timedelta(minutes=10)
GAMEPASS_AFTER_VISIT = timedelta(hours=6)   # passes are reloaded until this long after a visit
GAMEPASS_MIN_GAP = timedelta(hours=1)
MAX_SESSION = timedelta(hours=36)   # a logout without duration closes only a visit this recent
# Logins at the PC and remote logins (phone / QR) are both visits.
LOGIN_ACTIONS = ("LoggedIn", "RemoteLoggedIn")
LOGOUT_ACTIONS = ("LoggedOut", "RemoteLoggedOut")
PAID_STATUSES = ("Paid", "PartiallyRefunded")
LINE_RULES = 2   # bump to re-apply stored transactions when the line rules change
CONTACT_TO_PARTNER = {"first_name": "name", "last_name": "name", "email": "email", "phone": "phone"}

# Areas that commit after every downloaded chunk (and use a savepoint per chunk themselves).
CHUNKED = {"activity", "launches", "transactions"}
_depth = threading.local()

_TS = re.compile(r"^(\d{4}-\d\d-\d\d)[T ](\d\d:\d\d(?::\d\d)?)(\.\d+)?(Z|[+-]\d\d:?\d\d)?$")


def parse_dt(value):
    """ggLeap ISO timestamp (any number of decimals, Z or offset) → naive UTC datetime."""
    if not value or not isinstance(value, str):
        return None
    m = _TS.match(value.strip())
    if not m:
        return None
    day, clock, frac, tz = m.groups()
    if len(clock) == 5:
        clock += ":00"
    try:
        out = datetime.strptime(day + " " + clock, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    if frac:
        out = out.replace(microsecond=int((frac[1:] + "000000")[:6]))
    if tz and tz != "Z":
        sign = 1 if tz[0] == "+" else -1
        hh, mm = int(tz[1:3]), int(tz[-2:])
        out -= sign * timedelta(hours=hh, minutes=mm)
    if out.year < 2000 or out.year > 2100:
        return None
    return out


def parse_date(value):
    out = parse_dt(value)
    return out.date() if out and out.year > 1900 else None


def parse_duration(value):
    """"08:37:34", "1.02:03:04" or "08:37:34.5" → timedelta (None when unknown)."""
    if not value or not isinstance(value, str):
        return None
    m = re.match(r"^(?:(\d+)\.)?(\d+):(\d\d):(\d\d)(?:\.\d+)?$", value.strip())
    if not m:
        return None
    days, hours, minutes, seconds = (int(x) if x else 0 for x in m.groups())
    return timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)


def api_ts(value):
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def clean(value):
    if isinstance(value, str):
        value = value.strip()
    return value or False


def day_names(days):
    """ggLeap days of the week (0 = Sunday, or names) → "Monday,Tuesday"; every day → False."""
    names = []
    for d in days or []:
        name = DAY_NAMES[d] if isinstance(d, int) and 0 <= d < 7 else d
        if name in DAY_NAMES and name not in names:
            names.append(name)
    if not names or len(names) == 7:
        return False
    return ",".join(sorted(names, key=DAY_NAMES.index))


def segment(visits, last, now, risk_days, lost_days):
    """Same rules as the win-back scripts (survey_recipients.py)."""
    if not last:
        return "nikdy"
    days = (now - last).days
    if visits <= 1:
        return "jednou_nedavno" if days < risk_days else "jednou_davno"
    if days < risk_days:
        return "aktivni_stali"
    if days < lost_days:
        return "ohrozeni"
    return "ztraceni"


class GgleapSync(models.AbstractModel):
    _name = "elite.arena.ggleap.sync"
    _description = "ggLeap – synchronizace"

    # ------------------------------------------------------------------ entry points
    @api.model
    def trigger(self):
        cron = self.env.ref("elite_arena_ggleap.cron_ggleap_sync", raise_if_not_found=False)
        if cron:
            cron.sudo()._trigger()

    @api.model
    def _cron_sync(self):
        self.sudo().run()

    @api.model
    def _make_client(self, settings, max_calls):
        return GgleapClient(BASES[settings["base"]], settings["auth_token"], rpm=settings["rpm"], max_calls=max_calls)

    @api.model
    def run(self, client=None, now=None, settings=None):
        """One sync run. ``client``/``now``/``settings`` are for tests. Returns the summary text."""
        settings = settings or get_settings(self.env)
        status = self.env["elite.arena.ggleap.status"].get_status()
        if client is None and not settings["auth_token"]:
            status.write({"message": "Chybí AuthToken ggLeapu, synchronizace neběží."})
            return status.message
        cr = self.env.cr
        cr.execute("select pg_try_advisory_lock(%s)", (LOCK_KEY,))
        if not cr.fetchone()[0]:
            _logger.info("ggLeap: synchronizace už běží, přeskakuji")
            return "Synchronizace už běží."
        try:
            return self.with_context(ggleap_sync=True, tracking_disable=True, mail_create_nolog=True,
                                     mail_notrack=True, active_test=False)._run_locked(status, settings, client, now)
        finally:
            try:
                cr.execute("select pg_advisory_unlock(%s)", (LOCK_KEY,))
            except Exception:  # aborted transaction: the session lock survives a rollback
                _logger.exception("ggLeap: uvolnění zámku selhalo, vracím transakci")
                if not getattr(threading.current_thread(), "testing", False):
                    cr.rollback()
                    cr.execute("select pg_advisory_unlock(%s)", (LOCK_KEY,))

    @contextmanager
    def _savepoint(self):
        """cr.savepoint() that remembers it is open, so _commit() can refuse to run inside it
        (a commit releases the savepoint and the block would fail on exit)."""
        _depth.value = getattr(_depth, "value", 0) + 1
        try:
            with self.env.cr.savepoint():
                yield
        finally:
            _depth.value -= 1

    def _commit(self):
        """Keep progress of long runs (the cron may be killed at its time limit). Tests run
        in one transaction, so no commit there (the savepoint check runs anyway)."""
        if getattr(_depth, "value", 0):
            raise RuntimeError("ggLeap: commit uvnitř savepointu")
        if getattr(threading.current_thread(), "testing", False) or self.env.registry.in_test_mode():
            return
        self.env.cr.commit()

    def _run_locked(self, status, settings, client, now):
        started = time.time()
        deadline = started + max(settings["run_seconds"], 20)
        now = now or datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
        left = status.calls_left_today(settings["daily_limit"])
        if left <= 0 and client is None:
            status.write({"message": "Dnešní limit dotazů na ggLeap je vyčerpaný, pokračuje se zítra."})
            return status.message
        client = client or self._make_client(settings, max_calls=left)
        steps = [
            ("machines", self._sync_machines, True),
            ("products", self._sync_products, True),
            ("apps", self._sync_apps, True),
            ("players", self._sync_players, True),
            ("activity", self._sync_activity, True),
            ("launches", self._sync_launches, True),
            ("transactions", self._sync_transactions, True),
            ("bookings", self._sync_bookings, True),
            # passes before the one-off backfills: they change with every visit
            ("gamepasses", self._sync_gamepasses, True),
            ("details", self._sync_details, True),
            ("sessions", self._sync_sessions, True),
            ("stats", self._sync_stats, False),
            ("partners", self._sync_partners, False),
            ("games", self._sync_games, False),   # after partners: new players have a contact by now
        ]
        errors, notes, stop_api = [], [], False
        for key, func, uses_api in steps:
            if uses_api and (stop_api or time.time() > deadline):
                if not stop_api:
                    notes.append("%s: nestihlo se, pokračuje další běh" % key)
                continue
            line = status.entity(key)
            calls_before = client.calls
            try:
                if key in CHUNKED:
                    res = func(client, settings, now, deadline, status) or {}
                else:
                    with self._savepoint():
                        res = func(client, settings, now, deadline, status) or {}
                line.write({"last_run_at": now, "created": res.get("created", 0), "updated": res.get("updated", 0),
                            "total": res.get("total", 0), "note": res.get("note") or False, "last_error": False})
            except GgleapAuthError as err:
                errors.append(str(err))
                line.write({"last_run_at": now, "last_error": str(err)[:250]})
                stop_api = True
            except GgleapBudgetError as err:
                notes.append(str(err))
                line.write({"last_run_at": now, "note": str(err)[:250]})
                stop_api = True
            except (GgleapError, requests.RequestException, ValueError, KeyError, TypeError) as err:
                _logger.exception("ggLeap: oblast %s selhala", key)
                errors.append("%s: %s" % (key, err))
                line.write({"last_run_at": now, "last_error": str(err)[:250]})
            _logger.info("ggLeap: %s hotovo (%d dotazů)", key, client.calls - calls_before)
            self._commit()

        calls = client.calls
        status.count_calls(calls)
        vals = {"last_run_at": now, "last_run_seconds": int(time.time() - started), "last_run_calls": calls}
        summary = self._summary(status)
        if errors:
            text = "\n".join(errors)
            if text != (status.last_error or ""):
                status.message_post(body="Synchronizace s ggLeap skončila chybou:\n%s" % text)
            vals.update(last_error=text, last_error_at=now)
        else:
            vals.update(last_success_at=now)
        vals["message"] = (summary + (" · " + "; ".join(notes) if notes else ""))[:500]
        status.write(vals)
        self._commit()
        return vals["message"]

    def _summary(self, status):
        parts = []
        labels = {"activity": "návštěvy", "launches": "spuštění her", "transactions": "prodeje", "players": "hráči",
                  "partners": "kontakty"}
        for line in status.entity_ids:
            if line.entity in labels and (line.created or line.updated):
                parts.append("%s +%d/~%d" % (labels[line.entity], line.created, line.updated))
        return "Hotovo" + (": " + ", ".join(parts) if parts else ", beze změn")

    # ------------------------------------------------------------------ generic upsert
    @staticmethod
    def _same(old, new):
        if hasattr(old, "_name"):
            old = old.id or False
        if isinstance(old, float) or isinstance(new, float):
            return abs((old or 0.0) - (new or 0.0)) < 0.005
        if isinstance(old, datetime) and isinstance(new, datetime):
            return abs((old - new).total_seconds()) < 1
        return (old or False) == (new or False)

    def _diff(self, rec, vals):
        return {k: v for k, v in vals.items() if not self._same(rec[k], v)}

    def _upsert(self, model, key_field, rows):
        """rows: {key: vals}. Returns (records by key, created, updated)."""
        Model = self.env[model].with_context(active_test=False)
        found = {r[key_field]: r for r in Model.search([(key_field, "in", list(rows))])} if rows else {}
        to_create, updated = [], 0
        for key, vals in rows.items():
            rec = found.get(key)
            if rec is None:
                to_create.append(dict(vals, **{key_field: key}))
                continue
            changes = self._diff(rec, vals)
            if changes:
                rec.write(changes)
                updated += 1
        if to_create:
            for rec in Model.create(to_create):
                found[rec[key_field]] = rec
        return found, len(to_create), updated

    def _sel(self, model, field, value):
        """Unknown selection values from the API become False instead of crashing."""
        allowed = dict(self.env[model]._fields[field]._description_selection(self.env))
        return value if value in allowed else False

    # ------------------------------------------------------------------ lookups (stubs for unknown ids)
    def _machines_by_uuid(self, uuids):
        uuids = {u for u in uuids if u}
        Machine = self.env["elite.arena.ggleap.machine"]
        found = {m.uuid: m.id for m in Machine.search([("uuid", "in", list(uuids))])}
        missing = uuids - set(found)
        if missing:
            for m in Machine.create([{"uuid": u, "name": "PC " + u[:8], "in_catalog": False} for u in missing]):
                found[m.uuid] = m.id
        return found

    def _players_by_uuid(self, uuids):
        uuids = {u for u in uuids if u}
        Player = self.env["elite.arena.ggleap.player"]
        found = {p.uuid: p.id for p in Player.search([("uuid", "in", list(uuids))])}
        missing = uuids - set(found)
        if missing:
            for p in Player.create([{"uuid": u} for u in missing]):
                found[p.uuid] = p.id
        return found

    def _products_by_uuid(self, items):
        """items: {uuid: name}. Products unknown to the catalog are created from the sale."""
        Product = self.env["elite.arena.ggleap.product"]
        found = {p.uuid: p for p in Product.search([("uuid", "in", list(items))])}
        missing = [u for u in items if u not in found]
        if missing:
            for p in Product.create([{"uuid": u, "name": items[u] or u[:8], "kind": guess_kind(items[u]),
                                      "in_catalog": False} for u in missing]):
                found[p.uuid] = p
        return found

    # ------------------------------------------------------------------ areas
    def _sync_machines(self, client, settings, now, deadline, status):
        machines = client.get("/machines/get-all").get("Machines") or []
        rows = {}
        for m in machines:
            if not m.get("Uuid"):
                continue
            rows[m["Uuid"]] = {"name": clean(m.get("Name")) or m["Uuid"][:8], "group_uuid": clean(m.get("GroupUuid")),
                               "state": clean(m.get("State")), "last_update": parse_dt(m.get("LastUpdate")),
                               "in_catalog": True, "active": not (m.get("FakeMachine") or m.get("TestMachine"))}
        _found, created, updated = self._upsert("elite.arena.ggleap.machine", "uuid", rows)
        Machine = self.env["elite.arena.ggleap.machine"]
        if rows:
            Machine.search([("uuid", "not in", list(rows)), ("in_catalog", "=", True)]).write({"in_catalog": False})
        return {"created": created, "updated": updated, "total": Machine.search_count([])}

    def _sync_products(self, client, settings, now, deadline, status):
        data = client.get("/pos/products/get-all")
        rows = {}
        for p in (data.get("Products") or []):
            uuid = p.get("ProductUuid")
            if uuid:
                rows[uuid] = {"name": clean(p.get("Name")) or uuid[:8], "product_type": clean(p.get("ProductType")),
                              "category_uuid": clean(p.get("CategoryUuid")), "price": float(p.get("Price") or 0),
                              "seconds": 0, "in_catalog": True, "active": True,
                              "kind": guess_kind(p.get("Name"), p.get("ProductType"), p.get("Price"))}
        for o in (data.get("Offers") or []):
            uuid = o.get("OfferUuid")
            if uuid:
                rows[uuid] = {"name": clean(o.get("Name")) or uuid[:8], "product_type": "Offers",
                              "category_uuid": clean(o.get("CategoryUuid")), "price": float(o.get("Price") or 0),
                              "seconds": int(o.get("Seconds") or 0), "in_catalog": True, "active": True,
                              "kind": guess_kind(o.get("Name"), "Offers", o.get("Price")),
                              "offer_type": self._sel("elite.arena.ggleap.product", "offer_type", o.get("OfferType")),
                              "offer_priority": clean(o.get("Priority")),
                              "eligible_days": day_names(o.get("EligibleDays")),
                              "eligible_pc_groups": json.dumps(sorted(o.get("EligiblePcGroups") or []))
                              if o.get("EligiblePcGroups") else False}
        Product = self.env["elite.arena.ggleap.product"]
        manual = set(Product.search([("uuid", "in", list(rows)), ("kind_manual", "=", True)]).mapped("uuid"))
        for uuid in manual:
            rows[uuid].pop("kind")
        _found, created, updated = self._upsert("elite.arena.ggleap.product", "uuid", rows)
        if rows:
            Product.search([("uuid", "not in", list(rows)), ("in_catalog", "=", True)]).write({"in_catalog": False})
        return {"created": created, "updated": updated, "total": Product.search_count([])}

    def _sync_players(self, client, settings, now, deadline, status):
        rows = {}
        for u in client.paged("/users/summaries", {}, "Users"):
            uuid = u.get("Uuid")
            if not uuid:
                continue
            email = clean(u.get("Email"))
            rows[uuid] = {"username": clean(u.get("Username")), "first_name": clean(u.get("FirstName")),
                          "last_name": clean(u.get("LastName")), "email": email.lower() if email else False,
                          "phone": clean(u.get("Phone")), "balance": float(u.get("Balance") or 0),
                          "group_uuid": clean(u.get("GroupUuid")), "locked": bool(u.get("Locked")), "deleted": False}
        Player = self.env["elite.arena.ggleap.player"]
        found = {p.uuid: p for p in Player.search([("uuid", "in", list(rows))])} if rows else {}
        to_create, updated = [], 0
        for uuid, vals in rows.items():
            rec = found.get(uuid)
            if rec is None:
                to_create.append(dict(vals, uuid=uuid, partner_dirty=True))
                continue
            changes = self._diff(rec, vals)
            if changes:
                touched = {CONTACT_TO_PARTNER[f] for f in changes if f in CONTACT_TO_PARTNER}
                if touched:
                    touched |= set(filter(None, (rec.partner_dirty_fields or "").split(",")))
                    changes.update(partner_dirty=True, partner_dirty_fields=",".join(sorted(touched)))
                rec.write(changes)
                updated += 1
        if to_create:
            Player.create(to_create)
        gone = 0
        if rows:  # summaries list all current accounts: the others were deleted in ggLeap
            missing = Player.search([("uuid", "not in", list(rows)), ("deleted", "=", False)])
            gone = len(missing)
            missing.write({"deleted": True})
        return {"created": len(to_create), "updated": updated + gone, "total": Player.search_count([]),
                "note": ("%d smazaných v ggLeap" % gone) if gone else False}

    def _history_start(self, settings, now):
        return now - timedelta(days=max(settings["history_days"], 1))

    def _sync_activity(self, client, settings, now, deadline, status):
        if not status.history_from:
            status.write({"history_from": self._history_start(settings, now)})
        start = (status.activity_cursor - ACTIVITY_OVERLAP) if status.activity_cursor else status.history_from
        created = updated = 0
        while start < now:
            if time.time() > deadline:
                return {"created": created, "updated": updated, "note": "pokračuje od %s" % start.date(),
                        "total": self.env["elite.arena.ggleap.visit"].search_count([])}
            end = min(start + ACTIVITY_WINDOW, now)
            with self._savepoint():
                entries = list(client.paged("/activity-logs/search", {
                    "TimeFrameType": "Custom", "Start": api_ts(start), "End": api_ts(end),
                    "Actions": list(LOGIN_ACTIONS + LOGOUT_ACTIONS) + ["CreatedUser"], "Limit": 500}, "Entries"))
                c, u = self._apply_activity(entries)
                status.write({"activity_cursor": end})
            created += c
            updated += u
            self._commit()
            start = end
        self._check_backfill(status)
        return {"created": created, "updated": updated, "total": self.env["elite.arena.ggleap.visit"].search_count([])}

    def _apply_activity(self, entries):
        Visit = self.env["elite.arena.ggleap.visit"]
        entries = sorted((e for e in entries if parse_dt(e.get("DateTime"))), key=lambda e: parse_dt(e["DateTime"]))
        machines = self._machines_by_uuid(e.get("MachineUuid") for e in entries)
        players = self._players_by_uuid(e.get("UserUuid") for e in entries if not e.get("IsGuest"))
        uuids = [e.get("Uuid") for e in entries if e.get("Uuid")]
        known_in = set(Visit.search([("login_uuid", "in", uuids)]).mapped("login_uuid"))
        known_out = set(Visit.search([("logout_uuid", "in", uuids)]).mapped("logout_uuid"))
        created = closed = 0
        for e in entries:
            action, uuid, when = e.get("Action"), e.get("Uuid"), parse_dt(e["DateTime"])
            guest = bool(e.get("IsGuest")) or not e.get("UserUuid")
            player_id = False if guest else players.get(e.get("UserUuid"))
            machine_id = machines.get(e.get("MachineUuid")) or False
            device = clean(e.get("DeviceUuid"))
            device_name = clean((e.get("Data") or {}).get("DeviceName"))
            if action == "CreatedUser":
                if player_id:
                    player = self.env["elite.arena.ggleap.player"].browse(player_id)
                    if not player.registered_at:
                        player.registered_at = when
                continue
            if not uuid:
                continue
            if action in LOGIN_ACTIONS:
                if uuid in known_in:
                    continue
                Visit.create({"login_uuid": uuid, "player_id": player_id, "is_guest": guest,
                              "machine_id": machine_id, "device_uuid": False if machine_id else device,
                              "device_name": False if machine_id else device_name, "start": when})
                known_in.add(uuid)
                created += 1
            elif action in LOGOUT_ACTIONS:
                if uuid in known_out:
                    continue
                duration = parse_duration((e.get("Data") or {}).get("Duration"))
                begin = when - duration if duration else None   # 0:00:00 / missing → unknown start
                domain = [("end", "=", False), ("start", "<=", when)]
                domain += [("player_id", "=", player_id)] if player_id else [("is_guest", "=", True)]
                domain.append(("start", ">=", (begin - LOGOUT_SLACK) if begin else when - MAX_SESSION))
                where = [("machine_id", "=", machine_id)] if machine_id else (
                    [("device_uuid", "=", device)] if device else [])
                visit = Visit.search(domain + where, order="start desc", limit=1) if where else Visit
                if not visit and (begin or not where):
                    visit = Visit.search(domain, order="start desc", limit=1)
                if visit:
                    visit.write({"end": when, "logout_uuid": uuid, "end_source": "logout",
                                 "duration_hours": (when - visit.start).total_seconds() / 3600.0})
                    closed += 1
                elif begin:  # login older than the downloaded history
                    Visit.create({"logout_uuid": uuid, "player_id": player_id, "is_guest": guest,
                                  "machine_id": machine_id, "device_uuid": False if machine_id else device,
                                  "device_name": False if machine_id else device_name,
                                  "start": begin, "end": when, "end_source": "logout",
                                  "duration_hours": duration.total_seconds() / 3600.0})
                    created += 1
                known_out.add(uuid)
        return created, closed

    def _check_backfill(self, status):
        if not status.backfill_done and status.activity_cursor and status.transaction_cursor:
            status.write({"backfill_done": True})

    def _sync_transactions(self, client, settings, now, deadline, status):
        if not status.history_from:
            status.write({"history_from": self._history_start(settings, now)})
        start = (status.transaction_cursor - TRANSACTION_OVERLAP) if status.transaction_cursor else status.history_from
        Tx = self.env["elite.arena.ggleap.transaction"]
        created = updated = 0
        while start < now:
            if time.time() > deadline:
                return {"created": created, "updated": updated, "note": "pokračuje od %s" % start.date(),
                        "total": Tx.search_count([])}
            end = min(start + TRANSACTION_WINDOW, now)
            with self._savepoint():
                items = list(client.paged("/transactions/search", {
                    "TimeFrameType": "Custom", "Start": api_ts(start), "End": api_ts(end), "Limit": 200},
                    "Transactions"))
                c, u = self._apply_transactions(items)
                status.write({"transaction_cursor": end})
            created += c
            updated += u
            self._commit()
            start = end
        self._check_backfill(status)
        return {"created": created, "updated": updated, "total": Tx.search_count([])}

    def _apply_transactions(self, items):
        Tx = self.env["elite.arena.ggleap.transaction"]
        items = [t for t in items if t.get("TransactionUuid")]
        players = self._players_by_uuid(((t.get("Details") or {}).get("User") or {}).get("Uuid") for t in items)
        products = self._products_by_uuid({
            i.get("ProductUuid"): i.get("Name")
            for t in items for i in (t.get("Items") or {}).values() if i.get("ProductUuid")})
        found = {t.uuid: t for t in Tx.search([("uuid", "in", [t["TransactionUuid"] for t in items])])}
        created = updated = 0
        for t in items:
            details = t.get("Details") or {}
            when = parse_dt(details.get("DateTime"))
            if not when:
                continue
            raw_items = list((t.get("Items") or {}).values())
            digest = hashlib.sha1(json.dumps([LINE_RULES, t.get("Status"), t.get("RefundedAt"), details, raw_items],
                                             sort_keys=True, default=str).encode()).hexdigest()
            rec = found.get(t["TransactionUuid"])
            if rec and rec.content_hash == digest:
                continue
            user_uuid = (details.get("User") or {}).get("Uuid")
            status_value = self._sel("elite.arena.ggleap.transaction", "status", t.get("Status"))
            vals = {
                "name": clean(t.get("TransactionId")), "date": when, "user_uuid": clean(user_uuid),
                "player_id": players.get(user_uuid) or False,
                "employee": clean((details.get("Employee") or {}).get("Name")),
                "tx_type": clean(t.get("Type")),
                "source": self._sel("elite.arena.ggleap.transaction", "source", t.get("Source")),
                "status": status_value,
                "is_paid": t.get("Status") in PAID_STATUSES and (t.get("Type") or "Sale") == "Sale",
                "refunded_at": parse_dt(t.get("RefundedAt")),
                "amount": float(details.get("TotalGross") or 0), "discount": float(details.get("TotalDiscount") or 0),
                "paid_cash": float(details.get("PaidWithCash") or 0), "paid_card": float(details.get("PaidWithCard") or 0),
                "paid_balance": float(details.get("PaidWithBalance") or 0),
                "coupon_code": clean((t.get("RedeemedCoupon") or {}).get("Code")),
                "content_hash": digest,
            }
            # item values are list prices; scale them to what was really paid (coins, discounts)
            listed = [float(i.get("GrossTotalValue", i.get("TotalPrice")) or 0) for i in raw_items]
            total = vals["amount"]
            factor = (total / sum(listed)) if sum(listed) > 0 else 0.0
            lines = []
            for i, list_value in zip(raw_items, listed):
                product = products.get(i.get("ProductUuid"))
                qty = float(i.get("Quantity") or 0)
                kind = product.kind if product else guess_kind(i.get("Name"))
                seconds = product.seconds if product else 0
                lines.append((0, 0, {
                    "product_id": product.id if product else False,
                    "name": clean(i.get("Name")) or (product.name if product else False),
                    "kind": kind, "quantity": qty,
                    "amount": round(list_value * factor, 2), "list_amount": list_value,
                    "discount": float(i.get("DiscountTotalValue") or 0),
                    "hours": qty * seconds / 3600.0 if kind in ("time", "free") else 0.0,
                }))
            if rec:
                rec.line_ids.unlink()
                rec.write(dict(vals, line_ids=lines))
                updated += 1
            else:
                Tx.create(dict(vals, uuid=t["TransactionUuid"], line_ids=lines))
                created += 1
        return created, updated

    def _sync_bookings(self, client, settings, now, deadline, status):
        Booking = self.env["elite.arena.ggleap.booking"]
        today = now.date()
        day, last = today - timedelta(days=2), today + timedelta(days=max(settings["bookings_ahead"], 0))
        raw = []
        while day <= last:
            data = client.get("/bookings/get-bookings", {"Date": day.isoformat(), "Days": 2,
                                                         "OnlyStartedSinceDate": True})
            raw.extend(data.get("Bookings") or [])
            day += timedelta(days=2)
        players = self._players_by_uuid(b.get("UserUuid") for b in raw)
        rows = {}
        for b in raw:
            uuid = b.get("BookingUuid")
            if not uuid:
                continue
            start = parse_dt(b.get("Start")) or parse_dt(b.get("StartLocal"))
            minutes = int(b.get("Duration") or 0)
            finished = parse_dt(b.get("FinishedAt"))
            reason = self._sel("elite.arena.ggleap.booking", "delete_reason", b.get("DeleteReason"))
            if b.get("Deleted"):
                state = "noshow" if reason == "NoShow" else "canceled"
            elif finished or (start and start + timedelta(minutes=minutes) < now):
                state = "done"
            else:
                state = "planned"
            rows[uuid] = {"name": clean(b.get("Name")), "player_id": players.get(b.get("UserUuid")) or False,
                          "guest_name": clean(b.get("GuestName")), "start": start, "duration_minutes": minutes,
                          "machine_count": len(b.get("Machines") or []), "paid": bool(b.get("Paid")),
                          "finished_at": finished, "deleted": bool(b.get("Deleted")), "delete_reason": reason,
                          "state": state}
        _found, created, updated = self._upsert("elite.arena.ggleap.booking", "uuid", rows)
        return {"created": created, "updated": updated, "total": Booking.search_count([])}

    def _sync_details(self, client, settings, now, deadline, status):
        limit = max(settings["details_per_run"], 0)
        if not limit:
            return {"note": "vypnuto"}
        Player = self.env["elite.arena.ggleap.player"]
        todo = Player.search([("details_synced_at", "=", False), ("deleted", "=", False)],
                             order="last_visit desc nulls last, id", limit=limit)
        done = 0
        for player in todo:
            if time.time() > deadline:
                break
            try:
                user = client.get("/users/user-details", {"Uuid": player.uuid}).get("User") or {}
            except GgleapError as err:
                if isinstance(err, (GgleapAuthError, GgleapBudgetError)):
                    raise
                _logger.info("ggLeap: detail hráče %s: %s", player.uuid, err)
                player.write({"details_synced_at": now})  # do not retry a broken account every run
                continue
            vals = {"details_synced_at": now,
                    "registered_at": parse_dt(user.get("RegisteredAt")) or player.registered_at,
                    "last_seen_ggleap": parse_dt(user.get("LastSeen")),
                    "birthdate": parse_date(user.get("Birthdate")),
                    "time_remaining_hours": int(user.get("TimeRemaining") or 0) / 3600.0}
            if user.get("Deleted"):
                vals["deleted"] = True
            player.write(vals)
            done += 1
        left = Player.search_count([("details_synced_at", "=", False), ("deleted", "=", False)])
        return {"updated": done, "total": Player.search_count([("details_synced_at", "!=", False)]),
                "note": ("zbývá %d hráčů" % left) if left else False}

    def _sync_sessions(self, client, settings, now, deadline, status):
        """Ends of sessions without a logout in the activity log (ggLeap does not log one when
        the time runs out). Asks /sessions/get-user-sessions per player and matches by start."""
        limit = max(settings["sessions_per_run"], 0)
        Visit = self.env["elite.arena.ggleap.visit"]
        open_domain = [("end", "=", False), ("end_source", "=", False), ("player_id", "!=", False),
                       ("start", "<", now - timedelta(hours=12))]
        if not limit:
            return {"note": "vypnuto"}
        players = Visit.search(open_domain, order="start desc").mapped("player_id")[:limit]
        closed = unknown = 0
        for player in players:
            if time.time() > deadline:
                break
            visits = Visit.search(open_domain + [("player_id", "=", player.id)], order="start")
            first, last = visits[0].start, visits[-1].start
            if (last - first).days > 31:  # one call covers a month; older ones come in later runs
                visits = visits.filtered(lambda v: v.start >= last - timedelta(days=31))
                first = visits[0].start
            data = client.get("/sessions/get-user-sessions", {
                "UserUuid": player.uuid, "Start": api_ts(first - timedelta(hours=1)),
                "End": api_ts(last + timedelta(days=1))})
            sessions = [(parse_dt(s.get("StartDateTime")), int(s.get("Seconds") or 0))
                        for s in data.get("Sessions") or [] if parse_dt(s.get("StartDateTime"))]
            for visit in visits:
                match = min(sessions, key=lambda s: abs((s[0] - visit.start).total_seconds()), default=None)
                if match and abs((match[0] - visit.start).total_seconds()) <= 180 and match[1] > 0:
                    visit.write({"end": visit.start + timedelta(seconds=match[1]), "end_source": "session",
                                 "duration_hours": match[1] / 3600.0})
                    closed += 1
                else:
                    visit.write({"end_source": "unknown"})
                    unknown += 1
        left = len(Visit.search(open_domain).mapped("player_id"))
        return {"updated": closed, "total": Visit.search_count([("end_source", "=", "session")]),
                "note": "; ".join(filter(None, [("bez konce: %d" % unknown) if unknown else "",
                                                ("zbývá %d hráčů" % left) if left else ""])) or False}

    # ------------------------------------------------------------------ game passes
    def _gamepass_vals(self, dto, now):
        seconds, used = int(dto.get("Seconds") or 0), int(dto.get("SecondsUsed") or 0)
        consumed, removed, expires = (parse_dt(dto.get("ConsumedAt")), parse_dt(dto.get("RemovedAt")),
                                      parse_dt(dto.get("ExpiresAt")))
        state, left = pass_state(seconds, used, consumed, removed, expires, now)
        return {"name": clean(dto.get("Name")), "offer_uuid": clean(dto.get("OfferUuid")),
                "seconds": seconds, "seconds_used": used, "hours_left": left, "state": state,
                "pass_type": self._sel("elite.arena.ggleap.gamepass", "pass_type", dto.get("Type")),
                "priority": clean(dto.get("Priority")), "added_at": parse_dt(dto.get("AddedAt")),
                "started_at": parse_dt(dto.get("StartedAt")), "consumed_at": consumed, "removed_at": removed,
                "expires_at": expires}

    def _apply_gamepasses(self, player, offers, now, complete=True):
        """offers: UserOfferDto list of one player. ``complete`` = the whole list from ggLeap
        (passes missing from it were removed there)."""
        Pass = self.env["elite.arena.ggleap.gamepass"].sudo()
        offers = [o for o in offers if o.get("Uuid")]
        products = {p.uuid: p.id for p in self.env["elite.arena.ggleap.product"].with_context(active_test=False)
                    .search([("uuid", "in", [o.get("OfferUuid") for o in offers if o.get("OfferUuid")])])}
        rows = {}
        for o in offers:
            vals = self._gamepass_vals(o, now)
            vals.update(player_id=player.id, product_id=products.get(o.get("OfferUuid")) or False)
            rows[o["Uuid"]] = vals
        found, created, updated = self.sudo()._upsert("elite.arena.ggleap.gamepass", "uuid", rows)
        if complete:
            gone = Pass.search([("player_id", "=", player.id), ("uuid", "not in", list(rows)),
                                ("state", "!=", "removed")])
            gone.write({"state": "removed", "hours_left": 0.0, "removed_at": now})
            player.sudo().write({"gamepasses_synced_at": now})
        return found, created, updated

    def _fetch_gamepasses(self, client, player, now):
        data = client.get("/users/gamepasses/list", {"UserUuid": player.uuid, "IncludeInactive": True})
        return self._apply_gamepasses(player, data.get("Offers") or [], now)

    def _gamepass_todo(self, now, limit):
        """Players whose passes should be (re)loaded: right after a visit (time is being used
        up), then everybody never loaded, the most recent visitors first."""
        Player = self.env["elite.arena.ggleap.player"]
        recent = Player.search([("deleted", "=", False), ("last_visit", ">=", now - timedelta(days=2))],
                               order="last_visit desc")
        todo = recent.filtered(lambda p: not p.gamepasses_synced_at or (
            p.gamepasses_synced_at < p.last_visit + GAMEPASS_AFTER_VISIT
            and p.gamepasses_synced_at < now - GAMEPASS_MIN_GAP))
        if len(todo) < limit:
            todo |= Player.search([("deleted", "=", False), ("gamepasses_synced_at", "=", False),
                                   ("id", "not in", todo.ids)],
                                  order="last_visit desc nulls last, id", limit=limit - len(todo))
        return todo[:limit]

    def _sync_gamepasses(self, client, settings, now, deadline, status):
        Pass = self.env["elite.arena.ggleap.gamepass"]
        expired = Pass.search([("state", "=", "active"), ("expires_at", "<", now)])
        expired.write({"state": "expired", "hours_left": 0.0})
        limit = max(settings["gamepasses_per_run"], 0)
        if not limit:
            return {"note": "vypnuto", "total": Pass.search_count([])}
        created = updated = 0
        for player in self._gamepass_todo(now, limit):
            if time.time() > deadline:
                break
            try:
                _found, c, u = self._fetch_gamepasses(client, player, now)
            except GgleapError as err:
                if isinstance(err, (GgleapAuthError, GgleapBudgetError)):
                    raise
                _logger.info("ggLeap: passy hráče %s: %s", player.uuid, err)
                player.write({"gamepasses_synced_at": now})
                continue
            created += c
            updated += u
        left = self.env["elite.arena.ggleap.player"].search_count(
            [("deleted", "=", False), ("gamepasses_synced_at", "=", False)])
        return {"created": created, "updated": updated + len(expired), "total": Pass.search_count([]),
                "note": ("zbývá %d hráčů" % left) if left else False}

    def _ui_client(self, calls):
        """Client for a button click (not the cron); counts the calls into today's limit."""
        settings = get_settings(self.env)
        if not settings["auth_token"]:
            raise UserError("Chybí AuthToken ggLeapu (Herna → Konfigurace → Nastavení).")
        status = self.env["elite.arena.ggleap.status"].sudo().get_status()
        if status.calls_left_today(settings["daily_limit"]) < calls:
            raise UserError("Dnešní limit dotazů na ggLeap je vyčerpaný. Zkuste to zítra nebo ho zvyšte v Nastavení.")
        return self._make_client(settings, max_calls=calls + 1), status, settings

    @api.model
    def refresh_gamepasses(self, players):
        """Loads the passes of the given players from ggLeap now (1 call each)."""
        players = players.filtered(lambda p: not p.deleted)
        if not players:
            return 0
        if len(players) > 20:
            raise UserError("Najednou jde načíst passy nejvýš 20 hráčů.")
        client, status, _settings = self._ui_client(len(players))
        now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
        count = 0
        try:
            for player in players:
                found, _c, _u = self._fetch_gamepasses(client, player, now)
                count += len(found)
        except GgleapError as err:
            raise UserError("ggLeap odpověděl chybou: %s" % err) from err
        finally:
            status.count_calls(client.calls)
        return count

    @api.model
    def grant_gamepass(self, player, product, seconds, name, expires_at, start_type, note=False, key=None):
        """Adds a game pass to the player's ggLeap account (POST /users/gamepasses/add) and
        stores it. ``key`` makes the call idempotent (a double click adds one pass)."""
        if player.deleted:
            raise UserError("Účet hráče je v ggLeapu smazaný.")
        if seconds <= 0:
            raise UserError("Pass musí mít kladný čas.")
        payload = {
            "UserUuid": player.uuid,
            "OfferUuid": product.uuid,
            "Name": name or product.name,
            "Seconds": int(seconds),
            "Type": start_type or product.offer_type or "StartOnFirstUse",
            "Priority": product.offer_priority or "Normal",
            "ExpiresAt": api_ts(expires_at),
            "EligibleDays": (product.eligible_days or ",".join(DAY_NAMES)).split(","),
            "EligiblePcGroups": json.loads(product.eligible_pc_groups or "[]"),
        }
        client, status, _settings = self._ui_client(2)
        try:
            dto = (client.post("/users/gamepasses/add", payload, correlation_id=key) or {}).get("Offer") or {}
        except GgleapError as err:
            raise UserError("ggLeap pass nepřidal: %s" % err) from err
        finally:
            status.count_calls(client.calls)
        if not dto.get("Uuid"):
            raise UserError("ggLeap pass přijal, ale nevrátil ho. Načtěte passy hráče znovu.")
        now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
        found, _c, _u = self._apply_gamepasses(player, [dto], now, complete=False)
        gamepass = found[dto["Uuid"]]
        gamepass.write({"granted_in_odoo": True, "granted_by_id": self.env.user.id, "grant_note": note or False})
        return gamepass

    # ------------------------------------------------------------------ games
    def _sync_apps(self, client, settings, now, deadline, status):
        """Catalog of enabled apps; the type (Game / Program / Setting) tells games from launchers."""
        apps = client.get("/apps/get-enabled-apps-summary").get("Apps") or []
        rows = {}
        for a in apps:
            uuid = a.get("Uuid")
            if not uuid:
                continue
            app_type = self._sel("elite.arena.ggleap.app", "app_type", a.get("AppType"))
            rows[uuid] = {"name": clean(a.get("Name")) or uuid[:8], "app_type": app_type,
                          "tags": ", ".join(t for t in (a.get("Tags") or []) if t and t != "Unknown") or False,
                          "is_game": guess_is_game(a.get("Name"), app_type), "in_catalog": True}
        App = self.env["elite.arena.ggleap.app"]
        manual = set(App.search([("uuid", "in", list(rows)), ("is_game_manual", "=", True)]).mapped("uuid"))
        for uuid in manual:
            rows[uuid].pop("is_game")
        _found, created, updated = self._upsert("elite.arena.ggleap.app", "uuid", rows)
        if rows:
            App.search([("uuid", "not in", list(rows)), ("in_catalog", "=", True)]).write({"in_catalog": False})
        # apps known only from launches: guess again (the word list may have grown)
        for app in App.search([("in_catalog", "=", False), ("is_game_manual", "=", False)]):
            guess = guess_is_game(app.name)
            if app.is_game != guess:
                app.write({"is_game": guess})
                updated += 1
        return {"created": created, "updated": updated, "total": App.search_count([])}

    def _sync_launches(self, client, settings, now, deadline, status):
        """Which games people start (activity log "LaunchedApplication", PCs only). Own cursor,
        so the history is walked even though visits were downloaded before."""
        if not status.history_from:
            status.write({"history_from": self._history_start(settings, now)})
        start = (status.launch_cursor - ACTIVITY_OVERLAP) if status.launch_cursor else status.history_from
        Launch = self.env["elite.arena.ggleap.app.launch"]
        created = 0
        while start < now:
            if time.time() > deadline:
                return {"created": created, "note": "pokračuje od %s" % start.date(), "total": Launch.search_count([])}
            end = min(start + ACTIVITY_WINDOW, now)
            with self._savepoint():
                entries = list(client.paged("/activity-logs/search", {
                    "TimeFrameType": "Custom", "Start": api_ts(start), "End": api_ts(end),
                    "Actions": ["LaunchedApplication"], "Limit": 500}, "Entries"))
                created += self._apply_launches(entries)
                status.write({"launch_cursor": end})
            self._commit()
            start = end
        return {"created": created, "total": Launch.search_count([])}

    def _apply_launches(self, entries):
        Launch = self.env["elite.arena.ggleap.app.launch"]
        App = self.env["elite.arena.ggleap.app"].with_context(active_test=False)
        entries = [e for e in entries if e.get("Action") == "LaunchedApplication" and e.get("Uuid")
                   and parse_dt(e.get("DateTime")) and (e.get("Data") or {}).get("ApplicationUuid")]
        known = set(Launch.search([("uuid", "in", [e["Uuid"] for e in entries])]).mapped("uuid"))
        entries = [e for e in entries if e["Uuid"] not in known]
        if not entries:
            return 0
        names = {}
        for e in entries:
            data = e["Data"]
            names.setdefault(data["ApplicationUuid"], clean(data.get("ApplicationName")))
        apps = {a.uuid: a.id for a in App.search([("uuid", "in", list(names))])}
        missing = [u for u in names if u not in apps]
        if missing:  # no longer in the catalog: known only from the launch
            for a in App.create([{"uuid": u, "name": names[u] or u[:8], "is_game": guess_is_game(names[u]),
                                  "in_catalog": False} for u in missing]):
                apps[a.uuid] = a.id

        def user_of(e):
            return e.get("UserUuid") or e["Data"].get("UserUuid")

        players = self._players_by_uuid(user_of(e) for e in entries if not e.get("IsGuest"))
        machines = self._machines_by_uuid(e.get("MachineUuid") for e in entries)
        vals, seen = [], set()
        for e in entries:
            if e["Uuid"] in seen:
                continue
            seen.add(e["Uuid"])
            guest = bool(e.get("IsGuest")) or not user_of(e)
            vals.append({"uuid": e["Uuid"], "start": parse_dt(e["DateTime"]), "app_id": apps[e["Data"]["ApplicationUuid"]],
                         "player_id": False if guest else players.get(user_of(e)) or False, "is_guest": guest,
                         "machine_id": machines.get(e.get("MachineUuid")) or False,
                         "session_uuid": clean(e["Data"].get("SessionUuid"))})
        Launch.create(vals)
        return len(vals)

    def _sync_games(self, client, settings, now, deadline, status):
        """Games of every player and contact, and how many players each game has (local only)."""
        cr = self.env.cr
        tz = self.env.user.tz or "Europe/Prague"
        cr.execute("""select app_id, count(distinct player_id), count(*), max(start)
                        from elite_arena_ggleap_app_launch group by app_id""")
        App = self.env["elite.arena.ggleap.app"].with_context(active_test=False)
        app_rows = {a: (players, launches, last) for a, players, launches, last in cr.fetchall()}
        for app in App.search([]):
            players, launches, last = app_rows.get(app.id, (0, 0, None))
            changes = self._diff(app, {"player_count": players, "launch_count": launches, "last_played": last or False})
            if changes:
                app.write(changes)

        cr.execute("""select l.player_id, l.app_id, count(distinct (l.start at time zone 'UTC' at time zone %s)::date),
                             count(*), min(l.start), max(l.start)
                        from elite_arena_ggleap_app_launch l join elite_arena_ggleap_app a on a.id = l.app_id
                       where l.player_id is not null and a.is_game
                       group by 1, 2""", (tz,))
        rows, by_player = {}, {}
        for player_id, app_id, days, launches, first, last in cr.fetchall():
            rows["%d-%d" % (player_id, app_id)] = {"player_id": player_id, "app_id": app_id, "days": days,
                                                   "launches": launches, "first_played": first, "last_played": last}
            by_player.setdefault(player_id, []).append((days, last, launches, app_id))
        found, created, updated = self._upsert("elite.arena.ggleap.player.game", "key", rows)
        stale = self.env["elite.arena.ggleap.player.game"].search([("key", "not in", list(rows))])
        removed = len(stale)
        stale.unlink()

        def summary(entries):
            ordered = sorted(entries, key=lambda r: (r[0], r[1], r[2]), reverse=True)
            return set(r[3] for r in ordered), (ordered[0][3] if ordered else False)

        Player = self.env["elite.arena.ggleap.player"]
        players_changed = 0
        for player in Player.search(["|", ("id", "in", list(by_player)), ("game_ids", "!=", False)]):
            games, main = summary(by_player.get(player.id, []))
            if set(player.game_ids.ids) != games or player.main_game_id.id != main:
                player.write({"game_ids": [(6, 0, sorted(games))], "main_game_id": main})
                players_changed += 1
        by_partner = {}
        for player_id, entries in by_player.items():
            partner = Player.browse(player_id).partner_id
            if partner:
                by_partner.setdefault(partner.id, []).extend(entries)
        Partner = self.env["res.partner"].with_context(active_test=False)
        for partner in Partner.search(["|", ("id", "in", list(by_partner)), ("ggleap_game_ids", "!=", False)]):
            games, main = summary(by_partner.get(partner.id, []))
            if set(partner.ggleap_game_ids.ids) != games or partner.ggleap_main_game_id.id != main:
                partner.write({"ggleap_game_ids": [(6, 0, sorted(games))], "ggleap_main_game_id": main})
        return {"created": created, "updated": updated + removed + players_changed,
                "total": App.search_count([("is_game", "=", True), ("player_count", ">", 0)])}

    def _sync_stats(self, client, settings, now, deadline, status):
        """Visit count, first/last visit, hours, spend and segment of every player (local only)."""
        cr = self.env.cr
        tz = self.env.user.tz or "Europe/Prague"
        # one visit = one day with sessions (several sessions in one evening are one visit)
        cr.execute("""select player_id, count(distinct (start at time zone 'UTC' at time zone %s)::date),
                             min(start), max(start), coalesce(sum(duration_hours), 0)
                        from elite_arena_ggleap_visit where player_id is not null group by player_id""", (tz,))
        visits = {r[0]: r[1:] for r in cr.fetchall()}
        cr.execute("""select player_id, coalesce(sum(amount), 0) from elite_arena_ggleap_transaction
                       where is_paid and player_id is not null group by player_id""")
        spent = dict(cr.fetchall())
        Player = self.env["elite.arena.ggleap.player"]
        updated = 0
        for player in Player.search([]):
            count, first, last, hours = visits.get(player.id, (0, None, None, 0.0))
            seen = player.last_seen_ggleap
            if seen and (not last or seen > last):
                last = seen
            if not first and last:
                first = last
            known = max(count, 1 if last else 0)
            vals = {"visit_count": count, "first_visit": first or False, "last_visit": last or False,
                    "days_since_visit": (now - last).days if last else 0, "hours_played": float(hours or 0),
                    "total_spent": float(spent.get(player.id, 0.0)),
                    "segment": segment(known, last, now, settings["risk_days"], settings["lost_days"])}
            changes = self._diff(player, vals)
            if changes:
                player.write(changes)
                updated += 1
        return {"updated": updated, "total": Player.search_count([])}

    @staticmethod
    def _nice_name(player):
        name = player.full_name or ""
        if name and name == name.lower():
            name = " ".join(w[:1].upper() + w[1:] for w in name.split())
        return name or player.username or player.email or player.uuid

    def _sync_partners(self, client, settings, now, deadline, status):
        """Links players to contacts (ggleap_uuid → ref = survey scripts → e-mail) and creates
        missing ones. An existing contact keeps its own name/e-mail when it is first linked;
        later changes made in ggLeap are copied over."""
        Player = self.env["elite.arena.ggleap.player"]
        Partner = self.env["res.partner"].with_context(active_test=False)
        tag = self.env.ref("elite_arena_ggleap.partner_category_player", raise_if_not_found=False)
        todo = Player.search([("deleted", "=", False), ("partner_dirty", "=", True)])
        created = updated = 0
        for player in todo:
            has_identity = player.email or player.full_name
            partner = player.partner_id
            first_link = not partner
            if not partner:
                partner = Partner.search([("ggleap_uuid", "=", player.uuid)], limit=1) \
                    or Partner.search([("ref", "=", player.uuid)], limit=1)
            if not partner and player.email:
                partner = Partner.search([("email", "=ilike", player.email), ("ggleap_uuid", "in", (False, ""))],
                                         limit=1)
            if not partner:
                if not settings["create_partners"] or not has_identity:
                    player.write({"partner_dirty": False, "partner_dirty_fields": False})
                    continue
                vals = {"name": self._nice_name(player), "email": player.email, "phone": player.phone,
                        "ggleap_uuid": player.uuid, "ref": player.uuid, "is_company": False}
                if tag:
                    vals["category_id"] = [(4, tag.id)]
                partner = Partner.create(vals)
                created += 1
            else:
                vals = {}
                if not partner.ggleap_uuid:
                    vals["ggleap_uuid"] = player.uuid
                if not partner.ref:
                    vals["ref"] = player.uuid
                if tag and tag not in partner.category_id:
                    vals["category_id"] = [(4, tag.id)]
                changed = set(filter(None, (player.partner_dirty_fields or "").split(",")))
                for field, value in (("email", player.email), ("phone", player.phone),
                                     ("name", self._nice_name(player) if player.full_name else False)):
                    if not value or partner[field] == value:
                        continue
                    # empty in Odoo → fill; otherwise only what ggLeap changed since the link
                    if not partner[field] or (not first_link and field in changed):
                        vals[field] = value
                if vals:
                    partner.write(vals)
                    updated += 1
            player.write({"partner_id": partner.id, "partner_dirty": False, "partner_dirty_fields": False})
        return {"created": created, "updated": updated,
                "total": Player.search_count([("partner_id", "!=", False)])}
