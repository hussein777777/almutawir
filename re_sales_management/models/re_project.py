# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class ReProject(models.Model):
    _inherit = 're.project'

    code = fields.Char(tracking=True)
    sales_state = fields.Selection([
        ('active', 'Active'),
        ('on_hold', 'On Hold'),
        ('closed', 'Closed'),
    ], string='Sales Status', default='active', required=True, tracking=True)
    developer_name = fields.Char('Developer Name')
    construction_start_date = fields.Date('Construction Start')
    completion_date = fields.Date('Completion')
    master_plan = fields.Binary(attachment=True)
    master_plan_filename = fields.Char()
    external_website = fields.Char('Project Website')
    analytic_account_id = fields.Many2one(
        'account.analytic.account', 'Analytic Account',
        help='Installment invoices of this project are tagged with this analytic account.')

    building_ids = fields.One2many('re.building', 'project_id', 'Buildings')
    all_unit_ids = fields.One2many('re.unit', 'project_id', 'All Units', context={'active_test': False})
    contract_ids = fields.One2many('re.contract', 'project_id', 'Contracts')

    building_count = fields.Integer('Building Count', compute='_compute_sales_stats')
    total_units = fields.Integer('Total Units', compute='_compute_sales_stats')
    available_units = fields.Integer('Available', compute='_compute_sales_stats')
    reserved_units = fields.Integer('Reserved', compute='_compute_sales_stats')
    sold_units = fields.Integer('Sold', compute='_compute_sales_stats')
    available_pct = fields.Float('Available %', compute='_compute_sales_stats')
    reserved_pct = fields.Float('Reserved %', compute='_compute_sales_stats')
    sold_pct = fields.Float('Sold %', compute='_compute_sales_stats')
    contract_count = fields.Integer('Contract Count', compute='_compute_sales_stats')
    sales_value = fields.Monetary('Sales Value', compute='_compute_sales_stats')
    collected_amount = fields.Monetary('Collected', compute='_compute_sales_stats')
    collection_pct = fields.Float('Collection %', compute='_compute_sales_stats')

    def _compute_sales_stats(self):
        Unit = self.env['re.unit'].sudo()
        unit_data = Unit._read_group([('project_id', 'in', self.ids)], ['project_id', 'state'], ['__count'])
        units = {}
        for project, state, count in unit_data:
            units.setdefault(project.id, {})[state] = count
        building_data = dict(self.env['re.building'].sudo()._read_group(
            [('project_id', 'in', self.ids)], ['project_id'], ['__count']))
        contract_data = self.env['re.contract'].sudo()._read_group(
            [('project_id', 'in', self.ids), ('state', 'in', ('active', 'closed'))],
            ['project_id'], ['__count', 'total_value:sum', 'collected_amount:sum'])
        contracts = {project.id: (count, total, collected) for project, count, total, collected in contract_data}
        for project in self:
            values = units.get(project.id, {})
            total = sum(values.values())
            project.total_units = total
            project.available_units = values.get('available', 0)
            project.reserved_units = values.get('reserved', 0)
            project.sold_units = values.get('sold', 0)
            project.available_pct = total and project.available_units * 100.0 / total or 0.0
            project.reserved_pct = total and project.reserved_units * 100.0 / total or 0.0
            project.sold_pct = total and project.sold_units * 100.0 / total or 0.0
            project.building_count = building_data.get(project, 0)
            count, value, collected = contracts.get(project.id, (0, 0.0, 0.0))
            project.contract_count = count
            project.sales_value = value
            project.collected_amount = collected
            project.collection_pct = value and collected * 100.0 / value or 0.0

    def action_set_active(self):
        self.write({'sales_state': 'active'})

    def action_set_on_hold(self):
        self.write({'sales_state': 'on_hold'})

    def action_set_closed(self):
        self.write({'sales_state': 'closed'})

    def _action_open(self, model, name, domain, context=None, views='list,form'):
        return {
            'type': 'ir.actions.act_window',
            'name': name,
            'res_model': model,
            'view_mode': views,
            'domain': domain,
            'context': dict(context or {}),
        }

    def action_view_buildings(self):
        self.ensure_one()
        return self._action_open('re.building', _('Buildings'), [('project_id', '=', self.id)],
                                 {'default_project_id': self.id})

    def action_view_all_units(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('re_sales_management.re_unit_sales_action')
        action.update({
            'domain': [('project_id', '=', self.id)],
            'context': {'default_project_id': self.id, 'search_default_group_building': 0},
            'name': _('Units - %s', self.name),
        })
        return action

    def action_view_contracts(self):
        self.ensure_one()
        return self._action_open('re.contract', _('Contracts'), [('project_id', '=', self.id)],
                                 {'default_project_id': self.id})

    def action_view_units_state(self):
        """Stat cards: open the units of the clicked status."""
        self.ensure_one()
        action = self.action_view_all_units()
        state = self.env.context.get('unit_state')
        if state:
            action['domain'] = [('project_id', '=', self.id), ('state', '=', state)]
        return action
