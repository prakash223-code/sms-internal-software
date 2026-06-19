{
    'name': 'Project Documents',
    'version': '19.0.1.2.0',
    'summary': 'Upload and manage project documents with role-based access',
    'author': 'SMS Enterprises',
    'depends': ['project', 'hr', 'custom_project'],
    'license': 'LGPL-3',
    'data': [
        'security/ir.model.access.csv',
        'views/project_document_views.xml',
        'views/project_project_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'custom_project_document/static/src/css/custom_project_document.css',
        ],
    },
    'installable': True,
    'application': False,
}