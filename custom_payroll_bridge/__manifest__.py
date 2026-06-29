# custom_payroll_bridge/__manifest__.py

{
    'name': 'Custom Payroll Bridge',
    'version': '19.0.1.2.0',
    'summary': 'Connects custom_attendance monthly summary to BrowseInfo payroll',
    'author': 'Internal',
    'category': 'Human Resources',
    'license': 'LGPL-3',
    'depends': [
        'bi_hr_payroll',  # BrowseInfo payroll module
        'custom_attendance',  # your attendance module (unpaid_absent_days)
        # custom_project must be installed first so that
        # custom_project.group_team_manager exists (and is env.ref()-resolvable)
        # by the time _ROLE_GROUPS / _resync_all_role_groups runs. Without this
        # explicit dependency, install/upgrade order between the two modules
        # is not guaranteed, and the Manager role's group assignment could
        # silently skip group_team_manager (the try/except in
        # _assign_role_groups logs a warning but does not fail loudly).
        'custom_project',
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/payroll_security.xml',
        'data/payroll_bridge_data.xml',
        'views/payslip_bridge_views.xml',
        'data/payslip_paperformat.xml',
        'views/payslip_kanban_views.xml',
        'views/payslip_kanban_fix.xml',
        'views/employee_payslip_menu.xml',
        'views/employee_defaults_view.xml',
        'views/create_user_password_view.xml',
        'views/report_payslip_custom_template.xml',
        # REVERTED: automatic role-group resync on every upgrade was removed
        # after it stripped groups from the Administrator account on a live
        # system. Role groups are now ONLY applied via the manual
        # "Setup Permissions" button on each employee's form, one employee
        # at a time, by deliberate human action. See
        # models/hr_employee_defaults.py for details — the underlying
        # _assign_role_groups() method (and its admin-account exclusion)
        # is kept, but data/role_groups_resync.xml is no longer loaded.
    ],
    'assets': {
        'web.assets_backend': [
            'custom_payroll_bridge/static/src/css/custom_payroll_bridge.css',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
