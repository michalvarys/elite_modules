import re

from markupsafe import Markup

from odoo import models

from ..brand import COLOR_DARK, NAME, URL

# "Powered by <a href="https://www.odoo.com?...">Odoo</a>" in e-mail layouts and templates of all
# apps (mail, auth_signup, portal, digest, ...), in any language: only the link is replaced.
ODOO_LINK = re.compile(
    r"""(<a\b[^>]*?\bhref=["'])https?://(?:www\.)?odoo\.com(?:[/?][^"']*)?(["'][^>]*>)"""
    r"""(\s*(?:<span\b[^>]*>)?\s*)Odoo(\s*(?:</span>)?\s*</a>)""",
    re.IGNORECASE,
)
# Odoo purple of buttons, headers and links in the e-mail layouts and templates.
ODOO_COLOR = re.compile(r"#(?:875a7b|714b67|71639e)\b", re.IGNORECASE)


def rebrand_html(body):
    """Body with every link to odoo.com labelled "Odoo" pointing to Varyshop instead, and the Odoo
    purple replaced by the Varyshop blue."""
    if not body:
        return body
    result = ODOO_COLOR.sub(COLOR_DARK, body)
    if "odoo.com" not in result:
        return Markup(result) if isinstance(body, Markup) else result
    result = ODOO_LINK.sub(
        lambda m: "%s%s?utm_source=db&amp;utm_medium=email%s%s%s%s" % (
            m.group(1), URL, m.group(2), m.group(3), NAME, m.group(4)),
        result,
    )
    return Markup(result) if isinstance(body, Markup) else result


class MailMail(models.Model):
    _inherit = "mail.mail"

    def _prepare_outgoing_body(self):
        return rebrand_html(super()._prepare_outgoing_body())
