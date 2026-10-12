# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    re_grace_days = fields.Integer(related='company_id.re_grace_days', readonly=False)
    re_auto_invoice = fields.Boolean(related='company_id.re_auto_invoice', readonly=False)
    re_invoice_lead_days = fields.Integer(related='company_id.re_invoice_lead_days', readonly=False)
    re_installment_product_id = fields.Many2one(related='company_id.re_installment_product_id', readonly=False)
    re_maintenance_product_id = fields.Many2one(related='company_id.re_maintenance_product_id', readonly=False)
    re_sales_journal_id = fields.Many2one(related='company_id.re_sales_journal_id', readonly=False)
    re_cash_journal_id = fields.Many2one(related='company_id.re_cash_journal_id', readonly=False)
    re_bank_journal_id = fields.Many2one(related='company_id.re_bank_journal_id', readonly=False)
    re_cheque_journal_id = fields.Many2one(related='company_id.re_cheque_journal_id', readonly=False)

    def action_re_setup_accounting(self):
        self.env['res.company']._re_setup_accounting()
