from odoo import SUPERUSER_ID, api

from odoo.addons.elite_vet_web import _nastav_cenik


def migrate(cr, version):
    """Prevede cenik na sekce a uklidi po mezikroku.

    Stitek, nadpis, popisek a spodni ramecek se stehuji do prvni sekce, ukony
    se do ni zaradi. Sloupce a tabulka, ktere uz zadne pole nema, se zahazuji,
    at v databazi nezustava neco, co nikdo necte.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    _nastav_cenik(env)

    cr.execute("DROP TABLE IF EXISTS elite_vet_price_note")
    for sloupec in ("price_title", "price_lead"):
        cr.execute("ALTER TABLE elite_vet_setting DROP COLUMN IF EXISTS %s" % sloupec)
    cr.execute("""DELETE FROM ir_model_fields
                  WHERE model = 'elite.vet.setting' AND name IN ('price_title', 'price_lead')""")
    cr.execute("""DELETE FROM ir_model WHERE model = 'elite.vet.price.note'""")
