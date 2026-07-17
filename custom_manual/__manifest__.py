# -*- coding: utf-8 -*-
{
    'name': 'Custom ERP Manual',
    'version': '19.0.1.0.0',
    'category': 'Human Resources',
    'summary': 'Role-based in-app user manual for the SMS Enterprises ERP',
    'description': """
Role-Based ERP Manual
======================
Serves an in-app reference manual whose visible sections are determined
by the logged-in user's employee_role (Employee / Manager / HR), read
directly from hr.employee — not user-selectable, not spoofable from the
browser.
    """,
    'author': 'Internal ERP Team',
    'depends': ['hr', 'custom_payroll_bridge'],
    'data': [
        'views/manual_menu.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
