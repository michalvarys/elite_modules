"""Brand constants shared by the Varyshop brand modules."""

NAME = "Varyshop"
URL = "https://www.varyshop.eu"
COLOR = "#6ea8fe"  # logo blue (--vs-blue on varyshop.eu)
COLOR_DARK = "#3d7bd9"  # UI blue with white text (--vs-blue-dark)
STATIC = "/varyshop_brand/static/img"
FAVICON = STATIC + "/favicon.ico"
LOGO = STATIC + "/logo.png"
LOGO_SVG = STATIC + "/logo.svg"
ICON_IOS = STATIC + "/icon-ios.png"


def url(medium):
    return "%s?utm_source=db&utm_medium=%s" % (URL, medium)
