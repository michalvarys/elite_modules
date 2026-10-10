{
    'name': 'Elite Vet Theme',
    'version': '18.0.1.1.0',
    'category': 'Theme/Health',
    'summary': 'Calm modern theme for Elite Vet veterinary clinic in Karlovy Vary',
    'description': """
Elite Vet Theme
===============

A clean, trust-focused theme for a veterinary clinic with:
- Navy + teal palette, white cards, rounded badges
- Custom header with clinic branding and call CTA
- Hero with feature card and stats
- Services grid (6 items)
- About / team section
- Google reviews highlight
- Careers call-to-action (email CTA)
- Contact block with address, opening hours, and map
    """,
    'author': 'Elite Vet',
    'website': 'https://elitevet.cz',
    'license': 'LGPL-3',
    'depends': [
        'theme_common',
        'website',
    ],
    'data': [
        'data/generate_primary_template.xml',
        'data/ir_asset.xml',
        'views/layout.xml',
        'views/snippets/s_vet_hero.xml',
        'views/snippets/s_vet_services.xml',
        'views/snippets/s_vet_about.xml',
        'views/snippets/s_vet_testimonials.xml',
        'views/snippets/s_vet_careers.xml',
        'views/snippets/s_vet_contact.xml',
        'views/snippets/snippets_registry.xml',
        'views/pages.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'theme_elite_vet/static/src/js/main.js',
        ],
    },
    'images': [
        'static/description/icon.png',
    ],
    'configurator_snippets': {
        'homepage': [
            's_vet_hero',
            's_vet_services',
            's_vet_about',
            's_vet_testimonials',
            's_vet_careers',
            's_vet_contact',
        ],
    },
    'installable': True,
    'auto_install': False,
}
