{
    'name': 'HR Employee Documents',
    'version': '19.0.1.0.0',
    'summary': 'Upload and manage employee documents with role-based access',
    'author': 'Your Company',
    'depends': ['hr'],
    'license': 'LGPL-3',
    'data': [
        'security/ir.model.access.csv',
        'views/hr_employee_document_views.xml',
        'views/hr_employee_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'custom_hr_document/static/src/css/custom_hr_document.css',
        ],
    },
    'installable': True,
    'application': False,
}