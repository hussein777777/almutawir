# -*- coding: utf-8 -*-
{
    'name': 'Real Estate Developer Website',
    'version': '18.0.1.2.0',
    'summary': 'Professional website for real estate developers & construction companies: '
               'projects, units, services, about us, company overview and contact (CRM leads).',
    'category': 'Website/Website',
    'author': 'Hussein',
    'license': 'LGPL-3',
    'depends': ['website', 'crm', 'mail'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'security/record_rules.xml',
        'data/website_menu.xml',
        'data/website_lang.xml',
        'data/website_brand.xml',
        'views/re_amenity_views.xml',
        'views/re_project_views.xml',
        'views/re_unit_views.xml',
        'views/re_service_views.xml',
        'views/re_team_member_views.xml',
        'views/website_views.xml',
        'views/crm_lead_views.xml',
        'views/menus.xml',
        'views/templates_common.xml',
        'views/templates_home.xml',
        'views/templates_projects.xml',
        'views/templates_units.xml',
        'views/templates_pages.xml',
    ],
    'demo': [
        'data/demo_data.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            're_developer_website/static/src/scss/estate.scss',
        ],
    },
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
    'installable': True,
    'application': True,
}
