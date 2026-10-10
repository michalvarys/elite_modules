# -*- coding: utf-8 -*-
"""Overi, ze stranky nespadnou, kdyz nastaveni webu neexistuje.

Prave na tom spadlo nasazeni: ev_web bylo None a kazde ev_web.neco shodilo
stranku na 500. Zkouska docasne smaze zaznam nastaveni a projde vsechny
stranky; potom ho vrati.
"""
import urllib.request

STRANKY = ["/", "/o-nas", "/cenik", "/nas-tym", "/rozpis-lekaru", "/rezervacni-system"]
ZAKLAD = "http://localhost:8069"


def kod(cesta):
    zadost = urllib.request.Request(ZAKLAD + cesta,
                                    headers={"Accept-Language": "cs-CZ,cs"})
    try:
        with urllib.request.urlopen(zadost) as odpoved:
            return odpoved.status
    except urllib.error.HTTPError as chyba:
        return chyba.code


Nastaveni = env["elite.vet.setting"].sudo()
zaznam = Nastaveni.search([], limit=1)
zaloha = {p: zaznam[p] for p in zaznam._fields
          if not zaznam._fields[p].compute and p not in ("id", "create_date",
                                                         "write_date", "create_uid",
                                                         "write_uid", "display_name")}

print("mazu nastaveni webu (docasne)")
zaznam.unlink()
env.cr.commit()

print()
vsechny_ok = True
for cesta in STRANKY:
    k = kod(cesta)
    if k != 200:
        vsechny_ok = False
    print("  %-22s %s" % (cesta, k))

print()
# nastaveni() zaznam zalozi znovu, kdyz zadny neni
novy = Nastaveni.nastaveni()
novy.write({k: v for k, v in zaloha.items() if v not in (None, False) or k.endswith("_url")})
env.cr.commit()
print("nastaveni vraceno, id =", novy.id)

print()
print("ZAVER:", "stranky prezily i bez nastaveni" if vsechny_ok
      else "NEKTERA STRANKA SPADLA")
