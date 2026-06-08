from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError


class ProjectTaskType(models.Model):
    _inherit = 'project.task.type'

    is_default_stage = fields.Boolean(
        string='Auto-add to New Projects',
        default=False,
    )

    def _check_stage_access(self):
        """Raise AccessError unless the current user is a manager or HR."""
        if self.env.su:
            return  # superuser bypasses check

        if (self.env.user.has_group('custom_project.group_team_manager')
                or self.env.user.has_group('hr.group_hr_user')):
            return

        raise AccessError(
            _('Only Managers and HR users can create, edit, or delete '
              'task stages. Go to Configuration > Task Stages to manage '
              'the stage library.')
        )

    @api.model
    def name_create(self, name):
        """
        Intercept kanban column creation.
        Find the existing stage, LINK IT to the current project, and return it.
        """
        existing_stage = self.search([('name', '=ilike', name)], limit=1)
        if existing_stage:
            # Explicitly link this stage to the current project's task board
            project_id = self.env.context.get('default_project_id')
            if project_id:
                existing_stage.sudo().write({'project_ids': [(4, project_id)]})

            return existing_stage.id, existing_stage.display_name

        # Safety net
        raise UserError(_('You cannot create new stages on the fly. Please select an existing stage.'))

    @api.model_create_multi
    def create(self, vals_list):
        self._check_stage_access()
        return super().create(vals_list)

    _STAGE_PROPERTY_FIELDS = {'name', 'sequence', 'fold', 'is_default_stage', 'active', 'description'}

    def write(self, vals):
        # Only guard when actual stage properties are being changed,
        # not when M2M relationships (project_ids) are being maintained.
        if self._STAGE_PROPERTY_FIELDS & set(vals):
            self._check_stage_access()
        return super().write(vals)

    def unlink(self):
        """
        Intercept the delete command to prevent accidental global data loss.
        """
        # 1. Check if the user is deleting from inside a project kanban
        project_id = self.env.context.get('default_project_id')

        if project_id:
            # 2. Soft Unlink: Remove the relation to this project ONLY.
            # sudo() ensures standard users can remove stages from their board
            self.sudo().write({'project_ids': [(3, project_id)]})

            # Return True to satisfy the UI, but DO NOT call super().unlink()
            # This keeps the global stage safe in the database.
            return True

            # 3. Hard Delete: If no project_id is in the context, they are in the
        # Configuration menu. Proceed with actual database deletion.
        self._check_stage_access()
        return super().unlink()
