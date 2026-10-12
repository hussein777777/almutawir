# -*- coding: utf-8 -*-
from datetime import date

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare, float_is_zero, float_round

FREQUENCY_MONTHS = {'monthly': 1, 'quarterly': 3, 'semiannual': 6, 'annual': 12}


class ReContract(models.Model):
    _name = 're.contract'
    _description = 'Real Estate Sales Contract'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'
    _check_company_auto = True

    name = fields.Char('Contract No.', readonly=True, copy=False, default='/', index=True, tracking=True)
    state = fields.Selection([
        ('draft', 'Reservation'),
        ('active', 'Active'),
        ('closed', 'Closed'),
        ('cancelled', 'Cancelled'),
    ], default='draft', required=True, tracking=True, index=True, copy=False)
    collection_status = fields.Selection([
        ('on_track', 'On Track'),
        ('at_risk', 'At Risk'),
        ('overdue', 'Overdue'),
        ('closed', 'Fully Paid'),
    ], compute='_compute_collection', store=True, index=True)

    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    user_id = fields.Many2one('res.users', 'Salesperson', default=lambda self: self.env.user, tracking=True)
    partner_id = fields.Many2one('res.partner', 'Customer', required=True, index=True, tracking=True,
                                 check_company=True)
    project_id = fields.Many2one('re.project', required=True, index=True, tracking=True)
    building_id = fields.Many2one(related='unit_id.building_id', store=True)
    unit_id = fields.Many2one('re.unit', 'Unit', required=True, index=True, tracking=True,
                              domain="[('project_id', '=', project_id), ('state', '=', 'available')]")
    unit_type = fields.Selection(related='unit_id.unit_type')
    date = fields.Date('Contract Date', required=True, default=fields.Date.context_today, tracking=True)

    unit_price = fields.Monetary('Unit Price', required=True, tracking=True)
    discount_amount = fields.Monetary('Discount')
    net_price = fields.Monetary(compute='_compute_amounts', store=True)
    maintenance_amount = fields.Monetary('Maintenance Deposit',
                                         help='Usually collected at delivery; added to the contract value.')
    maintenance_due_date = fields.Date()
    total_value = fields.Monetary('Contract Value', compute='_compute_amounts', store=True, tracking=True)

    # Payment plan
    down_payment_type = fields.Selection([('percent', 'Percentage'), ('fixed', 'Fixed Amount')],
                                         default='percent', required=True)
    down_payment_percent = fields.Float('Down Payment %', default=10.0)
    down_payment_fixed = fields.Monetary('Fixed Down Payment')
    down_payment_amount = fields.Monetary(compute='_compute_amounts', store=True)
    down_payment_date = fields.Date()
    installment_count = fields.Integer('Number of Installments', default=28)
    installment_frequency = fields.Selection([
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('semiannual', 'Semi-annual'),
        ('annual', 'Annual'),
    ], default='quarterly', required=True)
    first_installment_date = fields.Date()
    installment_ids = fields.One2many('re.contract.installment', 'contract_id', 'Installments', copy=False)
    installment_total = fields.Monetary('Scheduled Total', compute='_compute_collection', store=True)

    # Collection figures (from accounting)
    collected_amount = fields.Monetary('Collected', compute='_compute_collection', store=True)
    remaining_amount = fields.Monetary('Remaining', compute='_compute_collection', store=True)
    overdue_amount = fields.Monetary('Overdue', compute='_compute_collection', store=True)
    collection_pct = fields.Float('Collection %', compute='_compute_collection', store=True)
    next_due_date = fields.Date(compute='_compute_collection', store=True)
    last_payment_date = fields.Date('Last Collection Date', compute='_compute_payments')
    payment_ids = fields.One2many('account.payment', 're_contract_id', 'Payments')
    payment_count = fields.Integer(compute='_compute_payments')
    invoice_count = fields.Integer(compute='_compute_invoice_count')
    notes = fields.Html()

    _sql_constraints = [
        ('name_company_uniq', 'unique(name, company_id)', 'Contract number must be unique.'),
    ]

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------
    @api.depends('unit_price', 'discount_amount', 'maintenance_amount', 'down_payment_type',
                 'down_payment_percent', 'down_payment_fixed')
    def _compute_amounts(self):
        for contract in self:
            contract.net_price = contract.unit_price - contract.discount_amount
            contract.total_value = contract.net_price + contract.maintenance_amount
            if contract.down_payment_type == 'percent':
                contract.down_payment_amount = contract.currency_id.round(
                    contract.net_price * contract.down_payment_percent / 100.0)
            else:
                contract.down_payment_amount = contract.down_payment_fixed

    @api.depends('state', 'total_value', 'installment_ids.amount', 'installment_ids.paid_amount',
                 'installment_ids.state', 'installment_ids.due_date', 'company_id.re_grace_days')
    def _compute_collection(self):
        today = fields.Date.context_today(self)
        for contract in self:
            installments = contract.installment_ids
            contract.installment_total = sum(installments.mapped('amount'))
            collected = sum(installments.mapped('paid_amount'))
            contract.collected_amount = collected
            contract.remaining_amount = contract.total_value - collected
            overdue = installments.filtered(lambda i: i.state == 'overdue') \
                if contract.state in ('active', 'closed') else installments.browse()
            contract.overdue_amount = sum(overdue.mapped('remaining_amount'))
            contract.collection_pct = contract.total_value and collected * 100.0 / contract.total_value or 0.0
            unpaid = installments.filtered(lambda i: i.state not in ('paid', 'cancelled')).sorted('due_date')
            contract.next_due_date = unpaid[:1].due_date
            if contract.state not in ('active', 'closed'):
                contract.collection_status = False
            elif float_is_zero(contract.remaining_amount, precision_rounding=contract.currency_id.rounding or 0.01) \
                    and installments:
                contract.collection_status = 'closed'
            elif overdue:
                late_days = max((today - due).days for due in overdue.mapped('due_date'))
                contract.collection_status = 'overdue' if late_days > contract.company_id.re_grace_days else 'at_risk'
            else:
                contract.collection_status = 'on_track'

    def _compute_payments(self):
        for contract in self:
            payments = contract.payment_ids.filtered(lambda p: p.state in ('in_process', 'paid'))
            contract.payment_count = len(contract.payment_ids)
            contract.last_payment_date = max(payments.mapped('date')) if payments else False

    def _compute_invoice_count(self):
        for contract in self:
            contract.invoice_count = len(contract.installment_ids.invoice_id)

    # ------------------------------------------------------------------
    # Onchanges / constraints
    # ------------------------------------------------------------------
    @api.onchange('unit_id')
    def _onchange_unit_id(self):
        if self.unit_id:
            self.project_id = self.unit_id.project_id
            self.unit_price = self.unit_id.price
            if self.unit_id.down_payment_pct:
                self.down_payment_percent = self.unit_id.down_payment_pct
            if self.unit_id.installment_years:
                months = FREQUENCY_MONTHS[self.installment_frequency or 'quarterly']
                self.installment_count = int(self.unit_id.installment_years * 12 / months)

    @api.onchange('date')
    def _onchange_date(self):
        if self.date:
            self.down_payment_date = self.date
            months = FREQUENCY_MONTHS[self.installment_frequency or 'quarterly']
            self.first_installment_date = self.date + relativedelta(months=months)

    @api.constrains('unit_id', 'state')
    def _check_unit_unique(self):
        for contract in self.filtered(lambda c: c.state != 'cancelled'):
            others = self.search_count([
                ('unit_id', '=', contract.unit_id.id), ('state', '!=', 'cancelled'), ('id', '!=', contract.id)])
            if others:
                raise ValidationError(_('Unit %s already has an open contract or reservation.',
                                        contract.unit_id.display_name))

    @api.constrains('unit_price', 'discount_amount', 'down_payment_percent', 'installment_count')
    def _check_values(self):
        for contract in self:
            if contract.unit_price < 0 or contract.discount_amount < 0:
                raise ValidationError(_('Prices cannot be negative.'))
            if contract.discount_amount > contract.unit_price:
                raise ValidationError(_('The discount cannot exceed the unit price.'))
            if not 0 <= contract.down_payment_percent <= 100:
                raise ValidationError(_('The down payment percentage must be between 0 and 100.'))
            if contract.installment_count < 0:
                raise ValidationError(_('The number of installments cannot be negative.'))

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = self.env['ir.sequence'].with_company(
                    vals.get('company_id') or self.env.company.id).next_by_code('re.contract') or '/'
            if vals.get('unit_id') and not vals.get('project_id'):
                vals['project_id'] = self.env['re.unit'].browse(vals['unit_id']).project_id.id
        contracts = super().create(vals_list)
        for contract in contracts:
            if not contract.down_payment_date:
                contract.down_payment_date = contract.date
            if not contract.first_installment_date:
                contract.first_installment_date = contract.date + relativedelta(
                    months=FREQUENCY_MONTHS[contract.installment_frequency])
        contracts.filtered(lambda c: c.state == 'draft').unit_id.sudo().write({'state': 'reserved'})
        contracts.partner_id.filtered(lambda p: not p.is_re_customer).write({'is_re_customer': True})
        return contracts

    def write(self, vals):
        old_units = {c.id: c.unit_id for c in self} if 'unit_id' in vals else {}
        res = super().write(vals)
        if old_units:
            for contract in self:
                old = old_units[contract.id]
                if old != contract.unit_id and contract.state == 'draft':
                    old.sudo().write({'state': 'available'})
                    contract.unit_id.sudo().write({'state': 'reserved'})
        if vals.get('partner_id'):
            self.partner_id.filtered(lambda p: not p.is_re_customer).write({'is_re_customer': True})
        return res

    def unlink(self):
        for contract in self:
            if contract.state not in ('draft', 'cancelled'):
                raise UserError(_('Cancel contract %s before deleting it.', contract.name))
        self.filtered(lambda c: c.state == 'draft').unit_id.sudo().write({'state': 'available'})
        return super().unlink()

    # ------------------------------------------------------------------
    # Payment schedule
    # ------------------------------------------------------------------
    def action_generate_schedule(self):
        """(Re)build down payment + equal installments + maintenance deposit.
        Installments already invoiced are kept."""
        for contract in self:
            if contract.state not in ('draft', 'active'):
                raise UserError(_('The schedule of a closed or cancelled contract cannot be changed.'))
            locked = contract.installment_ids.filtered(lambda i: i.invoice_id)
            if locked:
                raise UserError(_('Some installments of %s are already invoiced. '
                                  'Edit the remaining installments manually.', contract.name))
            contract.installment_ids.unlink()
            currency = contract.currency_id
            lines = []
            sequence = 1
            if contract.down_payment_amount:
                lines.append({'sequence': sequence, 'name': _('Down Payment'), 'installment_type': 'down_payment',
                              'due_date': contract.down_payment_date or contract.date,
                              'amount': contract.down_payment_amount})
                sequence += 1
            remaining = contract.net_price - contract.down_payment_amount
            count = contract.installment_count
            if float_compare(remaining, 0, precision_rounding=currency.rounding) > 0:
                if not count:
                    raise UserError(_('Set the number of installments to schedule %s.',
                                      currency.format(remaining)))
                each = float_round(remaining / count, precision_rounding=currency.rounding, rounding_method='DOWN')
                months = FREQUENCY_MONTHS[contract.installment_frequency]
                first = contract.first_installment_date or contract.date + relativedelta(months=months)
                for index in range(count):
                    amount = each if index < count - 1 else currency.round(remaining - each * (count - 1))
                    lines.append({'sequence': sequence, 'name': _('Installment %s', index + 1),
                                  'installment_type': 'installment',
                                  'due_date': first + relativedelta(months=months * index), 'amount': amount})
                    sequence += 1
            if contract.maintenance_amount:
                last_due = lines and lines[-1]['due_date'] or contract.date
                lines.append({'sequence': sequence, 'name': _('Maintenance Deposit'),
                              'installment_type': 'maintenance',
                              'due_date': contract.maintenance_due_date or contract.unit_id.delivery_date
                              or contract.project_id.delivery_date or last_due,
                              'amount': contract.maintenance_amount})
            contract.installment_ids = [(0, 0, vals) for vals in lines]
        return True

    def _check_schedule(self):
        for contract in self:
            if not contract.installment_ids:
                raise UserError(_('Generate the payment schedule of %s first.', contract.name))
            if float_compare(contract.installment_total, contract.total_value,
                             precision_rounding=contract.currency_id.rounding) != 0:
                raise UserError(_(
                    'The installments of %(contract)s total %(scheduled)s but the contract value is %(value)s. '
                    'Fix the schedule before confirming.',
                    contract=contract.name, scheduled=contract.currency_id.format(contract.installment_total),
                    value=contract.currency_id.format(contract.total_value)))

    # ------------------------------------------------------------------
    # Workflow
    # ------------------------------------------------------------------
    def action_confirm(self):
        for contract in self.filtered(lambda c: c.state == 'draft'):
            if not contract.installment_ids:
                contract.action_generate_schedule()
            contract._check_schedule()
            contract.write({'state': 'active'})
            contract.unit_id.sudo().write({'state': 'sold'})
            contract.message_post(body=_('Contract confirmed: unit %s is sold.', contract.unit_id.display_name))
        self._re_auto_invoice()
        return True

    def action_cancel(self):
        for contract in self:
            if contract.payment_ids.filtered(lambda p: p.state in ('in_process', 'paid')):
                raise UserError(_('Contract %s has collected payments: refund or cancel them first.', contract.name))
            invoices = contract.installment_ids.invoice_id
            invoices.filtered(lambda m: m.state == 'posted').button_draft()
            invoices.filtered(lambda m: m.state == 'draft').button_cancel()
            contract.write({'state': 'cancelled'})
            if contract.unit_id.contract_id in (contract, self.env['re.contract']):
                contract.unit_id.sudo().write({'state': 'available'})
        return True

    def action_set_draft(self):
        for contract in self.filtered(lambda c: c.state == 'cancelled'):
            if self.search_count([('unit_id', '=', contract.unit_id.id), ('state', '!=', 'cancelled'),
                                  ('id', '!=', contract.id)]):
                raise UserError(_('Unit %s was sold again in the meantime.', contract.unit_id.display_name))
            contract.installment_ids.filtered(lambda i: i.invoice_id.state == 'cancel').write({'invoice_id': False})
            contract.write({'state': 'draft'})
            contract.unit_id.sudo().write({'state': 'reserved'})
        return True

    def _check_fully_paid(self):
        for contract in self.filtered(lambda c: c.state == 'active' and c.installment_ids):
            if float_is_zero(contract.remaining_amount, precision_rounding=contract.currency_id.rounding):
                contract.state = 'closed'
                contract.message_post(body=_('Contract fully paid.'))
        for contract in self.filtered(lambda c: c.state == 'closed'):
            if not float_is_zero(contract.remaining_amount, precision_rounding=contract.currency_id.rounding):
                contract.state = 'active'

    # ------------------------------------------------------------------
    # Invoicing / payments
    # ------------------------------------------------------------------
    def _re_auto_invoice(self):
        today = fields.Date.context_today(self)
        for contract in self.filtered(lambda c: c.state == 'active' and c.company_id.re_auto_invoice):
            limit = today + relativedelta(days=contract.company_id.re_invoice_lead_days)
            contract.installment_ids.filtered(
                lambda i: not i.invoice_id and i.due_date <= limit and i.amount > 0)._create_invoices()

    def action_invoice_all(self):
        self.ensure_one()
        if self.state != 'active':
            raise UserError(_('Confirm the contract first.'))
        self.installment_ids.filtered(lambda i: not i.invoice_id and i.amount > 0)._create_invoices()

    def action_register_payment(self):
        self.ensure_one()
        if self.state not in ('active', 'closed'):
            raise UserError(_('Confirm the contract before recording payments.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Record Payment'),
            'res_model': 're.payment.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_contract_id': self.id},
        }

    def action_view_payments(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Payments'),
            'res_model': 'account.payment',
            'view_mode': 'list,form',
            'views': [(self.env.ref('re_sales_management.view_account_payment_re_list').id, 'list'), (False, 'form')],
            'domain': [('re_contract_id', '=', self.id)],
            'context': {'create': False},
        }

    def action_view_invoices(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Invoices'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.installment_ids.invoice_id.ids)],
            'context': {'create': False, 'default_move_type': 'out_invoice'},
        }

    def action_print_statement(self):
        return self.env.ref('re_sales_management.action_report_contract_statement').report_action(self)

    # ------------------------------------------------------------------
    # Cron
    # ------------------------------------------------------------------
    @api.model
    def _cron_daily(self):
        """Refresh date-based statuses, invoice due installments, close fully paid contracts."""
        installments = self.env['re.contract.installment'].search([('state', 'not in', ('paid', 'cancelled'))])
        installments._refresh_state()
        contracts = self.search([('state', 'in', ('active', 'closed'))])
        self.env.add_to_compute(self._fields['collection_status'], contracts)
        self.env.flush_all()
        contracts._re_auto_invoice()
        contracts._check_fully_paid()
        return True

    # ------------------------------------------------------------------
    # Dashboard
    # ------------------------------------------------------------------
    @api.model
    def get_dashboard_data(self, year=None):
        today = fields.Date.context_today(self)
        year = int(year or today.year)
        company = self.env.company
        currency = company.currency_id
        Contract = self.search([])  # respects multi-company rules
        active = Contract.filtered(lambda c: c.state in ('active', 'closed'))
        Installment = self.env['re.contract.installment']
        Payment = self.env['account.payment']
        Project = self.env['re.project']
        month_start = today.replace(day=1)
        next_month = month_start + relativedelta(months=1)

        open_installments = Installment.search([('contract_id', 'in', active.ids),
                                                ('state', 'not in', ('paid', 'cancelled'))])
        payments = Payment.search([('re_contract_id', '!=', False), ('state', 'in', ('in_process', 'paid'))])

        # Monthly collections vs pending for the selected year
        collected_by_month = [0.0] * 12
        for payment in payments.filtered(lambda p: p.date.year == year):
            collected_by_month[payment.date.month - 1] += payment.amount
        pending_by_month = [0.0] * 12
        for installment in open_installments.filtered(lambda i: i.due_date.year == year):
            pending_by_month[installment.due_date.month - 1] += installment.remaining_amount

        status_counts = {key: 0 for key in ('on_track', 'at_risk', 'overdue', 'closed')}
        for contract in active:
            if contract.collection_status in status_counts:
                status_counts[contract.collection_status] += 1

        total_value = sum(active.mapped('total_value'))
        collected = sum(active.mapped('collected_amount'))
        month_start_dt = fields.Datetime.to_datetime(month_start)
        month_new = lambda records, field: len(records.filtered(  # noqa: E731
            lambda r: r[field] and r[field] >= month_start_dt))

        customers = self.env['res.partner'].search([('is_re_customer', '=', True)])
        projects = Project.search([], order='sequence, id')

        def contract_row(c):
            return {'id': c.id, 'name': c.name, 'customer': c.partner_id.name, 'project': c.project_id.name,
                    'unit': c.unit_id.name, 'value': c.total_value, 'collected': c.collected_amount,
                    'remaining': c.remaining_amount, 'status': c.collection_status or c.state,
                    'status_label': dict(c._fields['collection_status']._description_selection(self.env)).get(
                        c.collection_status) or dict(c._fields['state']._description_selection(self.env))[c.state]}

        upcoming = open_installments.sorted(lambda i: (i.due_date, i.id))[:6]
        inst_states = dict(Installment._fields['state']._description_selection(self.env))
        method_labels = dict(Payment._fields['re_payment_method']._description_selection(self.env))
        return {
            'currency': {'symbol': currency.symbol, 'position': currency.position, 'id': currency.id},
            'year': year,
            'years': list(range(today.year - 3, today.year + 3)),
            'kpi': {
                'projects': len(projects),
                'projects_new': month_new(projects, 'create_date'),
                'customers': len(customers),
                'customers_new': month_new(customers, 'create_date'),
                'contracts': len(active),
                'contracts_new': len(active.filtered(lambda c: c.date >= month_start)),
                'total_value': total_value,
                'collected': collected,
                'collected_pct': total_value and round(collected * 100.0 / total_value, 1) or 0,
            },
            'chart': {'collected': collected_by_month, 'pending': pending_by_month},
            'status': status_counts,
            'receivables': {
                'outstanding': sum(active.mapped('remaining_amount')),
                'due_this_month': sum(open_installments.filtered(
                    lambda i: month_start <= i.due_date < next_month).mapped('remaining_amount')),
                'overdue': sum(open_installments.filtered(lambda i: i.state == 'overdue').mapped('remaining_amount')),
            },
            'recent_contracts': [contract_row(c) for c in active.sorted(lambda c: (c.date, c.id), reverse=True)[:5]],
            'upcoming': [{'id': i.id, 'due_date': fields.Date.to_string(i.due_date), 'contract': i.contract_id.name,
                          'contract_id': i.contract_id.id, 'customer': i.partner_id.name,
                          'amount': i.remaining_amount, 'state': i.state, 'state_label': inst_states[i.state]}
                         for i in upcoming],
            'recent_payments': [{'id': p.id, 'date': fields.Date.to_string(p.date), 'contract': p.re_contract_id.name,
                                 'customer': p.partner_id.name, 'amount': p.amount,
                                 'method': p.re_payment_method or 'bank_transfer',
                                 'method_label': method_labels.get(p.re_payment_method or 'bank_transfer'),
                                 'reference': p.re_cheque_number or p.memo or p.name}
                                for p in payments.sorted(lambda p: (p.date, p.id), reverse=True)[:5]],
            'projects': [{'id': p.id, 'name': p.name, 'units': p.total_units, 'sold': p.sold_units,
                          'available': p.available_units, 'sales_value': p.sales_value,
                          'collection_pct': round(p.collection_pct, 1)} for p in projects[:8]],
        }

    # ------------------------------------------------------------------
    # Demo data
    # ------------------------------------------------------------------
    @api.model
    def _re_load_demo(self):
        """Create demo contracts with schedules, invoices and collections.
        Skipped when the company has no chart of accounts yet."""
        company = self.env.company
        if not company.chart_template or not self.env['account.journal'].search_count(
                [('company_id', '=', company.id), ('type', '=', 'bank')]):
            return False
        ref = lambda xmlid: self.env.ref(xmlid, raise_if_not_found=False)  # noqa: E731
        today = fields.Date.context_today(self)
        Wizard = self.env['re.payment.wizard']

        def pay_due(contract, until, method='bank_transfer', skip=(), cheque_prefix='10'):
            """Pay every installment due before `until`, each one on its due date."""
            for index, inst in enumerate(contract.installment_ids.sorted(lambda i: (i.due_date, i.sequence))):
                if inst.due_date > until or index in skip or inst.state == 'paid':
                    continue
                vals = {
                    'contract_id': contract.id,
                    'installment_ids': [(6, 0, inst.ids)],
                    'amount': inst.remaining_amount,
                    'date': min(inst.due_date, today),
                    'payment_method': method,
                    'journal_id': company._re_get_journal(method).id,
                }
                if method == 'cheque':
                    vals.update({'cheque_number': '%s%04d' % (cheque_prefix, contract.id * 100 + index),
                                 'cheque_date': inst.due_date, 'cheque_holder': contract.partner_id.name})
                elif method == 'bank_transfer':
                    vals['reference'] = 'TRX-%s-%02d' % (contract.id, index + 1)
                Wizard.create(vals).action_confirm()

        plans = [
            # unit, customer, days ago, frequency, count, dp %, payer, method, skip, extra
            ('re_developer_website.unit_palm_a101', 'customer_ahmed', 330, 'quarterly', 32, 10, today, 'bank_transfer', (), {}),
            ('re_developer_website.unit_palm_b204', 'customer_sara', 250, 'monthly', 96, 10,
             today - relativedelta(days=75), 'cash', (), {}),
            ('re_developer_website.unit_bay_c07', 'customer_omar', 210, 'quarterly', 40, 5, today, 'cheque', (), {}),
            ('re_developer_website.unit_tower_o1205', 'customer_mona', 140, 'monthly', 48, 20,
             today - relativedelta(days=20), 'bank_transfer', (), {'maintenance_amount': 150000}),
            ('re_developer_website.unit_bay_t03', 'customer_youssef', 95, 'quarterly', 40, 5, today, 'cheque', (), {}),
            ('re_sales_management.unit_tower_k04', 'customer_nour', 45, 'quarterly', 0, 100, today, 'cash', (), {}),
            ('re_sales_management.unit_palm_a305', 'customer_laila', 12, 'quarterly', 32, 10, today, 'bank_transfer', (), {}),
        ]
        created = self.browse()
        for unit_x, customer_x, days, freq, count, dp, until, method, skip, extra in plans:
            unit = ref(unit_x)
            partner = ref('re_sales_management.%s' % customer_x)
            if not unit or not partner or unit.contract_ids:
                continue
            cdate = today - relativedelta(days=days)
            contract = self.create(dict({
                'partner_id': partner.id,
                'user_id': self.env.ref('base.user_admin').id,
                'unit_id': unit.id,
                'project_id': unit.project_id.id,
                'date': cdate,
                'unit_price': unit.price,
                'down_payment_type': 'percent',
                'down_payment_percent': dp,
                'down_payment_date': cdate,
                'installment_frequency': freq,
                'installment_count': count,
                'first_installment_date': cdate + relativedelta(months=FREQUENCY_MONTHS[freq]),
            }, **extra))
            contract.action_generate_schedule()
            contract.action_confirm()
            pay_due(contract, until, method=method, skip=skip, cheque_prefix=str(40 + len(created)))
            created |= contract
        # Cheques: older ones cleared, the latest one of TW-03 bounced
        cheques = self.env['account.payment'].search(
            [('re_contract_id', 'in', created.ids), ('re_payment_method', '=', 'cheque')], order='date')
        if cheques:
            cheques[:-2].action_re_cheque_deposit()
            cheques[:-2].action_re_cheque_clear()
            bounced = cheques.filtered(lambda p: p.re_unit_id == ref('re_developer_website.unit_bay_t03'))[-1:]
            if bounced:
                bounced.action_re_cheque_bounce()
        # A reservation waiting for confirmation
        unit = ref('re_developer_website.unit_palm_d01')
        partner = ref('re_sales_management.customer_ahmed')
        if unit and partner and not unit.contract_ids:
            reservation = self.create({
                'partner_id': partner.id, 'unit_id': unit.id, 'project_id': unit.project_id.id,
                'date': today - relativedelta(days=3), 'unit_price': unit.price, 'discount_amount': 300000,
                'down_payment_percent': 15, 'installment_frequency': 'quarterly', 'installment_count': 28,
            })
            reservation.action_generate_schedule()
        self.env['re.contract']._cron_daily()
        return True
