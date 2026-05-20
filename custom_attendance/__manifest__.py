# -*- coding: utf-8 -*-
{
    'name': 'Custom Attendance Management',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Attendance',
    'summary': 'Advanced attendance tracking with late detection, monthly summary, and payroll integration',
    'author': 'Internal ERP Team',
    'depends': [
        'hr',
        'hr_attendance',
        'hr_holidays',
    ],
    'data': [
        # Security
        'security/ir.model.access.csv',
        'security/attendance_security.xml',

        # Data
        'data/attendance_cron.xml',

        # Views
        'views/attendance_views.xml',
        'views/monthly_summary_views.xml',
        'views/attendance_checkin_views.xml',
        'views/company_holiday_views.xml',
        'views/attendance_batch_wizard_views.xml',
        'views/attendance_menu.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
