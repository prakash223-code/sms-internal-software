{
    'name': 'Case Study',
    'version': '1.0',
    'summary': 'Manage Case Studies',
    'description': 'A module to manage case studies',
    'category': 'Project',
    'author': 'SMS Software team',
    'license':'LGPL-3',
    'depends': ['base', 'mail','hr','project',
        'hr_timesheet',],
    'data': [
        'security/ir.model.access.csv',
        'data/case_study_sequence.xml',
        'data/case_study_stages_data.xml',
        'views/case_study_views.xml',
    ],
    'installable': True,
    'application': True,
}