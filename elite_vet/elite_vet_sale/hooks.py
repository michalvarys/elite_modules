def post_init_hook(env):
    env["elite.vet.sale.setup"].ensure_setup()
