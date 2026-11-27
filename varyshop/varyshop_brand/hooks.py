from .brand import NAME

APP_NAME_PARAM = "web.web_app_name"


def post_init_hook(env):
    """Name of the installable web app (PWA). Odoo's default is "Odoo"; a name someone set stays."""
    params = env["ir.config_parameter"].sudo()
    if params.get_param(APP_NAME_PARAM, "Odoo") == "Odoo":
        params.set_param(APP_NAME_PARAM, NAME)


def uninstall_hook(env):
    params = env["ir.config_parameter"].sudo()
    if params.get_param(APP_NAME_PARAM) == NAME:
        params.set_param(APP_NAME_PARAM, False)
