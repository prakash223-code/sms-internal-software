# custom_payroll_bridge/models/hr_payslip.py

from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


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

    def compute_sheet(self):
        """Sync absent days input BEFORE payslip lines are computed."""
        for slip in self:
            slip._sync_absent_days_input()
        return super().compute_sheet()

    def _sync_absent_days_input(self):
        Summary = self.env['attendance.monthly.summary']

        if not self.employee_id or not self.date_from:
            _logger.warning('Payslip %s: missing employee or date_from', self.id)
            return

        month_int = self.date_from.month
        month_str = str(month_int)
        year      = self.date_from.year

        # ── Try both string and integer month (defensive) ─────────────
        summary = Summary.search([
            ('employee_id', '=', self.employee_id.id),
            ('month',       '=', month_str),
            ('year',        '=', year),
            ('state',       '=', 'confirmed'),
        ], limit=1)

        # Fallback: try integer month in case stored differently
        if not summary:
            summary = Summary.search([
                ('employee_id', '=', self.employee_id.id),
                ('month',       '=', month_int),
                ('year',        '=', year),
                ('state',       '=', 'confirmed'),
            ], limit=1)

        _logger.info(
            'Payslip %s | employee: %s (id=%s) | %s/%s | '
            'summary found: %s | unpaid_absent_days: %s',
            self.id,
            self.employee_id.name,
            self.employee_id.id,
            month_str,
            year,
            bool(summary),
            summary.unpaid_absent_days if summary else 0.0,
        )

        if not summary:
            _logger.warning(
                'Payslip %s: No confirmed summary for employee "%s" '
                'month=%s year=%s — deduction will be 0.',
                self.id, self.employee_id.name, month_str, year,
            )

        unpaid_days = summary.unpaid_absent_days if summary else 0.0

        self.attendance_summary_id = summary.id if summary else False
        self.unpaid_absent_days    = unpaid_days

        if not self.contract_id:
            _logger.warning('Payslip %s: no contract — cannot inject ABSENT_DAYS.', self.id)
            return

        # ── Remove stale input ────────────────────────────────────────
        stale = self.env['hr.payslip.input'].sudo().search([
            ('payslip_id', '=', self.id),
            ('code',       '=', 'ABSENT_DAYS'),
        ])
        if stale:
            stale.sudo().unlink()

        # ── Inject fresh input ────────────────────────────────────────
        self.env['hr.payslip.input'].sudo().create({
            'name':        'Unpaid Absent Days',
            'code':        'ABSENT_DAYS',
            'amount':      unpaid_days,
            'contract_id': self.contract_id.id,
            'payslip_id':  self.id,
            'sequence':    5,
        })

        _logger.info(
            'Payslip %s: ABSENT_DAYS injected — amount=%s', self.id, unpaid_days
        )