# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from .tools import map_embed_url, video_embed_url


class ReProject(models.Model):
    _name = 're.project'
    _description = 'Real Estate Project'
    _inherit = [
        'mail.thread',
        'mail.activity.mixin',
        'image.mixin',
        'website.published.mixin',
        'website.seo.metadata',
    ]
    _order = 'sequence, id desc'

    name = fields.Char(required=True, translate=True, tracking=True)
    subtitle = fields.Char(translate=True, help='Short catch line shown under the project name.')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    is_featured = fields.Boolean('Featured on Homepage', tracking=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')

    project_type = fields.Selection([
        ('residential', 'Residential'),
        ('commercial', 'Commercial'),
        ('administrative', 'Administrative'),
        ('mixed', 'Mixed Use'),
        ('coastal', 'Coastal / Resort'),
    ], required=True, default='residential', tracking=True)
    state = fields.Selection([
        ('planning', 'Launching Soon'),
        ('construction', 'Under Construction'),
        ('delivered', 'Delivered'),
    ], string='Status', required=True, default='construction', tracking=True)

    city = fields.Char(translate=True)
    location = fields.Char('Address / Location', translate=True)
    map_query = fields.Char(
        'Map Location', help='Address or "latitude,longitude" used for the Google map on the website.')
    map_embed_url = fields.Char(compute='_compute_embed_urls')

    total_area = fields.Float('Total Land Area (m²)')
    launch_date = fields.Date()
    delivery_date = fields.Date('Expected Delivery')
    construction_progress = fields.Integer('Construction Progress (%)', tracking=True)

    short_description = fields.Text(translate=True, help='Shown on project cards.')
    description = fields.Html(translate=True, sanitize_attributes=False)
    video_url = fields.Char('Video URL', help='YouTube or Vimeo link.')
    video_embed_url = fields.Char(compute='_compute_embed_urls')
    brochure = fields.Binary(attachment=True)
    brochure_filename = fields.Char()

    amenity_ids = fields.Many2many('re.amenity', string='Amenities')
    unit_ids = fields.One2many('re.unit', 'project_id', string='Units')
    unit_count = fields.Integer(compute='_compute_unit_stats')
    available_unit_count = fields.Integer(compute='_compute_unit_stats')
    min_price = fields.Monetary('Starting Price', compute='_compute_unit_stats')

    @api.constrains('construction_progress')
    def _check_progress(self):
        for project in self:
            if not 0 <= project.construction_progress <= 100:
                raise ValidationError(_('Construction progress must be between 0 and 100.'))

    @api.depends('map_query', 'location', 'city', 'video_url')
    def _compute_embed_urls(self):
        for project in self:
            query = project.map_query or ', '.join(filter(None, [project.location, project.city]))
            project.map_embed_url = map_embed_url(query)
            project.video_embed_url = video_embed_url(project.video_url)

    @api.depends('unit_ids.state', 'unit_ids.price', 'unit_ids.is_published')
    def _compute_unit_stats(self):
        for project in self:
            # sudo: public visitors only see published units, stats must stay consistent
            units = project.sudo().unit_ids.filtered('is_published')
            available = units.filtered(lambda u: u.state == 'available')
            project.unit_count = len(units)
            project.available_unit_count = len(available)
            project.min_price = min(available.mapped('price')) if available else 0.0

    def _compute_website_url(self):
        super()._compute_website_url()
        for project in self:
            if project.id:
                project.website_url = '/estate/project/%s' % self.env['ir.http']._slug(project)

    def action_view_units(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Units'),
            'res_model': 're.unit',
            'view_mode': 'list,kanban,form',
            'domain': [('project_id', '=', self.id)],
            'context': {'default_project_id': self.id},
        }
