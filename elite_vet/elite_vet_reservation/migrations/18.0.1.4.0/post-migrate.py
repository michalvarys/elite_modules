"""18.0.1.4.0: druh blokace. Všechny dosavadní blokace byly úplné (nikdo tam nic nevytvoří)."""


def migrate(cr, version):
    cr.execute("UPDATE elite_vet_reservation SET block_scope = 'full' WHERE kind = 'block'")
