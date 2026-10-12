# -*- coding: utf-8 -*-
from odoo import fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    re_installment_id = fields.Many2one('re.contract.installment', 'Contract Installment', copy=False,
                                        index='btree_not_null', readonly=True)
    re_contract_id = fields.Many2one(related='re_installment_id.contract_id', string='Real Estate Contract',
                                     store=True, index='btree_not_null')

    def _re_contracts_after_change(self):
        contracts = self.re_contract_id
        if contracts:
            self.env.flush_all()
            contracts._check_fully_paid()

    def button_cancel(self):
        res = super().button_cancel()
        # a cancelled invoice frees its installment so it can be invoiced again
        for move in self.filtered(lambda m: m.re_installment_id and m.state == 'cancel'):
            if move.re_installment_id.invoice_id == move:
                move.re_installment_id.invoice_id = False
        return res

    def js_assign_outstanding_line(self, line_id):
        # payments matched from the invoice "Outstanding credits" widget
        res = super().js_assign_outstanding_line(line_id)
        self._re_contracts_after_change()
        return res
