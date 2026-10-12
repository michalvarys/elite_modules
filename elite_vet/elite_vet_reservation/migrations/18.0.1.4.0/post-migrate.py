"""18.0.1.4.0: block scope. All existing blocks were full blocks (nothing can be booked into them)."""


def migrate(cr, version):
    cr.execute("UPDATE elite_vet_reservation SET block_scope = 'full' WHERE kind = 'block'")
