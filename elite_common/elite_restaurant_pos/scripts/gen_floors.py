"""Draws the floor plan backgrounds static/img/floor_<key>.png of a restaurant module from its floors.json:
coloured sections with their names and free labels. Tables are not drawn; the till draws them.

usage: python3 elite_common/elite_restaurant_pos/scripts/gen_floors.py <restaurant module dir>"""
import json
import os
import sys

from PIL import Image, ImageDraw, ImageFont

MODULE_DIR = sys.argv[1]
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
TEXT = "#3C4043"


def font(size):
    return ImageFont.truetype(FONT, size)


with open(os.path.join(MODULE_DIR, "floors.json"), encoding="utf-8") as f:
    layout = json.load(f)
os.makedirs(os.path.join(MODULE_DIR, "static", "img"), exist_ok=True)
for floor in layout["floors"]:
    image = Image.new("RGB", tuple(floor["size"]), floor["background"])
    draw = ImageDraw.Draw(image)
    for section in floor["sections"]:
        x, y, w, h = section["box"]
        draw.rectangle([x, y, x + w - 1, y + h - 1], fill=section["color"])
        if section["name"]:
            draw.text((x + w / 2, y + 22), section["name"], fill=TEXT, font=font(22), anchor="mm")
    for label in floor.get("labels", []):
        draw.text(tuple(label["at"]), label["text"], fill=TEXT, font=font(label["size"]), anchor="mm")
    path = os.path.join(MODULE_DIR, "static", "img", "floor_%s.png" % floor["key"])
    image.save(path, optimize=True)
    print(path)
