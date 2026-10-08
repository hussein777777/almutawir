# -*- coding: utf-8 -*-
from odoo import fields, models


class ReAmenity(models.Model):
    _name = 're.amenity'
    _description = 'Project Amenity'
    _order = 'sequence, name'

    name = fields.Char(required=True, translate=True)
    icon = fields.Char(
        default='fa-check',
        help='Font Awesome 4 class shown on the website, e.g. fa-tree, fa-car, fa-shield.')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('name_uniq', 'unique(name)', 'This amenity already exists.'),
    ]
