{
    'name': 'Custom Project – Team Task Management',
    'version': '19.0.4.0.0',
    'summary': 'Team-based task assignment with cross-team manager approval workflow',
    'author': 'Your Company',
    'license': 'LGPL-3',
    'depends': ['hr', 'project', 'mail', 'custom_employee_id'],
    'data': [
        # 1. Security (must load first)
        'security/security_groups.xml',
        'security/ir.model.access.csv',
        'security/record_rules.xml',
        # 2. Sequences
        'data/sequences.xml',
        # 3. Seed data — project stages library
        'data/project_stage_data.xml',
        # 4. Views
        'views/team_views.xml',
        'views/task_views.xml',
        'views/assignment_request_views.xml',
        'views/hr_employee_views.xml',
        'views/project_stage_views.xml',
        'views/project_project_views.xml',
        # 5. Menus (last — reference actions defined in views)
        'views/menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            # CSS
            'custom_project/static/src/css/custom_project.css',
            # JS patch — must load before the XML template that references it
            'custom_project/static/src/js/project_stage_selector.js',
            # OWL template override for KanbanColumnQuickCreate
            'custom_project/static/src/xml/project_stage_selector.xml',
        ],
    },
    'installable': True,
    'application': False,
}