# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ReBuilding(models.Model):
    _name = 're.building'
    _description = 'Building'
    _inherit = ['mail.thread', 'image.mixin']
    _order = 'project_id, sequence, name'

    name = fields.Char(required=True, tracking=True)
    code = fields.Char()
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    project_id = fields.Many2one('re.project', required=True, ondelete='cascade', index=True, tracking=True)
    company_id = fields.Many2one(related='project_id.company_id', store=True)
    floors_label = fields.Char('Floors', help='e.g. G+5')
    floor_count = fields.Integer('Number of Floors')
    notes = fields.Html()
    unit_ids = fields.One2many('re.unit', 'building_id', 'Units')
    unit_count = fields.Integer(compute='_compute_unit_stats')
    available_count = fields.Integer('Available', compute='_compute_unit_stats')
    reserved_count = fields.Integer('Reserved', compute='_compute_unit_stats')
    sold_count = fields.Integer('Sold', compute='_compute_unit_stats')

    _sql_constraints = [
        ('name_project_uniq', 'unique(project_id, name)', 'A building with this name already exists in the project.'),
    ]

    def _compute_unit_stats(self):
        data = self.env['re.unit']._read_group(
            [('building_id', 'in', self.ids)], ['building_id', 'state'], ['__count'])
        stats = {}
        for building, state, count in data:
            stats.setdefault(building.id, {})[state] = count
        for building in self:
            values = stats.get(building.id, {})
            building.available_count = values.get('available', 0)
            building.reserved_count = values.get('reserved', 0)
            building.sold_count = values.get('sold', 0)
            building.unit_count = sum(values.values())

    @api.depends('name', 'project_id.name')
    def _compute_display_name(self):
        for building in self:
            building.display_name = '%s / %s' % (building.project_id.name, building.name) \
                if building.project_id else building.name

    def action_view_units(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.display_name,
            'res_model': 're.unit',
            'view_mode': 'list,form',
            'domain': [('building_id', '=', self.id)],
            'context': {'default_building_id': self.id, 'default_project_id': self.project_id.id},
        }
