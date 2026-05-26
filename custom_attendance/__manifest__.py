# -*- coding: utf-8 -*-
{
    'name': 'Custom Attendance Management',
    'version': '19.0.2.1.0',
    'category': 'Human Resources/Attendance',
    'summary': 'Advanced attendance tracking with late detection, monthly summary, and payroll integration',
    'author': 'Internal ERP Team',
    'depends': [
        'hr',
        'hr_attendance',
        'hr_holidays',
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/attendance_security.xml',
        'data/attendance_cron.xml',
        'views/attendance_views.xml',
        'views/monthly_summary_views.xml',
        'views/attendance_checkin_views.xml',
        'views/company_holiday_views.xml',
        'views/attendance_batch_wizard_views.xml',
        'views/attendance_menu.xml',
    ],
    # CSS delivered via the standard web assets pipeline.
    # This avoids Content-Security-Policy violations caused by inline
    # style= attributes in view XML, which trigger "Style compilation
    # failed" errors in Odoo 17+.
    'assets': {
        'web.assets_backend': [
            'custom_attendance/static/src/css/attendance.css',
        ],
    },
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}