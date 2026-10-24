def post_init_hook(env):
    env["elite.vet.sale.setup"].ensure_setup()
    env["elite.vet.winvet.item"].with_context(active_test=False).search([])._sync_products()
    # Recepce users existing before the install get the till group (task 14).
    env["res.users"]._elite_vet_split_till_rights()
