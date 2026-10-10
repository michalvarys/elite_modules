# -*- coding: utf-8 -*-
"""Zrusenim spravy stranky /o-nas zbyla v databazi prazdna tabulka.

Stranka je poskladana z bloku a prepisuje se primo v editoru, takze zaznam
v adminu uz nic neridil. Odstranuje se i s pravy a polozkou v nabidce.
"""


def migrate(cr, version):
    cr.execute("""
        DELETE FROM ir_model_data
         WHERE model IN ('ir.model', 'ir.model.fields', 'ir.model.access',
                         'ir.ui.view', 'ir.actions.act_window', 'ir.ui.menu')
           AND (name LIKE '%%elite_vet_about%%' OR name LIKE '%%o_nas_views%%')
    """)
    cr.execute("DROP TABLE IF EXISTS elite_vet_about")
