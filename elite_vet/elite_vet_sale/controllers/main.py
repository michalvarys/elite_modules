"""The POS route renders the till and opens a session under sudo for any internal user (Odoo
checks the rights only on the data calls). Task 14: only users with the POS rights (Recepce via
group_till_stock, Vedení) may open it; a doctor or a nurse gets 403."""
from werkzeug.exceptions import Forbidden

from odoo import http
from odoo.http import request

from odoo.addons.point_of_sale.controllers.main import PosController


class ElitePosController(PosController):

    @http.route()
    def pos_web(self, config_id=False, from_backend=False, **k):
        user = request.env.user
        if user._is_internal() and not user.has_group("point_of_sale.group_pos_user"):
            raise Forbidden("Pokladnu může otevřít jen recepce nebo vedení.")
        return super().pos_web(config_id=config_id, from_backend=from_backend, **k)
