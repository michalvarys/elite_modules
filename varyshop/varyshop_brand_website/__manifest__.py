{
    "name": "Varyshop – značka na webu",
    "summary": "Patička webu „Běží na Varyshop“, favicona webu a logo Varyshop v editoru webu",
    "version": "18.0.1.0.0",
    "category": "Hidden/Tools",
    "author": "Varyshop",
    "website": "https://www.varyshop.eu",
    "license": "LGPL-3",
    "depends": ["varyshop_brand", "website"],
    "auto_install": True,
    "data": ["views/website_templates.xml"],
    "assets": {
        "web.assets_backend": ["varyshop_brand_website/static/src/website.scss"],
    },
    "post_init_hook": "post_init_hook",
    "uninstall_hook": "uninstall_hook",
    "installable": True,
}
