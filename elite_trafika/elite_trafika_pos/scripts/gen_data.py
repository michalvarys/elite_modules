"""Generates data/*.xml and zbozi.csv of elite_trafika_pos from the Dotykačka product export.

usage: python3 scripts/gen_data.py "<archiv>/Produkty/01 Produkty – aktuální nesmazané.xlsx" .
Needs openpyxl (pip install openpyxl); run from the module directory, or pass the module directory."""
import collections
import csv
import re
import sys
from xml.sax.saxutils import escape

import openpyxl

RAW, OUT = sys.argv[1], sys.argv[2]

# Till tabs in the order of the till screen (video of 3. 11. 2026); the export has no category order.
TAB_ORDER = [
    ("cigarety", "CIGARETY"), ("pivo", "PIVO"), ("energy", "ENERGY DRINKY"), ("vapes", "VAPES"),
    ("cbd_cartridge", "CBD CARTRIDGE"), ("alcohol", "ALCOHOL"), ("prislusenstvi", "PŘÍSLUŠENSTVÍ A ZBOŽÍ"),
    ("cokolada", "ČOKOLÁDA"), ("zvykacky", "ŽVÝKAČKY-BONBONY-CHIPS"), ("lizatka", "LÍZÁTKA - DROPS"),
    ("canna_bloom", "CANNA BLOOM - KVĚTY"), ("oleje", "OLEJE - KAPKY - TEA"), ("hasish", "HASISH"),
    ("gumies", "GUMIES - SHOTS"), ("pre_rolls", "PREE-ROLLS"), ("cookies", "COOKIES"), ("tyson", "TYSON"),
    ("veo", "VEO ZAH. TABÁK"), ("neo", "NEO"), ("velo", "VELO"), ("siberia", "SIBERIA"), ("iqos", "IQOS"),
    ("tabaky", "TABÁKY-DUTINKY-PAPIRKY"), ("vuse", "VUSE"), ("syx_bar", "SYX BAR"), ("dutinky", "DUTINKY"),
    ("zapalovace", "ZAPALOVAČE"), ("doutniky", "DOUTNÍKY"), ("syx_pod", "SYX POD"), ("napoje", "NÁPOJE"),
    ("pipe_bong", "PIPE A BONG"), ("vahy", "VÁHY"), ("kvety", "KVĚTY VOLNÉ"), ("kleaner", "KLEANER"),
    ("pytliky", "PYTLÍKY"),
]
KEY = {name: key for key, name in TAB_ORDER}
# Main groups of the till; the tabs of Dotykačka are their subcategories, TYSON stays on its own.
GROUPS = [
    ("tabak", "Tabák a cigarety", 10, ["cigarety", "tabaky", "dutinky", "doutniky"]),
    ("nikotin", "Nikotin a IQOS", 20, ["velo", "siberia", "iqos", "veo", "neo"]),
    ("vape", "Vape", 30, ["vapes", "vuse", "syx_bar", "syx_pod", "cbd_cartridge"]),
    ("konopi", "Konopí a CBD", 40, ["kvety", "canna_bloom", "hasish", "oleje", "pre_rolls", "gumies"]),
    ("sladke", "Sladké a snacky", 50, ["cokolada", "cookies", "lizatka", "zvykacky"]),
    ("napoje_alkohol", "Nápoje a alkohol", 60, ["napoje", "energy", "pivo", "alcohol"]),
    ("prislusenstvi_vse", "Příslušenství", 80, ["prislusenstvi", "zapalovace", "pipe_bong", "vahy", "kleaner",
                                                 "pytliky"]),
]
REDUCED_VAT = 12.0


def text(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


sheet = list(openpyxl.load_workbook(RAW, read_only=True, data_only=True).active.iter_rows(values_only=True))
rows = [dict(zip(sheet[0], r)) for r in sheet[1:]]
assert all(r["deleted"] == "0" for r in rows)
categories = collections.OrderedDict()  # key -> name as in Dotykačka
for r in rows:
    name = text(r["categoryName"])
    categories[KEY[name.upper()]] = name
categories = collections.OrderedDict((k, categories[k]) for k, _ in TAB_ORDER if k in categories)
assert len(categories) == len({text(r["categoryName"]) for r in rows})

products, seen_ean, shared_ean = [], {}, []
for r in sorted(rows, key=lambda r: float(r["sortOrder"])):
    eans = [e for e in str(r["ean"] or "").split(",") if e.strip()]
    ean = eans[0].strip() if eans else ""
    name = text(r["name"])
    if ean in seen_ean:
        shared_ean.append((ean, name, seen_ean[ean]))
        ean = ""  # Odoo needs a unique barcode; the first product of the till keeps it
    elif ean:
        seen_ean[ean] = name
    products.append(dict(id=r["productId"], xmlid="product_%s" % r["productId"], categ=KEY[text(r["categoryName"]).upper()],
                         category=text(r["categoryName"]), name=name, price=round(float(r["priceWithVAT"]), 2),
                         vat=float(r["vat"]), barcode=ean, age=bool(r["minCustomerAge"])))
order = {k: i for i, k in enumerate(categories)}
products.sort(key=lambda p: order[p["categ"]])  # stable: keeps the till order inside a category


def categories_xml():
    out = ['<?xml version="1.0" encoding="utf-8"?>', "<odoo>", '    <data noupdate="1">',
           "        <!-- Skupiny zboží podle pokladny Elite Trafika (kategorie Dotykačky, export z 3. 11. 2026),",
           "             v pořadí záložek na pokladně. -->",
           '        <record id="product_category_trafika" model="product.category">',
           '            <field name="name">Elite Trafika</field>', "        </record>"]
    for key, name in categories.items():
        out += ['        <record id="product_category_%s" model="product.category">' % key,
                '            <field name="name">%s</field>' % escape(name),
                '            <field name="parent_id" ref="product_category_trafika"/>', "        </record>"]
    for seq, (key, name) in enumerate(categories.items(), 1):
        out += ['        <record id="pos_category_%s" model="pos.category">' % key,
                '            <field name="name">%s</field>' % escape(name),
                '            <field name="sequence">%d</field>' % (seq * 10), "        </record>"]
    out.append("        <!-- Hlavní skupiny; podskupiny k nim přiřadí category_groups v data/setup.xml. -->")
    for key, name, seq, _children in GROUPS:
        out += ['        <record id="pos_category_group_%s" model="pos.category">' % key,
                '            <field name="name">%s</field>' % escape(name),
                '            <field name="sequence">%d</field>' % seq, "        </record>"]
    out += ["    </data>", "</odoo>", ""]
    return "\n".join(out)


def products_xml():
    out = ['<?xml version="1.0" encoding="utf-8"?>', "<odoo>", '    <data noupdate="1">',
           "        <!-- Zboží z pokladny Elite Trafika: export produktů Dotykačky z 3. 11. 2026 (aktuální,",
           "             nesmazané). Id záznamu = id produktu v Dotykačce, čárový kód = EAN z Dotykačky.",
           "             Ceny jsou včetně DPH; sazbu nastaví data/setup.xml. -->"]
    categ = None
    for p in products:
        if p["categ"] != categ:
            categ = p["categ"]
            out.append("        <!-- %s -->" % escape(p["category"]))
        out += ['        <record id="%s" model="product.template">' % p["xmlid"],
                '            <field name="name">%s</field>' % escape(p["name"]),
                '            <field name="type">consu</field>',
                '            <field name="is_storable" eval="True"/>',
                '            <field name="list_price">%.2f</field>' % p["price"]]
        if p["barcode"]:
            out.append('            <field name="barcode">%s</field>' % p["barcode"])
        out += ['            <field name="sale_ok" eval="True"/>',
                '            <field name="purchase_ok" eval="True"/>',
                '            <field name="available_in_pos" eval="True"/>',
                '            <field name="categ_id" ref="product_category_%s"/>' % p["categ"],
                '            <field name="pos_categ_ids" eval="[(6, 0, [ref(\'pos_category_%s\')])]"/>' % p["categ"],
                "        </record>"]
    out += ["    </data>", "</odoo>", ""]
    return "\n".join(out)


def setup_xml():
    reduced = [p["xmlid"] for p in products if p["vat"] == REDUCED_VAT]
    refs = "".join("\n                ref('%s')," % x for x in reduced)
    groups = "".join("\n                'group_%s': %r," % (key, children) for key, _n, _s, children in GROUPS)
    return """<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <!-- Nastavení pokladny pro jednu firmu. Ostatních firem v databázi se modul nedotkne a u cílové
         firmy nic nepřepisuje: osnovu a daně založí jen firmě, která ještě nemá účetnictví,
         jinak použije to, co firma má. Kód je v models/setup.py, běh je bezpečné opakovat.

         company      firma (přesný název), pro kterou se pokladna zakládá; když v databázi není,
                      instalace skončí chybou a nic se nezmění
         pos_name     název pokladny
         reduced_vat  zboží s DPH 12 %%, ostatní 21 %%. Sazby jsou převzaté z Dotykačky, kde má
                      všechno zboží trafiky 21 %% (i čokolády, sušenky a lízátka); zboží s 12 %%
                      stačí doplnit sem, např. ref('product_271606912178637').
         category_groups  hlavní skupina pokladny a její podskupiny; skupinu, kterou někdo v Odoo
                      přesunul jinam, modul nepřesouvá -->
    <function model="elite.trafika.pos.setup" name="ensure_setup">
        <value eval="{
            'company': 'Elite Trafika',
            'pos_name': 'Elite Trafika',
            'reduced_vat': [%s
            ],
            'category_groups': {%s
            },
        }"/>
    </function>
</odoo>
""" % (refs, groups)


with open(OUT + "/data/product_category_data.xml", "w") as f:
    f.write(categories_xml())
with open(OUT + "/data/product_data.xml", "w") as f:
    f.write(products_xml())
with open(OUT + "/data/setup.xml", "w") as f:
    f.write(setup_xml())
with open(OUT + "/zbozi.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["xmlid", "id_dotykacka", "skupina", "název", "cena", "dph", "ean", "18+"])
    for p in products:
        w.writerow([p["xmlid"], p["id"], p["category"], p["name"], "%.2f" % p["price"], "%g" % p["vat"],
                    p["barcode"], "ano" if p["age"] else ""])
print(len(products), "products,", len(categories), "categories,", sum(1 for p in products if p["barcode"]), "barcodes")
for ean, name, first in shared_ean:
    print("shared EAN %s: %s (kept on %s)" % (ean, name, first))
