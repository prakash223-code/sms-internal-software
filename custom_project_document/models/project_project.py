from odoo import models, fields


class ProjectProject(models.Model):
    _inherit = 'project.project'

    # ── Documents ─────────────────────────────────────────────────────

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
        can_write = self._docs_user_can_write()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Project Documents',
            'res_model': 'project.document',
            'view_mode': 'kanban,list,form',
            'domain': [('project_id', '=', self.id)],
            'context': {
                'default_project_id': self.id,
                'create': can_write,
                'delete': can_write,
            },
        }

    # ── Shared write-permission check ─────────────────────────────────

    def _docs_user_can_write(self):
        """
        Mirrors the _user_can_write logic from project.document so the
        action method can set UI flags without instantiating the model first.

        Team Lead status is NOT a stored field on hr.employee — it is
        derived from team.team.team_lead_id (defined in custom_project).
        """
        user = self.env.user
        if user.has_group('project.group_project_manager'):
            return True
        if user.has_group('hr.group_hr_user'):
            return True
        employee = self.env['hr.employee'].sudo().search(
            [('user_id', '=', user.id)], limit=1
        )
        if not employee:
            return False
        is_lead = self.env['team.team'].sudo().search_count(
            [('team_lead_id', '=', employee.id)]
        )
        return bool(is_lead)