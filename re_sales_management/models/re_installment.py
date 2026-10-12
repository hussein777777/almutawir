# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare, float_is_zero

PAYMENT_METHODS = [
    ('cash', 'Cash'),
    ('bank_transfer', 'Bank Transfer'),
    ('cheque', 'Cheque'),
]


class ReContractInstallment(models.Model):
    _name = 're.contract.installment'
    _description = 'Contract Installment'
    _order = 'contract_id, due_date, sequence, id'
    _rec_name = 'name'

    contract_id = fields.Many2one('re.contract', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    name = fields.Char('Description', required=True)
    installment_type = fields.Selection([
        ('down_payment', 'Down Payment'),
        ('installment', 'Installment'),
        ('maintenance', 'Maintenance Deposit'),
        ('other', 'Other'),
    ], default='installment', required=True)
    due_date = fields.Date(required=True, index=True)
    amount_type = fields.Selection([('fixed', 'Fixed Amount'), ('percent', 'Percentage of Unit Price')],
                                   default='fixed', required=True)
    percent = fields.Float('Percentage')
    amount = fields.Monetary(required=True)
    company_id = fields.Many2one(related='contract_id.company_id', store=True)
    currency_id = fields.Many2one(related='contract_id.currency_id')
    partner_id = fields.Many2one(related='contract_id.partner_id', store=True, index=True)
    project_id = fields.Many2one(related='contract_id.project_id', store=True, index=True)
    unit_id = fields.Many2one(related='contract_id.unit_id', store=True)
    contract_state = fields.Selection(related='contract_id.state', store=True, string='Contract Status')

    invoice_id = fields.Many2one('account.move', 'Invoice', copy=False, readonly=True, index=True)
    invoice_state = fields.Selection(related='invoice_id.payment_state', string='Invoice Payment Status')
    paid_amount = fields.Monetary('Paid', compute='_compute_paid', store=True)
    remaining_amount = fields.Monetary('Remaining', compute='_compute_paid', store=True)
    state = fields.Selection([
        ('upcoming', 'Upcoming'),
        ('due', 'Due Today'),
        ('overdue', 'Overdue'),
        ('partial', 'Partially Paid'),
        ('paid', 'Paid'),
        ('cancelled', 'Cancelled'),
    ], compute='_compute_state', store=True, index=True)
    days_overdue = fields.Integer(compute='_compute_days_overdue')

    # Planned payment (e.g. post-dated cheques received at signing)
    payment_method = fields.Selection(PAYMENT_METHODS, 'Payment Method', default='bank_transfer')
    reference = fields.Char()
    cheque_number = fields.Char()
    cheque_date = fields.Date()
    cheque_bank_id = fields.Many2one('res.bank', 'Bank')
    cheque_holder = fields.Char('Account Holder')
    cheque_amount = fields.Monetary()
    notes = fields.Text()
    attachment_ids = fields.Many2many('ir.attachment', string='Attachments')

    # Context panel (dialog)
    unit_price = fields.Monetary(related='contract_id.unit_price')
    contract_value = fields.Monetary(related='contract_id.total_value')
    contract_installment_count = fields.Integer(compute='_compute_contract_info')
    contract_remaining = fields.Monetary(related='contract_id.remaining_amount', string='Contract Remaining')

    @api.depends('amount', 'invoice_id.amount_residual', 'invoice_id.state', 'invoice_id.amount_total')
    def _compute_paid(self):
        for installment in self:
            invoice = installment.invoice_id
            if invoice and invoice.state == 'posted':
                paid = invoice.amount_total - invoice.amount_residual
            else:
                paid = 0.0
            installment.paid_amount = paid
            installment.remaining_amount = installment.amount - paid

    @api.depends('due_date', 'paid_amount', 'remaining_amount', 'contract_id.state')
    def _compute_state(self):
        today = fields.Date.context_today(self)
        for installment in self:
            rounding = installment.currency_id.rounding or 0.01
            if installment.contract_id.state == 'cancelled':
                installment.state = 'cancelled'
            elif float_is_zero(installment.remaining_amount, precision_rounding=rounding) and installment.amount:
                installment.state = 'paid'
            elif installment.due_date and installment.due_date < today \
                    and installment.contract_id.state in ('active', 'closed'):
                installment.state = 'overdue'
            elif float_compare(installment.paid_amount, 0, precision_rounding=rounding) > 0:
                installment.state = 'partial'
            elif installment.due_date == today:
                installment.state = 'due'
            else:
                installment.state = 'upcoming'

    def _compute_days_overdue(self):
        today = fields.Date.context_today(self)
        for installment in self:
            installment.days_overdue = max((today - installment.due_date).days, 0) \
                if installment.state == 'overdue' else 0

    def _compute_contract_info(self):
        for installment in self:
            installment.contract_installment_count = len(installment.contract_id.installment_ids)

    def _refresh_state(self):
        """Statuses depend on today's date: recompute them (daily cron)."""
        if self:
            self.env.add_to_compute(self._fields['state'], self)
            self.env.flush_all()

    @api.onchange('amount_type', 'percent')
    def _onchange_percent(self):
        if self.amount_type == 'percent' and self.contract_id:
            self.amount = self.currency_id.round(self.contract_id.unit_price * self.percent / 100.0)

    @api.onchange('payment_method', 'amount')
    def _onchange_cheque_amount(self):
        if self.payment_method == 'cheque' and not self.cheque_amount:
            self.cheque_amount = self.amount
        if self.payment_method == 'cheque' and not self.cheque_date:
            self.cheque_date = self.due_date

    @api.constrains('amount')
    def _check_amount(self):
        for installment in self:
            if installment.amount < 0:
                raise ValidationError(_('Installment amounts cannot be negative.'))

    def write(self, vals):
        locked = {'amount', 'due_date', 'contract_id'} & set(vals)
        if locked:
            for installment in self.filtered('invoice_id'):
                if installment.invoice_id.state != 'cancel' and (
                        'amount' in vals and float_compare(vals['amount'], installment.amount,
                                                          precision_rounding=installment.currency_id.rounding) != 0
                        or 'contract_id' in vals):
                    raise UserError(_('"%s" is already invoiced: cancel its invoice before changing the amount.',
                                      installment.name))
        return super().write(vals)

    def unlink(self):
        if self.filtered(lambda i: i.invoice_id and i.invoice_id.state != 'cancel'):
            raise UserError(_('Invoiced installments cannot be deleted.'))
        return super().unlink()

    # ------------------------------------------------------------------
    # Accounting
    # ------------------------------------------------------------------
    def _prepare_invoice_vals(self):
        self.ensure_one()
        contract = self.contract_id
        company = contract.company_id
        product = company._re_get_product(self.installment_type)
        if not product:
            raise UserError(_('Configure the installment products in Real Estate settings.'))
        today = fields.Date.context_today(self)
        line = {
            'product_id': product.id,
            'name': '%s - %s - %s' % (contract.name, self.name, contract.unit_id.display_name),
            'quantity': 1.0,
            'price_unit': self.amount,
            'tax_ids': [(6, 0, [])],
        }
        if contract.project_id.analytic_account_id:
            line['analytic_distribution'] = {str(contract.project_id.analytic_account_id.id): 100}
        vals = {
            'move_type': 'out_invoice',
            'partner_id': contract.partner_id.id,
            'company_id': company.id,
            'currency_id': contract.currency_id.id,
            'invoice_date': min(self.due_date, today),
            'invoice_date_due': self.due_date,
            'invoice_origin': contract.name,
            'ref': '%s / %s' % (contract.name, self.name),
            'invoice_user_id': contract.user_id.id,
            're_installment_id': self.id,
            'invoice_line_ids': [(0, 0, line)],
        }
        if company.re_sales_journal_id:
            vals['journal_id'] = company.re_sales_journal_id.id
        return vals

    def _create_invoices(self, post=True):
        """Create (and post) one customer invoice per installment."""
        invoices = self.env['account.move']
        for installment in self:
            if installment.invoice_id and installment.invoice_id.state != 'cancel':
                invoices |= installment.invoice_id
                continue
            if installment.contract_id.state not in ('active', 'closed'):
                raise UserError(_('Confirm contract %s before invoicing.', installment.contract_id.name))
            invoice = self.env['account.move'].with_company(installment.company_id).create(
                installment._prepare_invoice_vals())
            installment.invoice_id = invoice
            invoices |= invoice
        if post:
            invoices.filtered(lambda m: m.state == 'draft').action_post()
        return invoices

    def action_create_invoice(self):
        invoices = self._create_invoices()
        if len(invoices) == 1:
            return {'type': 'ir.actions.act_window', 'res_model': 'account.move', 'res_id': invoices.id,
                    'view_mode': 'form'}
        return True

    def action_open_invoice(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 'account.move', 'res_id': self.invoice_id.id,
                'view_mode': 'form'}

    def action_register_payment(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Record Payment'),
            'res_model': 're.payment.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_contract_id': self.contract_id.id, 'default_installment_ids': [self.id]},
        }

    def action_open_contract(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 're.contract', 'res_id': self.contract_id.id,
                'view_mode': 'form'}
