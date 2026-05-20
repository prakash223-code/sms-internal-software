from odoo import models, fields, api
from odoo.exceptions import ValidationError

class WorkReport(models.Model):
    _name = 'work.report'
    _description = 'Daily Work Report'
    _order = 'date desc, id desc'

    name = fields.Char(
        string='Reference',
        readonly=True,
        copy=False,
        default='New'
    )
    date = fields.Date(
        string='Date',
        required=True,
        default=fields.Date.context_today
    )
    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        required=True,
        readonly=True,          # ← always readonly, set by system
        default=lambda self: self._default_employee()
    )
    project_id = fields.Many2one(
        'project.project',
        string='Project'
    )
    description = fields.Text(
        string='Work Done',
        required=True
    )
    hours_spent = fields.Float(
        string='Hours Spent'
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
    ], default='draft', string='Status', readonly=True)

    def _default_employee(self):
        # Find employee linked to current user
        employee = self.env['hr.employee'].search(
            [('user_id', '=', self.env.uid)], limit=1
        )
        return employee

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'work.report.seq'
                ) or 'New'
            # Force employee to current user's employee record
            if not vals.get('employee_id'):
                employee = self.env['hr.employee'].search(
                    [('user_id', '=', self.env.uid)], limit=1
                )
                if employee:
                    vals['employee_id'] = employee.id
        return super().create(vals_list)

    def action_submit(self):
        for rec in self:
            if rec.state != 'draft':
                raise ValidationError("Only draft reports can be submitted.")
            rec.state = 'submitted'

    def action_reset_draft(self):
        for rec in self:
            rec.state = 'draft'