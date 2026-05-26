{
    'name': 'Custom Employee ID',
    'version': '19.0.1.0.0',
    'summary': 'Auto-generate Employee IDs in YY+DEPT+SEQ format',
    'author': 'Your Company',
    'depends': ['hr'],
    'license': 'LGPL-3',
    'data': [
        'data/sequences.xml',
        'views/hr_department_views.xml',
        'views/hr_employee_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'custom_employee_id/static/src/css/employee_id.css',
        ],
    },
    'installable': True,
    'application': False,
}