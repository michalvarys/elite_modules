"""Kontrola účtu s rolí „WinVet data → Jen čtení (API)“ přes API Odoo (XML-RPC).

Ověří, že účet čte všechna data z WinVetu a že na nich nemá žádné právo zápisu, vytvoření
ani mazání. Nic nezapisuje: na práva se jen ptá (`has_access`), takže ani špatně
nastavený účet tím nic nezmění.

Spouští se na vlastním počítači (stačí Python 3), heslo nebo API klíč se zadává skrytě:

    python3 kontrola-uctu-jen-cteni.py https://www.elite-vet.cz slavek [databáze]

Bez dotazu (např. pro agenta): proměnná prostředí ODOO_SECRET. Databázi není třeba uvádět, když ji server vypíše sám (jediná databáze).
"""
import getpass
import os
import sys
import xmlrpc.client
from datetime import date

#: (model, popis) – všechno, co posílá most z WinVetu; chybějící modul se přeskočí
DATA_MODELS = [
    ("res.partner", "majitelé"), ("elite.vet.pet", "pacienti"), ("elite.vet.visit", "návštěvy"),
    ("elite.vet.visit.vital", "vitální hodnoty"), ("elite.vet.vaccination", "očkování"),
    ("elite.vet.sale.document", "doklady"), ("elite.vet.sale.line", "položky tržeb"),
    ("elite.vet.payment", "platby"), ("elite.vet.deposit", "zálohy"), ("elite.vet.deposit.use", "čerpání záloh"),
    ("elite.vet.expense", "výdaje"), ("elite.vet.expense.category", "kategorie výdajů"),
    ("elite.vet.winvet.item", "ceník"), ("elite.vet.winvet.user", "uživatelé WinVetu"),
    ("elite.vet.winvet.contact", "kontakty"), ("elite.vet.winvet.calendar.event", "kalendář WinVetu"),
    ("elite.vet.winvet.calendar.resource", "kalendáře → ordinace"),
    ("elite.vet.winvet.calendar.activity", "činnosti → úkony"), ("elite.vet.winvet.status", "stav synchronizace"),
    ("elite.vet.winvet.status.entity", "stav po entitách"), ("elite.vet.winvet.schema.change", "změny struktury"),
    ("elite.vet.winvet.stock.layer", "sklad – šarže"), ("elite.vet.winvet.stock.total", "sklad – stavy"),
    ("elite.vet.procedure.bundle", "balíčky úkonů"), ("elite.vet.procedure.bundle.line", "řádky balíčků"),
    ("elite.vet.text.template", "fráze"),
]
#: musí zůstat skryté (API klíč mostu, log běhů)
HIDDEN_MODELS = ["elite.vet.winvet.config", "elite.vet.winvet.run"]
#: role, které smí zapisovat – účet je mít nesmí
WRITER_GROUPS = ["elite_vet_reservation.group_reservation_reception",
                 "elite_vet_reservation.group_reservation_manager", "base.group_system", "base.group_erp_manager"]

problems = []


def report(ok, text):
    print(("  OK     " if ok else "  CHYBA  ") + text)
    if not ok:
        problems.append(text)


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    url, login = sys.argv[1].rstrip("/"), sys.argv[2]
    common = xmlrpc.client.ServerProxy(url + "/xmlrpc/2/common", allow_none=True)
    database = sys.argv[3] if len(sys.argv) > 3 else None
    if not database:
        try:
            databases = xmlrpc.client.ServerProxy(url + "/xmlrpc/2/db").list()
        except xmlrpc.client.Fault:
            databases = []
        if len(databases) != 1:
            sys.exit("Uveďte databázi jako třetí parametr (server vypsal: %s)." % (databases or "nic"))
        database = databases[0]
    secret = os.environ.get("ODOO_SECRET") or getpass.getpass("Heslo nebo API klíč pro %s: " % login)
    uid = common.authenticate(database, login, secret, {})
    if not uid:
        sys.exit("Přihlášení se nepovedlo (databáze %s, účet %s)." % (database, login))
    models = xmlrpc.client.ServerProxy(url + "/xmlrpc/2/object", allow_none=True)

    def call(model, method, *args, **kwargs):
        return models.execute_kw(database, uid, secret, model, method, list(args), kwargs)

    print("Odoo %s, databáze %s, účet %s (id %s)\n" % (common.version()["server_version"], database, login, uid))

    print("Role účtu")
    for xmlid in ["elite_vet_winvet.group_winvet_readonly"] + WRITER_GROUPS:
        has = call("res.users", "has_group", [uid], xmlid)
        if xmlid == "elite_vet_winvet.group_winvet_readonly":
            report(has, "má roli WinVet data → Jen čtení (API)")
        else:
            report(not has, "nemá roli %s" % xmlid)

    print("\nData z WinVetu (čtení ano, zápis / vytvoření / mazání ne)")
    for model, label in DATA_MODELS:
        try:
            readable = call(model, "has_access", [], "read")
        except xmlrpc.client.Fault as error:
            if "doesn't exist" in error.faultString or "does not exist" in error.faultString:
                print("  –      %s (%s): modul není nainstalovaný" % (label, model))
                continue
            report(False, "%s (%s): %s" % (label, model, error.faultString.strip().splitlines()[-1]))
            continue
        writable = [op for op in ("write", "create", "unlink") if call(model, "has_access", [], op)]
        count = call(model, "search_count", []) if readable else 0
        report(readable and not writable, "%s (%s): %s záznamů%s" % (
            label, model, count, ", smí %s" % "/".join(writable) if writable else "") if readable
            else "%s (%s): nečte" % (label, model))

    print("\nSkryté")
    for model in HIDDEN_MODELS:
        try:
            readable = call(model, "has_access", [], "read")
        except xmlrpc.client.Fault:
            readable = False
        report(not readable, "%s nečte" % model)

    print("\nUkázkové čtení")
    try:
        partners = call("res.partner", "search_read", [("winvet_ref", "!=", False)], ["name"], limit=1)
        report(True, "majitel: %s" % (partners[0]["name"] if partners else "(žádný)"))
    except xmlrpc.client.Fault as error:
        report(False, "majitelé: %s" % error.faultString.strip().splitlines()[-1])
    today = date.today()
    first = today.replace(day=1).isoformat()
    for model, method, args, label in [
            ("elite.vet.winvet.dashboard", "get_data", [first, today.isoformat()], "přehled tržeb"),
            ("elite.vet.cash.closure", "closure_data", [first, today.isoformat()], "uzávěrka jako data")]:
        try:
            data = call(model, method, *args)
            extra = " – tržby %s Kč" % data["sales_total"] if "sales_total" in data else ""
            report(bool(data), "%s od %s%s" % (label, first, extra))
        except xmlrpc.client.Fault as error:
            report(False, "%s: %s" % (label, error.faultString.strip().splitlines()[-1]))

    print("\n" + ("Vše v pořádku." if not problems else "Problémy: %d" % len(problems)))
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
