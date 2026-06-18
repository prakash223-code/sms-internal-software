# hooks.py
# PURPOSE: Post-migrate hook — re-applies role groups to all existing
#   employees that have a linked user. Runs on every module upgrade so
#   new groups added to _ROLE_GROUPS propagate automatically without
#   requiring manual "Setup Permissions" clicks per employee.

import logging
_logger = logging.getLogger(__name__)


def post_migrate(env):
    employees = env['hr.employee'].search([('user_id', '!=', False)])
    _logger.info(
        'custom_payroll_bridge post_migrate: applying role groups '
        'to %d employee(s)', len(employees)
    )
    employees._assign_role_groups()