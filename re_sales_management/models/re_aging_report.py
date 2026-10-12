# -*- coding: utf-8 -*-
from odoo import fields, models, tools


class ReReceivableAging(models.Model):
    """Unpaid installments of active contracts, bucketed by days overdue (as of today)."""
    _name = 're.receivable.aging'
    _description = 'Receivables Aging'
    _auto = False
    _order = 'due_date'

    installment_id = fields.Many2one('re.contract.installment', readonly=True)
    contract_id = fields.Many2one('re.contract', readonly=True)
    partner_id = fields.Many2one('res.partner', 'Customer', readonly=True)
    project_id = fields.Many2one('re.project', readonly=True)
    unit_id = fields.Many2one('re.unit', readonly=True)
    user_id = fields.Many2one('res.users', 'Salesperson', readonly=True)
    company_id = fields.Many2one('res.company', readonly=True)
    currency_id = fields.Many2one('res.currency', readonly=True)
    due_date = fields.Date(readonly=True)
    days_overdue = fields.Integer(readonly=True, aggregator='max')
    amount = fields.Monetary('Installment Amount', readonly=True)
    remaining_amount = fields.Monetary('Outstanding', readonly=True)
    not_due = fields.Monetary('Not Due Yet', readonly=True)
    bucket_0_30 = fields.Monetary('1-30 Days', readonly=True)
    bucket_31_60 = fields.Monetary('31-60 Days', readonly=True)
    bucket_61_90 = fields.Monetary('61-90 Days', readonly=True)
    bucket_90_plus = fields.Monetary('Over 90 Days', readonly=True)
    bucket = fields.Selection([
        ('0_not_due', 'Not Due Yet'),
        ('1_0_30', '1-30 Days'),
        ('2_31_60', '31-60 Days'),
        ('3_61_90', '61-90 Days'),
        ('4_90_plus', 'Over 90 Days'),
    ], readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    i.id AS id,
                    i.id AS installment_id,
                    c.id AS contract_id,
                    c.partner_id,
                    c.project_id,
                    c.unit_id,
                    c.user_id,
                    c.company_id,
                    rc.currency_id,
                    i.due_date,
                    GREATEST(CURRENT_DATE - i.due_date, 0) AS days_overdue,
                    i.amount,
                    i.remaining_amount,
                    CASE WHEN i.due_date >= CURRENT_DATE THEN i.remaining_amount ELSE 0 END AS not_due,
                    CASE WHEN CURRENT_DATE - i.due_date BETWEEN 1 AND 30 THEN i.remaining_amount ELSE 0 END AS bucket_0_30,
                    CASE WHEN CURRENT_DATE - i.due_date BETWEEN 31 AND 60 THEN i.remaining_amount ELSE 0 END AS bucket_31_60,
                    CASE WHEN CURRENT_DATE - i.due_date BETWEEN 61 AND 90 THEN i.remaining_amount ELSE 0 END AS bucket_61_90,
                    CASE WHEN CURRENT_DATE - i.due_date > 90 THEN i.remaining_amount ELSE 0 END AS bucket_90_plus,
                    CASE
                        WHEN i.due_date >= CURRENT_DATE THEN '0_not_due'
                        WHEN CURRENT_DATE - i.due_date <= 30 THEN '1_0_30'
                        WHEN CURRENT_DATE - i.due_date <= 60 THEN '2_31_60'
                        WHEN CURRENT_DATE - i.due_date <= 90 THEN '3_61_90'
                        ELSE '4_90_plus'
                    END AS bucket
                FROM re_contract_installment i
                JOIN re_contract c ON c.id = i.contract_id
                JOIN res_company rc ON rc.id = c.company_id
                WHERE c.state IN ('active', 'closed')
                  AND i.remaining_amount > 0.001
            )
        """ % self._table)
