import logging

from odoo import SUPERUSER_ID, fields, http
from odoo.http import request

_logger = logging.getLogger(__name__)

UNAUTHORIZED = {"ok": False, "error": "unauthorized"}


class WinvetApi(http.Controller):
    """JSON-RPC API for the WinVet bridge (winvet_bridge/CONTRACT.md)."""

    def _authorized(self):
        header = request.httprequest.headers.get("Authorization") or ""
        scheme, _sep, token = header.partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            return False
        return request.env["elite.vet.winvet.config"].sudo().check_key(token.strip())

    def _call(self, method, params):
        if not self._authorized():
            return UNAUTHORIZED
        request.update_env(user=SUPERUSER_ID)
        sync = request.env["elite.vet.winvet.sync"]
        try:
            with request.env.cr.savepoint():
                return getattr(sync, method)(params)
        except Exception as exc:  # noqa: BLE001 - the batch is rolled back, the bridge retries
            _logger.exception("WinVet %s failed", method)
            request.env.invalidate_all()
            status = request.env["elite.vet.winvet.status"].get_status()
            status.last_error = "%s %s %s: %s" % (fields.Datetime.to_string(fields.Datetime.now()), method,
                                                  params.get("entity") or "", exc)
            return {"ok": False, "error": "server error"}

    @http.route("/winvet/api/v1/status", type="json", auth="none", methods=["POST"], csrf=False,
                readonly=False)
    def status(self, **params):
        return self._call("receive_status", params)

    @http.route("/winvet/api/v1/push", type="json", auth="none", methods=["POST"], csrf=False,
                readonly=False)
    def push(self, **params):
        return self._call("push", params)
