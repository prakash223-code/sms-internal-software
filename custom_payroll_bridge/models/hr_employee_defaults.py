# custom_payroll_bridge/models/hr_employee_defaults.py

from odoo import models, api
import logging

_logger = logging.getLogger(__name__)


class HrEmployeeDefaults(models.Model):
    _inherit = 'hr.employee'

    # ── Groups every employee user must have ─────────────────────────────────
    # Add or remove entries here as your system grows
    _EMPLOYEE_DEFAULT_GROUPS = [
        'base.group_user',                          # Internal User (base)
        'hr_attendance.group_hr_attendance',        # Attendance check-in/out
        'project.group_project_user',               # View/work on project tasks
    ]

    # ── Optional: groups for your custom modules ──────────────────────────────
    # These use try/except so a missing module won't crash the whole thing
    _EMPLOYEE_OPTIONAL_GROUPS = [
        'custom_expense.group_expense_user',        # Your custom expense module
        'custom_attendance.group_attendance_user',  # Your custom attendance module (if any)
    ]

    def _assign_default_employee_groups(self):
        """
        Assign required groups to the user linked to this employee.
        Safe to call multiple times — uses (4, id) which is add-if-not-present.
        """
        for employee in self:
            user = employee.user_id
            if not user:
                continue

            group_ids = []

            # Required groups
            for xml_id in self._EMPLOYEE_DEFAULT_GROUPS:
                try:
                    group = self.env.ref(xml_id)
                    group_ids.append((4, group.id))
                except Exception:
                    _logger.warning('Employee defaults: group not found: %s', xml_id)

            # Optional groups (won't fail if module not installed)
            for xml_id in self._EMPLOYEE_OPTIONAL_GROUPS:
                try:
                    group = self.env.ref(xml_id)
                    group_ids.append((4, group.id))
                except Exception:
                    pass  # Module not installed — skip silently

            if group_ids:
                user.sudo().write({'group_ids': group_ids})
                _logger.info(
                    'Employee defaults: assigned %d group(s) to user %s (employee: %s)',
                    len(group_ids), user.login, employee.name
                )

    # ── Auto-trigger on create ────────────────────────────────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        employees = super().create(vals_list)
        employees.filtered('user_id')._assign_default_employee_groups()
        return employees

    # ── Auto-trigger when user_id is set or changed ───────────────────────────
    def write(self, vals):
        res = super().write(vals)
        if 'user_id' in vals and vals['user_id']:
            self._assign_default_employee_groups()
        return res

    # ── Manual button: HR can re-run this on any employee ────────────────────
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