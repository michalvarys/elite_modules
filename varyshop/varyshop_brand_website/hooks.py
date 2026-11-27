from .models.website import ODOO_FAVICON, VARYSHOP_FAVICON


def post_init_hook(env):
    env["website"]._varyshop_swap_favicon(ODOO_FAVICON, VARYSHOP_FAVICON)


def uninstall_hook(env):
    env["website"]._varyshop_swap_favicon(VARYSHOP_FAVICON, ODOO_FAVICON)
