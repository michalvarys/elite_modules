#!/usr/bin/env python3
"""Build the published guide page (Czech + English) from the Markdown guides in the repository.

Usage: python3 build.py OUT_DIR
Writes OUT_DIR/navody.html and OUT_DIR/img/<module>/<file>. Publish navody.html as the artifact
with the images as supporting files. Requires markdown-it-py.
"""
import html
import json
import re
import shutil
import sys
from pathlib import Path

from markdown_it import MarkdownIt

HERE = Path(__file__).resolve().parent
ELITE_VET = HERE.parents[1]

ROLES = [
    {"key": "reception", "cs": "Recepce", "en": "Reception"},
    {"key": "clinic", "cs": "Ordinace", "en": "Consulting room"},
    {"key": "management", "cs": "Vedení", "en": "Management"},
    {"key": "admin", "cs": "Správce", "en": "Administrator"},
]

GUIDES = [
    {"key": "pokladna-recepce", "role": "reception", "path": "elite_vet_reception/doc/recepce-v-pokladne.md",
     "en": "elite_vet_reception/doc/en/recepce-v-pokladne.md",
     "title": {"cs": "Recepce v pokladně", "en": "Reception in the till"},
     "desc": {"cs": "Den u přepážky: příchody, přijetí, kartotéka, objednání a placení.",
              "en": "The day at the desk: arrivals, check-in, card file, booking and payment."}},
    {"key": "kalendar", "role": "reception", "path": "elite_vet_reservation/doc/recepce.md",
     "en": "elite_vet_reservation/doc/en/recepce.md",
     "title": {"cs": "Kalendář a rezervace", "en": "Calendar and reservations"},
     "desc": {"cs": "Žádosti z webu, nová rezervace, přesuny, blokace a rušení.",
              "en": "Web requests, new reservations, moving, blocks and cancelling."}},
    {"key": "pokladna-sklad", "role": "reception", "path": "elite_vet_sale/doc/pokladna-a-sklad.md",
     "en": "elite_vet_sale/doc/en/pokladna-a-sklad.md",
     "title": {"cs": "Pokladna a sklad", "en": "Till and stock"},
     "desc": {"cs": "Účty, faktury, zálohy, vratky, uzávěrka, příjem zboží.",
              "en": "Bills, invoices, deposits, refunds, closing the till, goods in."}},
    {"key": "ordinace", "role": "clinic", "path": "elite_vet_reception/doc/ordinace.md",
     "en": "elite_vet_reception/doc/en/ordinace.md",
     "title": {"cs": "Ordinace", "en": "Consulting room"},
     "desc": {"cs": "Moji pacienti dnes, karta pacienta, záznam a účet návštěvy.",
              "en": "My patients today, the patient card, the visit record and bill."}},
    {"key": "planovani", "role": "clinic", "path": "elite_vet_planning/doc/planovani.md",
     "en": "elite_vet_planning/doc/en/planovani.md",
     "title": {"cs": "Plánování služeb", "en": "Staff planning"},
     "desc": {"cs": "Moje směny a dostupnost, plán měsíce, zveřejnění na webu, bilance hodin, přehled po lidech a PDF.",
              "en": "My shifts and availability, the monthly plan, publishing, hours balance, overview by person and PDF."}},
    {"key": "prehledy", "role": "management", "path": "elite_vet_winvet/doc/data-a-prehledy.md",
     "en": "elite_vet_winvet/doc/en/data-a-prehledy.md",
     "title": {"cs": "Data a přehledy", "en": "Data and dashboards"},
     "desc": {"cs": "Přehled tržeb a výdajů, kontingenční tabulky, uzávěrka, regleta skladu.",
              "en": "Revenue and expenses dashboard, pivots, closure, stock report."}},
    {"key": "nastaveni", "role": "admin", "path": "elite_vet_reservation/doc/nastaveni.md",
     "en": "elite_vet_reservation/doc/en/nastaveni.md",
     "title": {"cs": "Nastavení rezervací", "en": "Reservation setup"},
     "desc": {"cs": "Práva, lékařky, ordinace, úkony, rozpis, e-maily.",
              "en": "Access rights, doctors, rooms, procedures, roster, e-mails."}},
    {"key": "jak-to-funguje", "role": "admin", "path": "elite_vet_reservation/doc/jak-to-funguje.md",
     "en": "elite_vet_reservation/doc/en/jak-to-funguje.md",
     "title": {"cs": "Jak fungují rezervace", "en": "How reservations work"},
     "desc": {"cs": "Výpočet volných termínů a pravidla, co co blokuje.",
              "en": "How free times are calculated and what blocks what."}},
    {"key": "most-winvet", "role": "admin", "path": "winvet_bridge/README.md", "en": "winvet_bridge/README.en.md",
     "title": {"cs": "Most WinVet", "en": "WinVet bridge"},
     "desc": {"cs": "Instalace na počítači s WinVetem a co dělat po jeho aktualizaci.",
              "en": "Installing on the WinVet PC and what to do after a WinVet update."}},
]

NO_LINK = "#no-link"
MD = MarkdownIt("commonmark", {"html": False, "linkify": False, "typographer": False}).enable("table")


def slug(text):
    table = str.maketrans("áčďéěíňóřšťúůýž", "acdeeinorstuuyz")
    text = re.sub(r"[^a-z0-9]+", "-", text.lower().translate(table)).strip("-")
    return text or "sekce"


def guide_by_path():
    out = {}
    for guide in GUIDES:
        out[guide["path"]] = guide["key"]
        out[guide["en"]] = guide["key"]
    return out


def render(guide, lang, out_dir, used_images):
    rel = guide["path"] if lang == "cs" else guide["en"]
    source = ELITE_VET / rel
    if not source.is_file():
        return None
    text = source.read_text(encoding="utf-8")
    tokens = MD.parse(text)
    toc, seen = [], {}
    title = None
    for i, token in enumerate(tokens):
        if token.type == "heading_open":
            label = tokens[i + 1].content
            plain = re.sub(r"[*`]", "", re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", label))
            if token.tag == "h1" and title is None:
                title = plain
            base = slug(plain)
            seen[base] = seen.get(base, 0) + 1
            anchor = base if seen[base] == 1 else f"{base}-{seen[base]}"
            token.attrSet("id", f"{lang}-{guide['key']}--{anchor}")
            if token.tag in ("h2", "h3"):
                toc.append({"level": int(token.tag[1]), "text": plain, "id": f"{lang}-{guide['key']}--{anchor}"})
        if token.type == "inline":
            for child in token.children or []:
                if child.type == "image":
                    child.attrSet("src", _image(child.attrGet("src"), source, out_dir, used_images))
                    child.attrSet("loading", "lazy")
                if child.type == "link_open":
                    child.attrSet("href", _link(child.attrGet("href"), source, lang))
    body = MD.renderer.render(tokens, MD.options, {})
    body = re.sub(rf'<a href="{NO_LINK}">(.*?)</a>', r"\1", body, flags=re.S)  # unpublished file: plain text
    body = re.sub(r"<h1[^>]*>.*?</h1>\s*", "", body, count=1, flags=re.S)  # shown in the guide header
    body = body.replace("<table>", '<div class="tbl"><table>').replace("</table>", "</table></div>")
    body = body.replace("<li>[ ] ", '<li class="check">').replace("<li>[x] ", '<li class="check done">')
    body = re.sub(r"<p>(<img [^>]*>)</p>", r'<figure>\1</figure>', body)
    return {"html": body, "toc": toc}


def _image(src, source, out_dir, used_images):
    path = (source.parent / src).resolve()
    if not path.is_file():
        raise SystemExit(f"Missing image {src} in {source}")
    module = path.relative_to(ELITE_VET).parts[0]
    target = out_dir / "img" / module / path.name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(path, target)
    published = f"img/{module}/{path.name}"
    used_images.add(published)
    return published


def _link(href, source, lang):
    if re.match(r"^[a-z]+:", href) or href.startswith("#"):
        return href
    file_part = href.split("#")[0]
    target = (source.parent / file_part).resolve()
    try:
        key = guide_by_path().get(str(target.relative_to(ELITE_VET)))
    except ValueError:
        key = None
    return f"#{lang}-{key}" if key else NO_LINK


def main():
    out_dir = Path(sys.argv[1]).resolve()
    if (out_dir / "img").exists():
        shutil.rmtree(out_dir / "img")
    out_dir.mkdir(parents=True, exist_ok=True)
    used = set()
    articles, nav = [], []
    for guide in GUIDES:
        entry = {"key": guide["key"], "role": guide["role"], "title": guide["title"], "desc": guide["desc"], "toc": {}}
        for lang in ("cs", "en"):
            result = render(guide, lang, out_dir, used)
            if result is None:
                print(f"MISSING {lang}: {guide['key']}")
                continue
            entry["toc"][lang] = result["toc"]
            articles.append(f'<article class="guide" id="g-{lang}-{guide["key"]}" lang="{lang}" hidden>'
                            f'<h1>{html.escape(guide["title"][lang])}</h1>{result["html"]}</article>')
        nav.append(entry)
    page = (HERE / "template.html").read_text(encoding="utf-8")
    page = page.replace("/*__DATA__*/null", json.dumps({"roles": ROLES, "guides": nav}, ensure_ascii=False))
    page = page.replace("<!--__ARTICLES__-->", "\n".join(articles))
    (out_dir / "navody.html").write_text(page, encoding="utf-8")
    print(f"{out_dir / 'navody.html'}: {len(page) // 1024} kB, {len(articles)} articles, {len(used)} images")


if __name__ == "__main__":
    main()
