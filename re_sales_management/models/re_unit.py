# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class ReUnitTag(models.Model):
    _name = 're.unit.tag'
    _description = 'Unit Tag'
    _order = 'name'

    name = fields.Char(required=True, translate=True)
    color = fields.Integer()

    _sql_constraints = [('name_uniq', 'unique(name)', 'This tag already exists.')]


class ReUnitImage(models.Model):
    _name = 're.unit.image'
    _description = 'Unit Image'
    _inherit = ['image.mixin']
    _order = 'sequence, id'

    name = fields.Char()
    sequence = fields.Integer(default=10)
    unit_id = fields.Many2one('re.unit', required=True, ondelete='cascade', index=True)
    image_1920 = fields.Image(required=True, max_width=1920, max_height=1920)


class ReUnit(models.Model):
    _inherit = 're.unit'

    building_id = fields.Many2one('re.building', 'Building', index=True, tracking=True,
                                  domain="[('project_id', '=', project_id)]")
    unit_number = fields.Char()
    facing = fields.Selection([
        ('north', 'North'), ('south', 'South'), ('east', 'East'), ('west', 'West'),
        ('north_east', 'North-East'), ('north_west', 'North-West'),
        ('south_east', 'South-East'), ('south_west', 'South-West'),
    ])
    has_parking = fields.Boolean('Parking Slot')
    parking_number = fields.Char('Parking Slot No.')
    tag_ids = fields.Many2many('re.unit.tag', string='Tags')
    internal_notes = fields.Text()
    image_ids = fields.One2many('re.unit.image', 'unit_id', 'Images')

    contract_ids = fields.One2many('re.contract', 'unit_id', 'Contracts')
    contract_id = fields.Many2one('re.contract', 'Current Contract', compute='_compute_contract', store=True)
    customer_id = fields.Many2one('res.partner', 'Customer', compute='_compute_contract', store=True, index=True)

    @api.depends('contract_ids.state', 'contract_ids.partner_id')
    def _compute_contract(self):
        for unit in self:
            contract = unit.contract_ids.filtered(lambda c: c.state != 'cancelled').sorted('id', reverse=True)[:1]
            unit.contract_id = contract
            unit.customer_id = contract.partner_id

    @api.constrains('building_id', 'project_id')
    def _check_building_project(self):
        for unit in self:
            if unit.building_id and unit.building_id.project_id != unit.project_id:
                raise ValidationError(_('The building of unit %s belongs to another project.', unit.name))

    @api.onchange('building_id')
    def _onchange_building_id(self):
        if self.building_id:
            self.project_id = self.building_id.project_id

    def _guard_contract_state(self):
        for unit in self:
            if unit.contract_id and unit.contract_id.state in ('draft', 'active', 'closed'):
                raise UserError(_('Unit %(unit)s is linked to contract %(contract)s: change it from the contract.',
                                  unit=unit.display_name, contract=unit.contract_id.name))

    def action_set_available(self):
        self._guard_contract_state()
        return super().action_set_available()

    def action_view_contracts(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Contracts'),
            'res_model': 're.contract',
            'view_mode': 'list,form',
            'domain': [('unit_id', '=', self.id)],
            'context': {'default_unit_id': self.id, 'default_project_id': self.project_id.id},
        }

    def action_new_contract(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('New Contract'),
            'res_model': 're.contract',
            'view_mode': 'form',
            'context': {'default_unit_id': self.id, 'default_project_id': self.project_id.id},
        }
