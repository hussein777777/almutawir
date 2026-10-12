# -*- coding: utf-8 -*-
{
    'name': 'Real Estate Property Portal',
    'version': '18.0.1.1.0',
    'summary': 'Property Finder style marketplace: buy / rent listings, map search, '
               'agents & agencies directory, agent portal with approval, saved search alerts.',
    'category': 'Website/Website',
    'author': 'Hussein',
    'license': 'LGPL-3',
    'depends': ['re_developer_website', 'portal', 'website', 'crm', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'security/record_rules.xml',
        'data/ir_sequence.xml',
        'data/ir_cron.xml',
        'data/website_menu.xml',
        'data/re_location_data.xml',
        'wizard/re_listing_reject_views.xml',
        'views/re_location_views.xml',
        'views/re_agency_views.xml',
        'views/re_agent_views.xml',
        'views/re_listing_views.xml',
        'views/re_search_alert_views.xml',
        'views/re_project_views.xml',
        'views/crm_lead_views.xml',
        'views/menus.xml',
        'views/templates_common.xml',
        'views/templates_search.xml',
        'views/templates_listing.xml',
        'views/templates_agents.xml',
        'views/templates_portal.xml',
        'views/templates_home.xml',
        'views/mail_templates.xml',
    ],
    'demo': [
        'data/demo_data.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            're_property_portal/static/src/scss/portal.scss',
            're_property_portal/static/src/js/property_portal.js',
        ],
        # Loaded only on pages showing a map
        're_property_portal.assets_map': [
            're_property_portal/static/lib/leaflet/leaflet.css',
            're_property_portal/static/lib/leaflet/leaflet.js',
            're_property_portal/static/src/js/property_map.js',
        ],
    },
    'installable': True,
    'application': True,
}
