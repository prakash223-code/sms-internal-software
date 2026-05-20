from odoo import models, api
from odoo.exceptions import UserError


class ProjectTask(models.Model):
    _inherit = 'project.task'

    # ------------------------------------------------------------------
    # Permission check helper
    # ------------------------------------------------------------------

    def _user_can_create_task(self):
        """
        Returns True if the current user is allowed to create tasks.

        Allowed:
          - Manager / HR  → has project.group_project_manager
                            (already assigned to both roles in custom_payroll_bridge)
          - Team Lead     → plain employee with is_team_lead = True on their
                            hr.employee record

        Blocked:
          - Plain employee (project_user only, is_team_lead = False)
        """
        # Managers and HR already have project_manager group
        if self.env.user.has_group('project.group_project_manager'):
            return True

        # Check if the linked employee record has Team Lead flag
        employee = self.env['hr.employee'].search(
            [('user_id', '=', self.env.uid)],
            limit=1
        )
        if employee and employee.is_team_lead:
            return True

        return False

    # ------------------------------------------------------------------
    # ORM override
    # ------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        """
        Block plain employees from creating tasks.
        Manager, HR, and Team Leads can create both main tasks and subtasks.
        """
        if not self._user_can_create_task():
            raise UserError(
                'You are not allowed to create tasks.\n\n'
                'Only Managers, HR, and Team Leads can create tasks.\n'
                'Please contact your Team Lead or Manager to have a task assigned to you.'
            )
        return super().create(vals_list)

    def copy(self, default=None):
        """Block plain employees from duplicating tasks as well."""
        if not self._user_can_create_task():
            raise UserError(
                'You are not allowed to duplicate tasks.\n\n'
                'Please contact your Team Lead or Manager.'
            )
        return super().copy(default)
