# custom_payroll_bridge/__manifest__.py

{
    'name': 'Custom Payroll Bridge',
    'version': '19.0.1.0.0',
    'summary': 'Connects custom_attendance monthly summary to BrowseInfo payroll',
    'author': 'Internal',
    'category': 'Human Resources',
    'license': 'LGPL-3',
    'depends': [
        'bi_hr_payroll',  # BrowseInfo payroll module
        'custom_attendance',  # your attendance module (unpaid_absent_days)
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/payroll_security.xml',
        'data/payroll_bridge_data.xml',
        'views/payslip_bridge_views.xml',
        'views/employee_payslip_menu.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
