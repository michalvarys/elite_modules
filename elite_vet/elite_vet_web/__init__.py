import logging

_logger = logging.getLogger(__name__)

from . import models


# Sluzby, se kterymi klinika startuje. Zaklada se jen pri prvni instalaci —
# od te chvile patri klinice a upgrade modulu do nich uz nesaha.
# Zdroj je anglicky, cestina a dalsi jazyky se dopisuji jako preklad; kdyby se
# zakladalo cesky, anglicky preklad by prepsal zdroj a cestina by ho zdedila.
VYCHOZI_SLUZBY = [
    {
        "kod": "prevence",
        "poradi": 10,
        "en": ("Preventive care",
               "Regular check-ups, vaccinations and deworming. Prevention is the foundation of your pet's health."),
        "cs": ("Preventivní péče",
               "Pravidelné prohlídky, vakcinace a odčervení. Prevence je základ zdraví vašeho mazlíčka."),
        "de": ("Präventivpflege",
               "Regelmäßige Untersuchungen, Impfungen und Entwurmung. Vorsorge ist die Grundlage der Gesundheit Ihres Tieres."),
        "ru": ("Профилактический уход",
               "Регулярные осмотры, вакцинация и дегельминтизация. Профилактика — основа здоровья вашего питомца."),
    },
    {
        "kod": "chirurgie",
        "poradi": 20,
        "en": ("Surgery",
               "Neutering and abdominal procedures. A modern operating theatre with anaesthesia monitoring."),
        "cs": ("Chirurgie",
               "Kastrační a abdominální zákroky. Moderní operační sál s anesteziologickým monitoringem."),
        "de": ("Chirurgie",
               "Kastrationen und abdominale Eingriffe. Moderner Operationssaal mit Anästhesie-Monitoring."),
        "ru": ("Хирургия",
               "Кастрация и абдоминальные вмешательства. Современная операционная с анестезиологическим мониторингом."),
    },
    {
        "kod": "interni",
        "poradi": 30,
        "en": ("Internal medicine",
               "Diagnosis and treatment of internal diseases, cardiology, endocrinology and gastroenterology."),
        "cs": ("Interní medicína",
               "Diagnostika a léčba vnitřních onemocnění, kardiologie, endokrinologie a gastroenterologie."),
        "de": ("Innere Medizin",
               "Diagnose und Behandlung innerer Erkrankungen, Kardiologie, Endokrinologie und Gastroenterologie."),
        "ru": ("Внутренние болезни",
               "Диагностика и лечение внутренних заболеваний, кардиология, эндокринология и гастроэнтерология."),
    },
    {
        "kod": "diagnostika",
        "poradi": 40,
        "en": ("Diagnostics",
               "RTG, ultrasound, laboratory blood and urine tests. Fast and accurate diagnostics for proper treatment.​"),
        "cs": ("Diagnostika",
               "RTG, ultrazvuk, laboratorní vyšetření krve a moči. Rychlá a přesná diagnostika pro správnou léčbu.​"),
        "de": ("Diagnostik",
               "Röntgen, Ultraschall, Labortests von Blut und Urin. Schnelle und genaue Diagnostik für die richtige Behandlung.​"),
        "ru": ("Диагностика",
               "Рентген, УЗИ, лабораторные анализы крови и мочи. Быстрая и точная диагностика для правильного лечения.​"),
    },
    {
        "kod": "stomatologie",
        "poradi": 50,
        "en": ("Dentistry",
               "Dental treatment, extractions, ultrasonic cleaning. Oral care for your pet's healthy teeth."),
        "cs": ("Stomatologie",
               "Ošetření zubů, extrakce, ultrazvukové čištění. Péče o dutinu ústní pro zdravý chrup vašeho mazlíčka."),
        "de": ("Zahnheilkunde",
               "Zahnbehandlung, Extraktionen, Ultraschallreinigung. Mundpflege für gesunde Zähne Ihres Tieres."),
        "ru": ("Стоматология",
               "Лечение зубов, удаления, ультразвуковая чистка. Уход за полостью рта для здоровых зубов вашего питомца."),
    },
    {
        "kod": "oftalmologie",
        "poradi": 60,
        "en": ("Ophthalmology",
               "Examination and treatment of eye diseases in small animals, including diagnostics and surgical procedures."),
        "cs": ("Oftalmologie",
               "Vyšetření a léčba očních onemocnění u malých zvířat, včetně diagnostiky a chirurgických zákroků."),
        "de": ("Ophthalmologie",
               "Untersuchung und Behandlung von Augenerkrankungen bei Kleintieren, einschließlich Diagnostik und chirurgischer Eingriffe."),
        "ru": ("Офтальмология",
               "Обследование и лечение глазных заболеваний у мелких животных, включая диагностику и хирургические вмешательства."),
    },
    {
        "kod": "dermatologie",
        "poradi": 70,
        "en": ("Dermatology",
               "Treatment of skin problems, allergies and parasitic diseases. Comprehensive care for skin and coat."),
        "cs": ("Dermatologie",
               "Léčba kožních problémů, alergií a parazitárních onemocnění. Komplexní péče o kůži a srst."),
        "de": ("Dermatologie",
               "Behandlung von Hautproblemen, Allergien und Parasitenerkrankungen. Umfassende Pflege von Haut und Fell."),
        "ru": ("Дерматология",
               "Лечение кожных проблем, аллергий и паразитарных заболеваний. Комплексный уход за кожей и шерстью."),
    },
    {
        "kod": "ultrazvuk",
        "poradi": 80,
        "en": ("Ultrasonography and sonological diagnostics",
               "We have doctors specialising in ultrasound diagnostics. We are developing this area further, including towards cardiology examinations."),
        "cs": ("Ultrasonografie a sonologická diagnostika",
               "Máme lékaře odborně zaměřené na ultrazvukovou diagnostiku. Tuto oblast dále rozvíjíme, a to i směrem ke kardiologickým vyšetřením."),
        "de": ("Ultrasonografie und sonologische Diagnostik",
               "Wir haben Ärzte mit Spezialisierung auf Ultraschalldiagnostik. Diesen Bereich bauen wir weiter aus, auch in Richtung kardiologischer Untersuchungen."),
        "ru": ("Ультрасонография и сонологическая диагностика",
               "У нас есть врачи, специализирующиеся на ультразвуковой диагностике. Мы развиваем это направление дальше, в том числе в сторону кардиологических исследований."),
    },
]


def _seed_sluzby(env):
    """Zalozi vychozi sluzby. Jen pri prvni instalaci — pak uz patri klinice."""
    jazyky_databaze = _nainstalovane_jazyky(env)
    Sluzba = env["elite.vet.service"]
    if Sluzba.search_count([]):
        return
    for radek in VYCHOZI_SLUZBY:
        nazev, popis = radek["en"]
        zaznam = Sluzba.create({
            "name": nazev,
            "description": popis,
            "sequence": radek["poradi"],
            "icon_code": radek["kod"],
        })
        for jazyk, klic in (("cs_CZ", "cs"), ("de_DE", "de"), ("ru_RU", "ru")):
            if jazyk not in jazyky_databaze:
                continue
            nazev_p, popis_p = radek[klic]
            if nazev_p:
                zaznam.with_context(lang=jazyk).name = nazev_p
            if popis_p:
                zaznam.with_context(lang=jazyk).description = popis_p


def _nainstalovane_jazyky(env):
    """Kody jazyku, ktere databaze opravdu zna.

    Zapis prekladu do jazyka, ktery nainstalovany neni, Odoo odmitne
    hlaskou "Invalid language code" a shodi celou instalaci modulu.
    """
    return set(env["res.lang"].search([("active", "=", True)]).mapped("code"))


def _pri_instalaci(env):
    """Vse, co se ma stat po prvni instalaci modulu."""
    from .models.seed import seed_galerie, seed_obsah
    _priradit_stranky_k_webu(env)
    _nastav_homepage(env)
    _nastav_seo(env)
    _nastav_cenik(env)
    _seed_sluzby(env)
    seed_galerie(env)
    seed_obsah(env)
    _srovnej_menu(env)
    _uklid_starych_stranek(env)
    _uklid_zbytku_rucniho_webu(env)
    _doplnit_preklady_stranek(env)


def _doplnit_preklady_stranek(env):
    """Doplni preklady do stranek upravovanych v editoru.

    Editor zapise cesky text do vsech jazyku najednou, takze na /de a /ru
    zustane cestina. Podrobnosti: elite_vet_web/preklad_stranek.py.
    """
    from .preklad_stranek import prelozit
    prelozit(env)


def _uklid_zbytku_rucniho_webu(env):
    """Uklid po webu, ktery se drive psal rucne.

    Musi bezet i pri INSTALACI, nejen pri upgradu. Migrace se spousti pouze
    pri zvyseni verze modulu, takze pri cerste instalaci do databaze, ktera
    uz rucni web ma, by uklid neprobehl nikdy -- a prave na tom spadl ostry
    web: `nas-tym` vracel 500 na dedicim pohledu `gen_key.*`, ktery miri
    na prvek, jaky novy header nema.
    """
    from .uklid import smaz_dvojniky_pohledu, vypni_zbytky_s_mrtvym_xpath
    vypni_zbytky_s_mrtvym_xpath(env)
    smaz_dvojniky_pohledu(env)
    _doplnit_chybejici_sekce_ceniku(env)


# Adresy, na kterych stranku dodava tenhle projekt. Domovska stranka v seznamu
# zamerne NENI: tu prepina _nastav_homepage a odpublikovat na "/" cizi zaznam
# znamena, ze web prestane mit domovskou stranku a "/" zacne vracet 404.
ADRESY_PROJEKTU = (
    "/o-nas",
    "/cenik",
    "/rezervacni-system",
    "/nas-tym",
    "/rozpis-lekaru",
)


def _uklid_starych_stranek(env):
    """Schova rucne delane stranky na adresach, ktere prebiraji moduly.

    Na webu, ktery se drive psal rucne, uz na techto adresach stranka je.
    Instalace modulu vedle ni zalozi svoji a vzniknou dve stranky na jedne
    adrese -- prave na tom padal dev: `/rozpis-lekaru` vracelo 500 a editor
    hlasil "Expected singleton".

    Odpublikovat starou stranku NESTACI. Odoo si pro adresu vybere jedinou
    stranku:

        search(domain, order='website_id asc', limit=1)

    Mezi strankami tehoz webu uz zadne dalsi razeni neni, takze si databaze
    muze vybrat kteroukoliv -- a kdyz padne na tu nezverejnenou, stranka
    vrati 404. Overeno: po pouhem odpublikovani zacaly ctyri stranky vracet
    404, prestoze modulova byla zverejnena.

    Stara stranka se proto **prejmenuje na `<adresa>-puvodni` a odpublikuje**.
    Nic se nemaze: obsah zustava v databazi a da se najit i otevrit.

    Sahne se jen na adresy tohohle projektu a jen na webu Elite Vet. Stranky,
    ktere moduly nedodavaji -- `/aktualni-informace` a kariera -- zustavaji
    presne takove, jake jsou.
    """
    from odoo.addons.elite_vet_calendar import _zvol_web

    web = _zvol_web(env)
    if not web:
        _logger.warning("Uklid stranek se nekonal: neznam web Elite Vet.")
        return

    Stranka = env["website.page"].sudo()

    # V databazi s jedinym webem nemaji stranky prirazeny web vubec; tam jsou
    # "obecne" stranky jeho. Kdyz je webu vic, obecna stranka patri vsem
    # a sahat na ni nesmime.
    if env["website"].search_count([]) <= 1:
        kde = ["|", ("website_id", "=", web.id), ("website_id", "=", False)]
    else:
        kde = [("website_id", "=", web.id)]

    _srovnej_domovskou_stranku(env, Stranka, kde)

    uklizeno = []
    for adresa in ADRESY_PROJEKTU:
        stranky = Stranka.search(kde + [("url", "=", adresa)])
        if len(stranky) < 2:
            continue

        nase = stranky.filtered(
            lambda s: (s.view_id.key or "").startswith("elite_vet"))
        if not nase:
            # Zadna z nich neni nase, tak do toho nemame co mluvit.
            _logger.warning(
                "Na adrese %s je vic stranek, ale zadna z modulu. Nechavam byt.",
                adresa)
            continue

        zustava = nase[0]
        zustava.is_published = True
        for poradi, stara in enumerate(stranky - zustava):
            nova_adresa = adresa + "-puvodni"
            if poradi:
                nova_adresa += "-%s" % (poradi + 1)
            stara.write({"url": nova_adresa, "is_published": False})
            uklizeno.append("%s -> %s" % (adresa, nova_adresa))

    if uklizeno:
        _logger.warning(
            "Starsi stranky na adresach projektu odsunuty: %s. Nic se nesmazalo, "
            "obsah je porad v databazi pod novou adresou.", ", ".join(uklizeno))
    else:
        _logger.info("Uklid stranek: zadna adresa projektu nema dve stranky.")


def _srovnej_domovskou_stranku(env, Stranka, kde):
    """Zaridi, aby "/" ukazovalo nasi homepage, at si Odoo vybere kterou chce.

    Na "/" nejde pouzit stejny trik jako u ostatnich adres -- prejmenovat
    domovskou stranku nelze. Kdyz jich je ale vic, Odoo si jednu vybere
    nahodne (razeni je jen podle website_id) a kdyz padne na tu starou nebo
    nezverejnenou, navstevnik dostane bud stary web, nebo 404.

    Reseni je proto opacne nez jinde: vsechny stranky na "/" dostanou nasi
    sablonu a zverejni se. Pak uz je jedno, kterou si Odoo vezme. Zadna se
    nemaze a stara sablona zustava v databazi.
    """
    sablona = env.ref("elite_vet_web.homepage", raise_if_not_found=False)
    if not sablona:
        return

    domovske = Stranka.search(kde + [("url", "=", "/")])
    if len(domovske) < 2:
        return

    jina_sablona = domovske.filtered(lambda s: s.view_id != sablona)
    nezverejnene = domovske.filtered(lambda s: not s.is_published)
    if not jina_sablona and not nezverejnene:
        return

    # Obe veci najednou: nezverejnena stranka by pri nahodnem vyberu dala 404,
    # cizi sablona zase stary web.
    domovske.write({"view_id": sablona.id, "is_published": True})
    _logger.warning(
        "Na '/' je %s stranek a Odoo si mezi nimi vybira nahodne, takze vsechny "
        "dostaly sablonu modulu (prepsano %s, zverejneno %s).",
        len(domovske), len(jina_sablona), len(nezverejnene))


# Nazvy polozky nabidky, ktera sjede ke kontaktni sekci na domovske strance.
KONTAKT_V_MENU = {
    "en_US": "Contact",
    "cs_CZ": "Kontakt",
    "de_DE": "Kontakt",
    "ru_RU": "Контакты",
}


def _srovnej_menu(env):
    """Dve opravy nabidky, ktere by se jinak musely delat rucne v databazi.

    1. Polozka mirici na "/#odpocet" vede na kotvu odpoctu z predstartovni
       stranky. Ta uz na webu neni, takze klik nikam nevede — prepne se na "/".
    2. Pod domovskou strankou pribyva "Kontakt", ktery sjede ke kontaktni
       sekci. Zaklada se anglicky a ostatni jazyky se dopisuji jako preklad;
       kdyby se zakladal cesky, cestina by se stala zdrojem a ukazala by se
       ve vsech jazycich.

    Sahne se jen na nabidku webu Elite Vet. Ostatni weby v databazi
    (Arena, trafika, Jack, IMI) maji svoji vlastni a ty se to netyka.
    """
    from odoo.addons.elite_vet_calendar import _zvol_web

    web = _zvol_web(env)
    if not web:
        _logger.warning("Nabidka se nesrovnala: nepodarilo se urcit web Elite Vet.")
        return

    Menu = env["website.menu"]

    zastarale = Menu.search([
        ("website_id", "=", web.id),
        ("url", "=like", "%#odpocet"),
    ])
    if zastarale:
        zastarale.url = "/"
        _logger.warning(
            "Polozek nabidky prepnutych z odpoctu na domovskou stranku: %s.",
            len(zastarale))

    # Domovska stranka v nabidce: polozka na "/", ktera nekde visi.
    domu = Menu.search([
        ("website_id", "=", web.id),
        ("url", "=", "/"),
        ("parent_id", "!=", False),
    ], limit=1)
    if not domu:
        _logger.info("Nabidka nema polozku domovske stranky, Kontakt se nepridava.")
        return

    if Menu.search_count([("parent_id", "=", domu.id), ("url", "=", "/#kontakt")]):
        return

    posledni = Menu.search(
        [("parent_id", "=", domu.id)], order="sequence desc", limit=1)
    polozka = Menu.with_context(lang="en_US").create({
        "name": KONTAKT_V_MENU["en_US"],
        "url": "/#kontakt",
        "parent_id": domu.id,
        "website_id": web.id,
        "sequence": (posledni.sequence if posledni else 0) + 1,
    })
    jazyky = _nainstalovane_jazyky(env)
    for jazyk, text in KONTAKT_V_MENU.items():
        if jazyk != "en_US" and jazyk in jazyky:
            polozka.with_context(lang=jazyk).name = text
    _logger.info("Do nabidky pribyl Kontakt (id %s).", polozka.id)


def _priradit_stranky_k_webu(env):
    """Prisije stranky modulu k webu Elite Vet.

    Stranka bez prirazeneho webu je v Odoo "obecna" a vykresli se na VSECH
    domenach v databazi. Ta hostuje i Elite Arenu, trafiku, Jacka a IMI —
    a na tech by cenik ani rezervace veterinarni kliniky nemely co delat.
    Uz jednou se to stalo, proto se to deje automaticky a ne rucne.
    """
    from odoo.addons.elite_vet_calendar import _priradit_k_webu
    for xml_id in ("elite_vet_web.rezervace_page", "elite_vet_web.cenik_page",
                   "elite_vet_web.o_nas_page"):
        _priradit_k_webu(env, xml_id)


def _nastav_homepage(env):
    """Prepne domovskou stranku na sablonu tohohle modulu.

    Nejde to udelat zaznamem v XML: `website.homepage_page` je v modulu website
    oznacena jako noupdate, takze ji cizi modul prepsat nesmi.

    Poradi je schvalne opatrne, protoze obecna stranka "/" patri vsem webum
    v databazi:

    1. Kdyz ma web Elite Vet vlastni stranku na "/", prepne se jen ta.
    2. Kdyz je v databazi jediny web, je obecna stranka jeho a prepne se.
    3. Kdyz je webu vic a Elite Vet vlastni "/" nema, NEPREPNE se nic. Prepsat
       obecnou stranku by znamenalo hodit veterinarni homepage i Arene
       a trafice. Zapise se to do logu a dodela se rucne podle nasazeni/README.

    Vlastni stranka na "/" se zamerne nezaklada. Dve stranky na stejne adrese
    znamenaji, ze si obsluha "/" vybere tu spatnou a misto homepage presmeruje
    na prvni polozku menu.
    """
    from odoo.addons.elite_vet_calendar import _zvol_web

    sablona = env.ref('elite_vet_web.homepage', raise_if_not_found=False)
    if not sablona:
        return

    # Zamerne se nemeni 'name': website.page pri prejmenovani prepise i klic
    # pohledu, takze by sablona modulu prestala mit svuj vlastni klic.
    zmena = {
        'view_id': sablona.id,
        'is_published': True,
        'website_indexed': True,
    }

    Stranka = env['website.page']
    web = _zvol_web(env)

    # 1. Web uz svoji domovskou stranku ma — jen se prepne na nasi sablonu.
    if web:
        vlastni = Stranka.search(
            [('url', '=', '/'), ('website_id', '=', web.id)], limit=1)
        if vlastni:
            vlastni.write(zmena)
            _logger.info("Homepage webu '%s' prepnuta na sablonu modulu.", web.name)
            _uklidit_obecne_homepage(env, sablona)
            return

    # 2. Jediny web v databazi: obecna stranka je jeho, takze se prepne ta.
    if env['website'].search_count([]) <= 1:
        obecna = env.ref('website.homepage_page', raise_if_not_found=False)
        if obecna:
            obecna.write(zmena)
            _logger.info("Obecna homepage prepnuta na sablonu modulu.")
        return

    # 3. Webu je vic. Obecnou stranku Odoo nesmime prepsat, protoze by se
    #    veterinarni homepage objevila i ostatnim webum. Zalozi se proto
    #    vlastni stranka jen pro web Elite Vet.
    if not web:
        _logger.warning(
            "Homepage se neprepnula: v databazi je vic webu a nepodarilo se "
            "urcit, ktery patri Elite Vet.")
        return

    Stranka.create(dict(zmena, url='/', website_id=web.id))
    _logger.info("Webu '%s' zalozena vlastni homepage na sablone modulu.", web.name)
    _uklidit_obecne_homepage(env, sablona)


def _uklidit_obecne_homepage(env, sablona):
    """Prisije k webu obecne stranky "/", ktere ukazuji na nasi sablonu.

    Dve OBECNE stranky na teze adrese znamenaji, ze si obsluha "/" vybere
    spatnou a misto homepage presmeruje na prvni polozku menu. Prave na tom
    stalo nasazeni: vedle Odoo vlastni stranky vznikla druha, obecna,
    ukazujici na nasi sablonu.
    """
    from odoo.addons.elite_vet_calendar import _zvol_web

    web = _zvol_web(env)
    if not web:
        return
    zbytecne = env['website.page'].search([
        ('url', '=', '/'),
        ('website_id', '=', False),
        ('view_id', '=', sablona.id),
    ])
    if zbytecne:
        zbytecne.write({'website_id': web.id})
        _logger.info(
            "Obecnych homepage na sablone modulu prisito k webu '%s': %s.",
            web.name, len(zbytecne))


def _nastav_seo(env):
    """Zapise SEO titulek a popis na zaznamy stranek, ve vsech ctyrech jazycich.

    Odoo bere meta popis z pole `website_meta_description` na zaznamu stranky,
    ne z `<t t-set="meta_description">` v sablone — ten tise ignoruje. Stranky
    proto zadny popis do vyhledavacu nemely, ani cesky.

    Texty se neberou z hlavy: jsou to tytez vety, ktere uz v sablonach jsou,
    i s preklady z i18n/*.po. Vytazene jsou v data/seo.json.

    Vyplnene pole se nikdy neprepisuje — co si klinika napsala, zustane.
    """
    import json
    import os

    cesta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "seo.json")
    if not os.path.exists(cesta):
        _logger.warning("SEO: soubor %s nenalezen, preskakuji.", cesta)
        return
    with open(cesta, encoding="utf-8") as soubor:
        stranky = json.load(soubor)

    # en_US je zdroj, ne jeden z jazyku: zapisuje se prvni, jinak by ostatni
    # jazyky bez vlastniho prekladu zdedily to, co se do nej napsalo naposled.
    PORADI = ["en_US", "cs_CZ", "de_DE", "ru_RU"]
    zapsano = 0
    for radek in stranky:
        stranka = env.ref(radek["stranka"], raise_if_not_found=False)
        if not stranka:
            continue
        for pole, hodnoty in (("website_meta_title", radek.get("title") or {}),
                              ("website_meta_description", radek.get("description") or {})):
            if (stranka[pole] or "").strip():
                continue                      # klinika uz si to vyplnila
            for jazyk in PORADI:
                text = hodnoty.get(jazyk)
                if text and jazyk in _nainstalovane_jazyky(env):
                    stranka.with_context(lang=jazyk)[pole] = text
            zapsano += 1
    _logger.info("SEO: doplneno %s hodnot na strankach.", zapsano)



def _nacti_cenik():
    """Vrati obsah data/cenik.json, nebo prazdno, kdyz soubor chybi."""
    import json
    import os

    cesta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "cenik.json")
    if not os.path.exists(cesta):
        _logger.warning("Ceník: soubor %s nenalezen.", cesta)
        return {}
    with open(cesta, encoding="utf-8") as soubor:
        return json.load(soubor)


def _zapis_jazyky(zaznam, pole, hodnoty):
    """Zapise zdroj a pak jednotlive preklady.

    en_US je zdroj, ne jeden z jazyku — kdyz se zapise az po ostatnich,
    prepise je. U Html poli prekladanych po terminech musi zdroj vzniknout
    uz pri create, jinak prvni zapis v cizim jazyce zdroj prepise.
    """
    if not hodnoty:
        return
    jazyky_databaze = _nainstalovane_jazyky(zaznam.env)
    for jazyk in ("en_US", "cs_CZ", "de_DE", "ru_RU"):
        text = hodnoty.get(jazyk)
        if text and (jazyk == "en_US" or jazyk in jazyky_databaze):
            zaznam.with_context(lang=jazyk)[pole] = text


def _nastav_cenik(env):
    """Zalozi cely cenik: hlavicku stranky, sekce a ukony v nich.

    Obsah ceniku zije v databazi, ne v sablone, takze se musi nekde vzit —
    lezi v data/cenik.json presne tak, jak si ho klinika nastavila, vcetne
    vsech jazyku, ve kterych uz text ma.

    Zaklada se jen jednou. Kdyz uz nejaka sekce existuje, nedela se nic —
    upgrade tak nikdy neprepise to, co klinika mezitim zmenila.
    """
    Sekce = env["elite.vet.price.category"].sudo()
    Ukon = env["elite.vet.price.item"].sudo()
    if Sekce.search_count([]):
        return

    sekce_data = (_nacti_cenik().get("sekce") or [])
    if not sekce_data:
        return

    # Ukony, ktere uz v databazi jsou (ze starsi instalace), nechceme mit
    # dvakrat — zaradi se do prvni sekce, ktera nejakou tabulku ma.
    stavajici = Ukon.search([("category_id", "=", False)])

    prvni_s_ukony = False
    for radek in sekce_data:
        sekce = _zaloz_sekci_ceniku(env, radek)
        if radek.get("ukony") and not prvni_s_ukony:
            prvni_s_ukony = sekce

    if stavajici and prvni_s_ukony:
        stavajici.write({"category_id": prvni_s_ukony.id})

    _logger.info("Ceník: zalozeno %s bloku.", len(sekce_data))


def _doplnit_chybejici_sekce_ceniku(env):
    """Doplni sekce z cenik.json, ktere v databazi jeste nejsou.

    Cenik se zaklada jen pri prvni instalaci, aby upgrade nikdy neprepsal to,
    co si klinika zmenila. Kdyz ale do modulu pribude cela nova sekce --
    treba vikendove a pohotovostni priplatky -- na uz bezici databazi by se
    neobjevila nikdy. Doplni se proto jen ty sekce, jejichz nazev v databazi
    neni v zadnem jazyce; co uz tam je, se nechava presne tak, jak to je.

    Hlavicka stranky se nedoplnuje nikdy: kazdy cenik uz nejakou ma a druha
    by na strance jen prekazela.
    """
    Sekce = env["elite.vet.price.category"].sudo().with_context(active_test=False)

    # Ctou se jen jazyky, ktere databaze opravdu zna. Cteni v jazyce, ktery
    # nainstalovany neni, Odoo odmitne hlaskou "Invalid language code"
    # a shodi celou instalaci modulu.
    jazyky = {"en_US"} | _nainstalovane_jazyky(env)

    zname = set()
    for jazyk in jazyky:
        for nazev in Sekce.with_context(lang=jazyk).search([]).mapped("name"):
            if nazev:
                zname.add(nazev.strip().lower())

    pridano = []
    for radek in (_nacti_cenik().get("sekce") or []):
        if (radek.get("typ") or "sekce") == "hlavicka":
            continue
        nazvy = {(h or "").strip().lower() for h in (radek.get("nazev") or {}).values()}
        nazvy.discard("")
        if not nazvy or (nazvy & zname):
            continue
        sekce = _zaloz_sekci_ceniku(env, radek)
        pridano.append(sekce.with_context(lang="en_US").name)

    if pridano:
        _logger.warning("Ceník: doplneny chybejici sekce: %s.", ", ".join(pridano))
    else:
        _logger.info("Ceník: vsechny sekce z modulu uz v databazi jsou.")


def _zaloz_sekci_ceniku(env, radek):
    """Zalozi jednu sekci ceniku vcetne ukonu a vsech jazyku."""
    Sekce = env["elite.vet.price.category"].sudo()
    Ukon = env["elite.vet.price.item"].sudo()

    nazev = radek.get("nazev") or {}
    sekce = Sekce.with_context(lang="en_US").create({
        "typ": radek.get("typ") or "sekce",
        "name": nazev.get("en_US") or nazev.get("cs_CZ") or "Ceník",
        "sequence": radek.get("poradi") or 10,
        # komentar musi byt uz tady, je to Html prekladane po terminech
        "comment": (radek.get("komentar") or {}).get("en_US") or False,
    })
    _zapis_jazyky(sekce, "name", nazev)
    _zapis_jazyky(sekce, "badge", radek.get("stitek"))
    _zapis_jazyky(sekce, "description", radek.get("popisek"))
    _zapis_jazyky(sekce, "comment", radek.get("komentar"))

    for polozka in radek.get("ukony") or []:
        jmeno = polozka.get("nazev") or {}
        cena = polozka.get("cena") or {}
        hodnoty = {
            "category_id": sekce.id,
            "name": jmeno.get("en_US") or jmeno.get("cs_CZ") or "",
            "price": cena.get("en_US") or cena.get("cs_CZ") or "",
            "price_from": bool(polozka.get("cena_od")),
            "sequence": polozka.get("poradi") or 10,
        }
        if polozka.get("ikona_kod"):
            hodnoty["icon_code"] = polozka["ikona_kod"]
        # ikona se hleda podle externiho ID: cislo zaznamu je na kazde
        # instalaci jine, xmlid je vsude stejne
        if polozka.get("ikona_xmlid"):
            ikona = env.ref(polozka["ikona_xmlid"], raise_if_not_found=False)
            if ikona:
                hodnoty["icon_id"] = ikona.id
            else:
                _logger.warning("Ceník: ikona %s nenalezena, úkon zůstane bez ní.",
                                polozka["ikona_xmlid"])
        ukon = Ukon.with_context(lang="en_US").create(hodnoty)
        _zapis_jazyky(ukon, "name", jmeno)
        _zapis_jazyky(ukon, "price", cena)
        _zapis_jazyky(ukon, "note", polozka.get("poznamka"))

    return sekce