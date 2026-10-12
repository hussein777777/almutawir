# -*- coding: utf-8 -*-
from odoo import api, models

RP_MENU_AR = {
    '/properties/buy': ('Buy', 'شراء'),
    '/properties/rent': ('Rent', 'إيجار'),
    '/agents': ('Find Agent', 'ابحث عن وكيل'),
}


class Website(models.Model):
    _inherit = 'website'

    @api.model
    def _rp_translate_menus(self):
        """Menus are copied per website and the copies don't get .po translations.
        Only fills menus still holding the English default without Arabic text."""
        arabic = self.env.ref('base.lang_ar', raise_if_not_found=False)
        if not arabic or not arabic.active:
            return
        for url, (english, translated) in RP_MENU_AR.items():
            for menu in self.env['website.menu'].search([('url', '=', url)]):
                if menu.with_context(lang='en_US').name == english \
                        and menu.with_context(lang=arabic.code).name == english:
                    menu.with_context(lang=arabic.code).name = translated
