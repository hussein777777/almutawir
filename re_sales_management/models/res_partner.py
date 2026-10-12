# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    is_re_customer = fields.Boolean('Real Estate Customer', index=True)
    re_customer_code = fields.Char('Customer Code', copy=False, readonly=True, index=True)
    re_national_id = fields.Char('National ID / Passport', index=True)
    re_birthdate = fields.Date('Date of Birth')
    re_source = fields.Selection([
        ('walk_in', 'Walk-in'),
        ('referral', 'Referral'),
        ('website', 'Website'),
        ('social', 'Social Media'),
        ('broker', 'Broker'),
        ('exhibition', 'Exhibition / Event'),
        ('other', 'Other'),
    ], string='Customer Source')
    re_contract_ids = fields.One2many('re.contract', 'partner_id', 'Real Estate Contracts')
    re_contract_count = fields.Integer('Contracts', compute='_compute_re_totals')
    re_unit_count = fields.Integer('Units', compute='_compute_re_totals')
    re_total_value = fields.Monetary('Total Contract Value', compute='_compute_re_totals',
                                     currency_field='re_currency_id')
    re_collected = fields.Monetary('Total Collected', compute='_compute_re_totals', currency_field='re_currency_id')
    re_remaining = fields.Monetary('Remaining', compute='_compute_re_totals', currency_field='re_currency_id')
    re_overdue_amount = fields.Monetary('Overdue Amount', compute='_compute_re_totals',
                                        currency_field='re_currency_id')
    re_overdue_count = fields.Integer('Overdue Installments', compute='_compute_re_totals')
    re_collection_pct = fields.Float('Collected %', compute='_compute_re_totals')
    re_currency_id = fields.Many2one('res.currency', compute='_compute_re_totals')

    _sql_constraints = [
        ('re_customer_code_uniq', 'unique(re_customer_code)', 'Customer code must be unique.'),
    ]

    def _compute_re_totals(self):
        Contract = self.env['re.contract'].sudo()
        Installment = self.env['re.contract.installment'].sudo()
        data = Contract._read_group(
            [('partner_id', 'in', self.ids), ('state', 'in', ('active', 'closed'))], ['partner_id'],
            ['__count', 'total_value:sum', 'collected_amount:sum', 'remaining_amount:sum'])
        totals = {partner.id: rest for partner, *rest in data}
        overdue = {partner.id: (count, amount) for partner, count, amount in Installment._read_group(
            [('partner_id', 'in', self.ids), ('state', '=', 'overdue')],
            ['partner_id'], ['__count', 'remaining_amount:sum'])}
        currency = self.env.company.currency_id
        for partner in self:
            count, value, collected, remaining = totals.get(partner.id, (0, 0.0, 0.0, 0.0))
            partner.re_contract_count = count
            partner.re_unit_count = count
            partner.re_total_value = value
            partner.re_collected = collected
            partner.re_remaining = remaining
            partner.re_collection_pct = value and collected * 100.0 / value or 0.0
            partner.re_overdue_count, partner.re_overdue_amount = overdue.get(partner.id, (0, 0.0))
            partner.re_currency_id = currency

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('is_re_customer') and not vals.get('re_customer_code'):
                vals['re_customer_code'] = self.env['ir.sequence'].sudo().next_by_code('re.customer')
        return super().create(vals_list)

    def write(self, vals):
        res = super().write(vals)
        if vals.get('is_re_customer'):
            for partner in self.filtered(lambda p: not p.re_customer_code):
                partner.re_customer_code = self.env['ir.sequence'].sudo().next_by_code('re.customer')
        return res

    def _re_action(self, model, name, domain, context=None):
        return {
            'type': 'ir.actions.act_window', 'name': name, 'res_model': model,
            'view_mode': 'list,form', 'domain': domain, 'context': context or {},
        }

    def action_re_view_contracts(self):
        self.ensure_one()
        return self._re_action('re.contract', _('Contracts'), [('partner_id', '=', self.id)],
                               {'default_partner_id': self.id})

    def action_re_view_installments(self):
        self.ensure_one()
        return self._re_action('re.contract.installment', _('Installments'),
                               [('partner_id', '=', self.id), ('contract_id.state', 'in', ('active', 'closed'))])

    def action_re_view_payments(self):
        self.ensure_one()
        action = self._re_action('account.payment', _('Payments'),
                                 [('partner_id', '=', self.id), ('re_contract_id', '!=', False)])
        action['context'] = {'create': False}
        return action

    def action_re_view_units(self):
        self.ensure_one()
        return self._re_action('re.unit', _('Units'), [('customer_id', '=', self.id)])
