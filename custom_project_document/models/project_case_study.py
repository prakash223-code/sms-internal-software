from odoo import models, fields, api
from odoo.exceptions import UserError


class ProjectCaseStudy(models.Model):
    _name = 'project.case.study'
    _description = 'Project Case Study'
    _order = 'upload_date desc, id desc'
    _rec_name = 'name'

    # ------------------------------------------------------------------
    # FIELDS
    # ------------------------------------------------------------------

    project_id = fields.Many2one(
        'project.project',
        string='Project',
        required=True,
        ondelete='cascade',
        index=True,
    )

    name = fields.Char(
        string='Case Study Title',
        required=True,
        help='e.g. Client Onboarding Success, Q3 Performance Review',
    )

    case_study_type = fields.Selection([
        ('technical',           'Technical Case Study'),
        ('business',            'Business / ROI Case Study'),
        ('client_success',      'Client Success Story'),
        ('process_improvement', 'Process Improvement'),
        ('risk_analysis',       'Risk Analysis'),
        ('post_mortem',         'Post-Mortem / Lessons Learned'),
        ('other',               'Other'),
    ], string='Case Study Type', required=True, default='other')

    # ── Narrative fields ──────────────────────────────────────────────

    summary = fields.Text(
        string='Executive Summary',
        help='A short overview of the case study (2–4 sentences).',
    )

    challenge = fields.Text(
        string='Challenge / Problem',
        help='What problem or challenge was this case study addressing?',
    )

    solution = fields.Text(
        string='Solution / Approach',
        help='How was the challenge tackled? Methods, tools, or processes used.',
    )

    outcome = fields.Text(
        string='Outcome / Results',
        help='Key results, metrics, or conclusions.',
    )

    # ── File attachment (same pattern as project.document) ────────────

    file = fields.Binary(
        string='Supporting File',
        attachment=True,
        help='Attach a PDF, Word doc, or any supporting document.',
    )

    filename = fields.Char(string='File Name')

    file_type = fields.Char(
        string='File Type',
        compute='_compute_file_type',
        store=True,
    )

    file_url = fields.Char(
        string='Preview',
        compute='_compute_file_url',
        help='Opens the attached file inline in the browser.',
    )

    # ── Audit ─────────────────────────────────────────────────────────

    upload_date = fields.Date(
        string='Recorded On',
        default=fields.Date.today,
        readonly=True,
    )

    uploaded_by = fields.Many2one(
        'res.users',
        string='Recorded By',
        default=lambda self: self.env.uid,
        readonly=True,
    )

    notes = fields.Text(
        string='Notes',
        help='Optional remarks or references.',
    )

    # Computed write-permission flag — consumed by view readonly expressions
    can_write = fields.Boolean(
        compute='_compute_can_write',
        help='True when the current user may create / edit / delete case studies.',
    )

    # ------------------------------------------------------------------
    # COMPUTED
    # ------------------------------------------------------------------

    @api.depends('filename')
    def _compute_file_type(self):
        for rec in self:
            if rec.filename and '.' in rec.filename:
                rec.file_type = rec.filename.rsplit('.', 1)[-1].upper()
            else:
                rec.file_type = '—'

    @api.depends('file', 'filename')
    def _compute_file_url(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        for rec in self:
            if rec.file and rec.id:
                rec.file_url = f'{base_url}/project/case-study/preview/{rec.id}'
            else:
                rec.file_url = False

    def _compute_can_write(self):
        result = self._user_can_write()
        for rec in self:
            rec.can_write = result


    # ------------------------------------------------------------------
    # ACCESS HELPERS  (same rules as project.document)
    # ------------------------------------------------------------------

    def _user_can_write(self):
        """Manager, HR, and Team Leads can create/edit/delete. Others read-only."""
        user = self.env.user

        if user.has_group('project.group_project_manager'):
            return True

        if user.has_group('hr.group_hr_user'):
            return True

        employee = self.env['hr.employee'].sudo().search(
            [('user_id', '=', user.id)], limit=1
        )
        if employee and employee.is_team_lead:
            return True

        return False

    # ------------------------------------------------------------------
    # ORM OVERRIDES
    # ------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        if not self._user_can_write():
            raise UserError(
                'Only Manager, HR, or Team Lead can create project case studies.'
            )
        return super().create(vals_list)

    def write(self, vals):
        if not self._user_can_write():
            raise UserError(
                'Only Manager, HR, or Team Lead can edit project case studies.'
            )
        return super().write(vals)

    def unlink(self):
        if not self._user_can_write():
            raise UserError(
                'Only Manager, HR, or Team Lead can delete project case studies.'
            )
        return super().unlink()