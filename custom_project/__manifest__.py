{
    'name': 'Custom Project – Team Task Management',
    'version': '19.0.2.0.0',
    'summary': 'Team-based task assignment with cross-team manager approval workflow',
    'author': 'Your Company',
    'license': 'LGPL-3',
    'depends': ['hr', 'project', 'mail', 'custom_employee_id'],
    'data': [
        # 1. Security
        'security/security_groups.xml',
        'security/ir.model.access.csv',
        'security/record_rules.xml',
        # 2. Sequences
        'data/sequences.xml',
        # 3. Default stage records  ← ADD THIS
        'data/project_stage_data.xml',
        # 4. Views
        'views/team_views.xml',
        'views/task_views.xml',
        'views/assignment_request_views.xml',
        'views/hr_employee_views.xml',
        'views/project_project_views.xml',  # ← ADD THIS
        'views/stage_config_views.xml',
        'views/project_stage_views.xml',  # ← ADD THIS (if used)
        'views/res_users_views.xml',  # ← ADD THIS (also missing)
        # 5. Menus
        'views/menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'custom_project/static/src/css/custom_project.css',
            'custom_project/static/src/js/project_stage_selector.js',
            'custom_project/static/src/xml/project_stage_selector.xml',
        ],
    },
    'installable': True,
    'application': False,
}
