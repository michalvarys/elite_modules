"""Projde cely web krok za krokem a overi, ze to, co se zada v adminu,
se opravdu projevi na strance.

Nejde o cteni kodu, ale o skutecnou zkousku: skript zaznam zalozi, stahne
stranku, podiva se, jestli tam je, a pak ho zase smaze. Co po sobe zmeni,
to vraci zpatky.

Pousti se v kontejneru s Odoo:

    docker exec -i <kontejner> odoo shell -c /etc/odoo/odoo.conf -d <databaze> \
        --no-http < nasazeni/test-vseho.py
"""

import urllib.request
import re


def telo(html):
    """Stranka bez <style> a <script>, aby nazev tridy v kodu neplatil jako vyskyt.

    Drive se delilo podle posledniho </style>. Jakmile si vlastni styl
    zacala vozit i paticka, vracel helper pouze ji. Skripty se vyhazuji
    taky — tridy a komentare v JS na strance nikdo necte.
    """
    bez_stylu = re.sub(r"<style[\s\S]*?</style>", " ", html)
    return re.sub(r"<script[\s\S]*?</script>", " ", bez_stylu)

ZAKLAD = "http://localhost:8069"
JAZYKY = [("cs", "", "cs-CZ,cs", "cs-CZ"), ("de", "/de", "de-DE,de", "de-DE"),
          ("en", "/en", "en-US,en", "en-US"), ("ru", "/ru", "ru-RU,ru", "ru-RU")]
STRANKY = ["/", "/rezervacni-system", "/cenik", "/rozpis-lekaru", "/nas-tym", "/o-nas"]

vysledky = []


def krok(nazev, podminka, detail=""):
    vysledky.append((bool(podminka), nazev, detail))
    print("%s  %s%s" % ("OK  " if podminka else "CHYBA", nazev,
                        ("  — " + detail) if detail and not podminka else ""))


def stahni(cesta, hlavicka="cs-CZ,cs"):
    zadost = urllib.request.Request(ZAKLAD + cesta, headers={
        "Accept-Language": hlavicka, "Accept": "text/html"})
    with urllib.request.urlopen(zadost, timeout=30) as odpoved:
        return odpoved.read().decode("utf-8", "replace")


print("\n===== 1. STRANKY A JAZYKY =====")
for stranka in STRANKY:
    for kod, predpona, hlavicka, ocekavany in JAZYKY:
        cesta = predpona + (stranka if stranka != "/" else "/")
        try:
            html = stahni(cesta, hlavicka)
            jazyk = html.split('<html', 1)[1].split('lang="', 1)[1].split('"', 1)[0]
            krok("%-20s %s" % (stranka, kod), jazyk == ocekavany, "vratilo jazyk " + jazyk)
        except Exception as chyba:
            krok("%-20s %s" % (stranka, kod), False, str(chyba)[:60])

print("\n===== 2. ADMIN =====")
APLIKACE = {
    "Hlavní stránka": ["elite.vet.page.section", "elite.vet.service", "elite.vet.species",
                       "elite.vet.gallery.photo", "elite.vet.opening.hours",
                       "elite.vet.contact"],
    "Nastavení kontaktu": ["elite.vet.setting"],
    "Rozpis služeb": ["elite.vet.shift", "elite.vet.doctor", "elite.vet.shift.type",
                      "elite.vet.team.specialization", "elite.vet.team.icon"],
    "Náš tým": ["elite.vet.team.member", "elite.vet.team.section",
                "elite.vet.team.fact.label"],
    "Ceník": ["elite.vet.price.category"],
    "Rezervace": ["elite.vet.setting", "elite.vet.faq"],
}
Menu = env["ir.ui.menu"].with_context(lang="cs_CZ")
for aplikace, modely in APLIKACE.items():
    koren = Menu.search([("parent_id", "=", False), ("name", "=", aplikace)], limit=1)
    if not koren:
        krok("aplikace %s" % aplikace, False, "v nabidce neni")
        continue
    deti = Menu.search([("parent_id", "child_of", koren.id), ("id", "!=", koren.id)])
    nalezene = set()
    for d in deti:
        if not d.action:
            continue
        # okenni akce nese model v res_model, serverova (Nastaveni webu) v model_id
        model = getattr(d.action, "res_model", None)
        if not model and getattr(d.action, "model_id", None):
            model = d.action.model_id.model
        if model:
            nalezene.add(model)
    chybi = [m for m in modely if m not in nalezene]
    krok("aplikace %-14s (%s polozek)" % (aplikace, len(deti)), not chybi,
         "chybi " + ", ".join(chybi))

print("\n===== 3. SLUZBY =====")
Sluzba = env["elite.vet.service"]
pred = Sluzba.search_count([])
nova = Sluzba.create({"name": "ZKOUSKA sluzba", "description": "Docasny zaznam z testu",
                      "icon_code": "prevence", "sequence": 999})
env.cr.commit()
# Domovska stranka je staticka, seznam sluzeb ji uz neplni. Overuje se
# proto zalozeni zaznamu, ne jeho vykresleni.
html = stahni("/")
krok("sluzba se zalozila", bool(nova) and nova.name == "ZKOUSKA sluzba")
krok("staticka stranka se pridanim sluzby nezmenila", "ZKOUSKA sluzba" not in html,
     "nalezeno %sx" % html.count("ZKOUSKA sluzba"))
nova.active = False
env.cr.commit()
krok("vypnuta sluzba ze stranky zmizi", "ZKOUSKA sluzba" not in stahni("/"))
nova.unlink()
env.cr.commit()
krok("po smazani zustal puvodni pocet", Sluzba.search_count([]) == pred)

print("\n===== 4. GALERIE =====")
Foto = env["elite.vet.gallery.photo"]
pocet_fotek = Foto.search_count([])
vzor = Foto.search([], limit=1)
strany_pred = (pocet_fotek + 2) // 3
nova_fotka = Foto.create({"name": "ZKOUSKA fotka", "image": vzor.image, "sequence": 999})
env.cr.commit()
html = stahni("/")
strany_po = (pocet_fotek + 1 + 2) // 3
krok("staticka stranka se pridanim fotky nezmenila", "ZKOUSKA fotka" not in html,
     "v pasu %s" % html.count('class="ev-gal-item"'))
krok("pocet stran se prepocital na %s" % strany_po,
     ('id="ev-gal-s%s"' % strany_po) in html)
nova_fotka.unlink()
env.cr.commit()
html = stahni("/")
krok("po smazani je pas zpatky na %s fotkach" % pocet_fotek,
     html.count('class="ev-gal-item"') == pocet_fotek)
krok("a stran je zase %s" % strany_pred,
     ('id="ev-gal-s%s"' % (strany_pred + 1)) not in html)

print("\n===== 5. KOHO PRIJIMAME =====")
Druh = env["elite.vet.species"]
novy_druh = Druh.create({"name": "ZKOUSKA druh", "icon_code": "pes", "sequence": 999})
env.cr.commit()
# Druhy zvirat uz nevykresluje zadna stranka — zustavaji jako ciselnik.
krok("druh se zalozil", bool(novy_druh) and novy_druh.name == "ZKOUSKA druh")
novy_druh.unlink()
env.cr.commit()
krok("po smazani zmizel", "ZKOUSKA druh" not in stahni("/"))

print("\n===== 6. OTEVIRACI DOBA =====")
radek = env["elite.vet.opening.hours"].search([], limit=1)
puvodni_cas = {j: radek.with_context(lang=j).time_text for j in ("cs_CZ", "de_DE", "en_US", "ru_RU")}
puvodni_kratce = {j: radek.with_context(lang=j).time_short for j in ("cs_CZ", "de_DE", "en_US", "ru_RU")}
for jazyk in puvodni_cas:
    radek.with_context(lang=jazyk).time_text = "5:55 – 21:11"
    radek.with_context(lang=jazyk).time_short = "5–21"
env.cr.commit()
domu, rozpis, rezervace = stahni("/"), stahni("/rozpis-lekaru"), stahni("/rezervacni-system")
# Hodiny uz domovskou stranku neplni, zato dal ridi rozpis a rezervaci.
krok("doba se zmenila v rozpisu", "5:55 – 21:11" in rozpis or "5–21" in rozpis)
krok("doba se zmenila v rezervaci", "5:55 – 21:11" in rezervace)
krok("staticka domovska stranka se nezmenila", "5:55 – 21:11" not in domu)
krok("doba se zmenila na rozpisu", "5:55 – 21:11" in rozpis)
krok("doba se zmenila na rezervaci", "5:55 – 21:11" in rezervace)
for jazyk, hodnota in puvodni_cas.items():
    radek.with_context(lang=jazyk).time_text = hodnota
    radek.with_context(lang=jazyk).time_short = puvodni_kratce[jazyk]
env.cr.commit()
krok("doba se vratila do puvodniho stavu", "5:55" not in stahni("/"))

print("\n===== 7. KONTAKTY A NASTAVENI =====")
nastaveni = env["elite.vet.setting"].nastaveni()
puvodni_telefon = nastaveni.phone
puvodni_zobrazeni = nastaveni.phone_display
nastaveni.write({"phone": "+420111222333", "phone_display": "+420 111 222 333"})
env.cr.commit()
krok("telefon se zmenil na domovske strance", "+420111222333" in stahni("/"))
krok("telefon se zmenil na strance tymu", "+420111222333" in stahni("/nas-tym"))
krok("telefon se zmenil na ceniku", "+420111222333" in stahni("/cenik"))
nastaveni.write({"phone": puvodni_telefon, "phone_display": puvodni_zobrazeni})
env.cr.commit()
krok("telefon se vratil", "+420111222333" not in stahni("/"))

print("\n===== 8. POHOTOVOST 24/7 =====")
puvodni_stav = nastaveni.emergency_mode

# Rezim "hidden" je ten, kvuli kteremu reklamace vznikla: po lince nesmi na
# strance zustat ani stopa, jinak si ji klienti prectou jako uz bezici.
# telo() je tu nutne — nazvy trid zustavaji v CSS i kdyz se nic nevykresli.
nastaveni.emergency_mode = "hidden"
env.cr.commit()
viditelne = telo(stahni("/"))
krok("schovana: kolecko 24/7 na strance neni", "ev-fab247-wrap" not in viditelne)
krok("schovana: bublina 24/7 na strance neni", 'id="ev-coach"' not in viditelne)
krok("schovana: v hodinach neni zminka o lince", "ev-hours-emergency" not in viditelne)
# Zminka o 24/7 smi zustat, kdyz rika, ze pohotovost NEBEZI — presne to
# si klinika do banneru napsala. Hlida se, ze ji stranka neslibuje.
krok("schovana: stranka pohotovost neslibuje",
     "ev-coach-call" not in viditelne and "ev-fab247" not in viditelne)

nastaveni.emergency_mode = "soon"
env.cr.commit()
html = stahni("/")
krok("uz brzy: tlacitko Volat je sede a neklikaci",
     'class="ev-coach-call" disabled=' in html and 'ev-coach-call ev-coach-call--zive' not in html)
krok("uz brzy: kolecko 24/7 nevola", 'class="ev-fab247" role="img"' in html)
nastaveni.write({"emergency_mode": "live", "emergency_phone": "+420999888777"})
env.cr.commit()
html = stahni("/")
krok("zapnuta: tlacitko je zelene s odkazem", "ev-coach-call--zive" in html
     and "tel:+420999888777" in html)
krok("zapnuta: kolecko 24/7 vola", html.count("tel:+420999888777") >= 2)
nastaveni.write({"emergency_mode": puvodni_stav, "emergency_phone": puvodni_telefon})
env.cr.commit()
krok("pohotovost vracena do puvodniho stavu",
     env["elite.vet.setting"].nastaveni().emergency_mode == puvodni_stav)


print("\n===== 8b. TEXTY VYPNUTE POHOTOVOSTI =====")
# Dokud jsou pole prazdna, plati puvodni veta ze sablony — a ta je prelozena.
# Jakmile klinika neco napise, prebije ji to.
puvodni_texty = {p: nastaveni[p] for p in
                 ("emergency_mode", "emergency_off_button",
                  "emergency_off_text", "emergency_off_note")}
nastaveni.write({"emergency_mode": "soon", "emergency_off_button": False,
                 "emergency_off_text": False, "emergency_off_note": False})
env.cr.commit()

# Ocekavane vety vzaty z opravdu vykreslene stranky, ne z hlavy.
PUVODNI = {
    "cs-CZ,cs": ["Volat již brzy", "pohotovostní linku", "V blízké době plánujeme"],
    "de-DE,de": ["Anrufen demnächst", "Notfallnummer", "Öffnungszeiten"],
    "en-US,en": ["Call SOON", "emergency line", "opening hours"],
    "ru-RU,ru": ["Позвонить скоро", "линию", "часы"],
}
# Vetu pod hodinami kreslila sablona sekce Kontakt; ta je na domovske
# strance nove staticka, takze uz se tam neprojevi. Bublina a plovouci
# kolecko ale zustavaji dynamicke, takze u nich prelozeny text platit ma.
for jazyk, vety in PUVODNI.items():
    html = stahni("/", jazyk)
    krok("prazdna pole, %s: tlacitko ma prelozeny popis" % jazyk[:2],
         vety[0] in html, vety[0])

nastaveni.write({"emergency_off_button": "ZKOUSKA tlacitko",
                 "emergency_off_text": "ZKOUSKA bublina, momentalne mimo provoz.",
                 "emergency_off_note": "ZKOUSKA poznamka pod hodinami."})
env.cr.commit()
html = stahni("/")
# Sekce Kontakt je na domovske strance staticka, takze se do ni texty
# pohotovosti uz nepropisuji. Pole v adminu ale musi zustat — ridi vetu
# pod hodinami tam, kde ji sablona dal kresli.
krok("pole textu pohotovosti se ulozila",
     nastaveni.emergency_off_button == "ZKOUSKA tlacitko"
     and "ZKOUSKA bublina" in (nastaveni.emergency_off_text or "")
     and "ZKOUSKA poznamka" in (nastaveni.emergency_off_note or ""))
# Mlcet ma stranka az ve schovanem rezimu, ne v rezimu "uz brzy".
nastaveni.emergency_mode = "hidden"
env.cr.commit()
schovana = telo(stahni("/"))
krok("ve schovanem rezimu stranka pohotovost neslibuje",
     "ev-fab247-wrap" not in schovana and 'id="ev-coach"' not in schovana)
nastaveni.emergency_mode = "soon"
env.cr.commit()

nastaveni.emergency_mode = "live"
env.cr.commit()
krok("po zapnuti pohotovosti texty vypnute varianty zmizely", "ZKOUSKA" not in stahni("/"))

nastaveni.write(puvodni_texty)
env.cr.commit()
krok("texty vraceny do puvodniho stavu", "ZKOUSKA" not in stahni("/"))
print("\n===== 9. CASTE DOTAZY =====")
Dotaz = env["elite.vet.faq"]
novy_dotaz = Dotaz.create({"name": "ZKOUSKA dotaz", "answer": "<p>Docasna odpoved.</p>",
                           "sequence": 999})
env.cr.commit()
krok("dotaz je na strance rezervace", "ZKOUSKA dotaz" in stahni("/rezervacni-system"))
novy_dotaz.unlink()
env.cr.commit()
krok("po smazani zmizel", "ZKOUSKA dotaz" not in stahni("/rezervacni-system"))

print("\n===== 9b. TEXTY REZERVACE =====")
# Pole jsou prekladatelna, takze zapis plati jen pro jazyk, ve kterem se pise.
# Test proto zapisuje cesky a cesky i cte — jinak by porovnaval dva jazyky.
cesky = nastaveni.with_context(lang="cs_CZ")
puvodni_hlaska = cesky.booking_loading_title
puvodni_tlacitko = cesky.schedule_link_button
cesky.write({"booking_loading_title": "ZKOUSKA hlaska",
             "schedule_link_button": "ZKOUSKA tlacitko"})
env.cr.commit()
krok("hlaska pri nacitani jde zmenit z adminu",
     "ZKOUSKA hlaska" in stahni("/rezervacni-system"))
krok("stejna hlaska se propsala i na rozpis",
     "ZKOUSKA hlaska" in stahni("/rozpis-lekaru"))
krok("tlacitko na rozpis jde zmenit",
     "ZKOUSKA tlacitko" in stahni("/rezervacni-system"))
cesky.write({"booking_loading_title": puvodni_hlaska,
             "schedule_link_button": puvodni_tlacitko})
env.cr.commit()
krok("texty vraceny", "ZKOUSKA" not in stahni("/rezervacni-system"))
krok("nemcina zustala nedotcena",
     "Reservierungssystem" in stahni("/rezervacni-system", "de-DE,de"))

print("\n===== 9c. TRETI HLASKA POD REZERVACI =====")
# Treti hlaska lezi v prazdnem miste pod prvnimi dvema a je v nem vycentrovana.
# Ukazuje se na obou strankach, kde rezervacni system visi.
puvodni_treti = nastaveni.with_context(lang="cs_CZ").booking_loading_middle
nastaveni.with_context(lang="cs_CZ").booking_loading_middle = "ZKOUSKA treti hlaska."
env.cr.commit()
for cesta in ("/rezervacni-system", "/rozpis-lekaru"):
    html = stahni(cesta)
    krok("%s: treti hlaska je na strance" % cesta, "ZKOUSKA treti hlaska" in html)
    # Vychozi misto textu je POD rameckem rezervace: bez skriptu je stranka
    # spravne. Skript ho na dobu nacitani presune dovnitr a pak vrati zpatky.
    krok("%s: text lezi pod rameckem rezervace" % cesta,
         "zprava-misto" in html
         and html.index("zprava-misto") < html.index("ZKOUSKA treti hlaska"))
    krok("%s: presun ma zaskok, kdyby load nedorazil" % cesta,
         "setTimeout(dolu,20000)" in html)

nastaveni.with_context(lang="de_DE").booking_loading_middle = "ZKOUSKA dritte Meldung."
env.cr.commit()
krok("hlaska jde prelozit",
     "ZKOUSKA dritte Meldung" in stahni("/rezervacni-system", "de-DE,de"))

nastaveni.with_context(lang="cs_CZ").booking_loading_middle = False
nastaveni.with_context(lang="de_DE").booking_loading_middle = False
env.cr.commit()
krok("prazdne pole = zadny text navic",
     "nacitani-zprava" not in stahni("/rezervacni-system").split("</style>")[-1])

nastaveni.with_context(lang="cs_CZ").booking_loading_middle = puvodni_treti or False
env.cr.commit()
krok("hlaska vracena do puvodniho stavu",
     (nastaveni.with_context(lang="cs_CZ").booking_loading_middle or "") == (puvodni_treti or ""))


print("\n===== 10. CENIK =====")
Cena = env["elite.vet.price.item"]
novy_ukon = Cena.create({"name": "ZKOUSKA ukon", "price": "1 Kč", "icon_code": "kocka",
                         "sequence": 999})
env.cr.commit()
html = stahni("/cenik")
krok("ukon je na ceniku", "ZKOUSKA ukon" in html)
krok("i s cenou", "1 Kč" in html)
novy_ukon.unlink()
env.cr.commit()
krok("po smazani zmizel", "ZKOUSKA ukon" not in stahni("/cenik"))

print("\n===== 10b. SEKCE CENIKU =====")
# Cely cenik je vypis sekci. Jedna sekce = stitek, nadpis, popisek, obrazek,
# tabulka ukonu a komentar pod ni — vsechno na jednom formulari v adminu.
# Prvni sekce dela zaroven hlavicku stranky.
Sekce = env["elite.vet.price.category"]
Ukon = env["elite.vet.price.item"]


cenik = stahni("/cenik")
prvni = Sekce.search([], limit=1)
krok("prvni sekce dela hlavicku stranky",
     bool(prvni) and (prvni.with_context(lang="cs_CZ").name or "") in cenik)
# Stitek je nepovinny, takze si ho zkouska nastavi sama a zase ho vrati.
puvodni_stitek = prvni.with_context(lang="cs_CZ").badge
prvni.with_context(lang="cs_CZ").badge = "ZKOUSKA stitek hlavicky"
env.cr.commit()
krok("stitek se ukaze na strance", "ZKOUSKA stitek hlavicky" in stahni("/cenik"))
prvni.with_context(lang="cs_CZ").badge = puvodni_stitek or False
env.cr.commit()
krok("prazdny stitek se nevykresli",
     bool(puvodni_stitek) or "ZKOUSKA stitek" not in stahni("/cenik"))
krok("nadpis je prelozeny do nemciny",
     (prvni.with_context(lang="de_DE").name or "") in stahni("/cenik", "de-DE,de"))
krok("stitek je prelozeny do rustiny",
     not prvni.badge
     or (prvni.with_context(lang="ru_RU").badge or "") in stahni("/cenik", "ru-RU,ru"))
krok("zadny ukon nezustal mimo sekce",
     Ukon.search_count([("category_id", "=", False)]) == 0)

radku_pred = cenik.count('class="ev-cen-row"')
ramecku_pred = telo(cenik).count('class="ev-cen-note"')

# cela nova sekce: stitek, nadpis, popisek, ukon, komentar
nova = Sekce.create({"name": "ZKOUSKA sekce", "sequence": 90})
nova.with_context(lang="cs_CZ").badge = "ZKOUSKA stitek"
nova.with_context(lang="cs_CZ").description = "ZKOUSKA popisek sekce."
nova.with_context(lang="cs_CZ").comment = "<p>ZKOUSKA komentar pod sekci.</p>"
presunuty = Ukon.search([], limit=1)
puvodni_sekce = presunuty.category_id
presunuty.category_id = nova.id
env.cr.commit()

html = stahni("/cenik")
krok("stitek nove sekce", "ZKOUSKA stitek" in html)
krok("nadpis nove sekce", "ZKOUSKA sekce" in html)
krok("popisek pod nadpisem", "ZKOUSKA popisek sekce" in html
     and html.index("ZKOUSKA sekce") < html.index("ZKOUSKA popisek sekce"))
krok("komentar je pod tabulkou", "ZKOUSKA komentar" in html
     and html.index("ZKOUSKA popisek sekce") < html.index("ZKOUSKA komentar"))
krok("rozdelenim se zadny ukon neztratil",
     html.count('class="ev-cen-row"') == radku_pred,
     "pred %s, po %s" % (radku_pred, html.count('class="ev-cen-row"')))
krok("komentarovy ramecek pribyl",
     telo(html).count('class="ev-cen-note"') == ramecku_pred + 1)

# obrazek sekce
PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
nova.image = PNG
nova.with_context(lang="cs_CZ").image_alt = "ZKOUSKA fotka"
env.cr.commit()
s_obrazkem = stahni("/cenik")
krok("nahrany obrazek se vykresli",
     "ev-cen-foto" in telo(s_obrazkem) and "ZKOUSKA fotka" in s_obrazkem)
nova.image = False
env.cr.commit()
krok("smazany obrazek ze stranky zmizel", "ev-cen-foto" not in telo(stahni("/cenik")))

# prazdny komentar nesmi nechat prazdny ramecek
nova.with_context(lang="cs_CZ").comment = False
env.cr.commit()
krok("prazdny komentar = zadny ramecek",
     telo(stahni("/cenik")).count('class="ev-cen-note"') == ramecku_pred)

# klinika se do sekce musi dostat i bez vyvojarskeho rezimu
seznam = env.ref("elite_vet_web.view_price_category_list")
krok("seznam sekci neni inline editovatelny", "editable=" not in seznam.arch)
formular = env.ref("elite_vet_web.view_price_category_form", raise_if_not_found=False)
krok("sekce ma vlastni formular", bool(formular))
krok("na jednom formulari je vsech sest casti",
     bool(formular) and all(('name="%s"' % p) in formular.arch for p in
                            ("badge", "name", "description", "image", "item_ids", "comment")))
polozky_ceniku = env.ref("elite_vet_web.menu_price_root").child_id
krok("cenik ma v nabidce jedinou polozku", len(polozky_ceniku) == 1,
     ", ".join(polozky_ceniku.mapped("name")))

presunuty.category_id = puvodni_sekce.id if puvodni_sekce else False
nova.unlink()
env.cr.commit()
po = stahni("/cenik")
krok("zkusebni sekce uklizena", "ZKOUSKA" not in po)
krok("cenik je zpatky jak byl",
     po.count('class="ev-cen-row"') == radku_pred
     and telo(po).count('class="ev-cen-note"') == ramecku_pred)


print("\n===== 11. STRANKA ZE STAVEBNICH BLOKU =====")
# Domovska stranka uz nevznika smyckou pres seznam v adminu. Zonu, ve ktere
# se obsah generuje (t-foreach i t-call), Odoo neoznaci jako editovatelnou
# a sekce v ni nejde mazat ani prehazovat — overeno v prohlizeci. Bloky proto
# lezi v zone primo.
html = stahni("/")
krok("stranka ma editovatelnou zonu",
     'id="oe_structure_homepage"' in html and "oe_structure" in html)

BLOKY = ("s_vet_letak", "s_vet_note", "s_vet_objednat", "s_vet_o_klinice", "s_vet_sluzby", "s_vet_tym", "s_vet_kontakt")
for blok in BLOKY:
    krok("blok %s je na strance" % blok, 'class="%s' % blok in html)

# Poradi se zamerne nekontroluje: bloky jdou v editoru prehazovat a jakmile
# klinika stranku ulozi, plati jeji poradi, ne to z modulu.
krok("stranka obsahuje vsechny bloky",
     all('class="%s' % b in html for b in BLOKY))

# Sablony zustavaji v modulu, aby slo smazany blok vratit z panelu.
Pohled = env["ir.ui.view"].sudo()
chybejici = [b for b in BLOKY
             if not Pohled.search_count([("key", "=", "elite_vet_theme." + b)])]
krok("vsechny bloky jsou i v panelu %s" % (chybejici or ""), not chybejici)
krok("bloky jsou zaregistrovane v editoru",
     bool(Pohled.search_count([("key", "=", "elite_vet_theme.ev_snippets_registry")])))

# Oznamovaci pruh: blok do nej klinika pise aktuality a barvu prepina
# v bocnim panelu. Volba je vlastni pohled dedici po website.snippet_options.
krok("oznamovaci pruh je zaregistrovany",
     bool(Pohled.search_count([("key", "=", "elite_vet_theme.s_vet_oznameni")])))
volby = Pohled.search([("key", "=", "elite_vet_theme.snippet_options_vet_oznameni")])
krok("prepinac barvy pruhu je v panelu voleb",
     bool(volby) and volby.active and volby.inherit_id.key == "website.snippet_options")
arch_voleb = volby.arch_db if volby else ""
if isinstance(arch_voleb, dict):
    arch_voleb = arch_voleb.get("en_US", "")
chybejici_barvy = [b for b in ("ev-oznam--info", "ev-oznam--uspech", "ev-oznam--pozor",
                               "ev-oznam--dulezite", "ev-oznam--tmavy")
                   if b not in arch_voleb]
krok("pruh nabizi vsechny barvy %s" % (chybejici_barvy or ""), not chybejici_barvy)

# Tecka i linky beru barvu z teze promenne, takze jeden vyber prebarvi oboji.
krok("pruh ma vyber barvy tecky a linek",
     "--oznam-cara" in arch_voleb)
krok("pruh ma vyber barvy pozadi",
     "--oznam-pozadi" in arch_voleb)
krok("linky nad a pod pruhem jdou vypnout",
     "ev-oznam--bez-car" in arch_voleb)
krok("tecka jde schovat", "ev-oznam--bez-tecky" in arch_voleb)

# Blok Nadpis: stitek a nadpis, zarovnani a schovani stitku v bocnim panelu.
krok("blok Nadpis je zaregistrovany",
     bool(Pohled.search_count([("key", "=", "elite_vet_theme.s_vet_nadpis")])))
volby_nadpis = Pohled.search([("key", "=", "elite_vet_theme.snippet_options_vet_nadpis")])
arch_nadpis = volby_nadpis.arch_db if volby_nadpis else ""
if isinstance(arch_nadpis, dict):
    arch_nadpis = arch_nadpis.get("en_US", "")
krok("Nadpis ma volbu zarovnani", "ev-nadpis--vlevo" in arch_nadpis)
krok("u Nadpisu jde schovat stitek", "ev-nadpis--bez-stitku" in arch_nadpis)

# Spodni prouzek paticky na webu nikdy nebyl.
krok("paticka nema spodni prouzek s jazyky",
     "ev-footer-bottom" not in stahni("/"))
print("\n===== 12. REZERVACE A ROZPIS =====")
rezervace = stahni("/rezervacni-system")
krok("kolecko nacitani je pod rameckem", "evrez-spinner" in rezervace)
krok("tlacitko na rozpis je nad castymi dotazy",
     "evrez-rozpis-btn" in rezervace
     and rezervace.index("evrez-rozpis-lead") < rezervace.index('class="ev-faq-list"'))
rozpis = stahni("/rozpis-lekaru")
krok("na rozpisu je legenda specializaci", "rs-leg" in rozpis)
# Smajlik se ukaze jen u lekarky, ktera ma specializaci a zrovna slouzi.
# Obojí si zkouska zaridi sama, at nestoji na tom, co je zrovna v rozpisu,
# a po sobe to zase uklidi.
import datetime

Smena = env["elite.vet.shift"]
Lekarka = env["elite.vet.doctor"]
typ_smeny = env["elite.vet.shift.type"].search([("is_note", "=", False)], limit=1)
specializace = env["elite.vet.team.specialization"].search([("icon_id", "!=", False)], limit=1)
lekarka = Lekarka.search([("specialization_ids", "!=", False)], limit=1)
pridana_specializace = False
if not lekarka and specializace:
    lekarka = Lekarka.search([("member_id", "!=", False)], limit=1)
    lekarka.member_id.specialization_ids = [(4, specializace.id)]
    pridana_specializace = True

if not lekarka or not typ_smeny or not specializace:
    krok("smajlik stoji pred jmenem", False,
         "v databazi chybi lekarka, typ smeny nebo specializace s ikonou")
else:
    zkusebni_smena = Smena.create({"date": datetime.date.today(),
                                   "doctor_id": lekarka.id,
                                   "type_id": typ_smeny.id})
    env.cr.commit()
    rozpis = stahni("/rozpis-lekaru")
    bunky = [b for b in rozpis.split('<span class="rs-doc">')[1:] if "rs-specs" in b]
    krok("smajlik stoji pred jmenem", bool(bunky) and all(
         b.index("rs-specs") < b.index(lekarka.name) for b in bunky if lekarka.name in b),
         "bunek se smajlikem: %s" % len(bunky))
    zkusebni_smena.unlink()
    if pridana_specializace:
        lekarka.member_id.specialization_ids = [(3, specializace.id)]
    env.cr.commit()
    krok("zkusebni smena i specializace uklizeny",
         not Smena.search_count([("id", "=", zkusebni_smena.id)])
         and (not pridana_specializace or not lekarka.specialization_ids))
krok("mesic je cesky", "Září" in rozpis or "Říjen" in rozpis)
krok("mesic je nemecky", "September" in stahni("/rozpis-lekaru", "de-DE,de")
     or "Oktober" in stahni("/rozpis-lekaru", "de-DE,de"))

print("\n===== 12b. DVE LEKARKY NA JEDNE SMENE =====")
Smena = env["elite.vet.shift"]
vzor = Smena.search([], limit=1, order="date")
druha = env["elite.vet.doctor"].search([("id", "!=", vzor.doctor_id.id)], limit=1)
zkusebni = Smena.create({"date": vzor.date, "type_id": vzor.type_id.id,
                         "doctor_id": druha.id})
env.cr.commit()
rozpis = stahni("/rozpis-lekaru")
krok("obe lekarky jsou na strance",
     vzor.doctor_id.name in rozpis and druha.name in rozpis)
krok("jmena jsou spojena plusem", " + " in rozpis)
# smena se ma vypsat jednou na skupinu, ne u kazde lekarky zvlast
bunka = rozpis[rozpis.find(druha.name) - 500:rozpis.find(druha.name) + 300]
nazev_smeny = vzor.type_id.with_context(lang="cs_CZ").name
krok("smena je v bunce uvedena jednou", bunka.count(nazev_smeny) == 1,
     "nalezeno %sx" % bunka.count(nazev_smeny))
zkusebni.unlink()
env.cr.commit()
krok("zkusebni smena uklizena",
     Smena.search_count([("date", "=", vzor.date), ("doctor_id", "=", druha.id)]) == 0)

print("\n===== 13. OBRAZKY A ODKAZY =====")
html = stahni("/")
chybne = []
for cast in html.split('src="')[1:]:
    adresa = cast.split('"', 1)[0]
    if not adresa.startswith("/elite_vet_web/static"):
        continue
    try:
        with urllib.request.urlopen(ZAKLAD + adresa, timeout=20) as odpoved:
            if odpoved.status != 200:
                chybne.append(adresa)
    except Exception:
        chybne.append(adresa)
krok("staticke obrazky se servuji", not chybne, ", ".join(chybne[:3]))
for polozka in env["website.menu"].search([("parent_id", "!=", False)]):
    pass
mimo = env["website.menu"].search([("url", "like", "winvet")])
krok("zadna polozka menu nevede mimo web", not mimo,
     ", ".join(mimo.mapped("url"))[:60])


print("\n===== 14. NIC NEPROSAKUJE NA CIZI WEBY =====")
# Databaze hostuje vic webu (Arena, trafika, Jack, IMI). Stranka bez prirazeneho
# webu je v Odoo "obecna" a vykresli se na vsech domenach — presne to se uz
# jednou stalo a rozpis sluzeb visel i tam, kam nepatri.
pocet_webu = env["website"].search_count([])
print("webu v databazi: %s" % pocet_webu)

for xml_id in ("elite_vet_web.rezervace_page", "elite_vet_web.cenik_page",
               "elite_vet_calendar.rozpis_lekaru_page", "elite_vet_team.nas_tym_page"):
    stranka = env.ref(xml_id, raise_if_not_found=False)
    krok("stranka %s patri jednomu webu" % (stranka.url if stranka else xml_id),
         bool(stranka and stranka.website_id))

obecne_menu = env["website.menu"].search([
    ("url", "in", ["/rozpis-lekaru", "/nas-tym", "/cenik", "/rezervacni-system"]),
    ("website_id", "=", False)])
krok("zadna polozka menu kliniky neni obecna",
     not obecne_menu, ", ".join(obecne_menu.mapped("url")))

if pocet_webu > 1:
    # Obecna homepage patri vsem webum, takze na ni sablona kliniky nesmi.
    obecna_domu = env["website.page"].search([("url", "=", "/"), ("website_id", "=", False)])
    krok("obecna homepage neukazuje na sablonu kliniky",
         not obecna_domu or obecna_domu.view_id.key != "elite_vet_web.homepage")
else:
    krok("jediny web v databazi, obecna homepage je v poradku", True)

print("\n===== 15. PREPINAC JAZYKU =====")
# Prepinac vede primo na jazykovou adresu. Pres /website/lang/ to stalo na cookie
# frontend_lang a in-app prohlizec Instagramu a Facebooku ho neposila tak, jak
# Odoo ceka — klik na jazyk skoncil zpatky na puvodni strance.
import re

for cesta in ("/", "/de", "/en", "/ru", "/de/cenik", "/ru/rozpis-lekaru", "/en/nas-tym"):
    html = stahni(cesta)
    # Panel se useka na svem </div>. Pevnych 600 znaku zasahovalo i odkazy
    # za nim, takze test hlasil o jeden jazyk navic.
    zacatek = html.find('class="ev-lang-panel"')
    panel = html[zacatek:html.find("</div>", zacatek)] if zacatek > -1 else ""
    odkazy = re.findall(r'href="([^"]*)"', panel)
    krok("%s: prepinac ma vsechny ctyri jazyky" % cesta, len(odkazy) == 4,
         "nalezeno %s" % len(odkazy))
    krok("%s: zadny odkaz neni prazdny" % cesta,
         bool(odkazy) and all(o.strip() for o in odkazy), str(odkazy))
    krok("%s: nejde pres /website/lang/" % cesta,
         not any("website/lang" in o for o in odkazy), str(odkazy))

# Klik na jazyk opravdu prepne, i kdyz prohlizec neposila Accept-Language.
import urllib.request
import re


def telo(html):
    """Stranka bez vsech <style>, aby nazev tridy v CSS neplatil jako vyskyt.

    Drive se delilo podle posledniho </style>. Jakmile si vlastni styl
    zacala vozit i paticka, vracel helper pouze ji.
    """
    return re.sub(r"<style[\s\S]*?</style>", " ", html)
import http.cookiejar

def prejdi(kroky):
    """Projde adresy se sdilenymi cookies a vrati <html lang> te posledni."""
    cookies = http.cookiejar.CookieJar()
    otevirac = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))
    html = ""
    for cesta in kroky:
        with otevirac.open(ZAKLAD + cesta, timeout=30) as odpoved:
            html = odpoved.read().decode("utf-8", "replace")
    nalez = re.search(r'<html[^>]*lang="([^"]+)"', html)
    return nalez.group(1) if nalez else "?"

for start, cil, ocekavano in (("/de", "/cs", "cs-CZ"), ("/en", "/cs", "cs-CZ"),
                              ("/ru", "/cs", "cs-CZ"), ("/", "/de", "de-DE"),
                              ("/de", "/ru", "ru-RU")):
    mam = prejdi([start, cil])
    krok("z %s na %s prepne na %s" % (start, cil, ocekavano), mam == ocekavano, mam)

print("\n===== 16. SEO TITULEK A POPIS =====")
# Odoo bere meta popis ze zaznamu stranky, ne z <t t-set="meta_description">
# v sablone — ten tise ignoruje. Stranky proto dlouho zadny popis nemely.
import re

for cesta, jazyk, znacka in (("/", "cs-CZ,cs", "cs"), ("/de/", "de-DE,de", "de"),
                             ("/en/", "en-US,en", "en"), ("/ru/", "ru-RU,ru", "ru"),
                             ("/cenik", "cs-CZ,cs", "cs"), ("/de/cenik", "de-DE,de", "de"),
                             ("/ru/rozpis-lekaru", "ru-RU,ru", "ru"),
                             ("/en/nas-tym", "en-US,en", "en")):
    html = stahni(cesta, jazyk)
    titulek = (re.search(r"<title>([^<]*)</title>", html) or [None, ""])[1]
    popis = (re.search(r'<meta name="description" content="([^"]*)"', html) or [None, ""])[1]
    krok("%s (%s): ma titulek" % (cesta, znacka), bool(titulek.strip()), titulek[:60])
    krok("%s (%s): ma meta popis" % (cesta, znacka), len(popis.strip()) > 40, popis[:60])
    if znacka == "ru":
        krok("%s: popis je v azbuce" % cesta,
             any("\u0400" <= z <= "\u04ff" for z in popis), popis[:60])
    if znacka == "de":
        krok("%s: popis neni cesky" % cesta,
             "služb" not in popis.lower() and "lékař" not in popis.lower(), popis[:60])

print("\n===== 17. STRANKA O NAS =====")
# Stranka je poskladana z bloku a prepisuje se primo v editoru. Zaznam
# v adminu byl zrusen, protoze uz nic neridil — testuje se tedy stranka,
# ne model.
o_nas = stahni("/o-nas")
krok("stranka /o-nas existuje", "<h1" in o_nas)
krok("ma editovatelnou zonu", 'id="oe_structure_o_nas"' in o_nas)
krok("zona je uloziteľna (id obsahuje oe_structure)",
     'id="oe_structure_o_nas" class="oe_structure"' in o_nas)
krok("obsah stranky zustal",
     "Vybudovali jsme pro vás moderní veterinární kliniku" in o_nas)
krok("lista je prelozena, ne anglicka", "Kontakt" in telo(o_nas))

# Video je blok Odoo, takze se adresa meni v bocnim panelu editoru.
krok("video je blok Odoo", "media_iframe_video" in o_nas)
krok("blok videa ma adresu", "youtube.com/embed/" in o_nas)

# Preklady: stranka musi chodit ve vsech ctyrech jazycich.
for zkratka, hlavicka, cekany in (("de", "de-DE,de", "Über uns"),
                                  ("en", "en-US,en", "About us"),
                                  ("ru", "ru-RU,ru", "О нас")):
    html = stahni("/o-nas", hlavicka)
    krok("/%s/o-nas ma prelozeny nadpis" % zkratka, cekany in html, cekany)

# model po zruseni nesmi zustat viset
krok("zaznam v adminu uz neexistuje", "elite.vet.about" not in env)

# stranka nesmi viset na cizich webech
krok("stranka patri jednomu webu", bool(env.ref("elite_vet_web.o_nas_page").website_id))
polozka = env["website.menu"].search([("url", "=", "/o-nas")], limit=1)
krok("odkaz v menu je prelozeny",
     bool(polozka) and polozka.with_context(lang="de_DE").name == "Über uns",
     polozka.with_context(lang="de_DE").name if polozka else "chybi")

print("\n===== SHRNUTI =====")
prosle = sum(1 for ok, _, _ in vysledky if ok)
print("proslo %s z %s kontrol" % (prosle, len(vysledky)))
for ok, nazev, detail in vysledky:
    if not ok:
        print("  CHYBA: %s — %s" % (nazev, detail))
