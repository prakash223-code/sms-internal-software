{
    'name': 'Session Expire on Browser Close',
    'version': '19.0.1.0.0',
    'category': 'Technical',
    'author': 'Internal ERP Team',
    'license': 'LGPL-3',
    'depends': ['web'],
    'assets': {
        'web.assets_backend': [
            'custom_session_expire/static/src/js/session_expire.js',
        ],
    },
    'installable': True,
    'auto_install': False,
}
