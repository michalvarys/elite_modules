"""Request 25. 10.: on /rozpis-lekaru the specialization icons are only in the bubble of the name."""
from datetime import date

from lxml import html as lxml_html

from odoo.tests import HttpCase, tagged

PNG_1PX = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")


@tagged("post_install", "-at_install")
class TestRosterSpecsInBubble(HttpCase):

    def setUp(self):
        super().setUp()
        section = self.env["elite.vet.team.section"].create({"name": "Sekce T22"})
        icon = self.env["elite.vet.team.icon"].create({"name": "Srdce T22", "image": PNG_1PX})
        spec = self.env["elite.vet.team.specialization"].create({"name": "Kardiologie T22", "icon_id": icon.id})
        member = self.env["elite.vet.team.member"].create({
            "name": "MVDr. Srdíčková T22", "section_id": section.id, "specialization_ids": [(6, 0, spec.ids)]})
        self.doctor = self.env["elite.vet.doctor"].create({"name": "MVDr. Srdíčková T22", "member_id": member.id})
        self.plain = self.env["elite.vet.doctor"].create({"name": "MVDr. Bezikonová T22"})
        work = self.env["elite.vet.shift.type"].create({"name": "Služba T22", "time_from": 8, "time_to": 14})
        today = date.today()
        for doctor in (self.doctor, self.plain):
            self.env["elite.vet.shift"].create({"date": today, "doctor_id": doctor.id, "type_id": work.id})

    def test_icons_only_in_the_bubble(self):
        resp = self.url_open("/rozpis-lekaru")
        self.assertEqual(resp.status_code, 200)
        tree = lxml_html.fromstring(resp.content)
        docs = [d for d in tree.xpath('//span[contains(concat(" ", @class, " "), " rs-doc ")]')
                if "MVDr. Srdíčková T22" in d.text_content()]
        self.assertEqual(len(docs), 1)   # one shift, both names joined with +
        doc = docs[0]
        self.assertEqual(doc.get("tabindex"), "0")
        self.assertEqual(doc.get("role"), "button")
        self.assertEqual(doc.get("aria-expanded"), "false")
        tip = doc.xpath('./span[@class="rs-tip"]')[0]
        # the cell itself (outside the bubble): dot and names, no icons
        doc.remove(tip)
        self.assertFalse(doc.xpath('.//*[contains(@class, "rs-spec")]'))
        self.assertIn("MVDr. Bezikonová T22", doc.text_content())
        # the bubble: shift time, then only the doctor with a specialization (named, two on the shift)
        self.assertIn("8:00–14:00", tip.xpath('.//span[@class="rs-tip-time"]')[0].text_content())
        rows = tip.xpath('.//span[@class="rs-tip-doc"]')
        self.assertEqual(len(rows), 1)
        self.assertIn("MVDr. Srdíčková T22", rows[0].xpath('./span[@class="rs-tip-name"]')[0].text_content())
        self.assertIn("Kardiologie T22", rows[0].xpath('.//span[@class="rs-spec-name"]')[0].text_content())
        self.assertTrue(rows[0].xpath('.//img[contains(@class, "ev-spec-ico")]'))

    def test_narrow_view_shows_only_the_time_with_a_colour_legend(self):
        """Task 25: under the name (narrow / touch view) only "8:00–14:00"; the shift name is in its own
        span hidden by those media queries, a short legend of the colours sits above each month."""
        resp = self.url_open("/rozpis-lekaru")
        tree = lxml_html.fromstring(resp.content)
        doc = [d for d in tree.xpath('//span[contains(concat(" ", @class, " "), " rs-doc ")]')
               if "MVDr. Srdíčková T22" in d.text_content()][0]
        time_span = doc.xpath('.//span[@class="rs-tip-time"]')[0]
        type_span = time_span.xpath('./span[@class="rs-tip-type"]')[0]
        self.assertIn("Služba T22", type_span.text_content())
        # what stays visible: the text after the hidden shift name
        self.assertEqual((type_span.tail or "").strip(), "8:00–14:00")
        self.assertEqual(time_span.text_content().replace(type_span.text_content(), "").strip(), "8:00–14:00")
        legend = tree.xpath('//div[@class="rs-month-legend"]')
        self.assertTrue(legend)
        self.assertIn("Služba T22", legend[0].text_content())
        css = "".join(tree.xpath("//style/text()"))
        self.assertIn(".rs-tip .rs-tip-type { display: none; }", css)
        self.assertIn(".rs-month-legend { display: flex; }", css)
