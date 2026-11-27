"""Generates data/product_category_data.xml and data/product_data.xml of a restaurant module from its
skupiny.csv (till groups) and zbozi.csv (menu).

usage: python3 elite_common/elite_restaurant_pos/scripts/gen_data.py <restaurant module dir> "<Name>"

zbozi.csv columns: kod (xml id suffix), skupina (kod of skupiny.csv), nazev, cena (with VAT),
dph (jidlo = 12 %, nealko = 21 % / 12 % from 2027, alkohol = 21 %), sklad (ano = stocked bottle or can),
alergeny (numbers as on the menu)."""
import csv
import os
import sys
from xml.sax.saxutils import escape

MODULE_DIR, LABEL = sys.argv[1], sys.argv[2]


def read(name):
    with open(os.path.join(MODULE_DIR, name), encoding="utf-8") as f:
        return list(csv.DictReader(f))


groups, menu = read("skupiny.csv"), read("zbozi.csv")
keys = {g["kod"] for g in groups}
root_of = {g["kod"]: g["nadrazena"] or g["kod"] for g in groups}
assert len({m["kod"] for m in menu}) == len(menu), "duplicate kod in zbozi.csv"
for m in menu:
    assert m["skupina"] in keys, m
    assert m["dph"] in ("jidlo", "nealko", "alkohol"), m
    float(m["cena"])

out = ['<?xml version="1.0" encoding="utf-8"?>', "<odoo>", '    <data noupdate="1">',
       "        <!-- Vygenerováno z skupiny.csv (elite_restaurant_pos/scripts/gen_data.py). -->",
       '        <record id="product_category_root" model="product.category">',
       "            <field name=\"name\">%s</field>" % escape(LABEL), "        </record>"]
for g in groups:
    if not g["nadrazena"]:
        out += ['        <record id="product_category_%s" model="product.category">' % g["kod"],
                "            <field name=\"name\">%s</field>" % escape(g["nazev"]),
                '            <field name="parent_id" ref="product_category_root"/>', "        </record>"]
for g in sorted(groups, key=lambda g: bool(g["nadrazena"])):
    out += ['        <record id="pos_category_%s" model="pos.category">' % g["kod"],
            "            <field name=\"name\">%s</field>" % escape(g["nazev"]),
            '            <field name="sequence">%s</field>' % g["poradi"]]
    if g["nadrazena"]:
        out.append('            <field name="parent_id" ref="pos_category_%s"/>' % g["nadrazena"])
    out.append("        </record>")
out += ["    </data>", "</odoo>", ""]
with open(os.path.join(MODULE_DIR, "data", "product_category_data.xml"), "w", encoding="utf-8") as f:
    f.write("\n".join(out))

out = ['<?xml version="1.0" encoding="utf-8"?>', "<odoo>", '    <data noupdate="1">',
       "        <!-- Vygenerováno z zbozi.csv (elite_restaurant_pos/scripts/gen_data.py). Ceny jsou včetně DPH;",
       "             firmu a sazbu DPH doplní elite.restaurant.pos.setup podle zbozi.csv. -->"]
for seq, m in enumerate(menu, 1):
    stocked = m["sklad"] == "ano"
    out += ['        <record id="product_%s" model="product.template">' % m["kod"],
            "            <field name=\"name\">%s</field>" % escape(m["nazev"]),
            '            <field name="type">consu</field>',
            '            <field name="is_storable" eval="%s"/>' % stocked,
            '            <field name="list_price">%.2f</field>' % float(m["cena"]),
            '            <field name="sale_ok" eval="True"/>',
            '            <field name="purchase_ok" eval="%s"/>' % stocked,
            '            <field name="available_in_pos" eval="True"/>',
            '            <field name="sequence">%d</field>' % seq,
            '            <field name="categ_id" ref="product_category_%s"/>' % root_of[m["skupina"]],
            "            <field name=\"pos_categ_ids\" eval=\"[(6, 0, [ref('pos_category_%s')])]\"/>" % m["skupina"]]
    if m["alergeny"]:
        out.append("            <field name=\"description_sale\">Alergeny: %s</field>" % escape(m["alergeny"]))
    out.append("        </record>")
out += ["    </data>", "</odoo>", ""]
with open(os.path.join(MODULE_DIR, "data", "product_data.xml"), "w", encoding="utf-8") as f:
    f.write("\n".join(out))
print(len(groups), "groups,", len(menu), "products")
