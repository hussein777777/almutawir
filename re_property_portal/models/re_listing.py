# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.osv import expression

PROPERTY_TYPES = [
    ('apartment', 'Apartment'),
    ('villa', 'Villa'),
    ('townhouse', 'Townhouse'),
    ('twinhouse', 'Twin House'),
    ('duplex', 'Duplex'),
    ('penthouse', 'Penthouse'),
    ('chalet', 'Chalet'),
    ('studio', 'Studio'),
    ('ivilla', 'iVilla'),
    ('office', 'Office'),
    ('retail', 'Retail / Shop'),
    ('clinic', 'Clinic'),
    ('land', 'Land'),
    ('building', 'Whole Building'),
]
NON_RESIDENTIAL = ('office', 'retail', 'clinic', 'land', 'building')
LISTING_SORTS = {
    'featured': 'is_premium desc, published_date desc, id desc',
    'newest': 'published_date desc, id desc',
    'price_asc': 'price asc, id desc',
    'price_desc': 'price desc, id desc',
    'area_desc': 'area desc, id desc',
}
# Fields an agent may edit from the portal (everything else is back-office only)
PORTAL_FIELDS = [
    'name', 'listing_type', 'property_type', 'completion', 'sale_type', 'furnishing', 'finishing',
    'price', 'rent_period', 'down_payment', 'installment_years', 'bedrooms', 'bathrooms', 'area',
    'garden_area', 'floor', 'delivery_date', 'location_id', 'address', 'latitude', 'longitude',
    'description', 'amenity_ids', 'project_id',
]


def _to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _to_float(value):
    try:
        return float(str(value).replace(',', ''))
    except (TypeError, ValueError):
        return 0.0


def _csv_values(value):
    if not value:
        return []
    if isinstance(value, (list, tuple)):
        value = ','.join(value)
    return [v for v in str(value).split(',') if v]


class ReListing(models.Model):
    _name = 're.listing'
    _description = 'Property Listing'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'website.published.mixin', 'website.seo.metadata']
    _order = 'is_premium desc, published_date desc, id desc'

    name = fields.Char('Title', required=True, translate=True, tracking=True)
    reference = fields.Char(readonly=True, copy=False, default='/', index=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('pending', 'Pending Review'),
        ('published', 'Published'),
        ('rejected', 'Rejected'),
        ('closed', 'Sold / Rented'),
    ], default='draft', required=True, tracking=True, index=True, copy=False)
    rejection_reason = fields.Text(copy=False)
    published_date = fields.Datetime(readonly=True, copy=False, index=True)
    is_premium = fields.Boolean('Premium', tracking=True, help='Premium listings are shown first.')
    active = fields.Boolean(default=True)

    listing_type = fields.Selection([
        ('sale', 'For Sale'),
        ('rent', 'For Rent'),
    ], string='Purpose', required=True, default='sale', index=True, tracking=True)
    property_type = fields.Selection(PROPERTY_TYPES, required=True, default='apartment', index=True)
    completion = fields.Selection([('ready', 'Ready'), ('offplan', 'Off-plan')], default='ready', required=True)
    sale_type = fields.Selection([('primary', 'First Sale'), ('resale', 'Resale')], default='resale')
    furnishing = fields.Selection([
        ('unfurnished', 'Unfurnished'),
        ('semi', 'Semi Furnished'),
        ('furnished', 'Furnished'),
    ], default='unfurnished')
    finishing = fields.Selection([
        ('core_shell', 'Core & Shell'),
        ('semi', 'Semi Finished'),
        ('fully', 'Fully Finished'),
    ], default='fully')

    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    price = fields.Monetary(required=True, tracking=True)
    rent_period = fields.Selection([('month', 'Monthly'), ('year', 'Yearly')], default='month')
    down_payment = fields.Monetary()
    installment_years = fields.Integer()
    monthly_installment = fields.Monetary(compute='_compute_figures')
    price_per_meter = fields.Monetary('Price / m²', compute='_compute_figures')

    bedrooms = fields.Integer(help='0 = studio')
    bathrooms = fields.Integer()
    area = fields.Float('Area (m²)')
    garden_area = fields.Float('Garden / Roof (m²)')
    floor = fields.Char()
    delivery_date = fields.Date()

    location_id = fields.Many2one('re.location', required=True, index=True, tracking=True)
    address = fields.Char()
    latitude = fields.Float(digits=(10, 7))
    longitude = fields.Float(digits=(10, 7))
    project_id = fields.Many2one('re.project', 'Project / Compound', index=True)

    agent_id = fields.Many2one('re.agent', required=True, index=True, tracking=True,
                               domain=[('state', '=', 'active')])
    agency_id = fields.Many2one(related='agent_id.agency_id', store=True, index=True)
    amenity_ids = fields.Many2many('re.amenity', string='Amenities')
    image_ids = fields.One2many('re.listing.image', 'listing_id', 'Photos', copy=True)
    cover_image_id = fields.Many2one('re.listing.image', compute='_compute_cover_image')
    image_count = fields.Integer(compute='_compute_cover_image')
    description = fields.Html(translate=True, sanitize_attributes=False)

    view_count = fields.Integer('Views', readonly=True, copy=False, default=0)
    lead_ids = fields.One2many('crm.lead', 're_listing_id', 'Inquiries')
    lead_count = fields.Integer(compute='_compute_lead_count')

    _sql_constraints = [
        ('price_positive', 'CHECK(price >= 0)', 'The price cannot be negative.'),
    ]

    # ------------------------------------------------------------------
    # Computes / constraints
    # ------------------------------------------------------------------
    @api.depends('price', 'area', 'down_payment', 'installment_years', 'listing_type')
    def _compute_figures(self):
        for listing in self:
            listing.price_per_meter = listing.area and listing.price / listing.area or 0.0
            months = listing.installment_years * 12
            if listing.listing_type == 'sale' and months:
                listing.monthly_installment = (listing.price - listing.down_payment) / months
            else:
                listing.monthly_installment = 0.0

    @api.depends('image_ids', 'image_ids.sequence')
    def _compute_cover_image(self):
        for listing in self:
            images = listing.image_ids.sorted('sequence')
            listing.cover_image_id = images[:1]
            listing.image_count = len(images)

    def _compute_lead_count(self):
        data = self.env['crm.lead'].sudo()._read_group(
            [('re_listing_id', 'in', self.ids)], ['re_listing_id'], ['__count'])
        counts = {listing.id: count for listing, count in data}
        for listing in self:
            listing.lead_count = counts.get(listing.id, 0)

    @api.constrains('down_payment', 'price', 'installment_years', 'latitude', 'longitude')
    def _check_values(self):
        for listing in self:
            if listing.down_payment < 0 or listing.down_payment > listing.price:
                raise ValidationError(_('The down payment must be between 0 and the price.'))
            if listing.installment_years < 0:
                raise ValidationError(_('Installment years cannot be negative.'))
            if not -90 <= listing.latitude <= 90 or not -180 <= listing.longitude <= 180:
                raise ValidationError(_('Invalid map coordinates.'))

    def _compute_website_url(self):
        super()._compute_website_url()
        for listing in self:
            if listing.id:
                listing.website_url = '/property/%s' % self.env['ir.http']._slug(listing)

    @api.depends('name', 'reference')
    def _compute_display_name(self):
        for listing in self:
            listing.display_name = '[%s] %s' % (listing.reference, listing.name) \
                if listing.reference and listing.reference != '/' else listing.name

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('reference', '/') == '/':
                vals['reference'] = self.env['ir.sequence'].sudo().next_by_code('re.listing') or '/'
        return super().create(vals_list)

    def write(self, vals):
        # Publishing is driven by the review workflow, keep the flag in sync
        if 'is_published' in vals and 'state' not in vals:
            for listing in self:
                if vals['is_published'] and listing.state != 'published':
                    raise UserError(_('Approve the listing to publish it.'))
        return super().write(vals)

    # ------------------------------------------------------------------
    # Display helpers
    # ------------------------------------------------------------------
    def _get_location_trail(self):
        """'Area, City' - the two most specific levels, as shown on cards."""
        self.ensure_one()
        names = []
        location = self.location_id
        while location and len(names) < 2:
            names.append(location.name)
            location = location.parent_id
        return ', '.join(names)

    def _get_images(self):
        self.ensure_one()
        return self.image_ids.sorted('sequence')

    # ------------------------------------------------------------------
    # Workflow
    # ------------------------------------------------------------------
    def _check_complete(self):
        for listing in self:
            if not listing.image_ids:
                raise UserError(_('Add at least one photo to "%s" before submitting it.', listing.name))

    def action_submit(self):
        self._check_complete()
        self.filtered(lambda l: l.state in ('draft', 'rejected')).write({
            'state': 'pending', 'rejection_reason': False})

    def action_approve(self):
        for listing in self:
            if listing.agent_id.state != 'active':
                raise UserError(_('The agent of "%s" is not active yet.', listing.name))
        self._check_complete()
        for listing in self:
            listing.write({
                'state': 'published',
                'is_published': True,
                'published_date': listing.published_date or fields.Datetime.now(),
            })
        self._notify_agent(_('Your listing is now live on the website.'))

    def action_reject_wizard(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Reject Listing'),
            'res_model': 're.listing.reject.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_listing_ids': self.ids},
        }

    def _reject(self, reason):
        self.write({'state': 'rejected', 'is_published': False, 'rejection_reason': reason})
        self._notify_agent(_('Your listing was not approved: %s', reason))

    def action_close(self):
        self.write({'state': 'closed', 'is_published': False})

    def action_reset_draft(self):
        self.write({'state': 'draft', 'is_published': False})

    def action_republish(self):
        """Bump a listing to the top as if it was just published."""
        self.filtered(lambda l: l.state == 'published').write({'published_date': fields.Datetime.now()})

    def _notify_agent(self, message):
        for listing in self.filtered(lambda l: l.agent_id.partner_id):
            listing.message_post(
                body=message,
                partner_ids=listing.agent_id.partner_id.ids,
                subtype_xmlid='mail.mt_comment',
            )

    def action_view_leads(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Inquiries'),
            'res_model': 'crm.lead',
            'view_mode': 'list,form',
            'domain': [('re_listing_id', '=', self.id)],
        }

    # ------------------------------------------------------------------
    # Search (website, map and saved alerts all use this)
    # ------------------------------------------------------------------
    @api.model
    def _search_filters_from_params(self, params):
        """Normalise raw query-string params into a clean filter dict."""
        valid_types = dict(PROPERTY_TYPES)
        filters = {
            'type': params.get('type') if params.get('type') in ('sale', 'rent') else 'sale',
            'q': (params.get('q') or '').strip()[:100],
            'ptype': [t for t in _csv_values(params.get('ptype')) if t in valid_types],
            'beds': params.get('beds') if params.get('beds') in ('0', '1', '2', '3', '4', '5') else '',
            'baths': params.get('baths') if params.get('baths') in ('1', '2', '3', '4', '5') else '',
            'price_min': _to_float(params.get('price_min')) or '',
            'price_max': _to_float(params.get('price_max')) or '',
            'area_min': _to_float(params.get('area_min')) or '',
            'area_max': _to_float(params.get('area_max')) or '',
            'completion': params.get('completion') if params.get('completion') in ('ready', 'offplan') else '',
            'sale_type': params.get('sale_type') if params.get('sale_type') in ('primary', 'resale') else '',
            'furnishing': params.get('furnishing') if params.get('furnishing') in (
                'unfurnished', 'semi', 'furnished') else '',
            'amenities': [_to_int(a) for a in _csv_values(params.get('amenities')) if _to_int(a)],
            'loc': _to_int(params.get('loc')) or '',
            'agent': _to_int(params.get('agent')) or '',
            'agency': _to_int(params.get('agency')) or '',
            'sort': params.get('sort') if params.get('sort') in LISTING_SORTS else '',
        }
        return filters

    @api.model
    def _search_domain(self, filters):
        domain = [('state', '=', 'published'), ('listing_type', '=', filters['type'])]
        if filters['q']:
            q = filters['q']
            domain.append('|')
            domain.append('|')
            domain.append('|')
            domain += [('location_id.complete_name', 'ilike', q), ('name', 'ilike', q),
                       ('reference', '=ilike', q), ('project_id.name', 'ilike', q)]
        if filters['loc']:
            domain.append(('location_id', 'child_of', filters['loc']))
        if filters['ptype']:
            domain.append(('property_type', 'in', filters['ptype']))
        if filters['beds']:
            beds = int(filters['beds'])
            domain.append(('bedrooms', '>=', beds) if beds == 5 else ('bedrooms', '=', beds))
            if beds == 0:  # "Studio": residential units only, not offices / land
                domain.append(('property_type', 'not in', NON_RESIDENTIAL))
        if filters['baths']:
            baths = int(filters['baths'])
            domain.append(('bathrooms', '>=', baths) if baths == 5 else ('bathrooms', '=', baths))
        for key, field, op in (('price_min', 'price', '>='), ('price_max', 'price', '<='),
                               ('area_min', 'area', '>='), ('area_max', 'area', '<=')):
            if filters[key]:
                domain.append((field, op, filters[key]))
        for key in ('completion', 'sale_type', 'furnishing'):
            if filters[key]:
                domain.append((key, '=', filters[key]))
        for amenity_id in filters['amenities']:
            domain.append(('amenity_ids', 'in', amenity_id))
        if filters['agent']:
            domain.append(('agent_id', '=', filters['agent']))
        if filters['agency']:
            domain.append(('agency_id', '=', filters['agency']))
        return expression.normalize_domain(domain)

    @api.model
    def _search_order(self, filters):
        return LISTING_SORTS.get(filters.get('sort') or 'featured')

    @api.model
    def _get_type_counts(self, filters):
        """{property_type: count} for the category shortcuts (ignores the type filter)."""
        base = dict(filters, ptype=[])
        data = self.sudo()._read_group(self._search_domain(base), ['property_type'], ['__count'])
        return dict(data)


class ReListingImage(models.Model):
    _name = 're.listing.image'
    _description = 'Listing Photo'
    _inherit = ['image.mixin']
    _order = 'sequence, id'

    name = fields.Char()
    sequence = fields.Integer(default=10)
    listing_id = fields.Many2one('re.listing', required=True, ondelete='cascade', index=True)
    image_1920 = fields.Image(required=True, max_width=1920, max_height=1920)
