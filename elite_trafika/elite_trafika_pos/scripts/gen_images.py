"""Generates the images of the goods without a photo and of the POS categories; needs Pillow.

Run from the module directory: python3 scripts/gen_images.py
Photos are listed in static/img/products/manifest.csv and stay as they are; all other goods get
a tile with the name in the brand colours of the shop (black and the lime of the elite-trafika.cz logo). A category
gets a tile with its name, or a typical product of the group from PHOTO_CATEGORIES.
"""
import csv
import os
import re

from PIL import Image, ImageDraw, ImageFilter, ImageFont

SIZE, SCALE = 320, 2
S = SIZE * SCALE
LIME, BLACK, WHITE = (156, 228, 36), (10, 10, 10), (255, 255, 255)
FONT = "/usr/share/fonts/truetype/lato/Lato-Black.ttf"
PRODUCTS, CATEGORIES = "static/img/products/", "static/img/categories/"
BAR, MARGIN = 14 * SCALE, 22 * SCALE
SIZE_SUFFIX = re.compile(r"^(.*\S)\s+(\d+(?:[,.]\d+)?\s?(?:g|ml|l|ks|pcs|mg)|\d+\s?%)$", re.I)
# category key -> id_dotykacka of a photo showing the group
PHOTO_CATEGORIES = {
    "energy": "1945892553900715", "alcohol": "3177298316807957", "veo": "1841524833115975",
    "neo": "232423925605050", "velo": "341666418783346", "iqos": "3318370812691614",
    "vuse": "2066374961007149", "syx_bar": "199653325149893", "syx_pod": "993578029816490",
    "napoje": "2450942038331154", "dutinky": "4091490695778851",
}


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


def cut_out(product):
    """Mask of a packshot: everything but the white background connected to the edges."""
    framed = Image.new("RGB", (product.width + 2, product.height + 2), WHITE)
    framed.paste(product, (1, 1))
    ImageDraw.floodfill(framed, (0, 0), (255, 0, 255), thresh=28)
    mask = Image.new("L", framed.size, 255)
    mask.paste(0, mask=Image.eval(framed.split()[1], lambda g: 255 if g == 0 else 0))
    return mask.crop((1, 1, product.width + 1, product.height + 1)).filter(ImageFilter.GaussianBlur(0.8))


def photo_category(path, product_id):
    image = tile()
    product = Image.open("%s%s.jpg" % (PRODUCTS, product_id)).convert("RGB")
    mask = cut_out(product)
    box = mask.point(lambda v: 255 if v > 128 else 0).getbbox()
    product, mask = product.crop(box), mask.crop(box)
    ratio = min((S - 2 * MARGIN) / product.width, (S - BAR - 2 * MARGIN) / product.height)
    size = (round(product.width * ratio), round(product.height * ratio))
    position = ((S - size[0]) // 2, (S - BAR - size[1]) // 2)
    image.paste(product.resize(size, Image.LANCZOS), position, mask.resize(size, Image.LANCZOS))
    save(image, path, 256)


def main():
    photos = set()
    if os.path.exists(PRODUCTS + "manifest.csv"):
        with open(PRODUCTS + "manifest.csv", encoding="utf-8") as f:
            photos = {row["id_dotykacka"] for row in csv.DictReader(f)}
    with open("zbozi.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["id_dotykacka"] not in photos:
                save(name_tile(row["název"], row["skupina"]), "%s%s.jpg" % (PRODUCTS, row["id_dotykacka"]))
    with open("data/product_category_data.xml", encoding="utf-8") as f:
        data = f.read()
    pattern = r'<record id="pos_category_(\w+)" model="pos.category">\s*<field name="name">(.*?)</field>'
    for key, name in re.findall(pattern, data):
        path = "%s%s.jpg" % (CATEGORIES, key)
        if key in PHOTO_CATEGORIES:
            photo_category(path, PHOTO_CATEGORIES[key])
        else:
            save(name_tile(name.replace("&amp;", "&")), path, 256)


main()
