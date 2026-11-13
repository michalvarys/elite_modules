from odoo import fields, models
from odoo.tools.misc import format_datetime


class ClosingReceiptReport(models.AbstractModel):
    """The closing receipt printed again later from the POS session in the back office."""

    _name = "report.elite_pos_closing_receipt.report_closing_receipt"
    _description = "Elite - uzávěrka pokladny (zpětný tisk)"

    def _get_report_values(self, docids, data=None):
        sessions = self.env["pos.session"].browse(docids)
        tz = self.env.user.tz or "Europe/Prague"

        def when(value):
            if not value:
                return ""
            return format_datetime(self.env, fields.Datetime.to_datetime(value), tz=tz,
                                   dt_format="d. M. yyyy H:mm")

        receipts = []
        for session in sessions:
            receipt = session.get_elite_closing_receipt()
            receipt.update(opened=when(receipt["opened"]), closed=when(receipt["closed"]))
            receipts.append(receipt)
        return {
            "doc_ids": docids,
            "doc_model": "pos.session",
            "docs": sessions,
            "receipts": list(zip(sessions, receipts)),
            "printed_at": when(fields.Datetime.now()),
        }
