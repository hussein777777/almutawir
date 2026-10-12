# -*- coding: utf-8 -*-
import base64
import logging

from werkzeug.exceptions import NotFound

from odoo import _, fields, http
from odoo.exceptions import UserError, ValidationError
from odoo.http import request
from odoo.models import BaseModel
from odoo.tools import html2plaintext, plaintext2html

from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager

from ..models.re_listing import PORTAL_FIELDS
from .helpers import render_values

_logger = logging.getLogger(__name__)

MAX_PHOTOS = 20
MAX_PHOTO_SIZE = 10 * 1024 * 1024
# Changing only these keeps a published listing online; anything else sends it back to review
LIVE_EDITABLE_FIELDS = {'price', 'down_payment', 'installment_years', 'rent_period'}
SALE_ONLY_FIELDS = ('sale_type', 'down_payment', 'installment_years')
RENT_ONLY_FIELDS = ('rent_period',)
STATE_TABS = {
    'all': None,
    'published': ['published'],
    'pending': ['pending'],
    'draft': ['draft', 'rejected'],
    'closed': ['closed'],
}


def _to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _to_float(value):
    if value in (None, False):
        return 0.0
    try:
        return float(str(value).replace(',', '').strip() or 0)
    except (TypeError, ValueError):
        raise ValidationError(_('"%s" is not a valid number.', value))


class AgentPortal(CustomerPortal):

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _get_agent(self):
        agent = request.env['re.agent']._get_for_user()
        if not agent:
            raise NotFound()
        return agent

    def _get_own_listing(self, agent, listing_id):
        listing = request.env['re.listing'].sudo().browse(_to_int(listing_id)).exists()
        if not listing or listing.agent_id != agent:
            raise NotFound()
        return listing

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        agent = request.env['re.agent']._get_for_user()
        if 're_listing_count' in counters:
            values['re_listing_count'] = len(agent.listing_ids) if agent else 0
        if 're_lead_count' in counters:
            values['re_lead_count'] = agent.lead_count if agent else 0
        return values

    @staticmethod
    def _form_dict(listing=None, post=None):
        """String values for every form input: the submitted values after an
        error, otherwise the saved listing (or the defaults for a new one)."""
        if post is not None:
            data = dict(post)
            data['amenity_ids'] = [_to_int(a) for a in request.httprequest.form.getlist('amenity_ids')]
            return data
        if not listing:
            return {'amenity_ids': []}
        data = {}
        for field in PORTAL_FIELDS:
            value = listing[field]
            if field == 'amenity_ids':
                data[field] = value.ids
            elif isinstance(value, BaseModel):
                data[field] = str(value.id) if value else ''
            elif field == 'description':
                data[field] = html2plaintext(value or '')
            elif isinstance(value, float):
                data[field] = ('%f' % value).rstrip('0').rstrip('.') if value else ''
            elif field in ('bedrooms',):
                data[field] = str(value)
            elif value in (False, None) or (isinstance(value, int) and not value):
                data[field] = ''
            else:
                data[field] = str(value)
        return data

    def _listing_form_values(self, agent, listing=None, form_values=None, error=None, post=None):
        env = request.env
        Listing = env['re.listing']
        selection = lambda field: Listing._fields[field]._description_selection(env)  # noqa: E731
        fv = form_values if form_values is not None else self._form_dict(listing, post)
        return render_values(
            agent=agent,
            listing=listing,
            fv=fv,
            form_error=error,
            page_name='re_listing_form',
            locations=env['re.location'].sudo().search([]),
            projects=env['re.project'].sudo().search([('is_published', '=', True)]),
            amenities=env['re.amenity'].sudo().search([]),
            listing_types=selection('listing_type'),
            completions=selection('completion'),
            sale_types=selection('sale_type'),
            furnishings=selection('furnishing'),
            finishings=selection('finishing'),
            rent_periods=selection('rent_period'),
            max_photos=MAX_PHOTOS,
        )

    def _parse_listing_form(self, post):
        """Whitelisted, validated values from the portal form."""
        Listing = request.env['re.listing']
        env = request.env
        vals = {}
        name = (post.get('name') or '').strip()
        if not name:
            raise ValidationError(_('Please enter a title.'))
        vals['name'] = name[:150]
        for field in ('listing_type', 'property_type', 'completion', 'sale_type', 'furnishing', 'finishing',
                      'rent_period'):
            allowed = dict(Listing._fields[field]._description_selection(env))
            value = post.get(field)
            if value not in allowed:
                if Listing._fields[field].required:
                    raise ValidationError(_('Please choose a value for "%s".', Listing._fields[field].string))
                value = False
            vals[field] = value
        vals['price'] = _to_float(post.get('price'))
        if vals['price'] <= 0:
            raise ValidationError(_('Please enter the price.'))
        vals['down_payment'] = _to_float(post.get('down_payment'))
        vals['installment_years'] = _to_int(post.get('installment_years'))
        for field in ('bedrooms', 'bathrooms'):
            vals[field] = max(_to_int(post.get(field)), 0)
        for field in ('area', 'garden_area', 'latitude', 'longitude'):
            vals[field] = _to_float(post.get(field))
        if vals['area'] <= 0 and vals['property_type'] != 'land':
            raise ValidationError(_('Please enter the area.'))
        vals['floor'] = (post.get('floor') or '').strip()[:30]
        vals['address'] = (post.get('address') or '').strip()[:200]
        vals['delivery_date'] = False
        if post.get('delivery_date') and vals['completion'] == 'offplan':
            try:
                vals['delivery_date'] = fields.Date.to_date(post['delivery_date'])
            except ValueError:
                vals['delivery_date'] = False
        location = env['re.location'].sudo().browse(_to_int(post.get('location_id'))).exists()
        if not location:
            raise ValidationError(_('Please choose the location.'))
        vals['location_id'] = location.id
        project = env['re.project'].sudo().browse(_to_int(post.get('project_id'))).exists()
        vals['project_id'] = project.id if project and project.is_published else False
        amenity_ids = [_to_int(a) for a in request.httprequest.form.getlist('amenity_ids')]
        vals['amenity_ids'] = [(6, 0, env['re.amenity'].sudo().browse(amenity_ids).exists().ids)]
        vals['description'] = plaintext2html((post.get('description') or '').strip()[:5000])
        assert set(vals) <= set(PORTAL_FIELDS)
        return vals

    @staticmethod
    def _field_changed(listing, field, value):
        current = listing[field]
        if field == 'amenity_ids':
            return set(current.ids) != set(value[0][2])
        if isinstance(current, BaseModel):
            return current.id != (value or False)
        if field == 'description':
            return html2plaintext(current or '').strip() != html2plaintext(value or '').strip()
        if isinstance(current, float) or isinstance(value, float):
            return abs((current or 0.0) - (value or 0.0)) > 1e-6
        return (current or False) != (value or False)

    def _read_uploaded_photos(self):
        photos = []
        for upload in request.httprequest.files.getlist('photos'):
            if not upload or not upload.filename:
                continue
            data = upload.read()
            if len(data) > MAX_PHOTO_SIZE:
                raise ValidationError(_('"%s" is larger than 10 MB.', upload.filename))
            if not (upload.mimetype or '').startswith('image/'):
                raise ValidationError(_('"%s" is not an image.', upload.filename))
            photos.append((upload.filename, base64.b64encode(data)))
        return photos

    # ------------------------------------------------------------------
    # My listings
    # ------------------------------------------------------------------
    @http.route(['/my/listings', '/my/listings/page/<int:page>'], type='http', auth='user', website=True)
    def my_listings(self, page=1, tab='all', **kw):
        agent = self._get_agent()
        tab = tab if tab in STATE_TABS else 'all'
        domain = [('agent_id', '=', agent.id)]
        if STATE_TABS[tab]:
            domain.append(('state', 'in', STATE_TABS[tab]))
        Listing = request.env['re.listing'].sudo()
        total = Listing.search_count(domain)
        pager = portal_pager(url='/my/listings', total=total, page=page, step=20, url_args={'tab': tab})
        listings = Listing.search(domain, order='write_date desc', limit=20, offset=pager['offset'])
        counts = dict(Listing._read_group([('agent_id', '=', agent.id)], ['state'], ['__count']))
        values = self._prepare_portal_layout_values()
        values.update(render_values(
            agent=agent, listings=listings, pager=pager, tab=tab, counts=counts,
            page_name='re_listings', default_url='/my/listings',
            saved=kw.get('saved'),
            confirm_close=_('Mark this property as sold / rented? It will be removed from the website.'),
            confirm_delete=_('Delete this draft permanently?'),
        ))
        return request.render('re_property_portal.portal_my_listings', values)

    @http.route('/my/listings/new', type='http', auth='user', website=True)
    def my_listing_new(self, **kw):
        agent = self._get_agent()
        values = self._prepare_portal_layout_values()
        values.update(self._listing_form_values(agent, form_values={
            'listing_type': kw.get('type') if kw.get('type') in ('sale', 'rent') else 'sale',
            'completion': 'ready', 'furnishing': 'unfurnished', 'finishing': 'fully',
            'sale_type': 'resale', 'rent_period': 'month', 'property_type': 'apartment',
            'amenity_ids': [],
        }))
        return request.render('re_property_portal.portal_listing_form', values)

    @http.route('/my/listings/<int:listing_id>/edit', type='http', auth='user', website=True)
    def my_listing_edit(self, listing_id, **kw):
        agent = self._get_agent()
        listing = self._get_own_listing(agent, listing_id)
        values = self._prepare_portal_layout_values()
        values.update(self._listing_form_values(agent, listing=listing))
        return request.render('re_property_portal.portal_listing_form', values)

    @http.route('/my/listings/save', type='http', auth='user', website=True, methods=['POST'])
    def my_listing_save(self, **post):
        agent = self._get_agent()
        listing = self._get_own_listing(agent, post['listing_id']) if post.get('listing_id') else None
        is_new = listing is None
        try:
            vals = self._parse_listing_form(post)
            photos = self._read_uploaded_photos()
            remove_ids = [_to_int(i) for i in request.httprequest.form.getlist('remove_image_ids')]
            Listing = request.env['re.listing'].sudo()
            with request.env.cr.savepoint():
                if listing:
                    if listing.state == 'closed':
                        raise UserError(_('Sold / rented listings cannot be edited.'))
                    irrelevant = RENT_ONLY_FIELDS if vals['listing_type'] == 'sale' else SALE_ONLY_FIELDS
                    for field in irrelevant:  # hidden inputs: keep the stored value
                        vals.pop(field, None)
                    changed = {f for f, v in vals.items() if self._field_changed(listing, f, v)}
                    content_changed = bool(changed - LIVE_EDITABLE_FIELDS) or photos or remove_ids
                    listing.write(vals)
                    if listing.state == 'published' and content_changed:
                        listing.write({'state': 'pending', 'is_published': False})
                        listing.message_post(body=_('Edited by the agent from the portal: sent back to review.'))
                else:
                    listing = Listing.create(dict(vals, agent_id=agent.id, state='draft'))
                to_remove = listing.image_ids.filtered(lambda img: img.id in remove_ids)
                to_remove.unlink()
                if len(listing.image_ids) + len(photos) > MAX_PHOTOS:
                    raise ValidationError(_('A listing can have at most %s photos.', MAX_PHOTOS))
                sequence = max(listing.image_ids.mapped('sequence') or [0])
                for index, (filename, data) in enumerate(photos, start=1):
                    request.env['re.listing.image'].sudo().create({
                        'listing_id': listing.id, 'name': filename[:100],
                        'image_1920': data, 'sequence': sequence + index,
                    })
                if post.get('submit_action') == 'submit' and listing.state in ('draft', 'rejected'):
                    listing.action_submit()
        except (UserError, ValidationError) as error:
            request.env.invalidate_all()
            listing = None if is_new else listing
            values = self._prepare_portal_layout_values()
            values.update(self._listing_form_values(agent, listing=listing, post=post, error=error.args[0]))
            return request.render('re_property_portal.portal_listing_form', values)
        except Exception as error:  # e.g. corrupted image file
            _logger.warning('Portal listing save failed: %s', error)
            request.env.invalidate_all()
            listing = None if is_new else listing
            values = self._prepare_portal_layout_values()
            values.update(self._listing_form_values(
                agent, listing=listing, post=post,
                error=_('Could not save the listing. Please check the photos (JPG / PNG) and try again.')))
            return request.render('re_property_portal.portal_listing_form', values)
        return request.redirect('/my/listings?saved=1')

    @http.route('/my/listings/<int:listing_id>/<string:action>', type='http', auth='user', website=True,
                methods=['POST'])
    def my_listing_action(self, listing_id, action, **post):
        agent = self._get_agent()
        listing = self._get_own_listing(agent, listing_id)
        try:
            if action == 'submit' and listing.state in ('draft', 'rejected'):
                listing.action_submit()
            elif action == 'close' and listing.state == 'published':
                listing.action_close()
            elif action == 'delete' and listing.state in ('draft', 'rejected'):
                listing.unlink()
            elif action == 'withdraw' and listing.state == 'pending':
                listing.action_reset_draft()
            else:
                raise NotFound()
        except UserError as error:
            return request.redirect('/my/listings?error=%s' % error.args[0])
        return request.redirect('/my/listings?saved=1')

    # ------------------------------------------------------------------
    # Inquiries received by the agent
    # ------------------------------------------------------------------
    @http.route(['/my/property-leads', '/my/property-leads/page/<int:page>'], type='http', auth='user',
                website=True)
    def my_leads(self, page=1, **kw):
        agent = self._get_agent()
        Lead = request.env['crm.lead'].sudo()
        domain = [('re_agent_id', '=', agent.id)]
        total = Lead.search_count(domain)
        pager = portal_pager(url='/my/property-leads', total=total, page=page, step=30)
        leads = Lead.search(domain, order='create_date desc', limit=30, offset=pager['offset'])
        values = self._prepare_portal_layout_values()
        values.update(render_values(agent=agent, leads=leads, pager=pager, page_name='re_leads',
                                    default_url='/my/property-leads', html2plaintext=html2plaintext))
        return request.render('re_property_portal.portal_my_leads', values)