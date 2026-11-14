{
    "name": "Elite - tisk uzávěrky pokladny",
    "version": "18.0.1.2.0",
    "category": "Sales/Point of Sale",
    "summary": "Při zavírání pokladny se tiskne uzávěrka na účtenkovou tiskárnu místo stahování reportu.",
    "description": """
Elite - tisk uzávěrky pokladny
==============================

V okně zavírání pokladny nahrazuje tlačítko pro stažení reportu denního prodeje tlačítkem
„Vytisknout uzávěrku“. Uzávěrka se vytiskne na účtenkovou tiskárnu pokladny (bez tiskárny přes
tisk prohlížeče): tržba, platby podle způsobu, hotovost v kase, DPH, slevy, vratky a prodej podle
kategorií, volitelně i po jednotlivém zboží. Uzávěrku kterékoli směny jde zpětně vytisknout
z formuláře směny v backendu (tlačítko „Vytisknout uzávěrku“, i menu Tisk). Popis je v README.md.
""",
    "author": "Michal Varys",
    "website": "https://www.michalvarys.eu",
    "license": "LGPL-3",
    "depends": ["point_of_sale"],
    "data": [
        "report/closing_receipt_report.xml",
        "views/pos_session_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "elite_pos_closing_receipt/static/src/backend/print_closing_receipt.js",
        ],
        "web.report_assets_common": [
            "elite_pos_closing_receipt/static/src/report/closing_receipt_report.scss",
        ],
        "point_of_sale._assets_pos": [
            "elite_pos_closing_receipt/static/src/closing_receipt/closing_receipt.js",
            "elite_pos_closing_receipt/static/src/closing_receipt/closing_receipt.xml",
            "elite_pos_closing_receipt/static/src/closing_receipt/closing_receipt.scss",
            "elite_pos_closing_receipt/static/src/closing_popup/closing_popup_patch.js",
            "elite_pos_closing_receipt/static/src/closing_popup/closing_popup_patch.xml",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": True,
}
