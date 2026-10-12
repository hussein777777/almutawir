# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ReLocation(models.Model):
    """Location tree: Governorate > City > Area / Compound."""
    _name = 're.location'
    _description = 'Property Location'
    _parent_store = True
    _parent_name = 'parent_id'
    _rec_name = 'complete_name'
    _order = 'complete_name'

    name = fields.Char(required=True, translate=True)
    complete_name = fields.Char(compute='_compute_complete_name', store=True, recursive=True, translate=True)
    parent_id = fields.Many2one('re.location', 'Parent Location', index=True, ondelete='restrict')
    parent_path = fields.Char(index=True)
    child_ids = fields.One2many('re.location', 'parent_id', 'Sub-locations')
    location_type = fields.Selection([
        ('governorate', 'Governorate'),
        ('city', 'City'),
        ('area', 'Area / District'),
        ('compound', 'Compound'),
    ], default='city', required=True)
    latitude = fields.Float(digits=(10, 7))
    longitude = fields.Float(digits=(10, 7))
    active = fields.Boolean(default=True)
    listing_count = fields.Integer('Published Listings', compute='_compute_listing_count')

    @api.depends('name', 'parent_id.complete_name')
    def _compute_complete_name(self):
        for location in self:
            if location.parent_id:
                location.complete_name = '%s, %s' % (location.name, location.parent_id.complete_name)
            else:
                location.complete_name = location.name

    def _compute_listing_count(self):
        Listing = self.env['re.listing'].sudo()
        for location in self:
            location.listing_count = Listing.search_count([
                ('location_id', 'child_of', location.id), ('state', '=', 'published')])

    @api.constrains('parent_id')
    def _check_parent(self):
        if self._has_cycle():
            raise ValidationError(_('You cannot create recursive locations.'))
