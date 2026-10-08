# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ReUnit(models.Model):
    _name = 're.unit'
    _description = 'Real Estate Unit'
    _inherit = [
        'mail.thread',
        'mail.activity.mixin',
        'image.mixin',
        'website.published.mixin',
        'website.seo.metadata',
    ]
    _order = 'project_id, sequence, name'

    name = fields.Char('Unit Code', required=True, tracking=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    is_featured = fields.Boolean('Featured on Homepage')
    project_id = fields.Many2one('re.project', required=True, ondelete='cascade', index=True, tracking=True)
    company_id = fields.Many2one(related='project_id.company_id', store=True)
    currency_id = fields.Many2one(related='project_id.currency_id')

    unit_type = fields.Selection([
        ('apartment', 'Apartment'),
        ('duplex', 'Duplex'),
        ('penthouse', 'Penthouse'),
        ('townhouse', 'Townhouse'),
        ('twinhouse', 'Twin House'),
        ('villa', 'Villa'),
        ('chalet', 'Chalet'),
        ('office', 'Office'),
        ('retail', 'Retail / Shop'),
        ('clinic', 'Clinic'),
    ], required=True, default='apartment', tracking=True)
    state = fields.Selection([
        ('available', 'Available'),
        ('reserved', 'Reserved'),
        ('sold', 'Sold'),
    ], string='Status', required=True, default='available', tracking=True)
    finishing = fields.Selection([
        ('core_shell', 'Core & Shell'),
        ('semi', 'Semi Finished'),
        ('fully', 'Fully Finished'),
        ('furnished', 'Furnished'),
    ], default='semi')

    bedrooms = fields.Integer()
    bathrooms = fields.Integer()
    area = fields.Float('Built-up Area (m²)')
    garden_area = fields.Float('Garden / Terrace (m²)')
    floor = fields.Char()
    unit_view = fields.Char('View', translate=True, help='e.g. Garden view, Lagoon view')
    delivery_date = fields.Date()

    price = fields.Monetary(tracking=True)
    price_per_meter = fields.Monetary('Price / m²', compute='_compute_payment_plan')
    down_payment_pct = fields.Float('Down Payment (%)', default=10.0)
    installment_years = fields.Integer('Installment Years', default=7)
    down_payment_amount = fields.Monetary(compute='_compute_payment_plan')
    monthly_installment = fields.Monetary(compute='_compute_payment_plan')

    description = fields.Html(translate=True, sanitize_attributes=False)

    _sql_constraints = [
        ('name_project_uniq', 'unique(project_id, name)', 'Unit code must be unique per project.'),
    ]

    @api.constrains('down_payment_pct', 'installment_years')
    def _check_payment_plan(self):
        for unit in self:
            if not 0 <= unit.down_payment_pct <= 100:
                raise ValidationError(_('Down payment must be between 0 and 100%.'))
            if unit.installment_years < 0:
                raise ValidationError(_('Installment years cannot be negative.'))

    @api.depends('price', 'area', 'down_payment_pct', 'installment_years')
    def _compute_payment_plan(self):
        for unit in self:
            unit.price_per_meter = unit.area and unit.price / unit.area or 0.0
            unit.down_payment_amount = unit.price * unit.down_payment_pct / 100.0
            months = unit.installment_years * 12
            remaining = unit.price - unit.down_payment_amount
            unit.monthly_installment = months and remaining / months or 0.0

    @api.depends('name', 'project_id.name')
    def _compute_display_name(self):
        for unit in self:
            unit.display_name = unit.project_id and '%s - %s' % (unit.project_id.name, unit.name) or unit.name

    def _compute_website_url(self):
        super()._compute_website_url()
        for unit in self:
            if unit.id:
                unit.website_url = '/estate/unit/%s' % self.env['ir.http']._slug(unit)

    def action_reserve(self):
        self.write({'state': 'reserved'})

    def action_sell(self):
        self.write({'state': 'sold'})

    def action_set_available(self):
        self.write({'state': 'available'})
