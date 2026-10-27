"""Clinic notifications go to rezervace@elite-vet.cz instead of the old default info@elite-vet.cz.

Only the untouched old default is changed; an address set by hand stays. The new switch
booking_notify_enabled is on (default), so nothing else changes for the clinic.
"""


def migrate(cr, version):
    cr.execute("""
        UPDATE elite_vet_setting SET booking_notify_email = 'rezervace@elite-vet.cz'
         WHERE lower(trim(booking_notify_email)) = 'info@elite-vet.cz'
    """)
