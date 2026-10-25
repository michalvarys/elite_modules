import re

from lxml import etree

from odoo.tests import HttpCase, tagged

WINVET_URL = "https://reservation.winvet.cz/booking/t24-test"
TEXT = "T24 text pod rezervací"
CENTER_RULE = ".vet-page .evrez-zprava-misto > .evrez-zprava{margin:26px auto 0}"


@tagged("post_install", "-at_install")
class TestWebBookingSwitchFollowups(HttpCase):
    """Task 20: the text under the booking is centered and editable in both modes, and
    /rozpis-lekaru follows the switch (WinVet frame / link to /rezervacni-system)."""

    def setUp(self):
        super().setUp()
        self.setting = self.env["elite.vet.setting"].nastaveni()
        self.setting.write({"booking_url": WINVET_URL})
        self.installed = dict(self.env["res.lang"].get_installed())

    def page(self, url, mode):
        self.setting.web_booking_source = mode
        resp = self.url_open(url)
        self.assertEqual(resp.status_code, 200, url)
        return resp.text

    # ------------------------------------------------------------------ 1. text centered
    def test_text_under_the_booking_centered_in_both_modes(self):
        for lang in ["en_US"] + list(self.installed):
            self.setting.with_context(lang=lang).booking_loading_middle = TEXT
        for mode in ("winvet", "elite"):
            html = self.page("/rezervacni-system", mode)
            # the rule of elite_vet_web that wins over ".vet-page p{margin:0}" is on the page
            self.assertIn(CENTER_RULE, html, mode)
            place, text = html.index('class="evrez-zprava-misto"'), html.index(TEXT)
            self.assertLess(place, text, mode)
        # WinVet keeps its loading behaviour: the script still moves the text into the notice
        html = self.page("/rezervacni-system", "winvet")
        self.assertIn('src="%s"' % WINVET_URL, html)
        self.assertIn('nacitani.appendChild(zprava)', html)
        self.assertIn('ram.addEventListener("load",dolu)', html)

    # ------------------------------------------------------------------ 2. settings form
    def test_text_under_the_booking_has_its_own_group(self):
        view = self.env.ref("elite_vet_web.view_setting_rezervace_form")
        arch = etree.fromstring(self.env["elite.vet.setting"].get_view(view.id, "form")["arch"])
        group = arch.xpath("//group[field[@name='booking_loading_middle']]")
        self.assertEqual(len(group), 1)
        group = group[0]
        self.assertEqual(group.get("string"), "Text pod rezervacemi")
        # visible in both modes; the help line is in the group
        self.assertFalse(group.get("invisible"))
        self.assertIn("ve WinVetu i v Elite Vet", " ".join(group.xpath("string(.)").split()))
        # the loading title and note stay in the WinVet-only group, without the text
        loading = arch.xpath("//group[field[@name='booking_loading_title']]")[0]
        self.assertEqual(loading.get("invisible"), "web_booking_source == 'elite'")
        self.assertTrue(loading.xpath("field[@name='booking_loading_note']"))
        self.assertFalse(loading.xpath(".//field[@name='booking_loading_middle']"))
        self.assertEqual(len(arch.xpath("//field[@name='booking_loading_middle']")), 1)
        # right after the loading group
        self.assertIs(loading.getnext(), group)

    # ------------------------------------------------------------------ 3. /rozpis-lekaru
    def test_schedule_page_winvet_keeps_the_frame(self):
        html = self.page("/rozpis-lekaru", "winvet")
        self.assertIn('class="rs-rez-frame"', html)
        self.assertIn('src="%s"' % WINVET_URL, html)
        self.assertIn('class="rs-rez-nacitani"', html)
        self.assertNotIn("rs-rez-online", html)

    def test_schedule_page_elite_links_to_the_booking(self):
        html = self.page("/rozpis-lekaru", "elite")
        self.assertNotIn('class="rs-rez-frame"', html)
        self.assertNotIn("<iframe", html)
        self.assertNotIn(WINVET_URL, html)
        section = html.split('id="rezervace"')[1].split("</section>")[0]
        self.assertIn('class="rs-rez-online"', section)
        # without a prefix the page is in the visitor's language; url_for adds its prefix
        # unless it is the default one ("/en/rezervacni-system" or "/rezervacni-system")
        hrefs = re.findall(r'href="([^"]*)"', section)
        self.assertEqual(len(hrefs), 1, hrefs)
        self.assertRegex(hrefs[0], r"^(/[A-Za-z_-]+)?/rezervacni-system$")
        self.assertIn("rs-cta", section)
        # the language prefix comes from url_for
        website = self.env["website"].get_current_website()
        default = website.default_lang_id.code
        for lang in website.language_ids.filtered(lambda l: l.code != default):
            html = self.url_open("/%s/rozpis-lekaru" % lang.url_code).text
            section = html.split('id="rezervace"')[1].split("</section>")[0]
            hrefs = re.findall(r'href="([^"]*)"', section)
            self.assertIn("/%s/rezervacni-system" % lang.url_code, hrefs, (lang.code, hrefs))

    def test_schedule_page_texts_translated(self):
        view = self.env.ref("elite_vet_reservation.rozpis_lekaru_booking")
        self.assertIn("We take online bookings on our booking page.", view.arch_db)
        self.assertIn(">Book online<", view.arch_db)
        expected = {"cs_CZ": ("Online objednávky přijímáme", "Objednat se online"),
                    "de_DE": ("Online-Termine buchen Sie", "Online buchen"),
                    "ru_RU": ("Записаться онлайн можно", "Записаться онлайн")}
        for lang, words in expected.items():
            if lang not in self.installed:
                continue
            arch = view.with_context(lang=lang).arch_db
            for word in words:
                self.assertIn(word, arch, lang)
