# -*- coding: utf-8 -*-
from odoo import fields, models


class ReTeamMember(models.Model):
    _name = 're.team.member'
    _description = 'Leadership / Team Member'
    _inherit = ['image.mixin', 'website.published.mixin']
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True)
    job_title = fields.Char(translate=True)
    bio = fields.Text(translate=True)
    linkedin_url = fields.Char('LinkedIn')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    def _compute_website_url(self):
        super()._compute_website_url()
        for member in self:
            member.website_url = '/estate/about#team'
