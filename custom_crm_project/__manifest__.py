{
    'name': 'CRM to Project Conversion',
    'version': '19.0.1.0.0',
    'summary': 'Manual conversion of CRM queries into projects with traceability',
    'author': 'Your Company',
    'license': 'LGPL-3',
    'depends': ['crm', 'project', 'hr'],
    'data': [
        'data/sequences.xml',
        'views/crm_lead_views.xml',
        'views/project_views.xml',
    ],
    'installable': True,
    'application': False,
}
