from . import models

def post_init_hook(env):
    """Assign work report groups to existing users after install."""

    employee_group = env.ref('custom_work_report.group_work_report_employee')
    hr_group = env.ref('custom_work_report.group_work_report_hr')
    manager_group = env.ref('custom_work_report.group_work_report_manager')

    # All internal users → employee group
    internal_users = env.ref('base.group_user').user_ids
    employee_group.write({
        'user_ids': [(4, u.id) for u in internal_users]
    })

    # HR Officers → hr group
    hr_users = env.ref('hr.group_hr_user').user_ids
    hr_group.write({
        'user_ids': [(4, u.id) for u in hr_users]
    })

    # HR Managers → manager group
    manager_users = env.ref('hr.group_hr_manager').user_ids
    manager_group.write({
        'user_ids': [(4, u.id) for u in manager_users]
    })