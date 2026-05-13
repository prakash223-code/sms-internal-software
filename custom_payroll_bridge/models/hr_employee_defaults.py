# custom_payroll_bridge/models/hr_employee_defaults.py

from odoo import models, api
import logging

_logger = logging.getLogger(__name__)


class HrEmployeeDefaults(models.Model):
    _inherit = 'hr.employee'

    _EMPLOYEE_DEFAULT_GROUPS = [
        'base.group_user',
        'hr_attendance.group_hr_attendance_own_reader',
        'project.group_project_user',
    ]

    _EMPLOYEE_OPTIONAL_GROUPS = [
        'custom_expense.group_expense_user',
        'custom_attendance.group_attendance_user',
    ]

    def _assign_default_employee_groups(self):
        for employee in self:
            user = employee.user_id
            if not user:
                continue

            group_ids = []

            for xml_id in self._EMPLOYEE_DEFAULT_GROUPS:
                try:
                    group = self.env.ref(xml_id)
                    group_ids.append((4, group.id))
                except Exception:
                    _logger.warning('Employee defaults: group not found: %s', xml_id)

            for xml_id in self._EMPLOYEE_OPTIONAL_GROUPS:
                try:
                    group = self.env.ref(xml_id)
                    group_ids.append((4, group.id))
                except Exception:
                    pass

            if group_ids:
                # Fixed: group_ids not groups_id (Odoo 19)
                user.sudo().write({'group_ids': group_ids})
                _logger.info(
                    'Employee defaults: assigned %d group(s) to user %s (employee: %s)',
                    len(group_ids), user.login, employee.name
                )

    @api.model_create_multi
    def create(self, vals_list):
        employees = super().create(vals_list)
        employees.filtered('user_id')._assign_default_employee_groups()
        return employees

    def write(self, vals):
        res = super().write(vals)
        if 'user_id' in vals and vals['user_id']:
            self._assign_default_employee_groups()
        return res

    def action_setup_employee_permissions(self):
        self._assign_default_employee_groups()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Permissions Updated',
                'message': f'Default permissions assigned to {self.name}.',
                'type': 'success',
                'sticky': False,
            }
        }
