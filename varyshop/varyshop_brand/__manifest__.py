{
    "name": "Varyshop – značka",
    "summary": "Logo, barvy a značka Varyshop místo Odoo: přihlášení, titulek okna, ikony, e-maily, pokladna a web",
    "version": "18.0.1.0.0",
    "category": "Hidden/Tools",
    "author": "Varyshop",
    "website": "https://www.varyshop.eu",
    "license": "LGPL-3",
    "depends": ["web", "mail"],
    "data": [
        "views/webclient_templates.xml",
        "views/mail_templates.xml",
    ],
    "assets": {
        "web._assets_primary_variables": [
            ("before", "web/static/src/scss/primary_variables.scss",
             "varyshop_brand/static/src/scss/primary_variables.scss"),
        ],
        "web.assets_backend": [
            "varyshop_brand/static/src/brand.js",
            "varyshop_brand/static/src/dialog.xml",
            "varyshop_brand/static/src/mail_message.js",
            "varyshop_brand/static/src/scss/backend.scss",
            "varyshop_brand/static/src/webclient/**/*",
        ],
    },
    "post_init_hook": "post_init_hook",
    "uninstall_hook": "uninstall_hook",
    "installable": True,
    "auto_install": True,
}
