{
    "name": "Varyshop – značka v pokladně",
    "summary": "Logo Varyshop v pokladně, na šetřiči obrazovky, na zákaznickém displeji a na účtence",
    "version": "18.0.1.0.0",
    "category": "Hidden/Tools",
    "author": "Varyshop",
    "website": "https://www.varyshop.eu",
    "license": "LGPL-3",
    "depends": ["varyshop_brand", "point_of_sale"],
    "auto_install": True,
    "data": ["views/pos_templates.xml"],
    "assets": {
        "point_of_sale._assets_pos": [
            "varyshop_brand/static/src/brand.js",
            "varyshop_brand/static/src/dialog.xml",
            "varyshop_brand_pos/static/src/pos.xml",
            "varyshop_brand_pos/static/src/odoo_logo.xml",
        ],
        "point_of_sale.customer_display_assets": [
            "varyshop_brand_pos/static/src/odoo_logo.xml",
        ],
    },
    "installable": True,
}
