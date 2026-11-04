"""Generates the images of the goods without a photo and of the POS categories; needs Pillow.

Run from the module directory: python3 scripts/gen_images.py
Photos are listed in static/img/products/manifest.csv and stay as they are. Goods without a package
get a photo of their kind (GENERIC), loose goods with the weight in the corner. The rest get a tile
with the name in the brand colours of the shop (black and the lime of the elite-trafika.cz logo).
Sources and licences of the kind photos and category images: static/img/generic/manifest.csv.
"""
import csv
import re

from PIL import Image, ImageDraw, ImageFilter, ImageFont

SIZE, SCALE = 320, 2
S = SIZE * SCALE
LIME, BLACK, WHITE = (156, 228, 36), (10, 10, 10), (255, 255, 255)
FONT = "/usr/share/fonts/truetype/lato/Lato-Black.ttf"
PRODUCTS, CATEGORIES, GENERIC_PHOTOS = "static/img/products/", "static/img/categories/", "static/img/generic/"
BAR, MARGIN = 14 * SCALE, 22 * SCALE
SIZE_SUFFIX = re.compile(r"^(.*\S)\s+(\d+(?:[,.]\d+)?\s?(?:g|ml|l|ks|pcs|mg)|\d+\s?%)$", re.I)
# (group, text in the name or None for the whole group, image of static/img/generic or None for the
# POS category image); the first match wins. Goods whose brand a generic photo would get wrong stay tiles.
GENERIC = [
    ("KVĚTY volné", "CHERRY", "bud-2"), ("KVĚTY volné", "PURPLE", "bud-2"), ("KVĚTY volné", "Royal", "bud-2"),
    ("KVĚTY volné", "WHITE", "bud-3"), ("KVĚTY volné", "MoonRock", "bud-3"), ("KVĚTY volné", "SC Italy", "bud-3"),
    ("KVĚTY volné", "AMNESIA", "bud-3"), ("KVĚTY volné", None, "bud-1"),
    ("Canna Bloom - Květy", None, "bud-1"),
    ("Hasish", "Black", "hash-dark"), ("Hasish", None, "hash-light"),
    ("PIPE a BONG", "BONG", "bong"), ("PIPE a BONG", "Drtička", "grinder"), ("PIPE a BONG", None, "glass-pipe"),
    ("VÁHY", None, "digital-scale"), ("PYTLÍKY", None, "zip-bags"),
    ("Zapalovače", "plyn", "gas-refill"), ("Zapalovače", None, "lighter"),
    ("Příslušenství a zboží", "plyn", "gas-refill"), ("Příslušenství a zboží", "drtička", "grinder"),
    ("Příslušenství a zboží", "power", "power-bank"),
    ("TYSON", "pre-roled", "joint"), ("TYSON", "Blunt", "joint"),
    ("Tabáky-Dutinky-Papirky", "filters", "filter-tips"),
    ("Tabáky-Dutinky-Papirky", None, "tabaky"), ("Dutinky", None, "dutinky"), ("Doutníky", None, "doutniky"),
    ("ČOKOLÁDA", None, "cokolada"), ("COOKIES", None, "cookies"), ("Lízátka - DROPS", None, "lizatka"),
    ("Gumies - Shots", None, "gumies"), ("Oleje - kapky - Tea", None, "oleje"), ("KLEANER", None, "kleaner"),
]
CATEGORY_IMAGES = {"tabaky", "dutinky", "doutniky", "cokolada", "cookies", "lizatka", "gumies", "oleje", "kleaner"}
BADGE_GROUPS = ("KVĚTY volné", "Hasish", "Canna Bloom - Květy")


def font(size):
    return ImageFont.truetype(FONT, size * SCALE)


def tile():
    """Black tile with a lime glow in the corner and a lime bar at the bottom."""
    glow = Image.new("RGB", (S, S), BLACK)
    ImageDraw.Draw(glow).ellipse([S * 0.45, -S * 0.45, S * 1.45, S * 0.55], fill=(44, 92, 10))
    image = glow.filter(ImageFilter.GaussianBlur(S * 0.14))
    ImageDraw.Draw(image).rectangle([0, S - BAR, S, S], fill=LIME)
    return image


def wrap(draw, value, size, width):
    lines, current = [], ""
    for word in value.split():
        candidate = (current + " " + word).strip()
        if draw.textlength(candidate, font=font(size)) <= width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    return lines + [current] if current else lines


def fit(draw, value, width, height, largest):
    """Largest font size at which the wrapped text fits the box, and its lines."""
    for size in range(largest, 13, -2):
        lines = wrap(draw, value, size, width)
        fits = all(draw.textlength(line, font=font(size)) <= width for line in lines)
        if fits and len(lines) * size * 1.18 * SCALE <= height:
            return size, lines
    return 14, wrap(draw, value, 14, width)


def block(draw, value, centre, height, largest, fill):
    size, lines = fit(draw, value, S - 2 * MARGIN, height, largest)
    line_height = size * 1.18 * SCALE
    y = centre - line_height * (len(lines) - 1) / 2
    for line in lines:
        draw.text((S / 2, y), line, font=font(size), fill=fill, anchor="mm")
        y += line_height


def name_tile(name, group=None):
    image = tile()
    draw = ImageDraw.Draw(image)
    top = MARGIN
    if group:
        block(draw, group.upper(), top + 14 * SCALE, 30 * SCALE, 19, LIME)
        top += 34 * SCALE
    bottom = S - BAR - MARGIN
    match = SIZE_SUFFIX.match(name)
    if match:
        block(draw, match[2], bottom - 34 * SCALE, 68 * SCALE, 60, LIME)
        bottom -= 76 * SCALE
        name = match[1]
    block(draw, name, (top + bottom) / 2, bottom - top, 52, WHITE)
    return image


def save(image, path, size=SIZE):
    image.resize((size, size), Image.LANCZOS).save(path, quality=82, optimize=True)


def generic_image(row):
    for group, part, image in GENERIC:
        if row["skupina"] == group and (part is None or part.lower() in row["název"].lower()):
            return "%s%s.jpg" % (CATEGORIES if image in CATEGORY_IMAGES else GENERIC_PHOTOS, image)
    return None


def generic_photo(path, row):
    """A photo of the kind of goods; loose goods get the weight in the corner, it tells the items apart."""
    image = Image.open(path).convert("RGB").resize((S, S), Image.LANCZOS)
    match = re.search(r"(\d+)\s?g\b", row["název"], re.I)
    if match and row["skupina"] in BADGE_GROUPS:
        draw = ImageDraw.Draw(image)
        label = match[1] + "g"
        width = draw.textlength(label, font=font(62)) + 28 * SCALE
        draw.rounded_rectangle([S - width - 8 * SCALE, S - 88 * SCALE, S - 8 * SCALE, S - 8 * SCALE],
                               radius=12 * SCALE, fill=LIME)
        draw.text((S - 8 * SCALE - width / 2, S - 48 * SCALE), label, font=font(62), fill=BLACK, anchor="mm")
    return image


def main():
    with open(PRODUCTS + "manifest.csv", encoding="utf-8") as f:
        photos = {row["id_dotykacka"] for row in csv.DictReader(f)}
    with open("zbozi.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["id_dotykacka"] in photos:
                continue
            path = generic_image(row)
            image = generic_photo(path, row) if path else name_tile(row["název"], row["skupina"])
            save(image, "%s%s.jpg" % (PRODUCTS, row["id_dotykacka"]))


main()
