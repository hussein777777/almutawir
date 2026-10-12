# -*- coding: utf-8 -*-
import logging
import uuid
from datetime import timedelta
from urllib.parse import parse_qsl, urlencode

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import email_normalize

_logger = logging.getLogger(__name__)

ALERT_PARAMS = ('type', 'q', 'ptype', 'beds', 'baths', 'price_min', 'price_max', 'area_min', 'area_max',
                'completion', 'sale_type', 'furnishing', 'amenities', 'loc')
MAX_LISTINGS_PER_EMAIL = 12


class ReSearchAlert(models.Model):
    """'Create alert' on the search page: email new matching listings."""
    _name = 're.search.alert'
    _description = 'Property Search Alert'
    _order = 'create_date desc'

    name = fields.Char('Search', required=True)
    email = fields.Char(required=True, index=True)
    partner_id = fields.Many2one('res.partner', ondelete='set null')
    query = fields.Char('Search Parameters', required=True, help='URL query string of the saved search.')
    frequency = fields.Selection([('daily', 'Daily'), ('weekly', 'Weekly')], default='daily', required=True)
    active = fields.Boolean(default=True)
    lang = fields.Char(default=lambda self: self.env.lang)
    website_id = fields.Many2one('website', ondelete='cascade')
    last_sent_date = fields.Datetime(default=fields.Datetime.now, required=True,
                                     help='Only listings published after this date are sent.')
    sent_count = fields.Integer('Emails Sent', readonly=True)
    token = fields.Char(required=True, copy=False, index=True, default=lambda self: uuid.uuid4().hex)

    _sql_constraints = [('token_uniq', 'unique(token)', 'Token must be unique.')]

    @api.constrains('email')
    def _check_email(self):
        for alert in self:
            if not email_normalize(alert.email):
                raise ValidationError(_('Invalid email address.'))

    @api.model
    def _clean_query(self, params):
        """Keep only the search parameters (no page / sort / view)."""
        return urlencode([(k, v) for k, v in params.items() if k in ALERT_PARAMS and v not in ('', None)])

    def _get_filters(self):
        self.ensure_one()
        return self.env['re.listing']._search_filters_from_params(dict(parse_qsl(self.query)))

    def _get_new_listings(self):
        self.ensure_one()
        Listing = self.env['re.listing'].sudo()
        domain = Listing._search_domain(self._get_filters()) + [('published_date', '>', self.last_sent_date)]
        return Listing.search(domain, order='published_date desc', limit=MAX_LISTINGS_PER_EMAIL)

    def _get_search_url(self):
        self.ensure_one()
        filters = self._get_filters()
        base = (self.website_id or self.env['website'].get_current_website()).get_base_url()
        path = '/properties/%s' % ('rent' if filters['type'] == 'rent' else 'buy')
        return '%s%s?%s' % (base, path, self.query)

    def _get_unsubscribe_url(self):
        self.ensure_one()
        base = (self.website_id or self.env['website'].get_current_website()).get_base_url()
        return '%s/property/alert/unsubscribe/%s' % (base, self.token)

    def _send_alert(self, listings):
        self.ensure_one()
        alert = self.with_context(lang=self.lang or 'en_US')
        base_url = (self.website_id or self.env['website'].get_current_website()).get_base_url()
        body = alert.env['ir.qweb']._render('re_property_portal.mail_search_alert', {
            'alert': alert,
            'listings': listings.with_context(lang=self.lang or 'en_US'),
            'base_url': base_url,
        })
        company = (self.website_id.company_id or self.env.company)
        self.env['mail.mail'].sudo().create({
            'subject': _('%(count)s new properties match "%(search)s"', count=len(listings), search=self.name),
            'email_from': company.email_formatted or self.env.user.email_formatted,
            'email_to': self.email,
            'body_html': body,
            'auto_delete': True,
        })

    @api.model
    def _cron_send_alerts(self):
        now = fields.Datetime.now()
        alerts = self.search([])
        for alert in alerts:
            delay = timedelta(days=7 if alert.frequency == 'weekly' else 1)
            if alert.last_sent_date > now - delay + timedelta(minutes=30):
                continue
            try:
                listings = alert._get_new_listings()
                if listings:
                    alert._send_alert(listings)
                    alert.sent_count += 1
                alert.last_sent_date = now
            except Exception:
                _logger.exception('Search alert %s failed', alert.id)
        return True

    def action_send_now(self):
        """Back-office test button: send what is new since the last email."""
        for alert in self:
            listings = alert._get_new_listings()
            if listings:
                alert._send_alert(listings)
                alert.write({'last_sent_date': fields.Datetime.now(), 'sent_count': alert.sent_count + 1})
