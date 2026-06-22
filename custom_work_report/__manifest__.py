{
    'name': 'Daily Work Report',
    'version': '19.0.1.0.0',
    'summary': 'Employee daily work reporting with submit workflow',
    'author': 'Your Company',
    'license': 'LGPL-3',
    'depends': ['hr', 'project'],
    'data': [
        'security/work_report_security.xml',
        'security/ir.model.access.csv',
        'views/work_report_views.xml',
    ],
    'installable': True,
    'application': True,
    'web_icon': 'custom_expense,static/description/icon.png',
    'post_init_hook': 'post_init_hook',  # ← add this
}
