from odoo import http
from odoo.http import request


class SequenceUnsubscribeController(http.Controller):
    """Unsubscribe link from automatic e-mails. Confirmed with a button (POST), so that mail
    scanners opening links do not unsubscribe people."""

    def _mail(self, token):
        if not token or len(token) > 64:
            return request.env["elite.arena.mail.sequence.mail"]
        return request.env["elite.arena.mail.sequence.mail"].sudo().search([("token", "=", token)], limit=1)

    @http.route("/arena/odhlasit/<string:token>", type="http", auth="public", website=True, sitemap=False,
                methods=["GET", "POST"])
    def unsubscribe(self, token, **kw):
        mail = self._mail(token)
        if not mail:
            return request.render("elite_arena_mail_sequence.unsubscribe_page", {"mail": mail, "done": False},
                                  status=404)
        done = False
        if request.httprequest.method == "POST":
            if not mail.is_test and mail.partner_id.email:
                request.env["mail.blacklist"].sudo()._add(
                    mail.partner_id.email, message="Odhlášení z automatických e-mailů (%s)." % (
                        mail.sequence_id.name or ""))
                request.env["elite.arena.mail.sequence.enrollment"].sudo().search(
                    [("partner_id", "=", mail.partner_id.id), ("state", "=", "running")]).write(
                    {"state": "unsubscribed", "next_at": False})
            done = True
        return request.render("elite_arena_mail_sequence.unsubscribe_page", {"mail": mail, "done": done})
