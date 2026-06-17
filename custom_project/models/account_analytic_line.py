from odoo import _, api, models
from odoo.exceptions import UserError


class AccountAnalyticLine(models.Model):
    """
    Restrict timesheet entries on project tasks so that only the employee
    assigned to the task (project.task.assigned_to) can log time.

    Managers (group_team_manager) and HR (group_hr_user) are exempt and
    can log or edit timesheets on behalf of any employee.
    """
    _inherit = 'account.analytic.line'

    # ── Access helper ─────────────────────────────────────────────────────────

    def _is_privileged(self):
        return (
            self.env.user.has_group('custom_project.group_team_manager')
            or self.env.user.has_group('hr.group_hr_user')
        )

    def _check_timesheet_employee(self, vals):
        """
        Called on create and write.

        Rules:
        • If the line is not linked to a task → no restriction.
        • If the line IS linked to a task that has no assigned_to → no restriction.
        • Otherwise the employee_id on the line MUST match task.assigned_to.
        • Managers and HR are always exempt.
        """
        if self._is_privileged():
            return

        task_id = vals.get('task_id') or (
            self.task_id.id if hasattr(self, 'task_id') and self.task_id else None
        )
        if not task_id:
            return

        task = self.env['project.task'].browse(task_id)
        if not task.assigned_to:
            return

        employee_id = vals.get('employee_id') or (
            self.employee_id.id if hasattr(self, 'employee_id') and self.employee_id else None
        )
        if not employee_id:
            return

        if employee_id != task.assigned_to.id:
            raise UserError(
                _(
                    'Only the assigned employee (%s) can log time on '
                    'task "%s".'
                ) % (task.assigned_to.name, task.name)
            )

    # ── ORM overrides ─────────────────────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._check_timesheet_employee(vals)
        return super().create(vals_list)

    def write(self, vals):
        # Only validate when task_id or employee_id is being changed,
        # or when a new task link is being set. Editing just the description
        # or date does not need re-checking.
        if 'task_id' in vals or 'employee_id' in vals:
            for line in self:
                merged = {
                    'task_id':     vals.get('task_id',     line.task_id.id if line.task_id else None),
                    'employee_id': vals.get('employee_id', line.employee_id.id if line.employee_id else None),
                }
                line._check_timesheet_employee(merged)
        return super().write(vals)