import mimetypes

from odoo import _, api, fields, models


class CaseStudyStage(models.Model):
    _name = 'case.study.stage'
    _description = 'Case Study Stage'
    _order = 'sequence, id'

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    fold = fields.Boolean(default=False)


class CaseStudyDepartment(models.Model):
    _name = 'case.study.department'
    _description = 'Case Study Department'
    _order = 'sequence, name'

    name = fields.Char(required=True)
    code = fields.Char(string='Code', help='e.g. CFD, FEA, ERP')
    sequence = fields.Integer(default=10)
    color = fields.Integer(default=0)
    description = fields.Text()
    active = fields.Boolean(default=True)

    case_study_ids = fields.One2many(
        'case.study', 'department_id', string='Case Studies'
    )
    case_study_count = fields.Integer(
        compute='_compute_case_study_count'
    )

    def _compute_case_study_count(self):
        for rec in self:
            rec.case_study_count = self.env['case.study'].search_count([
                ('department_id', '=', rec.id)
            ])

    def action_view_case_studies(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.name,
            'res_model': 'case.study',
            'view_mode': 'kanban,list,form',
            'domain': [('department_id', '=', self.id)],
            'context': {'default_department_id': self.id},
        }


class CaseStudySoftware(models.Model):
    """Configurable dropdown list of software used (CFD/FEA/ERP tools)."""
    _name = 'case.study.software'
    _description = 'Case Study Software'
    _order = 'sequence, name'

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)


class CaseStudyTag(models.Model):
    """Simple colored tags for internal filtering/search."""
    _name = 'case.study.tag'
    _description = 'Case Study Tag'
    _order = 'name'

    name = fields.Char(required=True)
    color = fields.Integer(default=0)


class CaseStudyTimesheet(models.Model):
    _name = 'case.study.timesheet'
    _description = 'Case Study Timesheet Line'
    _order = 'date desc, id desc'

    case_study_id = fields.Many2one(
        'case.study', required=True, ondelete='cascade'
    )
    employee_id = fields.Many2one(
        'hr.employee', string='Employee', required=True
    )
    date = fields.Date(required=True, default=fields.Date.context_today)
    hours = fields.Float(required=True)
    description = fields.Char(string='Work Description')

    # ---- new columns requested ----
    project_id = fields.Many2one(
        'project.project', string='Project'
    )
    task_id = fields.Many2one(
        'project.task', string='Task',
        domain="[('project_id', '=', project_id)]"
    )
    software_id = fields.Many2one(
        'case.study.software', string='Software Used'
    )


class CaseStudyDocument(models.Model):
    """Document lines for the Documents tab (Document Name, Category,
    Type, File, Preview, Uploaded On)."""
    _name = 'case.study.document'
    _description = 'Case Study Document'
    _order = 'uploaded_on desc, id desc'

    case_study_id = fields.Many2one(
        'case.study', required=True, ondelete='cascade'
    )
    name = fields.Char(string='Document Name', required=True)
    category = fields.Char(string='Category')
    file_data = fields.Binary(string='File', attachment=True)
    file_name = fields.Char(string='File Name')
    mimetype = fields.Char(compute='_compute_file_info', store=True)
    type = fields.Char(string='Type', compute='_compute_file_info', store=True)
    preview = fields.Binary(string='Preview', compute='_compute_preview')
    uploaded_on = fields.Datetime(
        string='Uploaded On', default=fields.Datetime.now
    )

    @api.depends('file_name')
    def _compute_file_info(self):
        for rec in self:
            ext = ''
            if rec.file_name and '.' in rec.file_name:
                ext = rec.file_name.rsplit('.', 1)[-1].upper()
            rec.type = ext or False
            guessed, _enc = mimetypes.guess_type(rec.file_name or '')
            rec.mimetype = guessed or False

    @api.depends('file_data', 'mimetype')
    def _compute_preview(self):
        for rec in self:
            if rec.mimetype and rec.mimetype.startswith('image/'):
                rec.preview = rec.file_data
            else:
                rec.preview = False


class CaseStudy(models.Model):
    _name = 'case.study'
    _description = 'Case Study'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'sequence, id desc'

    name = fields.Char(required=True, tracking=True)
    code = fields.Char(
        string='Case Study No.', copy=False, readonly=True,
        default=lambda self: _('New')
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    color = fields.Integer(default=0)

    # ---- Confirm button -> locks the record (read-only) ----
    locked = fields.Boolean(string='Locked', default=False, tracking=True)

    department_id = fields.Many2one(
        'case.study.department',
        string='Department',
        required=True,
        tracking=True,
    )
    project_id = fields.Many2one(
        'project.project', string='Project', tracking=True
    )
    stage_id = fields.Many2one(
        'case.study.stage',
        string='Stage',
        tracking=True,
        group_expand='_read_group_stage_ids',
        default=lambda self: self.env['case.study.stage'].search(
            [], order='sequence asc', limit=1
        ),
    )
    user_id = fields.Many2one(
        'res.users',
        string='Responsible',
        default=lambda self: self.env.user,
        tracking=True,
    )
    team_user_ids = fields.Many2many(
        'res.users', 'case_study_team_rel', 'case_study_id', 'user_id',
        string='Team Members'
    )
    partner_id = fields.Many2one(
        'res.partner', string='Client', tracking=True
    )
    priority = fields.Selection(
        [('0', 'Normal'), ('1', 'Important')],
        string='Priority', default='0'
    )
    tag_ids = fields.Many2many(
        'case.study.tag', string='Tags'
    )
    date_start = fields.Date(string='Start Date')
    date_end = fields.Date(string='End Date')

    description = fields.Html(string='Overview')
    problem_statement = fields.Html(string='Problem Statement')
    objective = fields.Html(string='Objective / Scope')
    methodology = fields.Html(string='Methodology / Approach')
    challenges = fields.Html(string='Challenges Faced')
    results = fields.Html(string='Results / Outcome')
    conclusion = fields.Html(string='Conclusion')

    planned_hours = fields.Float(string='Planned Hours')

    # ---- Documents tab now backed by case.study.document ----
    document_ids = fields.One2many(
        'case.study.document', 'case_study_id', string='Documents'
    )
    document_count = fields.Integer(compute='_compute_document_count')

    timesheet_ids = fields.One2many(
        'case.study.timesheet', 'case_study_id', string='Timesheet'
    )
    total_hours = fields.Float(
        compute='_compute_total_hours', store=True
    )

    @api.depends('document_ids')
    def _compute_document_count(self):
        for rec in self:
            rec.document_count = len(rec.document_ids)

    @api.depends('timesheet_ids.hours')
    def _compute_total_hours(self):
        for rec in self:
            rec.total_hours = sum(rec.timesheet_ids.mapped('hours'))

    def _read_group_stage_ids(self, stages, domain):
        return self.env['case.study.stage'].search([], order='sequence asc')

    def action_view_case_studies(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.name,
            'res_model': 'case.study',
            'view_mode': 'kanban,list,form',
            'domain': [('department_id', '=', self.id)],
            'context': {
                'default_department_id': self.id,
            },
        }

    def action_confirm(self):
        self.write({'locked': True})

    def action_draft(self):
        self.write({'locked': False})

    def action_open_project(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.project_id.name,
            'res_model': 'project.project',
            'view_mode': 'form',
            'res_id': self.project_id.id,
        }

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('code', _('New')) == _('New'):
                vals['code'] = self.env['ir.sequence'].next_by_code(
                    'case.study'
                ) or _('New')
        return super().create(vals_list)