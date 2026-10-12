# -*- coding: utf-8 -*-
"""Rendering helpers shared by the website and portal controllers."""
from datetime import datetime
from urllib.parse import quote, urlencode

from babel.dates import format_timedelta

from odoo import fields
from odoo.http import request
from odoo.tools import babel_locale_parse, is_html_empty

from odoo.addons.re_developer_website.models.tools import whatsapp_url

QUERY_KEYS = ('q', 'loc', 'ptype', 'beds', 'baths', 'price_min', 'price_max', 'area_min', 'area_max',
              'completion', 'sale_type', 'furnishing', 'amenities', 'agent', 'agency', 'sort')


def _plain(value):
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def filters_to_query(filters, **overrides):
    """Filter dict -> query-string dict (empty values dropped)."""
    data = dict(filters, **overrides)
    query = {}
    for key in QUERY_KEYS:
        value = data.get(key)
        if isinstance(value, (list, tuple)):
            value = ','.join(str(v) for v in value)
        value = _plain(value)
        if value not in ('', None, False, 0):
            query[key] = value
    return query


def search_url(filters, purpose=None, view=None, **overrides):
    purpose = purpose or ('rent' if filters.get('type') == 'rent' else 'buy')
    query = filters_to_query(filters, **overrides)
    if view == 'map':
        query['view'] = 'map'
    path = '/properties/%s' % purpose
    return '%s?%s' % (path, urlencode(query)) if query else path


def short_price(amount):
    """7450000 -> '7.45M', 45000 -> '45K' (map markers)."""
    amount = amount or 0
    for divider, suffix in ((1_000_000_000, 'B'), (1_000_000, 'M'), (1_000, 'K')):
        if amount >= divider:
            value = amount / divider
            text = ('%.2f' % value).rstrip('0').rstrip('.')
            return '%s%s' % (text, suffix)
    return '%d' % amount


def money(amount, currency):
    """'EGP 7,450,000' - whole amounts without decimals, honouring the symbol position."""
    amount = amount or 0.0
    text = '{:,.0f}'.format(amount) if float(amount).is_integer() or amount >= 1000 else '{:,.2f}'.format(amount)
    symbol = currency.symbol or currency.name or ''
    return '%s %s' % (text, symbol) if currency.position == 'after' else '%s %s' % (symbol, text)


def listed_ago(date):
    if not date:
        return ''
    delta = fields.Datetime.to_datetime(date) - datetime.now()
    lang = request.env.lang or 'en_US'
    try:
        locale = babel_locale_parse(lang)
    except Exception:
        locale = babel_locale_parse('en_US')
    return format_timedelta(delta, add_direction=True, locale=locale, threshold=1)


def listing_whatsapp(listing):
    agent = listing.sudo().agent_id
    base = whatsapp_url(agent.whatsapp or agent.phone)
    if not base:
        return False
    text = '%s %s (%s)' % (listing.reference, listing.name, request.httprequest.host_url.rstrip('/') + listing.website_url)
    return '%s?text=%s' % (base, quote(text))


def render_values(**values):
    """Common values for every marketplace page."""
    Listing = request.env['re.listing']
    env = request.env
    values.setdefault('property_types', Listing._fields['property_type']._description_selection(env))
    values.update(
        short_price=short_price,
        money=money,
        listed_ago=listed_ago,
        listing_whatsapp=listing_whatsapp,
        search_url=search_url,
        filters_to_query=filters_to_query,
        is_html_empty=is_html_empty,
    )
    return values
