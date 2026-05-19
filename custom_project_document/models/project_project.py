from odoo import models, fields


class ProjectProject(models.Model):
    _inherit = 'project.project'

    document_ids = fields.One2many(
        'project.document',
        'project_id',
        string='Documents',
    )

    document_count = fields.Integer(
        string='Documents',
        compute='_compute_document_count',
    )

    def _compute_document_count(self):
        for project in self:
            project.document_count = len(project.document_ids)
