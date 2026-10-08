# -*- coding: utf-8 -*-
from odoo import api, fields, models

from .tools import video_embed_url, whatsapp_url

RE_MENU_AR = {
    '/estate/projects': ('Projects', 'المشروعات'),
    '/estate/units': ('Units', 'الوحدات'),
    '/estate/services': ('Services', 'الخدمات'),
    '/estate/about': ('About Us', 'من نحن'),
}
RE_BRAND_PARAM = 're_developer_website.brand_palette_applied'
# El Motawer brand: gold on deep navy (sampled from the company logo)
RE_BRAND_PALETTE = {
    'o-color-1': '#C8A45D',  # gold - buttons, accents
    'o-color-2': '#13233F',  # navy - secondary
    'o-color-3': '#F7F3EA',  # warm cream - light sections
    'o-color-4': '#FFFFFF',  # white
    'o-color-5': '#06101E',  # deep navy - header, footer, hero
    # header / footer use colour combination 5 (deep navy) so the gold logo
    # sits on its own background
    'menu': 5,
    'footer': 5,
    'copyright': 5,
}
RE_BRAND_LAYOUT = {
    'logo-height': '2.6rem',
}
RE_DEFAULTS_AR = {
    're_tagline': ('Building Communities That Last', 'نبني مجتمعات تدوم'),
    're_overview_title': ('Company Overview', 'نبذة عن الشركة'),
    're_office_hours': ('Sat - Thu, 10:00 AM - 7:00 PM', 'السبت - الخميس، من 10 صباحاً حتى 7 مساءً'),
}


class Website(models.Model):
    _inherit = 'website'

    # Hero
    re_tagline = fields.Char('Hero Tagline', translate=True, default='Building Communities That Last')
    re_hero_subtitle = fields.Text('Hero Subtitle', translate=True)
    re_hero_image = fields.Image('Hero Image', max_width=1920, max_height=1080)

    # Company overview / interview
    re_overview_title = fields.Char('Overview Title', translate=True, default='Company Overview')
    re_overview = fields.Html('Company Overview', translate=True, sanitize_attributes=False)
    re_video_url = fields.Char('Company Interview / Overview Video', help='YouTube or Vimeo link.')
    re_video_embed_url = fields.Char(compute='_compute_re_links')
    re_vision = fields.Text('Vision', translate=True)
    re_mission = fields.Text('Mission', translate=True)

    # Key figures
    re_founded_year = fields.Integer('Founded In')
    re_years_experience = fields.Integer('Years of Experience')
    re_projects_count = fields.Integer('Projects Delivered')
    re_units_count = fields.Integer('Units Delivered')
    re_clients_count = fields.Integer('Happy Clients')

    # Contact
    re_whatsapp = fields.Char('WhatsApp Number')
    re_whatsapp_url = fields.Char(compute='_compute_re_links')
    re_office_hours = fields.Char('Office Hours', translate=True, default='Sat - Thu, 10:00 AM - 7:00 PM')

    # Lead routing
    re_lead_team_id = fields.Many2one('crm.team', 'Inquiries Sales Team')
    re_lead_user_id = fields.Many2one('res.users', 'Inquiries Salesperson', domain=[('share', '=', False)])

    @api.model
    def _re_enable_arabic(self):
        """Add Arabic next to English on every website so the header shows the
        English / العربية switcher. Safe to run on every install / upgrade."""
        arabic = self.env.ref('base.lang_ar', raise_if_not_found=False)
        if not arabic:
            return
        arabic = arabic.with_context(active_test=False)
        websites = self.search([]).filtered(lambda w: arabic not in w.language_ids)
        if not arabic.active or websites:
            # Same wizard as Settings > Languages > Add: activates the language,
            # loads the Arabic translations of every installed module and adds
            # it to the selected websites.
            self.env['base.language.install'].create({
                'lang_ids': [(6, 0, arabic.ids)],
                'website_ids': [(6, 0, websites.ids)],
                'overwrite': False,
            }).lang_install()
        self._re_translate_arabic_defaults(arabic.code)

    @api.model
    def _re_translate_arabic_defaults(self, lang):
        """Menus are copied per website (the copies don't get .po translations)
        and the default texts are field values, so give them an Arabic version.
        Only fills values that still hold the module's English default and have
        no Arabic translation yet - never overwrites the user's own text."""
        def translate(records, field, english, arabic):
            for record in records:
                en_value = record.with_context(lang='en_US')[field]
                if en_value == english and record.with_context(lang=lang)[field] == en_value:
                    record.with_context(lang=lang)[field] = arabic

        for url, (english, arabic) in RE_MENU_AR.items():
            translate(self.env['website.menu'].search([('url', '=', url)]), 'name', english, arabic)
        websites = self.search([])
        for field, (english, arabic) in RE_DEFAULTS_AR.items():
            translate(websites, field, english, arabic)

    @api.model
    def _re_apply_brand_palette(self, force=False):
        """Apply the brand colours to every website, exactly like picking a
        palette in the website editor. Runs once (tracked by a system
        parameter) so later changes made in the editor are never overwritten."""
        params = self.env['ir.config_parameter'].sudo()
        if params.get_param(RE_BRAND_PARAM) and not force:
            return
        assets = self.env['web_editor.assets']
        for website in self.search([]):
            website_assets = assets.with_context(website_id=website.id)
            website_assets.make_scss_customization(
                '/website/static/src/scss/options/user_values.scss',
                dict(RE_BRAND_LAYOUT, **{'color-palettes-name': "'base-1'"}),
            )
            website_assets.make_scss_customization(
                '/website/static/src/scss/options/colors/user_color_palette.scss',
                RE_BRAND_PALETTE,
            )
        params.set_param(RE_BRAND_PARAM, '1')

    @api.model
    def _re_translate_html_terms(self, website_ids, field, arabic_terms):
        """Translate an HTML field paragraph by paragraph (writing the whole
        value in Arabic would replace the English version as well)."""
        lang = self.env.ref('base.lang_ar').code
        for website in self.browse(website_ids):
            translations = website.get_field_translations(field, langs=[lang])[0]
            sources = list(dict.fromkeys(t['source'] for t in translations))
            website.update_field_translations(field, {lang: dict(zip(sources, arabic_terms))})

    @api.model
    def _re_write_arabic(self, website_ids, values):
        """Write the Arabic version of website texts (used by demo data)."""
        lang = self.env.ref('base.lang_ar').code
        self.browse(website_ids).with_context(lang=lang).write(values)

    @api.depends('re_video_url', 're_whatsapp')
    def _compute_re_links(self):
        for website in self:
            website.re_video_embed_url = video_embed_url(website.re_video_url)
            website.re_whatsapp_url = whatsapp_url(website.re_whatsapp)
