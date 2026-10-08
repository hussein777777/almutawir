# -*- coding: utf-8 -*-
import logging
from urllib.parse import quote

from werkzeug.exceptions import NotFound

from odoo import _, fields, http
from odoo.http import request
from odoo.tools import email_normalize

_logger = logging.getLogger(__name__)

UNITS_PER_PAGE = 12
UNIT_SORTS = {
    'price_asc': 'price asc',
    'price_desc': 'price desc',
    'area_desc': 'area desc',
    'newest': 'id desc',
}


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


def _sitemap_records(model):
    def generator(env, rule, qs):
        for record in env[model].search([('is_published', '=', True)]):
            loc = record.website_url
            if not qs or qs.lower() in loc.lower():
                yield {'loc': loc}
    return generator


sitemap_projects = _sitemap_records('re.project')
sitemap_units = _sitemap_records('re.unit')


class RealEstateWebsite(http.Controller):

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _is_editor(self):
        return request.env.user.has_group('website.group_website_restricted_editor')

    def _published_domain(self):
        return [] if self._is_editor() else [('is_published', '=', True)]

    def _ensure_visible(self, record):
        if not record or not record.exists():
            raise NotFound()
        if not self._is_editor() and not record.sudo().is_published:
            raise NotFound()
        return record

    def _common_values(self, **extra):
        env = request.env
        values = {
            'unit_types': env['re.unit']._fields['unit_type']._description_selection(env),
            'inquiry_types': env['crm.lead']._fields['re_inquiry_type']._description_selection(env),
            'search_projects': env['re.project'].search(self._published_domain()),
            'form_values': {},
            'form_error': False,
        }
        values.update(extra)
        return values

    # ------------------------------------------------------------------
    # Home
    # ------------------------------------------------------------------
    @http.route('/estate', type='http', auth='public', website=True, sitemap=True)
    def home(self, **kw):
        Project = request.env['re.project']
        Unit = request.env['re.unit']
        domain = self._published_domain()
        projects = Project.search(domain + [('is_featured', '=', True)], limit=6) \
            or Project.search(domain, limit=6)
        units = Unit.search(domain + [('state', '=', 'available'), ('is_featured', '=', True)], limit=6) \
            or Unit.search(domain + [('state', '=', 'available')], limit=6)
        services = request.env['re.service'].search(domain, limit=6)
        return request.render('re_developer_website.page_home', self._common_values(
            projects=projects, units=units, services=services,
        ))

    # ------------------------------------------------------------------
    # Projects
    # ------------------------------------------------------------------
    @http.route('/estate/projects', type='http', auth='public', website=True, sitemap=True)
    def projects(self, status=None, project_type=None, **kw):
        Project = request.env['re.project']
        domain = self._published_domain()
        states = dict(Project._fields['state']._description_selection(request.env))
        types = dict(Project._fields['project_type']._description_selection(request.env))
        if status in states:
            domain.append(('state', '=', status))
        if project_type in types:
            domain.append(('project_type', '=', project_type))
        return request.render('re_developer_website.page_projects', self._common_values(
            projects=Project.search(domain),
            project_states=list(states.items()),
            project_types=list(types.items()),
            current_status=status if status in states else '',
            current_type=project_type if project_type in types else '',
        ))

    @http.route('/estate/project/<model("re.project"):project>', type='http', auth='public',
                website=True, sitemap=sitemap_projects)
    def project_detail(self, project, **kw):
        self._ensure_visible(project)
        units = request.env['re.unit'].search(
            self._published_domain() + [('project_id', '=', project.id)],
            order='state, sequence, price')
        return request.render('re_developer_website.page_project_detail', self._common_values(
            project=project,
            main_object=project,
            units=units,
            form_project=project,
            form_type='visit',
        ))

    # ------------------------------------------------------------------
    # Units
    # ------------------------------------------------------------------
    @http.route(['/estate/units', '/estate/units/page/<int:page>'], type='http', auth='public',
                website=True, sitemap=True)
    def units(self, page=1, project=None, unit_type=None, bedrooms=None, max_price=None,
              status=None, sort=None, **kw):
        Unit = request.env['re.unit']
        domain = self._published_domain()
        if not self._is_editor():
            domain.append(('project_id.is_published', '=', True))

        project_id = _to_int(project)
        if project_id:
            domain.append(('project_id', '=', project_id))
        if unit_type in dict(Unit._fields['unit_type']._description_selection(request.env)):
            domain.append(('unit_type', '=', unit_type))
        else:
            unit_type = ''
        beds = _to_int(bedrooms)
        if beds:
            domain.append(('bedrooms', '>=', beds))
        price_cap = _to_float(max_price)
        if price_cap:
            domain.append(('price', '<=', price_cap))
        status = status or 'available'
        if status in ('available', 'reserved', 'sold'):
            domain.append(('state', '=', status))
        else:
            status = 'all'

        order = UNIT_SORTS.get(sort, 'is_featured desc, sequence, id desc')
        url_args = {k: v for k, v in {
            'project': project_id or '', 'unit_type': unit_type, 'bedrooms': beds or '',
            'max_price': max_price or '', 'status': status, 'sort': sort or '',
        }.items() if v}

        total = Unit.search_count(domain)
        pager = request.website.pager(url='/estate/units', total=total, page=page,
                                      step=UNITS_PER_PAGE, url_args=url_args)
        units = Unit.search(domain, order=order, limit=UNITS_PER_PAGE, offset=pager['offset'])
        return request.render('re_developer_website.page_units', self._common_values(
            units=units, pager=pager, total=total,
            filters={'project': project_id, 'unit_type': unit_type, 'bedrooms': beds,
                     'max_price': max_price or '', 'status': status, 'sort': sort or ''},
        ))

    @http.route('/estate/unit/<model("re.unit"):unit>', type='http', auth='public',
                website=True, sitemap=sitemap_units)
    def unit_detail(self, unit, **kw):
        self._ensure_visible(unit)
        self._ensure_visible(unit.project_id)
        similar = request.env['re.unit'].search(self._published_domain() + [
            ('project_id', '=', unit.project_id.id), ('id', '!=', unit.id), ('state', '=', 'available'),
        ], limit=3)
        whatsapp_link = False
        if request.website.re_whatsapp_url:
            text = _('Hello, I am interested in unit %(unit)s (%(url)s)',
                     unit=unit.display_name, url=request.httprequest.url)
            whatsapp_link = '%s?text=%s' % (request.website.re_whatsapp_url, quote(text))
        return request.render('re_developer_website.page_unit_detail', self._common_values(
            unit=unit,
            main_object=unit,
            whatsapp_link=whatsapp_link,
            similar_units=similar,
            form_project=unit.project_id,
            form_unit=unit,
            form_type='unit',
        ))

    # ------------------------------------------------------------------
    # Static-ish pages
    # ------------------------------------------------------------------
    @http.route('/estate/services', type='http', auth='public', website=True, sitemap=True)
    def services(self, **kw):
        services = request.env['re.service'].search(self._published_domain())
        return request.render('re_developer_website.page_services', self._common_values(services=services))

    @http.route('/estate/about', type='http', auth='public', website=True, sitemap=True)
    def about(self, **kw):
        team = request.env['re.team.member'].search(self._published_domain())
        return request.render('re_developer_website.page_about', self._common_values(team=team))

    # ------------------------------------------------------------------
    # Contact / Inquiries -> CRM
    # ------------------------------------------------------------------
    @http.route(['/estate/contact', '/contactus'], type='http', auth='public', website=True, sitemap=True)
    def contact(self, project_id=None, unit_id=None, inquiry_type=None, service_id=None, **kw):
        values = self._common_values(form_type=inquiry_type or 'general')
        unit = request.env['re.unit'].search(
            self._published_domain() + [('id', '=', _to_int(unit_id))], limit=1) if unit_id else False
        project = unit and unit.project_id or (request.env['re.project'].search(
            self._published_domain() + [('id', '=', _to_int(project_id))], limit=1) if project_id else False)
        service = request.env['re.service'].search(
            self._published_domain() + [('id', '=', _to_int(service_id))], limit=1) if service_id else False
        if service:
            values['form_type'] = 'service'
            values['form_values'] = {'description': _('I would like to know more about: %s', service.name)}
        if unit:
            values['form_type'] = inquiry_type or 'unit'
        values.update(form_project=project, form_unit=unit)
        return request.render('re_developer_website.page_contact', values)

    @http.route('/estate/contact/submit', type='http', auth='public', website=True,
                methods=['POST'], sitemap=False)
    def contact_submit(self, **post):
        # Honeypot: bots fill every input, humans never see this one.
        if post.get('website_url_hp'):
            return request.redirect('/estate/thank-you')

        name = (post.get('contact_name') or '').strip()
        email = (post.get('email_from') or '').strip()
        phone = (post.get('phone') or '').strip()
        error = False
        if not name:
            error = _('Please enter your name.')
        elif not email and not phone:
            error = _('Please enter a phone number or an email so we can reach you.')
        elif email and not email_normalize(email):
            error = _('The email address looks invalid.')

        env = request.env
        unit = env['re.unit'].sudo().browse(_to_int(post.get('unit_id'))).exists().filtered('is_published')
        project = unit.project_id or env['re.project'].sudo().browse(
            _to_int(post.get('project_id'))).exists().filtered('is_published')

        inquiry_types = dict(env['crm.lead']._fields['re_inquiry_type']._description_selection(env))
        inquiry_type = post.get('inquiry_type') if post.get('inquiry_type') in inquiry_types else 'general'

        if error:
            return request.render('re_developer_website.page_contact', self._common_values(
                form_error=error, form_values=post, form_type=inquiry_type,
                form_project=project, form_unit=unit,
            ))

        preferred_date = False
        if post.get('preferred_date'):
            try:
                preferred_date = fields.Date.to_date(post['preferred_date'])
            except ValueError:
                preferred_date = False

        subject = unit and unit.display_name or project and project.name or ''
        title = '%s - %s' % (inquiry_types[inquiry_type], subject or name)
        website = request.website
        medium = env.ref('utm.utm_medium_website', raise_if_not_found=False)
        lead_vals = {
            'name': title,
            'contact_name': name,
            'email_from': email,
            'phone': phone,
            'description': post.get('description') or '',
            're_inquiry_type': inquiry_type,
            're_project_id': project.id or False,
            're_unit_id': unit.id or False,
            're_preferred_date': preferred_date,
            're_budget': (post.get('budget') or '').strip(),
            'user_id': website.re_lead_user_id.id or False,
            'team_id': website.re_lead_team_id.id or False,
            'company_id': website.company_id.id,
            'medium_id': medium and medium.id or False,
        }
        try:
            env['crm.lead'].sudo().create(lead_vals)
        except Exception:
            _logger.exception('Could not create website real-estate inquiry')
            return request.render('re_developer_website.page_contact', self._common_values(
                form_error=_('Something went wrong, please try again or call us.'),
                form_values=post, form_type=inquiry_type, form_project=project, form_unit=unit,
            ))
        return request.redirect('/estate/thank-you')

    @http.route('/estate/thank-you', type='http', auth='public', website=True, sitemap=False)
    def thank_you(self, **kw):
        return request.render('re_developer_website.page_thank_you', self._common_values())
