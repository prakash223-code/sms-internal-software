from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ProjectTaskType(models.Model):
    _inherit = 'project.task.type'

    is_default_stage = fields.Boolean(
        string='Default Stage',
        default=False,
        help=(
            'When enabled, this stage is automatically linked to every '
            'new project at creation time. Users can remove it afterwards '
            'if it is not needed for their project.'
        ),
    )

    @api.model
    def name_create(self, name):
        """
        Intercept the kanban column quick-create.

        • Exact (case-insensitive) match found  → return the existing stage.
        • No match + caller is a manager        → allow creation.
        • No match + regular user               → raise a helpful error.

        This ensures the "Add a Stage" input in the project task kanban
        always resolves to a stage from the configured library instead of
        silently spawning a new one.
        """
        existing = self.search([('name', '=ilike', name)], limit=1)
        if existing:
            return existing.id, existing.display_name

        if self.env.user.has_group('custom_project.group_team_manager'):
            return super().name_create(name)

        raise UserError(_(
            'Stage "%s" does not exist in the library.\n\n'
            'Please select an existing stage from the list, or ask a manager '
            'to add it under Project ▸ Configuration ▸ Project Stages.'
        ) % name)