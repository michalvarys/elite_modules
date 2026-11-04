"""Generates the images of the game items and the POS categories; needs Pillow.

Run from the module directory: python3 scripts/gen_images.py
Items without a package (hours, passes, vouchers) get a drawn tile in the brand colours of the Arena
(black and the gold of elite-arena.cz), a category shows a typical product of its group
(static/img/products/<SKU>.jpg) on such a tile.
"""
import math

from PIL import Image, ImageDraw, ImageFilter, ImageFont

SIZE, SCALE = 512, 3
S = SIZE * SCALE
GOLD, BLACK, WHITE = (244, 196, 48), (10, 10, 10), (255, 255, 255)
FONT = "/usr/share/fonts/truetype/lato/Lato-Black.ttf"
PRODUCTS, CATEGORIES = "static/img/products/", "static/img/categories/"


def font(size):
    return ImageFont.truetype(FONT, size * SCALE)


def tile():
    """Black tile with a gold glow in the corner and a gold bar at the bottom."""
    glow = Image.new("RGB", (S, S), BLACK)
    ImageDraw.Draw(glow).ellipse([S * 0.45, -S * 0.45, S * 1.45, S * 0.55], fill=(96, 72, 10))
    image = glow.filter(ImageFilter.GaussianBlur(S * 0.14))
    ImageDraw.Draw(image).rectangle([0, S - 22 * SCALE, S, S], fill=GOLD)
    return image


def text(draw, y, value, size, fill=WHITE, max_width=452):
    """Centred line; the font shrinks to fit. `y` is the centre of the line in tile pixels."""
    while draw.textlength(value, font=font(size)) > max_width * SCALE:
        size -= 2
    draw.text((S / 2, y * SCALE), value, font=font(size), fill=fill, anchor="mm")


def px(*values):
    return [value * SCALE for value in values]


def sun(draw, x, y, r):
    draw.ellipse(px(x - r, y - r, x + r, y + r), fill=GOLD)
    for i in range(8):
        angle = i * math.pi / 4
        points = [(x + math.cos(angle) * r * k, y + math.sin(angle) * r * k) for k in (1.35, 1.8)]
        draw.line(px(*points[0], *points[1]), fill=GOLD, width=9 * SCALE)


def moon(draw, x, y, r):
    mask = Image.new("1", (S, S))
    shape = ImageDraw.Draw(mask)
    shape.ellipse(px(x - r, y - r, x + r, y + r), fill=1)
    shape.ellipse(px(x - r * 0.45, y - r * 1.1, x + r * 1.35, y + r * 0.7), fill=0)
    draw.bitmap((0, 0), mask, fill=GOLD)


def gamepad(draw, x, y, w):
    h = w * 0.56
    draw.rounded_rectangle(px(x - w / 2, y - h / 2, x + w / 2, y + h / 2), radius=h * 0.45 * SCALE, fill=GOLD)
    for side in (-1, 1):
        cx = x + side * w * 0.36
        draw.ellipse(px(cx - w * 0.15, y - h * 0.1, cx + w * 0.15, y + h * 0.82), fill=GOLD)
    cx, arm, thick = x - w * 0.25, w * 0.1, w * 0.035
    draw.rectangle(px(cx - arm, y - thick, cx + arm, y + thick), fill=BLACK)
    draw.rectangle(px(cx - thick, y - arm, cx + thick, y + arm), fill=BLACK)
    r = w * 0.042
    for dx, dy in ((0.17, 0.0), (0.33, 0.0), (0.25, -0.09), (0.25, 0.09)):
        draw.ellipse(px(x + w * dx - r, y + w * dy - r, x + w * dx + r, y + w * dy + r), fill=BLACK)


def wheel(draw, x, y, r):
    width = int(r * 0.2) * SCALE
    draw.ellipse(px(x - r, y - r, x + r, y + r), outline=GOLD, width=width)
    hub = r * 0.27
    draw.ellipse(px(x - hub, y - hub, x + hub, y + hub), fill=GOLD)
    for angle in (math.pi, 0, math.pi / 2):
        draw.line(px(x, y, x + math.cos(angle) * r * 0.92, y + math.sin(angle) * r * 0.92),
                  fill=GOLD, width=width)


def ticket(draw, x, y, w, h):
    draw.rounded_rectangle(px(x - w / 2, y - h / 2, x + w / 2, y + h / 2), radius=20 * SCALE, fill=GOLD)


def hours(sku, number, word):
    image = tile()
    draw = ImageDraw.Draw(image)
    text(draw, 205, number, 250, GOLD)
    text(draw, 395, word, 66)
    save(image, PRODUCTS, sku)


def icon_tile(sku, icon, title, subtitle=None, folder=PRODUCTS):
    image = tile()
    draw = ImageDraw.Draw(image)
    icon(draw)
    text(draw, 355 if subtitle else 385, title, 74)
    if subtitle:
        text(draw, 432, subtitle, 46, GOLD)
    save(image, folder, sku)


def voucher(sku, value):
    image = tile()
    draw = ImageDraw.Draw(image)
    ticket(draw, 256, 205, 440, 230)
    text(draw, 205, value, 104, BLACK, max_width=330)
    text(draw, 402, "VOUCHER", 74)
    save(image, PRODUCTS, sku)


def save(image, folder, name):
    image.resize((SIZE, SIZE), Image.LANCZOS).save("%s%s.jpg" % (folder, name), quality=88)


def cut_out(product):
    """Mask of a packshot: everything but the white background connected to the edges."""
    framed = Image.new("RGB", (product.width + 2, product.height + 2), WHITE)
    framed.paste(product, (1, 1))
    ImageDraw.floodfill(framed, (0, 0), (255, 0, 255), thresh=28)
    mask = Image.new("L", framed.size, 255)
    mask.paste(0, mask=Image.eval(framed.convert("RGB").split()[1], lambda g: 255 if g == 0 else 0))
    return mask.crop((1, 1, product.width + 1, product.height + 1)).filter(ImageFilter.GaussianBlur(0.8))


def product_category(name, sku, round_photo=False):
    image = tile()
    product = Image.open("%s%s.jpg" % (PRODUCTS, sku)).convert("RGB")
    if round_photo:
        mask = Image.new("L", product.size, 0)
        ImageDraw.Draw(mask).ellipse([0, 0, product.width, product.height], fill=255)
    else:
        mask = cut_out(product)
        box = mask.point(lambda v: 255 if v > 128 else 0).getbbox()
        product, mask = product.crop(box), mask.crop(box)
    ratio = min(430 * SCALE / product.width, 430 * SCALE / product.height)
    size = (round(product.width * ratio), round(product.height * ratio))
    position = ((S - size[0]) // 2, (S - 22 * SCALE - size[1]) // 2)
    image.paste(product.resize(size, Image.LANCZOS), position, mask.resize(size, Image.LANCZOS))
    image.resize((256, 256), Image.LANCZOS).save("%s%s.jpg" % (CATEGORIES, name), quality=88)


hours("16052", "1", "HODINA")
hours("16053", "3", "HODINY")
hours("16056", "5", "HODIN")
hours("16054", "8", "HODIN")
hours("16055", "10", "HODIN")
icon_tile("16070", lambda d: sun(d, 256, 165, 70), "DAY PASS", "PO–ČT")
icon_tile("16057", lambda d: sun(d, 256, 165, 70), "DAY PASS", "VÍKEND")
icon_tile("16058", lambda d: moon(d, 256, 170, 95), "NIGHT PASS")
icon_tile("16064", lambda d: gamepad(d, 256, 165, 270), "PLAY STATION", "1 HODINA")
icon_tile("16065", lambda d: wheel(d, 256, 175, 115), "SIM RACING")
voucher("16071", "1000 Kč")
voucher("16072", "500 Kč")

image = tile()
draw = ImageDraw.Draw(image)
text(draw, 195, "FREE", 170, GOLD)
text(draw, 385, "1 HODINA", 74)
save(image, PRODUCTS, "16073")

icon_tile("game", lambda d: gamepad(d, 256, 190, 330), "GAME", folder=CATEGORIES)
image = tile()
draw = ImageDraw.Draw(image)
text(draw, 215, "SERVICE", 100)
text(draw, 325, "FEE", 100, GOLD)
save(image, CATEGORIES, "service_fee")

for category, sku in (
    ("big_shock", "16019"), ("big_shock_500", "16020"), ("big_shock_hroznovy", "16039"),
    ("big_shock_smart", "16024"), ("big_shock_tea", "16027"), ("big_shock_tycinka", "16036"),
    ("big_shock_waio", "16031"), ("nealko", "16015"), ("nealko_voda", "16048"), ("pivo", "16034"),
    ("sladkosti", "16061"),
):
    product_category(category, sku)
product_category("jidlo", "16059", round_photo=True)
