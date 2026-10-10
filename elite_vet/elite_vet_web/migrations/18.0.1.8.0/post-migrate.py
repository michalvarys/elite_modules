# -*- coding: utf-8 -*-
"""Pohotovost 24/7: z dvoustavoveho prepinace na tristavovy.

Puvodni ``emergency_active`` mel jen zapnuto/vypnuto a to vypnute porad
slibovalo linku "jiz brzy" — sede tlacitko, blikajici kolecko a vetu pod
ordinacnimi hodinami. Klinika kvuli tomu resila, ze jim lide volaji mimo
ordinacni dobu v domneni, ze pohotovost uz bezi.

Migrace zachova, jak web vypadal: zapnuta pohotovost -> "live", vypnuta ->
"soon". Uplne schovat ("hidden") je rozhodnuti kliniky, ne migrace.
"""


def migrate(cr, version):
    cr.execute("""
        SELECT column_name FROM information_schema.columns
         WHERE table_name = 'elite_vet_setting'
           AND column_name IN ('emergency_active', 'emergency_mode')
    """)
    sloupce = {radek[0] for radek in cr.fetchall()}
    if "emergency_mode" not in sloupce:
        return
    if "emergency_active" not in sloupce:
        return
    cr.execute("""
        UPDATE elite_vet_setting
           SET emergency_mode = CASE WHEN emergency_active THEN 'live' ELSE 'soon' END
         WHERE emergency_mode IS NULL
    """)
    cr.execute("ALTER TABLE elite_vet_setting DROP COLUMN emergency_active")
