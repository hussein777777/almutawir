# -*- coding: utf-8 -*-
import json
import logging
from urllib.parse import parse_qsl, urlencode

from werkzeug.exceptions import NotFound

from odoo import _, http
from odoo.exceptions import AccessError, MissingError
from odoo.http import request
from odoo.tools import email_normalize, html_escape

from odoo.addons.re_developer_website.controllers.main import RealEstateWebsite

from .helpers import filters_to_query, render_values, search_url, short_price

_logger = logging.getLogger(__name__)

LISTINGS_PER_PAGE = 20
MAP_MAX_MARKERS = 500


def _to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


class RealEstateWebsiteMarketplace(RealEstateWebsite):
    """Add the latest marketplace listings to the developer homepage."""

    @http.route()
    def home(self, **kw):
        response = super().home(**kw)
        if getattr(response, 'qcontext', None) is not None:
            Listing = request.env['re.listing']
            latest = Listing.search([('state', '=', 'published')], limit=4,
                                    order='is_premium desc, published_date desc')
            response.qcontext.update(render_values(
                rp_latest=latest,
                rp_search=True,
                purpose='buy',
                view='list',
                filters=Listing._search_filters_from_params({'type': 'sale'}),
                locations=request.env['re.location'].sudo().search([]),
                amenities=request.env['re.amenity'].sudo().search([]),
                **response.qcontext))
        return response


class PropertyMarketplace(http.Controller):

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _is_editor(self):
        return request.env.user.has_group('re_developer_website.group_re_manager')

    def _visible_listing(self, listing):
        """Published listings for everyone; drafts for their agent and managers."""
        try:
            listing = listing.exists()
            if not listing:
                raise NotFound()
            sudo_listing = listing.sudo()
            if sudo_listing.state == 'published' or self._is_editor():
                return sudo_listing
            if sudo_listing.agent_id.user_id == request.env.user:
                return sudo_listing
        except (AccessError, MissingError):
            pass
        raise NotFound()

    def _alert_name(self, filters):
        Listing = request.env['re.listing']
        types = dict(Listing._fields['property_type']._description_selection(request.env))
        what = ', '.join(types[t] for t in filters['ptype']) if filters['ptype'] else _('Properties')
        purpose = _('for rent') if filters['type'] == 'rent' else _('for sale')
        where = ''
        if filters['loc']:
            location = request.env['re.location'].sudo().browse(filters['loc']).exists()
            where = location.name or ''
        elif filters['q']:
            where = filters['q']
        return ('%s %s %s %s' % (what, purpose, _('in'), where) if where else '%s %s' % (what, purpose)).strip()

    # ------------------------------------------------------------------
    # Search / listing pages
    # ------------------------------------------------------------------
    @http.route('/properties', type='http', auth='public', website=True, sitemap=False)
    def properties_root(self, **kw):
        return request.redirect('/properties/buy')

    @http.route(['/properties/<string:purpose>', '/properties/<string:purpose>/page/<int:page>'],
                type='http', auth='public', website=True, sitemap=True)
    def properties(self, purpose='buy', page=1, view=None, alert=None, **kw):
        if purpose not in ('buy', 'rent'):
            raise NotFound()
        Listing = request.env['re.listing']
        params = dict(kw, type='rent' if purpose == 'rent' else 'sale')
        for key in ('amenities', 'ptype'):  # checkboxes send the key several times
            values = request.httprequest.args.getlist(key)
            if len(values) > 1:
                params[key] = ','.join(values)
        filters = Listing._search_filters_from_params(params)
        domain = Listing._search_domain(filters)
        total = Listing.search_count(domain)
        values = {
            'purpose': purpose,
            'filters': filters,
            'total': total,
            'view': 'map' if view == 'map' else 'list',
            'alert_created': alert == '1',
            'type_counts': Listing._get_type_counts(filters),
            'amenities': request.env['re.amenity'].sudo().search([]),
            'locations': request.env['re.location'].sudo().search([]),
            'alert_query': request.env['re.search.alert']._clean_query(
                dict(filters_to_query(filters), type=filters['type'])),
            'alert_name': self._alert_name(filters),
        }
        if purpose == 'buy' and int(page or 1) == 1 and not (filters['agent'] or filters['agency']):
            values['projects'] = self._matching_projects(filters)
        if values['view'] == 'map':
            listings = Listing.search(domain + [('latitude', '!=', 0), ('longitude', '!=', 0)],
                                      order=Listing._search_order(filters), limit=MAP_MAX_MARKERS)
            values['listings'] = listings
            values['markers_json'] = json.dumps(self._map_markers(listings))
        else:
            pager = request.website.pager(
                url='/properties/%s' % purpose, total=total, page=page, step=LISTINGS_PER_PAGE,
                url_args=filters_to_query(filters))
            values['pager'] = pager
            values['listings'] = Listing.search(domain, order=Listing._search_order(filters),
                                                limit=LISTINGS_PER_PAGE, offset=pager['offset'])
        return request.render('re_property_portal.page_search', render_values(**values))

    def _matching_projects(self, filters, limit=6):
        """New projects (re.project) matching the search, shown above the listings."""
        domain = [] if self._is_editor() else [('is_published', '=', True)]
        q = filters['q']
        if q:
            domain += ['|', '|', '|', ('name', 'ilike', q), ('city', 'ilike', q), ('location', 'ilike', q),
                       ('location_id.complete_name', 'ilike', q)]
        if filters['loc']:
            domain.append(('location_id', 'child_of', filters['loc']))
        if filters['completion'] == 'offplan':
            domain.append(('state', 'in', ('planning', 'construction')))
        elif filters['completion'] == 'ready':
            domain.append(('state', '=', 'delivered'))
        if filters['ptype']:
            domain.append(('unit_ids.unit_type', 'in', filters['ptype']))
        if filters['price_max']:
            domain.append(('unit_ids.price', '<=', filters['price_max']))
        return request.env['re.project'].search(domain, limit=limit)

    def _map_markers(self, listings):
        markers = []
        for listing in listings:
            cover = listing.cover_image_id
            markers.append({
                'id': listing.id,
                'lat': listing.latitude,
                'lng': listing.longitude,
                'price': short_price(listing.price),
                'title': listing.name,
                'url': listing.website_url,
                'img': cover and '/web/image/re.listing.image/%s/image_256' % cover.id or '',
                'beds': listing.bedrooms,
                'baths': listing.bathrooms,
                'area': '%g' % listing.area,
                'location': listing._get_location_trail(),
                'premium': listing.is_premium,
            })
        return markers

    @http.route('/property/<model("re.listing"):listing>', type='http', auth='public', website=True,
                sitemap=False)
    def listing_detail(self, listing, sent=None, **kw):
        listing = self._visible_listing(listing)
        is_owner = listing.agent_id.user_id == request.env.user
        if listing.state == 'published' and not is_owner and not self._is_editor():
            request.env.cr.execute('UPDATE re_listing SET view_count = COALESCE(view_count, 0) + 1 WHERE id = %s', [listing.id])
        similar = request.env['re.listing'].search([
            ('state', '=', 'published'), ('id', '!=', listing.id),
            ('listing_type', '=', listing.listing_type),
            ('location_id', 'child_of', listing.location_id.parent_id.id or listing.location_id.id),
        ], limit=4)
        markers = []
        if listing.latitude and listing.longitude:
            markers = self._map_markers(listing)
        return request.render('re_property_portal.page_listing', render_values(
            listing=listing,
            main_object=listing,
            similar=similar,
            inquiry_sent=sent == '1',
            markers_json=json.dumps(markers),
            is_preview=listing.state != 'published',
            inquiry_message=_('Hello, I am interested in %(title)s (%(ref)s). Please contact me.',
                              title=listing.name, ref=listing.reference),
        ))

    @http.route('/property/inquiry', type='http', auth='public', website=True, methods=['POST'], sitemap=False)
    def listing_inquiry(self, **post):
        listing = request.env['re.listing'].sudo().browse(_to_int(post.get('listing_id'))).exists()
        if not listing or listing.state != 'published':
            raise NotFound()
        if post.get('website_url_hp'):
            return request.redirect('%s?sent=1#contact' % listing.website_url)
        name = (post.get('contact_name') or '').strip()
        email = (post.get('email_from') or '').strip()
        phone = (post.get('phone') or '').strip()
        if not name or not (email or phone) or (email and not email_normalize(email)):
            return request.redirect('%s?error=1#contact' % listing.website_url)
        website = request.website
        medium = request.env.ref('utm.utm_medium_website', raise_if_not_found=False)
        lead = request.env['crm.lead'].sudo().create({
            'name': _('Property inquiry - %(ref)s %(title)s', ref=listing.reference, title=listing.name),
            'contact_name': name,
            'email_from': email,
            'phone': phone,
            'description': post.get('message') or '',
            're_inquiry_type': 'unit',
            're_listing_id': listing.id,
            're_agent_id': listing.agent_id.id,
            'user_id': website.re_lead_user_id.id or False,
            'team_id': website.re_lead_team_id.id or False,
            'company_id': website.company_id.id,
            'medium_id': medium and medium.id or False,
        })
        self._notify_agent_of_lead(listing, lead)
        return request.redirect('%s?sent=1#contact' % listing.website_url)

    def _notify_agent_of_lead(self, listing, lead):
        agent = listing.agent_id
        if not agent.email:
            return
        try:
            body = request.env['ir.qweb']._render('re_property_portal.mail_new_inquiry', {
                'listing': listing, 'lead': lead, 'agent': agent,
                'base_url': request.website.get_base_url(),
            })
            request.env['mail.mail'].sudo().create({
                'subject': _('New inquiry: %s', listing.name),
                'email_from': request.website.company_id.email_formatted,
                'email_to': agent.email,
                'reply_to': lead.email_from or False,
                'body_html': body,
                'auto_delete': True,
            })
        except Exception:
            _logger.exception('Could not notify agent %s of lead %s', agent.id, lead.id)

    # ------------------------------------------------------------------
    # Search alerts
    # ------------------------------------------------------------------
    @http.route('/property/alert/create', type='http', auth='public', website=True, methods=['POST'],
                sitemap=False)
    def alert_create(self, **post):
        Alert = request.env['re.search.alert'].sudo()
        filters = request.env['re.listing']._search_filters_from_params(dict(parse_qsl(post.get('query') or '')))
        back = search_url(filters)
        email = email_normalize(post.get('email') or '')
        if post.get('website_url_hp') or not email:
            return request.redirect(back)
        clean = Alert._clean_query(dict(filters_to_query(filters), type=filters['type']))
        existing = Alert.search([('email', '=', email), ('query', '=', clean)], limit=1)
        if existing:
            existing.active = True
        else:
            Alert.create({
                'name': (post.get('name') or self._alert_name(filters))[:200],
                'email': email,
                'query': clean,
                'frequency': 'weekly' if post.get('frequency') == 'weekly' else 'daily',
                'lang': request.env.lang,
                'website_id': request.website.id,
                'partner_id': not request.env.user._is_public() and request.env.user.partner_id.id or False,
            })
        return request.redirect('%s%salert=1' % (back, '&' if '?' in back else '?'))

    @http.route('/property/alert/unsubscribe/<string:token>', type='http', auth='public', website=True,
                sitemap=False)
    def alert_unsubscribe(self, token, **kw):
        alert = request.env['re.search.alert'].sudo().search([('token', '=', token)], limit=1)
        if alert:
            alert.active = False
        return request.render('re_property_portal.page_message', render_values(
            message_title=_('You are unsubscribed'),
            message_text=_('You will not receive emails for this search anymore.'),
            message_icon='fa-bell-slash',
        ))

    # ------------------------------------------------------------------
    # Agents & agencies
    # ------------------------------------------------------------------
    @http.route(['/agents', '/agents/page/<int:page>'], type='http', auth='public', website=True, sitemap=True)
    def agents(self, page=1, tab='agents', q=None, **kw):
        tab = 'agencies' if tab == 'agencies' else 'agents'
        q = (q or '').strip()[:80]
        if tab == 'agencies':
            Model = request.env['re.agency']
            domain = [('is_published', '=', True)]
        else:
            Model = request.env['re.agent']
            domain = [('state', '=', 'active'), ('is_published', '=', True)]
        if q:
            domain.append(('name', 'ilike', q))
        total = Model.search_count(domain)
        pager = request.website.pager(url='/agents', total=total, page=page, step=24,
                                      url_args={k: v for k, v in {'tab': tab, 'q': q}.items() if v})
        records = Model.search(domain, limit=24, offset=pager['offset'])
        tab_urls = {t: '/agents?%s' % urlencode({k: v for k, v in {'tab': t, 'q': q}.items() if v})
                    for t in ('agents', 'agencies')}
        return request.render('re_property_portal.page_agents', render_values(
            tab=tab, q=q, records=records, pager=pager, total=total, tab_urls=tab_urls))

    @http.route('/agent/<model("re.agent"):agent>', type='http', auth='public', website=True, sitemap=False)
    def agent_profile(self, agent, purpose='sale', **kw):
        agent = agent.sudo()
        if agent.state != 'active' or (not agent.is_published and not self._is_editor()):
            raise NotFound()
        listings = request.env['re.listing'].search([('agent_id', '=', agent.id), ('state', '=', 'published')],
                                                     limit=48)
        return request.render('re_property_portal.page_agent', render_values(
            agent=agent, main_object=agent, listings=listings))

    @http.route('/agency/<model("re.agency"):agency>', type='http', auth='public', website=True, sitemap=False)
    def agency_profile(self, agency, **kw):
        agency = agency.sudo()
        if not agency.is_published and not self._is_editor():
            raise NotFound()
        agents = agency.agent_ids.filtered(lambda a: a.state == 'active' and a.is_published)
        listings = request.env['re.listing'].search([('agency_id', '=', agency.id), ('state', '=', 'published')],
                                                     limit=48)
        projects = request.env['re.project'].search([('agency_id', '=', agency.id), ('is_published', '=', True)])
        return request.render('re_property_portal.page_agency', render_values(
            agency=agency, main_object=agency, agents=agents, listings=listings, projects=projects))

    # ------------------------------------------------------------------
    # Become an agent / owner ("List your property")
    # ------------------------------------------------------------------
    @http.route('/list-your-property', type='http', auth='public', website=True, sitemap=True)
    def become_agent(self, **kw):
        if request.env['re.agent']._get_for_user():
            return request.redirect('/my/listings')
        return request.render('re_property_portal.page_become_agent', render_values(form_values={}, form_error=False))

    @http.route('/list-your-property/submit', type='http', auth='public', website=True, methods=['POST'],
                sitemap=False)
    def become_agent_submit(self, **post):
        if post.get('website_url_hp'):
            return request.redirect('/list-your-property/thanks')
        name = (post.get('name') or '').strip()
        email = email_normalize(post.get('email') or '')
        phone = (post.get('phone') or '').strip()
        error = False
        if not name or not phone:
            error = _('Please fill in your name and phone number.')
        elif not email:
            error = _('Please enter a valid email: your portal login will be sent to it.')
        if error:
            return request.render('re_property_portal.page_become_agent', render_values(
                form_values=post, form_error=error))
        Agent = request.env['re.agent'].sudo().with_context(active_test=False)
        existing = Agent.search([('email', '=ilike', email)], limit=1)
        if existing:
            if existing.state == 'active':
                return request.redirect('/web/login?login=%s&redirect=/my/listings' % html_escape(email))
            return request.redirect('/list-your-property/thanks')
        kind = 'owner' if post.get('agent_kind') == 'owner' else 'agent'
        agent = Agent.create({
            'name': name,
            'email': email,
            'phone': phone,
            'whatsapp': (post.get('whatsapp') or '').strip() or phone,
            'agent_kind': kind,
            'requested_agency': (post.get('agency') or '').strip() if kind == 'agent' else False,
            'state': 'pending',
            'is_published': False,
        })
        if post.get('message'):
            agent.message_post(body=html_escape(post['message']))
        agent.activity_schedule(
            'mail.mail_activity_data_todo',
            summary=_('Review agent request'),
            user_id=(request.website.re_lead_user_id or request.env.ref('base.user_admin')).id,
        )
        return request.redirect('/list-your-property/thanks')

    @http.route('/list-your-property/thanks', type='http', auth='public', website=True, sitemap=False)
    def become_agent_thanks(self, **kw):
        return request.render('re_property_portal.page_message', render_values(
            message_title=_('Request received'),
            message_text=_('Our team will review your request and email you a link to set your password. '
                           'Then you can add your properties from "My Account".'),
            message_icon='fa-check',
        ))
