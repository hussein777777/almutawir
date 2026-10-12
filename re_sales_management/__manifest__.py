# -*- coding: utf-8 -*-
{
    'name': 'Real Estate Sales Management',
    'version': '18.0.1.0.0',
    'summary': 'Real estate developer sales: projects, buildings, units, customers, contracts, '
               'installment schedules, collections, cheques, receivables aging and a sales dashboard. '
               'Fully integrated with Odoo Accounting.',
    'category': 'Sales/Real Estate',
    'author': 'Hussein',
    'license': 'LGPL-3',
    'depends': ['re_developer_website', 'account', 'mail', 'web'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'security/record_rules.xml',
        'data/ir_sequence.xml',
        'data/product_data.xml',
        'data/ir_cron.xml',
        'data/accounting_setup.xml',
        'wizard/re_payment_wizard_views.xml',
        'views/re_building_views.xml',
        'views/re_project_views.xml',
        'views/re_unit_views.xml',
        'views/res_partner_views.xml',
        'views/re_installment_views.xml',
        'views/re_contract_views.xml',
        'views/account_payment_views.xml',
        'views/re_aging_report_views.xml',
        'views/res_config_settings_views.xml',
        'views/dashboard_action.xml',
        'views/menus.xml',
        'report/contract_statement.xml',
    ],
    'demo': [
        'data/demo_data.xml',
    ],
    'assets': {
        'web.assets_backend': [
            're_sales_management/static/src/dashboard/dashboard.scss',
            're_sales_management/static/src/dashboard/dashboard.js',
            're_sales_management/static/src/dashboard/dashboard.xml',
            're_sales_management/static/src/views/backend.scss',
        ],
    },
    'installable': True,
    'application': True,
}
