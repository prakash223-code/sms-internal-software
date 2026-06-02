{
    'name': 'Custom Project',
    'version': '19.0.1.0.0',
    'summary': 'Team Lead role + task creation restrictions for project management',
    'author': 'Your Company',
    'depends': ['hr', 'project', 'custom_employee_id'],
    'license': 'LGPL-3',
    'data': [
        'views/hr_employee_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'custom_project/static/src/css/custom_project.css',
        ],
    },
    'installable': True,
    'application': False,
}