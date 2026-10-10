import logging

_logger = logging.getLogger(__name__)

from . import models
from .preklady import PREKLADY


def _seed_team(env):
    """Naplni stranku tim, co na ni je dnes, aby klinika nezacinala u prazdneho
    seznamu a mohla rovnou upravovat.

    Zaznamy se zamerne nezakladaji jako data modulu s XML id. Takovy zaznam by
    se pri kazdem upgradu modulu obnovil, takze smazany clovek by se vratil.
    Takhle vzniknou jednou pri instalaci a od te chvile patri klinice.
    """
    _priradit_k_webu(env, "elite_vet_team.nas_tym_page")

    Section = env["elite.vet.team.section"]
    if Section.search_count([]):
        return

    Label = env["elite.vet.team.fact.label"]
    popisky = {}
    for poradi, (nazev, predvyplnit) in enumerate(POPISKY, start=1):
        popisky[nazev] = Label.create({
            "name": nazev,
            "sequence": poradi * 10,
            "is_default": predvyplnit,
        })

    Member = env["elite.vet.team.member"]
    for poradi_sekce, sekce in enumerate(SEKCE, start=1):
        zaznam_sekce = Section.create({
            "name": sekce["name"],
            "anchor": sekce["anchor"],
            "sequence": poradi_sekce * 10,
        })
        for poradi, clen in enumerate(sekce["members"], start=1):
            Member.create({
                "section_id": zaznam_sekce.id,
                "sequence": poradi * 10,
                "name": clen["name"],
                "role": clen["role"],
                "email": clen["email"],
                "badge": clen["badge"],
                "highlight": clen["highlight"],
                "perex": clen["perex"],
                "fact_ids": [
                    (0, 0, {
                        "label_id": popisky[popisek].id,
                        "value": text,
                        "sequence": i * 10,
                    })
                    for i, (popisek, text) in enumerate(clen["facts"], start=1)
                ],
            })
    _seed_preklady(env)


# Popisky podrobnosti. True = u noveho cloveka se radek predvyplni prazdny.
POPISKY = [
    ("Vzdělání", True),
    ("Praxe", True),
    ("Specializace", True),
    ("Další vzdělávání", True),
    ("Jazyky", True),
    ("Praxe a zaměření", False),
    ("Zaměření", False),
    ("Dovednosti", False),
    ("Náplň práce", False),
    ("Další zkušenosti", False),
    ("Profesní přístup", False),
]

SEKCE = [
    {
        "anchor": "lekarky",
        "name": "Veterinární lékařky",
        "members": [
            {
                "name": "MVDr. Dominika Pražáková",
                "role": "Garantka veterinární kliniky · chirurgie měkkých tkání a interní medicína",
                "email": "prazakova@elite-vet.cz",
                "badge": "Odborná garantka",
                "highlight": True,
                "perex": "Jako garantka kliniky dohlíží na odborný standard poskytované péče, kontinuitu léčebných postupů a další rozvoj týmu. Její profesní profil spojuje zkušenosti z klinického provozu, terénní veterinární služby, chirurgického sálu i zahraničních stáží. Díky zkušenostem z terénu i chirurgického sálu spojuje systematický přístup s rychlým a rozhodným jednáním při řešení komplexních případů.",
                "facts": [
                    ("Vzdělání", "Fakulta veterinárního lékařství VETUNI Brno."),
                    ("Praxe", "PremiumVet Praha — chirurgie, interní medicína a výjezdová veterinární služba. Zahraniční zkušenosti zahrnují tříměsíční stáž na veterinární klinice v Tromsø v Norsku a šestiměsíční chirurgickou stáž v Centru São Vicente na Kapverdách."),
                    ("Specializace", "Chirurgie měkkých tkání a interní medicína."),
                    ("Další vzdělávání", "Ucelený specializační cyklus Chirurgie měkkých tkání pod hlavičkou VetCoaching."),
                    ("Jazyky", "Angličtina."),
                ],
            },
            {
                "name": "MVDr. Sandra Mrázová",
                "role": "Veterinární lékařka · interní medicína, všeobecná a akutní chirurgie, péče o kritické pacienty",
                "email": "mrazova@elite-vet.cz",
                "badge": "",
                "highlight": False,
                "perex": "Její odborné směřování stojí na akutní medicíně, chirurgii a péči o kritické pacienty. Praktické zkušenosti získávala při nočních službách, pohotovostní péči i během zahraniční stáže a dále je rozvíjí na renomovaném pracovišti AAvet.",
                "facts": [
                    ("Vzdělání", "Fakulta veterinárního lékařství VETUNI Brno."),
                    ("Praxe", "Noční služby jako veterinární asistentka v Brně, zahraniční stáž ve Veterinární nemocnici Shirayamachó v Japonsku a klinická i noční pohotovostní péče na AAvet."),
                    ("Zaměření", "Všeobecná a akutní chirurgie, řešení akutních stavů a management kritických pacientů. Provádí preventivní chirurgické zákroky a v rámci pohotovostních služeb se zdokonaluje také v akutní chirurgii včetně operačního řešení GDV / torze žaludku."),
                    ("Další vzdělávání", "Urgentní medicína, chirurgie, onkologie a urologie; kurzy a semináře Péče o akutního a kritického pacienta, CPR u psa a kočky (MVDr. Novák) a chirurgické trendy u očních onemocnění (MVDr. Renata Stavinohová). Plánuje účast na odborném semináři Akutní pacient pod vedením MVDr. Raušerové."),
                    ("Jazyky", "Angličtina B2, španělština A2, japonština N4."),
                ],
            },
            {
                "name": "MVDr. Kateřina Kadavá",
                "role": "Veterinární lékařka · interní medicína, akutní stavy a oftalmologie",
                "email": "kadava@elite-vet.cz",
                "badge": "",
                "highlight": False,
                "perex": "Po absolvování Veterinární univerzity nastoupila bezprostředně na renomovanou referenční kliniku s nepřetržitým provozem. Zde získala intenzivní zkušenosti s akutními život ohrožujícími stavy a náročnými případy interní medicíny; současně systematicky rozvíjí zaměření na oftalmologii malých zvířat.",
                "facts": [
                    ("Vzdělání", "Veterinární univerzita v Brně."),
                    ("Praxe", "Referenční klinika s nepřetržitým provozem se zaměřením na akutní medicínu a náročné interní případy. Zkušenosti s drobnými savci získávala na specializované klinice Jekl & Hauptman v Brně."),
                    ("Specializace", "Interní medicína psů, koček a drobných savců."),
                    ("Další vzdělávání", "Oftalmologie v praxi malých zvířat (VetCoaching, Žilina), Understanding Ophthalmology (Jablonec nad Nisou), praktický workshop diagnostiky slepoty u psů a koček na akademii Medipet; dále gastroenterologie, urologie koček a urgentní medicína."),
                    ("Jazyky", "Angličtina."),
                ],
            },
            {
                "name": "MVDr. Georgiana Chihaia",
                "role": "Veterinární lékařka · pohotovostní a intenzivní péče, ultrasonografie a stomatologie",
                "email": "chihaia@elite-vet.cz",
                "badge": "",
                "highlight": False,
                "perex": "Profesně se zaměřuje na urgentní a intenzivní péči, vnitřní lékařství, pokročilou diagnostiku a veterinární stomatologii. Má zkušenosti s vedením pohotovostních směn a řešením komplikovaných akutních, infekčních i neurologických stavů.",
                "facts": [
                    ("Vzdělání", "Univerzita agronomických věd a veterinární medicíny v Bukurešti."),
                    ("Praxe", "Vedení pohotovostních směn, řešení krizových, infekčních a neurologických stavů."),
                    ("Specializace", "Urgentní a intenzivní péče, vnitřní lékařství, ultrasonografie včetně protokolů AFAST a TFAST, radiologická diagnostika a veterinární stomatologie včetně chirurgických stomatologických zákroků."),
                    ("Další vzdělávání", "Certifikovaný program Abdominal Ultrasonography in Companion Animals (Zet Diagnostic), Fundamentals of Veterinary Dentistry (Vetakademos) a Veterinary Dental Prosthetics (RSVD)."),
                    ("Jazyky", "Plynulá angličtina."),
                ],
            },
        ],
    },
    {
        "anchor": "sestry",
        "name": "Veterinární sestry",
        "members": [
            {
                "name": "Silvie Tranta, DiS.",
                "role": "Veterinární sestra",
                "email": "",
                "badge": "",
                "highlight": False,
                "perex": "Do kliniky přináší praktické zkušenosti z veterinárního provozu ordinace malých zvířat, kde se aktivně pohybovala již před zahájením odborného studia a následně v jeho průběhu. Její profesní přínos stojí na klinické asistenci, organizaci práce a klidné komunikaci v náročných situacích.",
                "facts": [
                    ("Vzdělání", "Obor Veterinářství / Veterinární sestra na European College Pilsen."),
                    ("Praxe", "Aktivní odborná činnost ve veterinárním provozu ordinace malých zvířat před zahájením i během studia."),
                    ("Dovednosti", "Asistence u vyšetřovacích a chirurgických výkonů, péče o hospitalizované pacienty, laboratorní práce, krizová komunikace a organizace práce."),
                    ("Další vzdělávání", "Ucelená řada workshopů Veterinární sestra I.–III. na klinice Jaggy v Praze."),
                    ("Další zkušenosti", "Dlouholeté zkušenosti z manažerských pozic a sociálních služeb; spolehlivost, klid v krizových situacích a empatická komunikace s majiteli zvířat."),
                ],
            },
            {
                "name": "Nikola Hejdová",
                "role": "Veterinární sestra",
                "email": "",
                "badge": "",
                "highlight": False,
                "perex": "Ve veterinární praxi působí řadu let a zkušenosti sbírala na pracovištích v České republice i během odborné stáže v Německu. V každodenním provozu staví na pečlivosti, spolehlivosti a vstřícném přístupu k pacientům i klientům.",
                "facts": [
                    ("Vzdělání", "Střední zemědělská škola v Dalovicích — obor Agropodnikání."),
                    ("Praxe", "Dlouholetá veterinární praxe, odborná stáž v Německu, zkušenosti z Veterinární kliniky Kleisslova v Plzni a z pracoviště Altavet v Praze."),
                    ("Dovednosti", "Certifikace pro nakládání s veterinárními léčivými přípravky, pokročilá znalost systému WinVet a péče o pacienty."),
                    ("Profesní přístup", "Pečlivost, vřelý přístup k pacientům a spolehlivost při zajištění hladkého chodu ordinace."),
                ],
            },
        ],
    },
    {
        "anchor": "recepce",
        "name": "Recepce a klientský servis",
        "members": [
            {
                "name": "Bc. Michala Dvořáková Szmigielská",
                "role": "Recepce a klientský servis / sestra · se zaměřením na pohybový aparát zvířat",
                "email": "",
                "badge": "",
                "highlight": False,
                "perex": "Propojuje dlouholetou praxi v obchodním servisu a administrativě s odborným zájmem o zdraví zvířat, rehabilitaci, výživu a první pomoc. Na recepci zajišťuje klientský servis a organizační podporu s odborným přesahem do péče o zvířata.",
                "facts": [
                    ("Vzdělání", "Vysoká škola obchodní v Praze (Bc.); odborné předměty na TRIVIS — Nemoci zvířat a instrumentář, Chov, výživa a dietetika zvířat."),
                    ("Praxe a zaměření", "Dlouholetá praxe v obchodním servisu a administrativě; odborné znalosti v rehabilitaci, fyzioterapii, výživě a první pomoci psů."),
                    ("Další vzdělávání", "Měkké techniky v rehabilitaci zvířat Level I., Dornova metoda pro psy a První pomoc pro psy."),
                    ("Jazyky", "Polština B2, němčina B1, angličtina A2."),
                ],
            },
        ],
    },
    {
        "anchor": "management",
        "name": "Provoz a management",
        "members": [
            {
                "name": "Lucie Svobodová",
                "role": "Provoz a management kliniky · veterinární technik",
                "email": "svobodova@elite-vet.cz",
                "badge": "",
                "highlight": False,
                "perex": "Spojuje odborné zázemí z veterinární praxe s projektovým a operativním řízením. Zkušenosti vrchní a sálové sestry doplňuje praxe projektové manažerky z mezinárodního prostředí; v ELITE VET odpovídá za koordinaci provozu, týmové procesy, vybavení a další rozvoj služeb.",
                "facts": [
                    ("Vzdělání", "Obor Veterinární technik."),
                    ("Praxe", "Zkušenosti jako vrchní a sálová sestra se zaměřením na ortopedii, chirurgii, diagnostické zobrazovací metody a pooperační rehabilitaci; praxe projektové manažerky v mezinárodním prostředí."),
                    ("Náplň práce", "Kompletní řízení kliniky, plánování provozu a efektivita týmu, výběr a nákup moderního přístrojového vybavení, komunikace s partnery a dodavateli, rozvoj portfolia služeb, zavádění interních systémů a podmínky pro vysoký standard péče i spokojenost personálu."),
                    ("Další vzdělávání", "Kurz radiační ochrany OZARO, Veterinární sestra — partner v krizových situacích, Hill's Vet Academy, Royal Canin Academy a odborné semináře zaměřené na neurologickou péči u MVDr. Aleše Tomka, DipECVN."),
                    ("Jazyky", "Plynulá angličtina."),
                ],
            },
        ],
    },
]


# Pole, ktera nesou text a daji se prelozit. Jmeno a e-mail zamerne chybi.
PREKLADANA_POLE = {
    "elite.vet.team.section": ["name"],
    "elite.vet.team.fact.label": ["name"],
    "elite.vet.team.member": ["role", "badge", "perex"],
    "elite.vet.team.fact": ["value"],
}


def _seed_preklady(env):
    """Doplni k zalozenemu obsahu nemcinu, anglictinu a rustinu.

    Puvodni rucni stranka /nas-tym mela preklady ulozene v archu. Kdyz se
    smaze a nahradi timhle modulem, preklady by zmizely a musely by se delat
    znovu. Proto si je modul pri instalaci naplni sam ze zalohy.

    Pouziva se update_field_translations, ne write s jazykovym kontextem.
    Write totiz umi sahnout na zdrojovy text a prepsat cestinu prekladem -
    coz se pri vyvoji tohohle modulu stalo.

    Prekladaji se jen jazyky, ktere jsou v databazi opravdu nainstalovane.
    Kdyz klinika prida jazyk az pozdeji, preklady se timhle nedoplni; da se
    to dohnat preinstalaci modulu na cistem webu, nebo rucne v rezimu
    Prelozit.
    """
    env.flush_all()

    aktivni = set(env["res.lang"].search([("active", "=", True)]).mapped("code"))
    jazyky = aktivni & {"de_DE", "en_US", "ru_RU"}

    # Kdyz v databazi neni nainstalovana cestina, bydli cesky text ve slotu
    # en_US - ten je pro Odoo zdrojovy. Zapsat do nej anglictinu by cestinu
    # prepsalo a stranka by se cesky uz nezobrazila.
    if "cs_CZ" not in aktivni:
        jazyky.discard("en_US")
        _logger.info(
            "Cestina neni nainstalovana, anglicke preklady se preskoci - "
            "en_US slot nese cesky zdrojovy text."
        )

    if not jazyky:
        return

    for model, pole in PREKLADANA_POLE.items():
        zaznamy = env[model].with_context(active_test=False).search([])
        for zaznam in zaznamy:
            for nazev_pole in pole:
                zdroj = zaznam[nazev_pole]
                if not zdroj:
                    continue
                preklad = PREKLADY.get(zdroj)
                if not preklad:
                    continue
                hodnoty = {
                    kod: text
                    for kod, text in preklad.items()
                    if kod in jazyky and text
                }
                # Cesky text je pri zalozeni ve zdrojovem slotu, ne v cs_CZ.
                # Kdyz do zdroje zapiseme anglictinu, cestina by zmizela -
                # musi se proto ulozit do sveho slotu.
                if "cs_CZ" in aktivni:
                    hodnoty["cs_CZ"] = zdroj
                if hodnoty:
                    zaznam.update_field_translations(nazev_pole, hodnoty)


def _zvol_web(env):
    """Vybere web, kteremu stranka patri.

    V databazi bezi vic webu vedle sebe (Elite Vet, Elite Arena, trafika,
    Jack, IMI). Stranka bez prirazeneho webu se v Odoo zobrazi na VSECH
    domenach, coz je presne to, co nechceme.

    Poradi hledani: domena obsahujici elite-vet, pak cokoli s "vet"
    v nazvu nebo domene, jinak jediny existujici web. Kdyz nic nesedi,
    vrati prvni a zapise to do logu - administrator to pak prepise
    v Web -> Konfigurace -> Stranky.
    """
    weby = env["website"].search([])
    if not weby:
        return False
    if len(weby) == 1:
        return weby

    for web in weby:
        if "elite-vet" in (web.domain or "").lower():
            return web
    for web in weby:
        popis = ((web.name or "") + " " + (web.domain or "")).lower()
        if "vet" in popis and "arena" not in popis:
            return web

    _logger.warning(
        "Nepodarilo se poznat, ktery web je Elite Vet. Stranka byla prirazena "
        "k webu '%s'. Zmenit ji jde v Web -> Konfigurace -> Stranky.",
        weby[0].name,
    )
    return weby[0]


def _priradit_k_webu(env, xml_id_stranky, xml_id_menu=None):
    """Priradi stranku (a volitelne polozku menu) ke konkretnimu webu.

    Bez toho je stranka spolecna pro vsechny weby v databazi a objevi se
    i na domenach, kam nepatri.
    """
    web = _zvol_web(env)
    if not web:
        return

    stranka = env.ref(xml_id_stranky, raise_if_not_found=False)
    if stranka:
        stranka.website_id = web.id

    if xml_id_menu:
        polozka = env.ref(xml_id_menu, raise_if_not_found=False)
        if polozka:
            polozka.website_id = web.id
            if web.menu_id:
                polozka.parent_id = web.menu_id.id

    _logger.info("Stranka %s prirazena k webu '%s'.", xml_id_stranky, web.name)
