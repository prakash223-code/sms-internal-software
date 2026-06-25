from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class WorkReport(models.Model):
    _name = 'work.report'
    _inherit = ['mail.thread']
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
        readonly=True,
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
    attachment_ids = fields.Many2many(
        'ir.attachment',
        'work_report_attachment_rel',
        'report_id',
        'attachment_id',
        string='Attachments',
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
    ], default='draft', string='Status', readonly=True)

    def _default_employee(self):
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
            if not vals.get('employee_id'):
                employee = self.env['hr.employee'].search(
                    [('user_id', '=', self.env.uid)], limit=1
                )
                if employee:
                    vals['employee_id'] = employee.id
        records = super().create(vals_list)
        records._reparent_attachments()
        return records

    def write(self, vals):
        res = super().write(vals)
        if 'attachment_ids' in vals:
            self._reparent_attachments()
        return res

    def _reparent_attachments(self):
        """
        Attachments are uploaded with res_model='ir.ui.view' / no res_id
        (the standard many2many_binary upload trick), which means Odoo's
        own ir.attachment access check only allows the *creator* to read
        them - everyone else, including HR/Manager, gets silently filtered
        out. Re-pointing res_model/res_id at the actual work.report record
        makes them fall under work.report's own ir.rule instead, so
        Manager/HR see all and employees see their own, same as the
        report itself.
        """
        for rec in self:
            stray = rec.attachment_ids.filtered(
                lambda a: a.res_model != 'work.report' or a.res_id != rec.id
            )
            if stray:
                stray.sudo().write({
                    'res_model': 'work.report',
                    'res_id': rec.id,
                })

    def action_submit(self):
        for rec in self:
            if rec.state != 'draft':
                raise ValidationError("Only draft reports can be submitted.")
            rec.state = 'submitted'
            rec._notify_managers_on_submit()

    def action_reset_draft(self):
        for rec in self:
            rec.state = 'draft'

    # ------------------------------------------------------------------
    # NOTIFICATIONS
    # ------------------------------------------------------------------

    def _notify_managers_on_submit(self):
        """
        Pushes an Inbox notification to every user in the Work Report
        Manager group when an employee submits their report.
        """
        self.ensure_one()
        manager_group = self.env.ref(
            'custom_work_report.group_work_report_manager',
            raise_if_not_found=False,
        )
        if not manager_group:
            return

        manager_partners = manager_group.user_ids.mapped('partner_id')
        manager_partners = manager_partners - self.env.user.partner_id
        if not manager_partners:
            return

        body = _('%(employee)s submitted a work report for %(date)s.') % {
            'employee': self.employee_id.name,
            'date': self.date,
        }
        self.message_notify(
            partner_ids=manager_partners.ids,
            subject=_('Work Report Submitted'),
            body=body,
            subtype_xmlid='mail.mt_comment',
        )