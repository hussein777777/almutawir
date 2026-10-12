# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ReAgency(models.Model):
    """A developer or brokerage company that publishes listings."""
    _name = 're.agency'
    _description = 'Real Estate Agency / Developer'
    _inherit = ['mail.thread', 'image.mixin', 'website.published.mixin', 'website.seo.metadata']
    _order = 'is_verified desc, name'

    name = fields.Char(required=True, tracking=True)
    agency_type = fields.Selection([
        ('developer', 'Developer'),
        ('brokerage', 'Brokerage'),
    ], required=True, default='brokerage', tracking=True)
    is_verified = fields.Boolean('Verified', tracking=True)
    active = fields.Boolean(default=True)
    description = fields.Html(translate=True, sanitize_attributes=False)
    phone = fields.Char()
    email = fields.Char()
    website = fields.Char()
    location_id = fields.Many2one('re.location', 'Head Office Location')
    agent_ids = fields.One2many('re.agent', 'agency_id', 'Agents')
    agent_count = fields.Integer(compute='_compute_counts')
    listing_count = fields.Integer('Published Listings', compute='_compute_counts')

    def _compute_counts(self):
        Listing = self.env['re.listing'].sudo()
        for agency in self:
            agency.agent_count = len(agency.agent_ids.filtered(lambda a: a.state == 'active'))
            agency.listing_count = Listing.search_count([
                ('agency_id', '=', agency.id), ('state', '=', 'published')])

    def _compute_website_url(self):
        super()._compute_website_url()
        for agency in self:
            if agency.id:
                agency.website_url = '/agency/%s' % self.env['ir.http']._slug(agency)

    def action_view_listings(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.name,
            'res_model': 're.listing',
            'view_mode': 'list,kanban,form',
            'domain': [('agency_id', '=', self.id)],
        }
