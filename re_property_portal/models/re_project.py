# -*- coding: utf-8 -*-
from odoo import fields, models


class ReProject(models.Model):
    _inherit = 're.project'

    agency_id = fields.Many2one('re.agency', 'Developer', domain=[('agency_type', '=', 'developer')], index=True)
    location_id = fields.Many2one('re.location', 'Location (marketplace)', index=True)
    listing_ids = fields.One2many('re.listing', 'project_id', 'Marketplace Listings')
