from odoo import api, models


class ProjectProject(models.Model):
    _inherit = 'project.project'

    @api.model_create_multi
    def create(self, vals_list):
        # 1. Fetch default stages BEFORE creating the project
        default_stages = self.env['project.task.type'].sudo().search([
            ('is_default_stage', '=', True)
        ])

        # 2. Inject them directly into the creation values
        if default_stages:
            stage_ids = default_stages.ids
            for vals in vals_list:
                # (6, 0, [IDs]) is the absolute command to set a Many2many field.
                # It guarantees Odoo creates the project with these stages already linked.
                if 'type_ids' not in vals:
                    vals['type_ids'] = [(6, 0, stage_ids)]

        # 3. Proceed with standard creation using our modified payload
        return super().create(vals_list)