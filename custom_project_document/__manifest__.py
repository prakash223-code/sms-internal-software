{
    'name': 'Project Documents',
    'version': '19.0.1.1.0',
    'summary': 'Upload and manage project documents and case studies with role-based access',
    'author': 'SMS Enterprises',
    'depends': ['project', 'hr'],
    'license': 'LGPL-3',
    'data': [
        'security/ir.model.access.csv',
        'views/project_case_study_views.xml',
        'views/project_document_views.xml',
        'views/project_project_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'custom_project_document/static/src/css/custom_project_document.css',
            'custom_project_document/static/src/css/custom_project_case_study.css',
        ],
    },
    'installable': True,
    'application': False,
}