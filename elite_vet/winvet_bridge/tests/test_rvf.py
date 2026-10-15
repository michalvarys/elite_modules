"""Unit tests: TRichView RVF -> plain text (synthetic documents only, no real clinical data)."""

import random
import unittest

from winvet_bridge.rvf import is_rvf, rvf_or_plain, rvf_to_text

from test_normalize_mapping import FakeBlob

CRLF = "\r\n"
DOC_HEADER = ["-8 1 3 1", "-9 0 0 0 0 0 7"]
#: binary-looking component stream (TPF0 marker, control characters, bytes undefined in WIN1250)
BINARY = "\x01\x00\x00TPF0\x0eTRVTableItem\x05Width\x02\x81\x98\x00\x1f"


def doc(*lines: str) -> str:
    return CRLF.join(DOC_HEADER + list(lines)) + CRLF


class RvfToTextTest(unittest.TestCase):
    def test_simple_text_items(self):
        text = doc("0 3 0 0 0 0", "Anamnéza:", "kulhá na levou hrudní", "", "0 1 0 0 0 0", "Terapie: klid")
        self.assertEqual(rvf_to_text(text), "Anamnéza:\nkulhá na levou hrudní\n\nTerapie: klid")

    def test_cp1250_bytes_and_blob_reader(self):
        raw = doc("0 1 0 0 0 0", "Žluťoučký kůň").encode("cp1250")
        self.assertEqual(rvf_to_text(raw), "Žluťoučký kůň")
        self.assertEqual(rvf_to_text(bytearray(raw)), "Žluťoučký kůň")
        blob = FakeBlob(raw)
        self.assertEqual(rvf_to_text(blob), "Žluťoučký kůň")
        self.assertTrue(blob.closed)

    def test_line_count_is_respected(self):
        # text lines that look like headers are text when inside the counted block
        text = doc("0 2 0 0 0 0", "0 1 0 0 0 0", "-60 4 0 0 2 0", "0 1 0 0 0 0", "konec")
        self.assertEqual(rvf_to_text(text), "0 1 0 0 0 0\n-60 4 0 0 2 0\nkonec")

    def test_styled_runs_continue_paragraph(self):
        # ParaNo -1 / option rvioSameAsPrev (1): the item continues the previous paragraph
        text = doc("11 1 0 0 0 0", "Hmotnost:", "0 1 -1 1 0 0", " 12 kg", "10 1 0 0 0 0", "Teplota: 38,5")
        self.assertEqual(rvf_to_text(text), "Hmotnost: 12 kg\nTeplota: 38,5")

    def test_table_and_component_records_are_skipped(self):
        text = doc(
            "-60 4 0 0 2 0 ",
            "TableTrias",
            "unremovable=1",
            "1",
            BINARY,
            "\x02\x00more binary",
            '-10 3 0 0 2 "50" 0',
            "ab",
            "Component",
            "}\x00\x00\x89xyz",
            "0 1 0 0 0 0",
            "Čas: 10:28",
        )
        out = rvf_to_text(text)
        self.assertEqual(out, "Čas: 10:28")
        for leftover in ("TableTrias", "unremovable", "TPF0", "TRV", "Component"):
            self.assertNotIn(leftover, out)

    def test_header_glued_to_binary_line(self):
        text = doc(
            "-60 4 0 0 2 0",
            "TableTrias",
            "unremovable=1",
            "1",
            BINARY + "-8 1 3 1",          # nested cell document glued to the binary
            "0 1 0 0 0 0",
            "Hmotnost: 60, Teplota: 38,2",
            "\x05\x00\x00\x07\x00\x00\x00" + "0 4 0 0 0 0",  # text item glued to the end of binary
            "Anamnéza:",
            "",
            "",
            "zvrací od rána",
            "-60 3 0 0 2 0",
            BINARY,
            "0 1 0 0 0 0",
            "MVDr. Test, 17.09.2026 11:56:25",
        )
        self.assertEqual(
            rvf_to_text(text),
            "Hmotnost: 60, Teplota: 38,2\nAnamnéza:\n\nzvrací od rána\nMVDr. Test, 17.09.2026 11:56:25",
        )

    def test_empty_lines_collapsed_and_trimmed(self):
        text = doc("0 8 0 0 0 0", "", "  ", "první  ", "", "", "", "druhá\t", "")
        self.assertEqual(rvf_to_text(text), "první\n\ndruhá")

    def test_control_characters_removed_binary_lines_dropped(self):
        text = doc("0 3 0 0 0 0", "text s chybou\x00 v textu\x07", BINARY, "\x01\x02\x03\x04ab", "0 1 0 0 0 0", "ok")
        self.assertEqual(rvf_to_text(text), "text s chybou v textu\nok")

    def test_unicode_item(self):
        hex_text = "Kůň".encode("utf-16-le").hex().upper()
        self.assertEqual(rvf_to_text(doc("0 1 0 8 0 0", hex_text)), "Kůň")

    def test_empty_documents(self):
        self.assertIsNone(rvf_to_text(None))
        self.assertIsNone(rvf_to_text(""))
        self.assertIsNone(rvf_to_text(b""))
        self.assertIsNone(rvf_to_text(doc("0 1 0 0 0 0", "", "")))
        self.assertIsNone(rvf_to_text(doc("-60 4 0 0 2 0", "TableTrias", "unremovable=1", "1", BINARY)))

    def test_truncated_document(self):
        self.assertEqual(rvf_to_text(doc("0 5 0 0 0 0", "jen jeden řádek")), "jen jeden řádek")

    def test_never_raises_on_garbage(self):
        rng = random.Random(1234)
        samples = [bytes(rng.randrange(256) for _ in range(rng.randrange(1, 400))) for _ in range(300)]
        samples += [doc("0 999999999999 0 0 0 0", "x"), "0 1 0 0 0 0", 12345, object(), ["list"]]
        for sample in samples:
            out = rvf_to_text(sample)
            self.assertTrue(out is None or isinstance(out, str))
            if out:
                self.assertNotRegex(out, "[\x00-\x09\x0b-\x1f\x7f-\x9f�]")

    def test_reader_that_fails(self):
        class Broken:
            def read(self):
                raise OSError("blob gone")

        self.assertIsNone(rvf_to_text(Broken()))
        self.assertIsNone(rvf_or_plain(Broken()))


class RvfOrPlainTest(unittest.TestCase):
    def test_detection(self):
        self.assertTrue(is_rvf(doc("0 1 0 0 0 0", "x")))
        self.assertTrue(is_rvf(doc("0 1 0 0 0 0", "x").encode("cp1250")))
        self.assertFalse(is_rvf("Vážený zákazníku"))
        self.assertFalse(is_rvf(None))

    def test_plain_text_passes_through(self):
        self.assertEqual(rvf_or_plain("  Vážený zákazníku,\r\nděkujeme.\x00 "), "Vážený zákazníku,\nděkujeme.")
        self.assertEqual(rvf_or_plain("Plain".encode("cp1250")), "Plain")
        self.assertIsNone(rvf_or_plain("   "))
        self.assertIsNone(rvf_or_plain(None))

    def test_rvf_is_converted(self):
        self.assertEqual(rvf_or_plain(doc("0 2 0 0 0 0", "Odčervení:", "1 tbl")), "Odčervení:\n1 tbl")


if __name__ == "__main__":
    unittest.main()
