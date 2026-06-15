{
    'name': 'Custom Login Theme',
    'version': '19.0.1.0.0',
    'summary': 'Branded, modern theme for the login / user-picker screen',
    'category': 'Theme/Backend',
    'depends': ['web'],
    'data': [
        'views/login_templates.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'custom_login_theme/static/src/scss/login_theme.scss',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}