"""TRichView RVF document -> plain text (WinVet clinical notes ``DENNI_ZAZNAM.DEKURS``, ``FRAZE.TEXT``).

An RVF document saved in text mode is a sequence of records separated by ``\\r\\n``. Every record
starts with a header line of 6 or 7 space separated fields::

    <style/type> <line count> <paragraph no> <item options> <save type> <tag> [<extra>]

* ``style >= 0`` with save type ``0`` is a text item: the next ``<line count>`` lines are text
  paragraphs (style = index of the text style - bold, colour ... - irrelevant for plain text).
  Paragraph number ``-1`` or option bit ``1`` (``rvioSameAsPrev``) continues the previous
  paragraph; option bit ``8`` (``rvioUnicode``) stores the text as hex-encoded UTF-16LE.
* Negative types are tables, pictures, controls, document properties ... Their content contains
  binary ``TPF0`` component streams that may include line breaks, so their line counts are not
  trusted: everything is skipped until the next line that is (or ends with) a record header. Table
  cells are nested RVF documents; their text items are extracted like any other text item.
* Tables (``TRVTableItem``): the component stream holds the size (``C <rows> <cols>`` as Delphi
  integers) and every cell starts with ``<colspan> <rowspan> "TD"``. The cells of a table with two
  or more columns are put back on their rows: one line per row, cells separated by a tab (lab
  results). Single column tables (frames around text) stay ordinary paragraphs. A table whose
  structure does not add up is flattened (one paragraph per cell) as before.

A header may be glued to the end of a binary line (``<binary>0 27 0 0 0 0``) - such trailing
headers are detected too. The converter never raises; it returns ``None`` when nothing readable
is left (or the input is not RVF at all, see :func:`rvf_or_plain`).
"""

from __future__ import annotations

import logging
import re
from typing import Any, List, Optional

from .normalize import norm_value, read_blob

log = logging.getLogger(__name__)

OPTION_SAME_AS_PREV = 1
OPTION_UNICODE = 8

_NUM = r"-?\d{1,9}"
_HEADER_BODY = rf"({_NUM}) (\d{{1,9}}) ({_NUM}) ({_NUM}) ({_NUM}) (?:\"[^\"\r\n]*\"|{_NUM})(?: {_NUM})?"
_HEADER_RE = re.compile(rf"{_HEADER_BODY} *")
_TRAILING_HEADER_RE = re.compile(rf"(?<![\d-]){_HEADER_BODY} *$")
#: RVF documents start with the version record ``-8 1 <version> ...``.
_RVF_START_RE = re.compile(r"^\s*-8 \d+ \d+")
_HEX_RE = re.compile(r"(?:[0-9A-Fa-f]{4})+")
#: Fragments of binary component streams that must never reach the output.
_BINARY_RE = re.compile("TPF0|TRV[A-Z][a-z]|TRichView")
#: Control characters and U+FFFD (bytes undefined in WIN1250).
_BAD_CHAR_RE = re.compile("[\\x00-\\x08\\x0a-\\x1f\\x7f-\\x9f\\ufffd]")
#: Delphi binary integers: ``\x02`` + 1 byte (Int8) or ``\x03`` + 2 bytes little endian (Int16).
_INT = "(?:\x02(.)|\x03(..))"
_TABLE_SIZE_RE = re.compile(f"\x01C{_INT}{_INT}\x01", re.S)
_TABLE_CELL_RE = re.compile(f"{_INT}{_INT}\x02TD\x00", re.S)
CELL_SEPARATOR = "\t"
#: Upper bound for the line count of one text item (protects against garbage headers).
MAX_ITEM_LINES = 100000


def _decode(value: Any) -> Optional[str]:
    value = read_blob(value)
    if value is None:
        return None
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).decode("cp1250", errors="replace")
    if isinstance(value, str):
        return value
    return None


def is_rvf(value: Any) -> bool:
    try:
        text = _decode(value)
    except Exception:  # pragma: no cover - defensive
        return False
    return bool(text) and bool(_RVF_START_RE.match(text))


def _parse_header(line: str, allow_trailing: bool):
    match = _HEADER_RE.fullmatch(line)
    if match is None and allow_trailing:
        match = _TRAILING_HEADER_RE.search(line)
    if match is None:
        return None
    style, count, para, options, save_type = (int(g) for g in match.groups())
    return style, count, para, options, save_type


def _decode_unicode(line: str) -> str:
    if _HEX_RE.fullmatch(line):
        try:
            return bytes.fromhex(line).decode("utf-16-le", errors="replace")
        except ValueError:
            return line
    return line


def _clean_line(line: str) -> Optional[str]:
    """Strip control characters; ``None`` when the line is a fragment of binary data."""
    if _BINARY_RE.search(line):
        return None
    bad = len(_BAD_CHAR_RE.findall(line))
    if bad and bad * 10 > len(line):
        return None
    return _BAD_CHAR_RE.sub("", line.replace("\t", " ")).rstrip()


def _int(short: Optional[str], long: Optional[str]) -> Optional[int]:
    """Value of a Delphi Int8 / Int16 decoded from WIN1250 (``None`` when a byte got lost)."""
    try:
        raw = (short if short is not None else long).encode("cp1250")
    except (UnicodeEncodeError, AttributeError):
        return None
    return int.from_bytes(raw, "little", signed=True)


class _Table:
    """Cells of one table, collected while its component stream and nested documents are read."""

    def __init__(self, rows: int, cols: int):
        self.rows, self.cols = rows, cols
        self.cells: List[tuple] = []  # (colspan, rowspan, paragraphs)
        self.area = 0

    @property
    def complete(self) -> bool:
        return self.area >= self.rows * self.cols

    def add_cell(self, colspan: Optional[int], rowspan: Optional[int]) -> bool:
        if not colspan or not rowspan or colspan < 1 or rowspan < 1 or self.complete:
            return False
        self.cells.append((colspan, rowspan, []))
        self.area += colspan * rowspan
        return True

    def paragraphs(self) -> List[str]:
        if self.cols < 2 or self.area != self.rows * self.cols:
            return [p for _c, _r, cell in self.cells for p in cell]
        grid = [[None] * self.cols for _ in range(self.rows)]
        cursor = 0
        for colspan, rowspan, cell in self.cells:
            while cursor < self.rows * self.cols and grid[cursor // self.cols][cursor % self.cols] is not None:
                cursor += 1
            if cursor >= self.rows * self.cols:
                return [p for _c, _r, c in self.cells for p in c]
            row, col = divmod(cursor, self.cols)
            for r in range(row, min(row + rowspan, self.rows)):
                for c in range(col, min(col + colspan, self.cols)):
                    grid[r][c] = ""
            grid[row][col] = " ".join(p.strip() for p in cell if p.strip())
        out = []
        for row in grid:
            cells = [c or "" for c in row]
            while cells and not cells[-1]:
                cells.pop()
            if cells:
                out.append(CELL_SEPARATOR.join(cells))
        return out


def _extract(text: str) -> List[str]:
    lines = text.split("\r\n")
    paragraphs: List[str] = []
    target = paragraphs  # where text items go: the document or the open table cell
    table: Optional[_Table] = None
    index, total = 0, len(lines)
    while index < total:
        line = lines[index]
        index += 1
        header = _parse_header(line, allow_trailing=True)
        if header is None or _HEADER_RE.fullmatch(line) is None:
            # component stream (possibly with a header glued to its end): table structure
            size = _TABLE_SIZE_RE.search(line)
            if table is not None and (table.complete or size):
                paragraphs.extend(table.paragraphs())
                table, target = None, paragraphs
            start = 0
            if size:
                rows, cols = _int(size.group(1), size.group(2)), _int(size.group(3), size.group(4))
                if rows and cols and rows > 0 and cols > 0:
                    table, start = _Table(rows, cols), size.end()
            if table is not None:
                for cell in _TABLE_CELL_RE.finditer(line, start):
                    if table.add_cell(_int(cell.group(1), cell.group(2)), _int(cell.group(3), cell.group(4))):
                        target = table.cells[-1][2]
        if header is None:
            continue  # content of a skipped (non-text) record
        style, count, para, options, save_type = header
        if style < 0 or save_type != 0 or count > MAX_ITEM_LINES:
            continue  # non-text record: skip until the next header
        continuation = para == -1 or bool(options & OPTION_SAME_AS_PREV)
        for offset, raw in enumerate(lines[index:index + count]):
            if options & OPTION_UNICODE:
                raw = _decode_unicode(raw)
            cleaned = _clean_line(raw)
            if cleaned is None:
                continue
            if offset == 0 and continuation and target:
                target[-1] = (target[-1] + cleaned).rstrip()
            else:
                target.append(cleaned)
        index += count
    if table is not None:
        paragraphs.extend(table.paragraphs())
    return paragraphs


def _join(paragraphs: List[str]) -> Optional[str]:
    out: List[str] = []
    for paragraph in paragraphs:
        paragraph = paragraph.rstrip()
        if not paragraph.strip():
            if out and out[-1] == "":
                continue
            paragraph = ""
        out.append(paragraph)
    result = "\n".join(out).strip()
    return result or None


def rvf_to_text(value: Any) -> Optional[str]:
    """Plain text of an RVF document (``str``, WIN1250 ``bytes`` or a BLOB reader); never raises."""
    try:
        text = _decode(value)
        if not text:
            return None
        return _join(_extract(text))
    except Exception as exc:  # garbage must never stop a sync run
        log.warning("RVF conversion failed (%s) - notes sent as null", type(exc).__name__)
        return None


def rvf_or_plain(value: Any) -> Optional[str]:
    """RVF -> plain text; a value that is not an RVF document is normalised as ordinary text."""
    try:
        text = _decode(value)
        if text is None:
            return None
        if _RVF_START_RE.match(text):
            return rvf_to_text(text)
        return norm_value(text.replace("\r\n", "\n"))
    except Exception as exc:
        log.warning("Text conversion failed (%s) - sent as null", type(exc).__name__)
        return None
