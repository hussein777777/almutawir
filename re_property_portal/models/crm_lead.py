# -*- coding: utf-8 -*-
from odoo import fields, models


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    re_listing_id = fields.Many2one('re.listing', 'Listing', index=True)
    re_agent_id = fields.Many2one('re.agent', 'Listing Agent', index=True)
