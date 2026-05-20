# custom_payroll_bridge/models/hr_payslip.py

from odoo import models, fields, api


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    attendance_summary_id = fields.Many2one(
        'attendance.monthly.summary',
        string='Attendance Summary',
        readonly=True,
    )

    unpaid_absent_days = fields.Float(
        string='Unpaid Absent Days',
        readonly=True,
    )

    def _sync_absent_days_input(self):
        Summary = self.env['attendance.monthly.summary']

        if not self.employee_id or not self.date_from:
            return

        # ── Find confirmed monthly summary ────────────────────────────────────
        summary = Summary.search([
            ('employee_id', '=', self.employee_id.id),
            ('month', '=', self.date_from.month),
            ('year', '=', self.date_from.year),
            ('state', '=', 'confirmed'),
        ], limit=1)

        unpaid_days = summary.unpaid_absent_days if summary else 0.0

        # ── Store on payslip for display ──────────────────────────────────────
        self.attendance_summary_id = summary.id if summary else False
        self.unpaid_absent_days = unpaid_days

        if not self.contract_id:
            return

        # ── Remove existing ABSENT_DAYS input line ────────────────────────────
        existing = self.env['hr.payslip.input'].sudo().search([
            ('payslip_id', '=', self.id),
            ('code', '=', 'ABSENT_DAYS'),
        ])
        if existing:
            existing.sudo().unlink()

        # ── Create fresh ABSENT_DAYS input line directly ──────────────────────
        # hr.payslip.input requires: name, code, amount, contract_id, payslip_id
        self.env['hr.payslip.input'].sudo().create({
            'name': 'Unpaid Absent Days',
            'code': 'ABSENT_DAYS',
            'amount': unpaid_days,
            'contract_id': self.contract_id.id,
            'payslip_id': self.id,
            'sequence': 5,
        })
