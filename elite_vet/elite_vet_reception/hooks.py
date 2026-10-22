def post_init_hook(env):
    """Reception setup (employee login, home URL) and role home actions of the existing users."""
    env["elite.vet.sale.setup"].ensure_setup()
    env["res.users"].search([("share", "=", False)])._elite_vet_apply_home_action()
