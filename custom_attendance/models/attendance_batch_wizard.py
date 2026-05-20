# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class AttendanceSummaryBatchWizard(models.TransientModel):
    _name = 'attendance.summary.batch.wizard'
    _description = 'Generate Monthly Attendance Summary — Batch'

    # ------------------------------------------------------------------
    # FIELDS
    # ------------------------------------------------------------------

    month = fields.Selection([
        ('1', 'January'), ('2', 'February'), ('3', 'March'),
        ('4', 'April'),   ('5', 'May'),      ('6', 'June'),
        ('7', 'July'),    ('8', 'August'),   ('9', 'September'),
        ('10', 'October'),('11', 'November'),('12', 'December'),
    ], string='Month', required=True)

    year = fields.Integer(
        string='Year',
        required=True,
        default=lambda self: fields.Date.today().year,
    )

    employee_ids = fields.Many2many(
        'hr.employee',
        string='Employees',
        domain=[('active', '=', True)],
        help='Leave empty to generate for ALL active employees.',
    )

    overwrite_draft = fields.Boolean(
        string='Recompute Existing Draft Summaries',
        default=True,
        help='If checked, existing Draft summaries for the selected period will be recomputed. '
             'Confirmed summaries are always protected and never overwritten.',
    )

    # result counters — shown after generation
    state = fields.Selection([
        ('draft',  'Setup'),
        ('done',   'Done'),
    ], default='draft')

    result_created   = fields.Integer(string='Created',   readonly=True)
    result_recomputed = fields.Integer(string='Recomputed', readonly=True)
    result_skipped   = fields.Integer(string='Skipped (Confirmed)', readonly=True)
    result_total     = fields.Integer(string='Total Employees',     readonly=True)

    # ------------------------------------------------------------------
    # DEFAULTS
    # ------------------------------------------------------------------

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        today = fields.Date.today()
        # Default to previous month (most common use case)
        if today.month == 1:
            res['month'] = '12'
            res['year']  = today.year - 1
        else:
            res['month'] = str(today.month - 1)
            res['year']  = today.year
        return res

    # ------------------------------------------------------------------
    # ACTION: Select All / Clear
    # ------------------------------------------------------------------

    def action_select_all_employees(self):
        self.ensure_one()
        all_employees = self.env['hr.employee'].search([('active', '=', True)])
        self.employee_ids = [(6, 0, all_employees.ids)]
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_clear_employees(self):
        self.ensure_one()
        self.employee_ids = [(5, 0, 0)]
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    # ------------------------------------------------------------------
    # ACTION: Generate
    # ------------------------------------------------------------------

    def action_generate(self):
        self.ensure_one()

        if not self.month or not self.year:
            raise UserError(_('Please select both Month and Year.'))

        if self.year < 2020 or self.year > 2100:
            raise UserError(_('Please enter a valid year.'))

        Summary = self.env['attendance.monthly.summary']

        # Resolve target employees
        if self.employee_ids:
            employees = self.employee_ids
        else:
            employees = self.env['hr.employee'].search([('active', '=', True)])

        if not employees:
            raise UserError(_('No active employees found to process.'))

        created    = 0
        recomputed = 0
        skipped    = 0

        for employee in employees:
            existing = Summary.search([
                ('employee_id', '=', employee.id),
                ('month',       '=', self.month),
                ('year',        '=', self.year),
            ], limit=1)

            if existing:
                if existing.state == 'confirmed':
                    skipped += 1
                    continue
                # Draft — recompute only if option is checked
                if self.overwrite_draft:
                    existing._compute_summary()
                    recomputed += 1
                # else: leave draft untouched, count as skipped
                else:
                    skipped += 1
            else:
                new_rec = Summary.create({
                    'employee_id': employee.id,
                    'month':       self.month,
                    'year':        self.year,
                    'state':       'draft',
                })
                new_rec._compute_summary()
                created += 1

        self.write({
            'state':              'done',
            'result_created':     created,
            'result_recomputed':  recomputed,
            'result_skipped':     skipped,
            'result_total':       len(employees),
        })

        # Stay open to show results
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    # ------------------------------------------------------------------
    # ACTION: Open generated summaries
    # ------------------------------------------------------------------

    def action_view_summaries(self):
        self.ensure_one()
        employee_ids = self.employee_ids.ids or \
            self.env['hr.employee'].search([('active', '=', True)]).ids
        return {
            'type': 'ir.actions.act_window',
            'name': _('Monthly Summaries'),
            'res_model': 'attendance.monthly.summary',
            'view_mode': 'list,form',
            'domain': [
                ('month',       '=', self.month),
                ('year',        '=', self.year),
                ('employee_id', 'in', employee_ids),
            ],
            'target': 'current',
        }