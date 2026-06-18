from odoo import api, models


class ProjectProject(models.Model):
    _inherit = 'project.project'

    @api.model_create_multi
    def create(self, vals_list):
        default_stages = self.env['project.task.type'].sudo().search(
            [('is_default_stage', '=', True)],
            order='sequence asc',
        )

        if default_stages:
            stage_ids = default_stages.ids
            for vals in vals_list:
                existing = vals.get('type_ids') or []
                has_real_stages = any(
                    isinstance(cmd, (list, tuple)) and (
                        (cmd[0] == 6 and cmd[2])  # (6, 0, [non-empty ids])
                        or cmd[0] == 4            # (4, id) individual link
                    )
                    for cmd in existing
                )
                if not has_real_stages:
                    vals['type_ids'] = [(6, 0, stage_ids)]

        return super(ProjectProject, self.sudo()).create(vals_list)