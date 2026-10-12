# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .re_installment import PAYMENT_METHODS


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    re_contract_id = fields.Many2one('re.contract', 'Real Estate Contract', index='btree_not_null', copy=False)
    re_project_id = fields.Many2one(related='re_contract_id.project_id', string='Project', store=True)
    re_unit_id = fields.Many2one(related='re_contract_id.unit_id', string='Unit', store=True)
    re_installment_ids = fields.Many2many('re.contract.installment', string='Installments', copy=False)
    re_payment_method = fields.Selection(PAYMENT_METHODS, 'Collection Method', copy=False)
    re_cheque_number = fields.Char('Cheque Number', copy=False, index='btree_not_null')
    re_cheque_date = fields.Date('Cheque Date', copy=False)
    re_cheque_bank_id = fields.Many2one('res.bank', 'Cheque Bank', copy=False)
    re_cheque_holder = fields.Char('Account Holder', copy=False)
    re_cheque_state = fields.Selection([
        ('received', 'Received'),
        ('deposited', 'Deposited'),
        ('cleared', 'Cleared'),
        ('bounced', 'Bounced'),
    ], 'Cheque Status', copy=False, tracking=True, index='btree_not_null')

    def _re_refresh_contracts(self):
        contracts = self.re_contract_id
        if contracts:
            self.env.flush_all()
            contracts._check_fully_paid()

    def action_re_cheque_deposit(self):
        for payment in self:
            if payment.re_cheque_state != 'received':
                raise UserError(_('Only received cheques can be deposited.'))
        self.write({'re_cheque_state': 'deposited'})

    def action_re_cheque_clear(self):
        for payment in self:
            if payment.re_cheque_state not in ('received', 'deposited'):
                raise UserError(_('Only received or deposited cheques can be cleared.'))
        self.write({'re_cheque_state': 'cleared'})

    def action_re_cheque_bounce(self):
        """Bounced cheque: cancel the payment so the installments are unpaid again."""
        for payment in self:
            if payment.re_cheque_state not in ('received', 'deposited'):
                raise UserError(_('Only received or deposited cheques can bounce.'))
            payment.action_draft()
            payment.action_cancel()
            payment.re_cheque_state = 'bounced'
            if payment.re_contract_id:
                payment.re_contract_id.message_post(body=_(
                    'Cheque %(number)s of %(amount)s bounced: the installments are unpaid again.',
                    number=payment.re_cheque_number or payment.name,
                    amount=payment.currency_id.format(payment.amount)))
        self._re_refresh_contracts()

    def action_cancel(self):
        res = super().action_cancel()
        self._re_refresh_contracts()
        return res

    def action_open_re_contract(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 're.contract', 'res_id': self.re_contract_id.id,
                'view_mode': 'form'}
