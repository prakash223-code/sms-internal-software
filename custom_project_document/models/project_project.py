from odoo import models, fields


class ProjectProject(models.Model):
    _inherit = 'project.project'

    document_ids = fields.One2many(
        'project.document',
        'project_id',
        string='Documents',
    )

    document_count = fields.Integer(
        string='Document Count',
        compute='_compute_document_count',
    )

    def _compute_document_count(self):
        for project in self:
            project.document_count = len(project.document_ids)

    def action_view_documents(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Project Documents',
            'res_model': 'project.document',
            'view_mode': 'kanban,list,form',
            'domain': [('project_id', '=', self.id)],
            'context': {'default_project_id': self.id},
        }