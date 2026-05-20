# custom_expense/__manifest__.py

{
    'name': 'Custom Expense',
    'version': '19.0.1.0.0',
    'summary': 'Controlled internal expense submission and approval',
    'author': 'Internal',
    'category': 'Human Resources',
    'license': 'LGPL-3',
    'depends': [
        'hr',
        'project',
        'mail',
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/expense_security.xml',
        'data/expense_sequence.xml',
        'data/expense_category_data.xml',
        'wizard/expense_reject_wizard_views.xml',
        'views/custom_expense_category_views.xml',
        'views/custom_expense_views.xml',
        'views/custom_expense_menu.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
