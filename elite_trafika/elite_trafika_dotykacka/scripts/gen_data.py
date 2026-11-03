"""Converts the Dotykačka archive of SL FORTIS (Elite Trafika) into the data files of elite_trafika_dotykacka.

usage: python3 scripts/gen_data.py <Dotykacka_SL_FORTIS_2026_archiv> .
Run with a Python that has openpyxl. Times of the archive are local (Europe/Prague); the CSV files hold UTC."""
import collections
import csv
import datetime
import os
import re
import sys
import zoneinfo
from xml.sax.saxutils import escape

import openpyxl

ARCHIVE, OUT = sys.argv[1], sys.argv[2]
PRAGUE = zoneinfo.ZoneInfo("Europe/Prague")
POS_MODULE = "elite_trafika_pos"


def load(name):
    ws = openpyxl.load_workbook(os.path.join(ARCHIVE, name), read_only=True, data_only=True).active
    rows = list(ws.iter_rows(values_only=True))
    return [dict(zip(rows[0], r)) for r in rows[1:]]


def text(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def utc(value):
    return value.replace(tzinfo=PRAGUE).astimezone(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def first_ean(value):
    eans = [e.strip() for e in str(value or "").split(",") if e.strip()]
    return eans[0] if eans else ""


all_products = load("Produkty/55 Produkty – všechny včetně smazaných.xlsx")
receipts = load("Reporty/17 Vystavené doklady.xlsx")
lines = load("Reporty/18 Detailní výpis prodejů.xlsx")
moves = load("Reporty/19 Pokladní pohyby.xlsx")
shifts = load("Reporty/12 Směny a uzávěrky.xlsx")
stock = load("Reporty/37 Stav skladu ke dni.xlsx")

# ---------------------------------------------------------------- products of the history
current = {p["productId"] for p in all_products if p["deleted"] == "0"}
by_name, by_ean = collections.defaultdict(list), collections.defaultdict(list)
for p in sorted(all_products, key=lambda p: (p["deleted"], float(p["sortOrder"] or 0))):  # current ones first
    by_name[text(p["name"])].append(p)
    if first_ean(p["ean"]):
        by_ean[first_ean(p["ean"])].append(p)

deleted_used, historic = {}, collections.OrderedDict()  # products the module has to create (archived)


def resolve(name, ean, price):
    """xmlid of the product sold under `name`: same name (the one with the EAN when names repeat),
    else the only product with that EAN, else an archived product of that name."""
    candidates = by_name.get(name, [])
    if len(candidates) > 1 and ean:
        candidates = [p for p in candidates if first_ean(p["ean"]) == ean] or candidates
    if not candidates and ean and len(by_ean.get(ean, [])) == 1:
        candidates = by_ean[ean]
    if candidates:
        p = candidates[0]
        if p["productId"] in current:
            return "%s.product_%s" % (POS_MODULE, p["productId"])
        deleted_used[p["productId"]] = p
        return "product_%s" % p["productId"]
    key = "product_hist_%s" % (re.sub(r"_+", "_", re.sub(r"[^a-z0-9]", "_", name.lower().encode(
        "ascii", "ignore").decode())).strip("_") or "x")
    while key in historic and historic[key]["name"] != name:
        key += "_"
    historic.setdefault(key, dict(name=name, ean=ean, price=price))
    return key


# ---------------------------------------------------------------- shifts, receipts, lines, payments
shift_rows = sorted(shifts, key=lambda s: s["Datum a čas otevření"])
shift_of = {}
for i, s in enumerate(shift_rows):
    s["key"] = "smena_%s" % s["Datum a čas otevření"].strftime("%Y%m%d_%H%M%S")


def find_shift(when):
    best = None
    for s in shift_rows:
        if s["Datum a čas otevření"] <= when:
            best = s
        if s["Datum a čas otevření"] <= when <= s["Datum a čas uzavření"]:
            return s
    return best or shift_rows[0]


payments = collections.defaultdict(lambda: collections.defaultdict(float))
for m in moves:
    if m["Typ operace"] in ("Prodej", "Vrácení") and m["Číslo daňového dokladu"]:
        payments[m["Číslo daňového dokladu"]][m["Typ platby"]] += m["Výše pohybu"]

os.makedirs(OUT + "/data/dotykacka", exist_ok=True)


def write(name, header, rows):
    with open(OUT + "/data/dotykacka/" + name, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


METHOD = {"Hotovost": "cash", "Platební karta": "card"}
write("smeny.csv", ["smena", "otevreno", "uzavreno", "obsluha", "hotovost_pri_uzavreni"],
      [(s["key"], utc(s["Datum a čas otevření"]), utc(s["Datum a čas uzavření"]), text(s["Zaměstnanec"]),
        "%.2f" % (s["Hodnota uzavření"] or 0)) for s in shift_rows])
receipt_rows, payment_rows = [], []
for r in sorted(receipts, key=lambda r: r["Číslo daňového dokladu"]):
    number = r["Číslo daňového dokladu"]
    receipt_rows.append((number, utc(r["Datum vystavení"]), find_shift(r["Datum vystavení"])["key"],
                         text(r["Zaměstnanec"]), "%.2f" % r["Celková hodnota dokladu"]))
    paid = {k: v for k, v in payments[number].items() if abs(v) > 0.001}
    if r["Zaplaceno"] == "Ano" and not paid:
        paid = {r["Typ platby"]: r["Celková hodnota dokladu"]}
    payment_rows += [(number, METHOD[k], "%.2f" % v) for k, v in sorted(paid.items())]
write("uctenky.csv", ["doklad", "datum", "smena", "obsluha", "celkem"], receipt_rows)
write("platby.csv", ["doklad", "platba", "castka"], payment_rows)
line_rows = []
for l in sorted(lines, key=lambda l: l["Číslo daňového dokladu"]):
    name, ean = text(l["Produkt"]), first_ean(l["EAN"])
    line_rows.append((l["Číslo daňového dokladu"], resolve(name, ean, l["Jedn. prodejní cena s DPH"]), name,
                      "%g" % l["Prodané množství"], "%.2f" % l["Jedn. prodejní cena s DPH"],
                      "%.2f" % l["Prodejní cena bez DPH"], "%.2f" % l["Prodejní cena s DPH"], "%g" % l["DPH"]))
write("polozky.csv", ["doklad", "produkt", "nazev", "mnozstvi", "cena_s_dph", "celkem_bez_dph", "celkem_s_dph",
                      "dph"], line_rows)

# ---------------------------------------------------------------- opening stock (current products only)
stock_rows, skipped = [], collections.Counter()
for s in stock:
    qty = s["Množství na skladu"] or 0
    if qty <= 0:
        skipped["záporný" if qty < 0 else "nulový"] += 1
        continue
    xmlid = resolve(text(s["Produkt"]), first_ean(s["EAN"]), 0)
    assert xmlid.startswith(POS_MODULE), (s["Produkt"], xmlid)
    stock_rows.append((xmlid, text(s["Produkt"]), "%g" % qty))
write("sklad.csv", ["produkt", "nazev", "mnozstvi"], stock_rows)

# ---------------------------------------------------------------- archived products
out = ['<?xml version="1.0" encoding="utf-8"?>', "<odoo>", '    <data noupdate="1">',
       "        <!-- Zboží, které se v Dotykačce prodávalo, ale dnes v ní není (smazané produkty a produkty",
       "             prodávané pod dřívějším názvem). Je archivované: v pokladně se nenabízí, jen drží",
       "             historické prodeje. -->",
       '        <record id="product_category_historie" model="product.category">',
       '            <field name="name">Dotykačka – dřívější zboží</field>',
       '            <field name="parent_id" ref="elite_trafika_pos.product_category_trafika"/>', "        </record>"]


def product_record(xmlid, name, price, ean):
    rec = ['        <record id="%s" model="product.template">' % xmlid,
           '            <field name="name">%s</field>' % escape(name),
           '            <field name="type">consu</field>',
           '            <field name="list_price">%.2f</field>' % price,
           '            <field name="available_in_pos" eval="True"/>',
           '            <field name="categ_id" ref="product_category_historie"/>',
           '            <field name="active" eval="False"/>', "        </record>"]
    return rec


for pid, p in deleted_used.items():
    out += product_record("product_%s" % pid, text(p["name"]), float(p["priceWithVAT"]), first_ean(p["ean"]))
for key, h in historic.items():
    out += product_record(key, h["name"], h["price"], h["ean"])
out += ["    </data>", "</odoo>", ""]
with open(OUT + "/data/product_history_data.xml", "w") as f:
    f.write("\n".join(out))

print("shifts", len(shift_rows), "receipts", len(receipt_rows), "lines", len(line_rows), "payments", len(payment_rows))
print("archived products: deleted", len(deleted_used), "renamed", len(historic), "->", [h["name"] for h in historic.values()][:40])
print("stock rows", len(stock_rows), "skipped", dict(skipped), "units", sum(float(r[2]) for r in stock_rows))
print("lines to archived products", sum(1 for r in line_rows if not r[1].startswith(POS_MODULE)))
