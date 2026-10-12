# -*- coding: utf-8 -*-
from odoo import fields, models


class ReListingRejectWizard(models.TransientModel):
    _name = 're.listing.reject.wizard'
    _description = 'Reject Listing'

    listing_ids = fields.Many2many('re.listing', required=True)
    reason = fields.Text(required=True, help='Sent to the agent so they can fix the listing.')

    def action_reject(self):
        self.listing_ids._reject(self.reason)
        return {'type': 'ir.actions.act_window_close'}
