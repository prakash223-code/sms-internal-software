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
                existing = vals.get('type_ids') or []
                has_real_stages = any(
                    isinstance(cmd, (list, tuple)) and cmd[0] == 6 and cmd[2]  # (6, 0, [non-empty ids])
                    or isinstance(cmd, (list, tuple)) and cmd[0] == 4  # (4, id) link
                    for cmd in existing
                )
                if not has_real_stages:
                    vals['type_ids'] = [(6, 0, stage_ids)]

        # 3. Proceed with standard creation using our modified payload
        return super().create(vals_list)

    def write(self, vals):
        if default_stages and not vals.get('type_ids'):
            # same injection logic
            vals['type_ids'] = [(6, 0, stage_ids)]
        return super().write(vals)
