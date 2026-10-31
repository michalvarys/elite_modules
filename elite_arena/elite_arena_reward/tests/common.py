from datetime import timedelta

from odoo import fields


def make_player(env, partner, uuid="arena-test-u1"):
    """A ggLeap player linked to the partner, as the sync would create it."""
    player = env["elite.arena.ggleap.player"].create({
        "uuid": uuid, "username": uuid, "email": partner.email, "partner_id": partner.id,
        "last_visit": fields.Datetime.now() - timedelta(days=60), "visit_count": 3,
    })
    partner.ggleap_uuid = uuid
    return player


def free_hour_product(env):
    return env["elite.arena.ggleap.product"].create({
        "uuid": "arena-test-free", "name": "1 HODINA FREE", "kind": "free", "product_type": "Offers",
        "seconds": 3600, "price": 0.0, "in_catalog": True, "offer_type": "StartOnFirstUse",
    })


class FakeGrant:
    """Stands in for elite.arena.ggleap.sync.grant_gamepass (no call to ggLeap)."""

    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def __get__(self, obj, owner=None):   # patched onto the model class: bind like a method
        return self if obj is None else (lambda *a, **k: self(obj, *a, **k))

    def __call__(self, sync, player, product, seconds, name, expires_at, start_type, note=False, key=None):
        from odoo.exceptions import UserError
        self.calls.append({"player": player, "product": product, "seconds": seconds, "name": name,
                           "expires_at": expires_at, "key": key, "note": note})
        if self.fail:
            raise UserError("ggLeap neodpovídá")
        return sync.env["elite.arena.ggleap.gamepass"].sudo().create({
            "uuid": "gp-%s" % key, "player_id": player.id, "name": name, "seconds": seconds,
            "state": "active", "hours_left": seconds / 3600.0, "expires_at": expires_at})
