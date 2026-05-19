{
    'name': 'Project Documents',
    'version': '19.0.1.0.0',
    'summary': 'Upload and manage project documents with role-based access',
    'author': 'SMS Enterprises',
    'depends': ['project', 'hr'],
    'license': 'LGPL-3',
    'data': [
        'security/ir.model.access.csv',
        'views/project_document_views.xml',
        'views/project_project_views.xml',
    ],
    'installable': True,
    'application': False,
}
