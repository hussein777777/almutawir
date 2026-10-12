# -*- coding: utf-8 -*-
import base64

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare, float_is_zero

from ..models.re_installment import PAYMENT_METHODS


class RePaymentWizard(models.TransientModel):
    """Record a collection on a contract.

    One Odoo payment is created for the received amount (one cheque = one payment) and it is
    reconciled with the installment invoices, oldest first. Installments without an invoice
    yet are invoiced on the fly."""
    _name = 're.payment.wizard'
    _description = 'Record Contract Payment'

    contract_id = fields.Many2one('re.contract', required=True, readonly=True)
    partner_id = fields.Many2one(related='contract_id.partner_id')
    company_id = fields.Many2one(related='contract_id.company_id')
    currency_id = fields.Many2one(related='contract_id.currency_id')
    installment_ids = fields.Many2many(
        're.contract.installment', string='Installments to Pay',
        domain="[('contract_id', '=', contract_id), ('state', 'not in', ('paid', 'cancelled'))]")
    selected_remaining = fields.Monetary('Selected Remaining', compute='_compute_selected_remaining')
    contract_remaining = fields.Monetary(related='contract_id.remaining_amount')
    amount = fields.Monetary(required=True)
    date = fields.Date('Payment Date', required=True, default=fields.Date.context_today)
    payment_method = fields.Selection(PAYMENT_METHODS, 'Payment Method', required=True, default='bank_transfer')
    journal_id = fields.Many2one('account.journal', required=True,
                                 domain="[('type', 'in', ('bank', 'cash')), ('company_id', 'parent_of', company_id)]")
    reference = fields.Char()
    cheque_number = fields.Char()
    cheque_date = fields.Date()
    cheque_bank_id = fields.Many2one('res.bank', 'Bank')
    cheque_holder = fields.Char('Account Holder')
    attachment = fields.Binary('Receipt / Cheque Copy')
    attachment_name = fields.Char()
    notes = fields.Text()

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        contract = self.env['re.contract'].browse(res.get('contract_id') or self.env.context.get('default_contract_id'))
        if contract:
            if not res.get('installment_ids'):
                open_installments = contract.installment_ids.filtered(
                    lambda i: i.state not in ('paid', 'cancelled')).sorted(lambda i: (i.due_date, i.sequence))
                res['installment_ids'] = [(6, 0, open_installments[:1].ids)]
            installments = self.env['re.contract.installment'].browse(
                self._ids_from_command(res.get('installment_ids')))
            first = installments.sorted(lambda i: (i.due_date, i.sequence))[:1]
            res.setdefault('amount', sum(installments.mapped('remaining_amount')))
            if first.payment_method:
                res['payment_method'] = first.payment_method
                res['reference'] = first.reference
                res['cheque_number'] = first.cheque_number
                res['cheque_date'] = first.cheque_date
                res['cheque_bank_id'] = first.cheque_bank_id.id
                res['cheque_holder'] = first.cheque_holder
            res['journal_id'] = contract.company_id._re_get_journal(res.get('payment_method', 'bank_transfer')).id
        return res

    @staticmethod
    def _ids_from_command(commands):
        ids = []
        for command in commands or []:
            if isinstance(command, (list, tuple)):
                if command[0] == 6:
                    ids += list(command[2])
                elif command[0] == 4:
                    ids.append(command[1])
            elif isinstance(command, int):
                ids.append(command)
        return ids

    @api.depends('installment_ids')
    def _compute_selected_remaining(self):
        for wizard in self:
            wizard.selected_remaining = sum(wizard.installment_ids.mapped('remaining_amount'))

    @api.onchange('installment_ids')
    def _onchange_installments(self):
        self.amount = sum(self.installment_ids.mapped('remaining_amount'))

    @api.onchange('payment_method')
    def _onchange_payment_method(self):
        if self.contract_id:
            self.journal_id = self.contract_id.company_id._re_get_journal(self.payment_method)

    def _allocation_targets(self):
        """Selected installments first (by due date), then the rest of the open schedule."""
        key = lambda i: (i.due_date, i.sequence, i.id)  # noqa: E731
        selected = self.installment_ids.filtered(lambda i: i.state not in ('paid', 'cancelled')).sorted(key)
        others = (self.contract_id.installment_ids - selected).filtered(
            lambda i: i.state not in ('paid', 'cancelled')).sorted(key)
        return selected + others

    def action_confirm(self):
        self.ensure_one()
        contract = self.contract_id
        currency = contract.currency_id
        if contract.state not in ('active', 'closed'):
            raise UserError(_('Confirm the contract before recording payments.'))
        if float_compare(self.amount, 0, precision_rounding=currency.rounding) <= 0:
            raise ValidationError(_('The amount must be positive.'))
        if self.payment_method == 'cheque' and not self.cheque_number:
            raise ValidationError(_('Enter the cheque number.'))
        if float_compare(self.amount, contract.remaining_amount, precision_rounding=currency.rounding) > 0:
            raise ValidationError(_('The amount (%(amount)s) is more than the remaining balance of the contract '
                                    '(%(remaining)s).', amount=currency.format(self.amount),
                                    remaining=currency.format(contract.remaining_amount)))

        # Allocate oldest first and make sure each targeted installment has a posted invoice
        allocation = []
        left = self.amount
        for installment in self._allocation_targets():
            if float_is_zero(left, precision_rounding=currency.rounding):
                break
            part = min(left, installment.remaining_amount)
            if float_compare(part, 0, precision_rounding=currency.rounding) <= 0:
                continue
            installment._create_invoices(post=True)
            allocation.append((installment, part))
            left -= part

        journal = self.journal_id
        method_line = journal.inbound_payment_method_line_ids[:1]
        if not method_line:
            raise UserError(_('Journal %s has no incoming payment method.', journal.display_name))
        memo_parts = [contract.name] + [inst.name for inst, _part in allocation]
        payment = self.env['account.payment'].with_company(contract.company_id).create({
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'partner_id': contract.partner_id.commercial_partner_id.id,
            'amount': self.amount,
            'currency_id': currency.id,
            'date': self.date,
            'journal_id': journal.id,
            'payment_method_line_id': method_line.id,
            'memo': self.reference or ' / '.join(memo_parts),
            're_contract_id': contract.id,
            're_installment_ids': [(6, 0, [inst.id for inst, _part in allocation])],
            're_payment_method': self.payment_method,
            're_cheque_number': self.cheque_number if self.payment_method == 'cheque' else False,
            're_cheque_date': self.cheque_date if self.payment_method == 'cheque' else False,
            're_cheque_bank_id': self.cheque_bank_id.id if self.payment_method == 'cheque' else False,
            're_cheque_holder': self.cheque_holder if self.payment_method == 'cheque' else False,
            're_cheque_state': 'received' if self.payment_method == 'cheque' else False,
        })
        payment.action_post()
        if not payment.move_id:
            raise UserError(_('Journal %s has no "Outstanding Receipts" account: set it in the journal '
                              'configuration so the payment can be reconciled.', journal.display_name))
        _liquidity, counterpart, _writeoff = payment._seek_for_lines()
        for installment, _part in allocation:
            invoice_lines = installment.invoice_id.line_ids.filtered(
                lambda line: line.account_id == counterpart.account_id and not line.reconciled)
            if invoice_lines and not counterpart.reconciled:
                (counterpart + invoice_lines).reconcile()
        if self.attachment:
            self.env['ir.attachment'].create({
                'name': self.attachment_name or _('Receipt'),
                'datas': self.attachment,
                'res_model': 'account.payment',
                'res_id': payment.id,
            })
        if self.notes:
            payment.message_post(body=self.notes)
        self.env.flush_all()
        contract._check_fully_paid()
        contract.message_post(body=_('Payment of %(amount)s recorded (%(method)s).',
                                     amount=currency.format(self.amount),
                                     method=dict(self._fields['payment_method']._description_selection(self.env))[
                                         self.payment_method]))
        return {'type': 'ir.actions.act_window_close'}
