# -*- coding: utf-8 -*-
{
    'name': 'Welcome Dashboard',
    'version': '19.0.1.0.0',
    'category': 'Human Resources',
    'summary': 'Daily quote home page with one-click check-in/out',
    'author': 'Internal ERP Team',
    'depends': [
        'hr',
        'hr_attendance',
        'custom_attendance',   # for action_toggle_attendance + company.holiday
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/welcome_quotes.xml',
        'views/welcome_views.xml',
        'views/welcome_menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'custom_welcome/static/src/css/welcome.css',
        ],
    },
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}