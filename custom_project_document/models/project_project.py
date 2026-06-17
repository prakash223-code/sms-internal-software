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
                # False hides New / Delete buttons in list + kanban for non-privileged users
                'create': can_write,
                'delete': can_write,
            },
        }

    # ── Case Studies ──────────────────────────────────────────────────

    case_study_ids = fields.One2many(
        'project.case.study',
        'project_id',
        string='Case Studies',
    )

    case_study_count = fields.Integer(
        string='Case Study Count',
        compute='_compute_case_study_count',
    )

    def _compute_case_study_count(self):
        for project in self:
            project.case_study_count = len(project.case_study_ids)

    def action_view_case_studies(self):
        self.ensure_one()
        can_write = self._docs_user_can_write()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Case Studies',
            'res_model': 'project.case.study',
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
        Mirrors the _user_can_write logic from project.document /
        project.case.study so the action methods can set UI flags
        without instantiating either model first.
        """
        user = self.env.user
        if user.has_group('project.group_project_manager'):
            return True
        if user.has_group('hr.group_hr_user'):
            return True
        employee = self.env['hr.employee'].sudo().search(
            [('user_id', '=', user.id)], limit=1
        )
        return bool(employee and employee.is_team_lead)