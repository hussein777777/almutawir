# -*- coding: utf-8 -*-
from odoo import fields, models


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    re_inquiry_type = fields.Selection([
        ('unit', 'Unit Inquiry'),
        ('visit', 'Site Visit'),
        ('meeting', 'Office Meeting / Interview'),
        ('service', 'Service Request'),
        ('general', 'General Inquiry'),
    ], string='Website Request Type', index=True)
    re_project_id = fields.Many2one('re.project', 'Interested Project', index=True)
    re_unit_id = fields.Many2one('re.unit', 'Interested Unit', index=True)
    re_preferred_date = fields.Date('Preferred Date')
    re_budget = fields.Char('Budget')
