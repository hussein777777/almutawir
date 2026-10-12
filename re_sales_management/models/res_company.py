# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    re_grace_days = fields.Integer(
        'Late Payment Grace (days)', default=30,
        help='Installments late by up to this number of days mark the contract "At Risk"; '
             'beyond it the contract is "Overdue".')
    re_auto_invoice = fields.Boolean(
        'Invoice Installments Automatically', default=True,
        help='A daily job creates and posts the customer invoice of each installment when it falls due.')
    re_invoice_lead_days = fields.Integer(
        'Invoice Days Before Due Date', default=0,
        help='Create the installment invoice this many days before its due date.')
    re_installment_product_id = fields.Many2one(
        'product.product', 'Installment Product',
        help='Product used on installment invoices (its income account is used).')
    re_maintenance_product_id = fields.Many2one(
        'product.product', 'Maintenance Deposit Product',
        help='Product used on maintenance deposit invoices. Point its income account to a liability '
             'account if the deposit is held for the owners association.')
    re_sales_journal_id = fields.Many2one('account.journal', 'Installments Journal', domain=[('type', '=', 'sale')])
    re_cash_journal_id = fields.Many2one('account.journal', 'Cash Journal', domain=[('type', '=', 'cash')])
    re_bank_journal_id = fields.Many2one('account.journal', 'Bank Transfer Journal', domain=[('type', '=', 'bank')])
    re_cheque_journal_id = fields.Many2one(
        'account.journal', 'Cheques Journal', domain=[('type', '=', 'bank')],
        help='Journal receiving customer cheques until they are deposited and cleared.')

    def _re_get_product(self, installment_type):
        self.ensure_one()
        if installment_type == 'maintenance':
            return self.re_maintenance_product_id or self.env.ref(
                're_sales_management.product_maintenance_deposit', raise_if_not_found=False)
        return self.re_installment_product_id or self.env.ref(
            're_sales_management.product_unit_installment', raise_if_not_found=False)

    def _re_get_journal(self, method):
        """Default journal for a payment method (cash / bank_transfer / cheque)."""
        self.ensure_one()
        Journal = self.env['account.journal'].with_company(self)
        domain = [('company_id', 'parent_of', self.id)]
        if method == 'cash':
            return self.re_cash_journal_id or Journal.search(domain + [('type', '=', 'cash')], limit=1)
        if method == 'cheque':
            return self.re_cheque_journal_id or self.re_bank_journal_id or Journal.search(
                domain + [('type', '=', 'bank')], limit=1)
        return self.re_bank_journal_id or Journal.search(
            domain + [('type', '=', 'bank'), ('id', '!=', self.re_cheque_journal_id.id)], limit=1)

    @api.model
    def _re_setup_accounting(self):
        """Create the 'Cheques Under Collection' journal for every company that has a chart of
        accounts. Safe to run again (install, upgrade, settings button)."""
        for company in self.search([]):
            if not company.chart_template or company.re_cheque_journal_id:
                continue
            Journal = self.env['account.journal'].with_company(company)
            journal = Journal.search([('code', '=', 'CHQ'), ('company_id', '=', company.id)], limit=1)
            if not journal:
                journal = Journal.create({
                    'name': self.env._('Cheques Under Collection'),
                    'code': 'CHQ',
                    'type': 'bank',
                    'company_id': company.id,
                })
            company.re_cheque_journal_id = journal
