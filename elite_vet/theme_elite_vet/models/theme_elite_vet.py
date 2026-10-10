from odoo import models


class ThemeEliteVet(models.AbstractModel):
    _inherit = 'theme.utils'

    def _theme_elite_vet_post_copy(self, mod):
        # vet_header/vet_footer inject into //header and //div[@id='footer']
        # directly. Disable the default header/footer variants so only our
        # content renders. theme.utils.disable_view() only touches the global
        # record — we also need to disable any website-specific COW copies
        # that pre-exist on this website (otherwise the default header keeps
        # rendering above ours).
        self.disable_view('website.template_header_default')
        self.disable_view('website.footer_custom')
        website = self.env['website'].get_current_website()
        View = self.env['ir.ui.view'].sudo()
        stale_keys = [
            'website.template_header_default',
            'website.footer_custom',
            'website_sale.template_header_default',
        ]
        stale = View.with_context(active_test=False).search([
            ('key', 'in', stale_keys),
            ('website_id', '=', website.id),
        ])
        if stale:
            stale.write({'active': False})

        self.enable_view('theme_elite_vet.vet_header')
        self.enable_view('theme_elite_vet.vet_footer')

        # Remove default empty homepage pages that would otherwise shadow the
        # theme's own "/" page (Odoo resolves "/" by lowest website_page id).
        website = self.env['website'].get_current_website()
        default_pages = self.env['website.page'].search([
            ('url', '=', '/'),
            ('view_id.key', '=', 'website.homepage'),
            '|', ('website_id', '=', website.id), ('website_id', '=', False),
        ])
        if default_pages:
            default_pages.unlink()

        # Ensure Czech is installed and set as the default language.
        Lang = self.env['res.lang']
        cs = Lang.with_context(active_test=False).search([('code', '=', 'cs_CZ')], limit=1)
        if cs and not cs.active:
            Lang._activate_lang('cs_CZ')
            cs = Lang.search([('code', '=', 'cs_CZ')], limit=1)
        if cs:
            website.default_lang_id = cs.id
            if cs.id not in website.language_ids.ids:
                website.language_ids = [(4, cs.id)]

        # Build navigation menu for this website (done in Python to avoid
        # theme.website.menu parent_id recursion issues during _theme_load).
        Menu = self.env['website.menu']
        root = website.menu_id
        # Remove existing children so we have a clean slate on reapply.
        root.child_id.unlink()
        menu_items = [
            ('Služby', '/#sluzby', 10),
            ('O nás', '/#o-nas', 20),
            ('Recenze', '/#recenze', 30),
            ('Kariéra', '/#kariera', 40),
            ('Kontakt', '/#kontakt', 50),
        ]
        for name, url, seq in menu_items:
            Menu.create({
                'name': name,
                'url': url,
                'parent_id': root.id,
                'sequence': seq,
                'website_id': website.id,
            })
