"""Generates data/catalog_data.xml and static/img/items/ of elite_trafika_catalog.

usage: python3 scripts/gen_data.py <folder with images named by the Euphoria slug> <products.json> .
products.json holds slug and ean of each product from euphoria.eu. Needs Pillow."""
import glob
import json
import os
import sys
from xml.sax.saxutils import escape

from PIL import Image

SOURCE, PRODUCTS, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
SIZE = 800

WHITE_WIDOW = "Kořeněná, lehce květinová vůně."
WATERMELON = "Sladký meloun s klasickým OG tónem."
BLUEBERRY = "Sladké borůvky s ostrým dieselovým tónem."
GRAPE = "Sladké hrozny s výrazným kush tónem."
PEACH = "Šťavnatá broskev s klasickým haze tónem."
LIMONCELLO = "Svěží citronová vůně."
SHERBERT = "Sladká ovocná vůně."
NORTHERN = "Výrazná, intenzivní vůně."
DAMIANA = "Zemitá bylinná vůně inspirovaná OG Kush."
RASPBERRY = "Sladká malina se zemitým tónem."

# (key, Euphoria slug, name, kind, pack, aroma, sold in the shop today: the till has the EAN and the same goods)
ITEMS = [
    ("white_widow_1g", "t9hc-white-widow-flowers-1-g-1", "T9HC White Widow", "flower", "1 g", WHITE_WIDOW, True),
    ("northern_lights_1g", "euphoria-t9hc-kvety-1-g", "T9HC Northern Lights", "flower", "1 g", NORTHERN, True),
    ("limoncello_1g", "euphoria-t9hc-limoncello-flowers-1-g-1", "T9HC Limoncello", "flower", "1 g", LIMONCELLO, True),
    ("sherbert_1g", "euphoria-t9hc-sherbert-flowers-1-g-1", "T9HC Sherbert", "flower", "1 g", SHERBERT, True),
    ("blueberry_1g", "t9hc-blueberry-diesel-flowers-1-g", "T9HC Blueberry Diesel", "flower", "1 g", BLUEBERRY, True),
    ("grape_1g", "t9hc-grape-kush-flowers-1-g", "T9HC Grape Kush", "flower", "1 g", GRAPE, True),
    ("peach_1g", "t9hc-peach-haze-flowers-1-g", "T9HC Peach Haze", "flower", "1 g", PEACH, True),
    ("watermelon_1g", "t9hc-watermelon-og-flowers-1-g", "T9HC Watermelon OG", "flower", "1 g", WATERMELON, True),
    ("white_widow_3g", "t9hc-white-widow-flowers-3-g", "T9HC White Widow", "flower", "3 g", WHITE_WIDOW, False),
    ("northern_lights_3g", "t9hc-northen-lights-flowers-3-g-1", "T9HC Northern Lights", "flower", "3 g", NORTHERN, False),
    ("limoncello_3g", "t9hc-limoncello-flowers-3-g-1", "T9HC Limoncello", "flower", "3 g", LIMONCELLO, False),
    ("sherbert_3g", "t9hc-sherbert-flowers-3-g", "T9HC Sherbert", "flower", "3 g", SHERBERT, False),
    ("blueberry_3g", "t9hc-blueberry-diesel-flowers-3-g", "T9HC Blueberry Diesel", "flower", "3 g", BLUEBERRY, False),
    ("grape_3g", "t9hc-grape-kush-flowers-3-g", "T9HC Grape Kush", "flower", "3 g", GRAPE, False),
    ("peach_3g", "t9hc-peach-haze-flowers-3-g", "T9HC Peach Haze", "flower", "3 g", PEACH, False),
    ("watermelon_3g", "t9hc-watermelon-og-flowers-3-g", "T9HC Watermelon OG", "flower", "3 g", WATERMELON, False),
    ("damiana_1g", "t9hc-bylinna-smes-damiana-og-kush-1-g", "T9HC Damiana OG Kush", "herbal", "1 g", DAMIANA, False),
    ("raspberry_1g", "t9hc-bylinna-smes-raspberry-chemdawg-1-g", "T9HC Raspberry Chemdawg", "herbal", "1 g", RASPBERRY, False),
    ("damiana_3g", "t9hc-herbal-mix-damiana-og-kush-3-g-1", "T9HC Damiana OG Kush", "herbal", "3 g", DAMIANA, False),
    ("raspberry_3g", "t9hc-herbal-mix-raspberry-chemdawg-3-g-1", "T9HC Raspberry Chemdawg", "herbal", "3 g", RASPBERRY, False),
    ("stick_white_widow", "t9hc-white-widow-aroma-stick-1-pcs", "T9HC Aroma Stick White Widow", "stick", "1 ks", WHITE_WIDOW, True),
    ("stick_watermelon", "t9hc-aroma-stick-watermelon-og-1-kus", "T9HC Aroma Stick Watermelon OG", "stick", "1 ks", WATERMELON, False),
    ("stick_blueberry", "t9hc-aromatic-sticks-blueberry-diesel-1-ks", "T9HC Aroma Stick Blueberry Diesel", "stick", "1 ks", BLUEBERRY, False),
    ("stick_grape", "t9hc-aromatic-sticks-grape-kush-1-ks", "T9HC Aroma Stick Grape Kush", "stick", "1 ks", GRAPE, False),
    ("stick_peach", "t9hc-aromatic-sticks-peach-haze-1-kus", "T9HC Aroma Stick Peach Haze", "stick", "1 ks", PEACH, False),
    ("stick_damiana", "t9hc-herbal-mix-damiana-og-kush-aroma-stick-1-pc", "T9HC Aroma Stick Damiana OG Kush", "stick", "1 ks", DAMIANA, False),
    ("stick_raspberry", "t9hc-herbal-mix-raspberry-chemdawg-prerolled-joint-1-pc-1", "T9HC Aroma Stick Raspberry Chemdawg", "stick", "1 ks", RASPBERRY, False),
    ("stick_t9hc", "euphoria-t9hc-predtaveny-joint", "T9HC Aroma Stick", "stick", "1 ks", "", False),
]


def write_image(key, slug):
    source = glob.glob(os.path.join(SOURCE, slug + ".*"))[0]
    image = Image.open(source).convert("RGBA")
    image.thumbnail((SIZE, SIZE))
    tile = Image.new("RGBA", (SIZE, SIZE), "white")
    tile.alpha_composite(image, ((SIZE - image.width) // 2, (SIZE - image.height) // 2))
    tile.convert("RGB").save(os.path.join(OUT, "static/img/items", key + ".jpg"), quality=82, optimize=True)


def main():
    eans = {product["slug"]: product["ean"] for product in json.load(open(PRODUCTS, encoding="utf-8"))}
    out = ['<?xml version="1.0" encoding="utf-8"?>', "<odoo>", '    <data noupdate="1">',
           "        <!-- Vygenerováno skriptem scripts/gen_data.py. Úpravy v Odoo aktualizace nepřepíše. -->"]
    for sequence, (key, slug, name, kind, pack, aroma, in_store) in enumerate(ITEMS, 1):
        write_image(key, slug)
        out += ['        <record id="item_%s" model="elite.trafika.catalog.item">' % key,
                '            <field name="name">%s</field>' % escape(name),
                '            <field name="kind">%s</field>' % kind,
                '            <field name="pack">%s</field>' % escape(pack)]
        if aroma:
            out.append('            <field name="aroma">%s</field>' % escape(aroma))
        out += ['            <field name="ean">%s</field>' % eans[slug],
                '            <field name="in_store" eval="%s"/>' % in_store,
                '            <field name="sequence">%d</field>' % (sequence * 10),
                '            <field name="image_1920" type="base64" '
                'file="elite_trafika_catalog/static/img/items/%s.jpg"/>' % key,
                "        </record>"]
    out += ["    </data>", "</odoo>", ""]
    with open(os.path.join(OUT, "data/catalog_data.xml"), "w", encoding="utf-8") as data:
        data.write("\n".join(out))
    print(len(ITEMS), "items")


main()
