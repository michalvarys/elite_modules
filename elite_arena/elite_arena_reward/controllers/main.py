from odoo import http
from odoo.exceptions import UserError
from odoo.http import request


class RewardClaimController(http.Controller):
    """Public page where a player claims a reward from an e-mail link. It is a normal
    website page, so the site's tracking (retargeting pixel) runs on it."""

    def _claim(self, token):
        if not token or len(token) > 64:
            return request.env["elite.arena.reward.claim"]
        return request.env["elite.arena.reward.claim"].sudo().search([("token", "=", token)], limit=1)

    def _render(self, claim, error=None, done=False):
        return request.render("elite_arena_reward.claim_page", {
            "claim": claim, "reward": claim.reward_id, "error": error, "done": done or claim.state == "claimed",
            "first_name": (claim.partner_id.name or "").split(" ")[0] if claim else "",
        })

    @http.route("/odmena/<string:token>", type="http", auth="public", website=True, sitemap=False)
    def claim_page(self, token, **kw):
        claim = self._claim(token)
        if not claim:
            return request.render("elite_arena_reward.claim_not_found", status=404)
        claim.mark_visited()
        return self._render(claim)

    @http.route("/odmena/<string:token>/vyzvednout", type="http", auth="public", website=True, sitemap=False,
                methods=["POST"])
    def claim_submit(self, token, **kw):
        claim = self._claim(token)
        if not claim:
            return request.render("elite_arena_reward.claim_not_found", status=404)
        try:
            claim.claim()
        except UserError as err:
            return self._render(claim, error=str(err.args[0] if err.args else err))
        return self._render(claim, done=True)
