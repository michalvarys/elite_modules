{
    "name": "Elite Vet - Prodej a sklad",
    "version": "18.0.1.0.0",
    "category": "Sales/Point of Sale",
    "summary": "Česká účetní osnova s cenami včetně DPH, pokladna Recepce, sklad s FEFO a role prodeje a skladu.",
    "description": """
Elite Vet - Prodej a sklad
==========================

Fáze 2+3 náhrady WinVetu: společné nastavení prodeje (pokladna Recepce, nabídky, faktury)
a skladu (šarže, expirace, výdej FEFO). Nastavení se provede při instalaci a lze ho
bezpečně spustit znovu (elite.vet.sale.setup.ensure_setup). Popis je v README.md.
""",
    "author": "Michal Varys",
    "website": "https://www.michalvarys.eu",
    "license": "LGPL-3",
    "depends": [
        "elite_vet_reservation",
        "elite_vet_clinic",
        "elite_vet_winvet",
        "point_of_sale",
        "pos_sale",
        "sale_management",
        "stock",
        "product_expiry",
        "l10n_cz",
    ],
    "data": [
        "security/groups.xml",
        "security/ir.model.access.csv",
        "data/product_data.xml",
        "views/item_views.xml",
        "views/status_views.xml",
        "views/sale_order_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "elite_vet_sale/static/src/board_patch/*",
            "elite_vet_sale/static/src/patient_card_patch/*",
        ],
    },
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": False,
    "auto_install": False,
}
