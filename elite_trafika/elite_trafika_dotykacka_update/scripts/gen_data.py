"""Converts a sales export of Dotykačka (SL FORTIS, Elite Trafika) into data/ of elite_trafika_dotykacka_update.

usage: python3 scripts/gen_data.py <export folder> <products xlsx> .
  <export folder>  the reports "Vystavené doklady", "Detailní výpis prodejů", "Pokladní pohyby" and
                   "Směny a uzávěrky" exported from Dotykačka (file names start with these words)
  <products xlsx>  "Produkty – všechny včetně smazaných" (the archive of 3. 11. 2026 has it)
Run with a Python that has openpyxl, from the module directory. Times of the export are local
(Europe/Prague); the CSV files hold UTC. Products: the ones of elite_trafika_pos by name or EAN, the
archived ones elite_trafika_dotykacka already has, otherwise a new archived product of this module."""
import collections
import csv
import datetime
import glob
import os
import re
import sys
import zoneinfo
from xml.etree import ElementTree
from xml.sax.saxutils import escape

import openpyxl

EXPORT, PRODUCTS, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
PRAGUE = zoneinfo.ZoneInfo("Europe/Prague")
POS_MODULE = "elite_trafika_pos"
HISTORY_MODULE = "elite_trafika_dotykacka"


def load(path):
    ws = openpyxl.load_workbook(path, read_only=True, data_only=True).active
    rows = list(ws.iter_rows(values_only=True))
    return [dict(zip(rows[0], r)) for r in rows[1:]]


def report(prefix):
    paths = sorted(glob.glob(os.path.join(EXPORT, prefix + "*.xlsx")))
    assert len(paths) == 1, (prefix, paths)
    return load(paths[0])


def text(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def utc(value):
    return value.replace(tzinfo=PRAGUE).astimezone(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def first_ean(value):
    eans = [e.strip() for e in str(value or "").split(",") if e.strip()]
    return eans[0] if eans else ""


all_products = load(PRODUCTS)
receipts = report("Vystavené doklady")
lines = report("Detailní výpis prodejů")
moves = report("Pokladní pohyby")
shifts = report("Směny a uzávěrky")

# archived products created by elite_trafika_dotykacka: xmlid by name
history_xml = os.path.join(OUT, "..", HISTORY_MODULE, "data", "product_history_data.xml")
known = {}
for record in ElementTree.parse(history_xml).getroot().iter("record"):
    if record.get("model") == "product.template":
        known[text(record.find("field[@name='name']").text)] = "%s.%s" % (HISTORY_MODULE, record.get("id"))

# ---------------------------------------------------------------- products of the sales
current = {p["productId"] for p in all_products if p["deleted"] == "0"}
by_name, by_ean = collections.defaultdict(list), collections.defaultdict(list)
for p in sorted(all_products, key=lambda p: (p["deleted"], float(p["sortOrder"] or 0))):  # current ones first
    by_name[text(p["name"])].append(p)
    if first_ean(p["ean"]):
        by_ean[first_ean(p["ean"])].append(p)

deleted_used, historic = {}, collections.OrderedDict()  # products this module has to create (archived)


def resolve(name, ean, price):
    """xmlid of the product sold under `name`, as in elite_trafika_dotykacka/scripts/gen_data.py; an
    archived product that module already created is reused."""
    candidates = by_name.get(name, [])
    if len(candidates) > 1 and ean:
        candidates = [p for p in candidates if first_ean(p["ean"]) == ean] or candidates
    if not candidates and ean and len(by_ean.get(ean, [])) == 1:
        candidates = by_ean[ean]
    if candidates:
        p = candidates[0]
        if p["productId"] in current:
            return "%s.product_%s" % (POS_MODULE, p["productId"])
        if text(p["name"]) in known:
            return known[text(p["name"])]
        deleted_used[p["productId"]] = p
        return "product_%s" % p["productId"]
    if name in known:
        return known[name]
    key = "product_hist_%s" % (re.sub(r"_+", "_", re.sub(r"[^a-z0-9]", "_", name.lower().encode(
        "ascii", "ignore").decode())).strip("_") or "x")
    while key in historic and historic[key]["name"] != name:
        key += "_"
    historic.setdefault(key, dict(name=name, ean=ean, price=price))
    return key


# ---------------------------------------------------------------- shifts, receipts, lines, payments
shift_rows = sorted(shifts, key=lambda s: s["Datum a čas otevření"])
for s in shift_rows:
    s["key"] = "smena_%s" % s["Datum a čas otevření"].strftime("%Y%m%d_%H%M%S")
    assert s["Datum a čas uzavření"], ("open shift, export after closing it", s["Datum a čas otevření"])


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
line_rows, rates = [], collections.Counter()
for l in sorted(lines, key=lambda l: l["Číslo daňového dokladu"]):
    name, ean = text(l["Produkt"]), first_ean(l["EAN"])
    rates[l["DPH"]] += 1
    line_rows.append((l["Číslo daňového dokladu"], resolve(name, ean, l["Jedn. prodejní cena s DPH"]), name,
                      "%g" % l["Prodané množství"], "%.2f" % l["Jedn. prodejní cena s DPH"],
                      "%.2f" % l["Prodejní cena bez DPH"], "%.2f" % l["Prodejní cena s DPH"], "%g" % l["DPH"]))
assert set(rates) == {21.0}, ("the import books every line at 21 %", rates)
write("polozky.csv", ["doklad", "produkt", "nazev", "mnozstvi", "cena_s_dph", "celkem_bez_dph", "celkem_s_dph",
                      "dph"], line_rows)

# ---------------------------------------------------------------- archived products new in this export
out = ['<?xml version="1.0" encoding="utf-8"?>', "<odoo>", '    <data noupdate="1">',
       "        <!-- Zboží z tohoto exportu, které v Dotykačce dnes není a modul elite_trafika_dotykacka ho",
       "             ještě nezaložil (smazané produkty a produkty prodávané pod jiným názvem). Je archivované:",
       "             v pokladně se nenabízí, jen drží historické prodeje. -->"]


def product_record(xmlid, name, price):
    return ['        <record id="%s" model="product.template">' % xmlid,
            '            <field name="name">%s</field>' % escape(name),
            '            <field name="type">consu</field>',
            '            <field name="list_price">%.2f</field>' % price,
            '            <field name="available_in_pos" eval="True"/>',
            '            <field name="categ_id" ref="%s.product_category_historie"/>' % HISTORY_MODULE,
            '            <field name="active" eval="False"/>', "        </record>"]


for pid, p in deleted_used.items():
    out += product_record("product_%s" % pid, text(p["name"]), float(p["priceWithVAT"]))
for key, h in historic.items():
    out += product_record(key, h["name"], h["price"])
out += ["    </data>", "</odoo>", ""]
with open(OUT + "/data/product_history_data.xml", "w") as f:
    f.write("\n".join(out))

total = sum(r["Celková hodnota dokladu"] for r in receipts)
print("shifts", len(shift_rows), "receipts", len(receipt_rows), "lines", len(line_rows), "payments",
      len(payment_rows), "total %.2f" % total)
print("first/last receipt", receipt_rows[0][0], receipt_rows[-1][0], receipt_rows[-1][1])
print("new archived products: deleted", len(deleted_used), "renamed", len(historic), "->",
      [h["name"] for h in historic.values()] + [text(p["name"]) for p in deleted_used.values()])
print("lines to archived products", sum(1 for r in line_rows if not r[1].startswith(POS_MODULE)))
