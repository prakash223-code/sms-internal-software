from odoo import api, models


class ProjectProject(models.Model):
    _inherit = 'project.project'

    @api.model_create_multi
    def create(self, vals_list):
        projects = super().create(vals_list)

        default_stages = self.env['project.task.type'].sudo().search(
            [('is_default_stage', '=', True)],
            order='sequence',
        )

        if default_stages:
            link_cmds = [(4, stage.id) for stage in default_stages]
            for project in projects:
                # (4, id) is a no-op if the stage is already linked,
                # so this is safe even when vals contained type_ids.
                project.sudo().write({'type_ids': link_cmds})

        return projects