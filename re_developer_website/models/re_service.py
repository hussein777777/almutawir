# -*- coding: utf-8 -*-
from odoo import fields, models


class ReService(models.Model):
    _name = 're.service'
    _description = 'Company Service'
    _inherit = ['image.mixin', 'website.published.mixin']
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    icon = fields.Char(default='fa-building', help='Font Awesome 4 class, e.g. fa-building, fa-paint-brush.')
    short_description = fields.Text(translate=True)
    description = fields.Html(translate=True, sanitize_attributes=False)

    def _compute_website_url(self):
        super()._compute_website_url()
        for service in self:
            if service.id:
                service.website_url = '/estate/services#service-%s' % service.id
