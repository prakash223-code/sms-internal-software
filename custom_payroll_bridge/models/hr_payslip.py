# custom_payroll_bridge/models/hr_payslip.py

from odoo import models, fields, api
import logging
import calendar
from datetime import date

try:
    from num2words import num2words
    NUM2WORDS_AVAILABLE = True
except ImportError:
    NUM2WORDS_AVAILABLE = False

_logger = logging.getLogger(__name__)


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    slip_month = fields.Selection(
        selection=[
            ('1', 'January'), ('2', 'February'), ('3', 'March'),
            ('4', 'April'), ('5', 'May'), ('6', 'June'),
            ('7', 'July'), ('8', 'August'), ('9', 'September'),
            ('10', 'October'), ('11', 'November'), ('12', 'December'),
        ],
        string='Month',
        compute='_compute_slip_period',
        inverse='_inverse_slip_period',
        store=True,
    )
    slip_year = fields.Integer(
        string='Year',
        compute='_compute_slip_period',
        inverse='_inverse_slip_period',
        store=True,
    )

    @api.depends('date_from')
    def _compute_slip_period(self):
        for slip in self:
            if slip.date_from:
                slip.slip_month = str(slip.date_from.month)
                slip.slip_year = slip.date_from.year
            else:
                slip.slip_month = False
                slip.slip_year = False

    def _inverse_slip_period(self):
        for slip in self:
            if slip.slip_month and slip.slip_year:
                month = int(slip.slip_month)
                year = slip.slip_year
                last_day = calendar.monthrange(year, month)[1]
                slip.date_from = date(year, month, 1)
                slip.date_to = date(year, month, last_day)

    attendance_summary_id = fields.Many2one(
        'attendance.monthly.summary',
        string='Attendance Summary',
        readonly=True,
    )

    unpaid_absent_days = fields.Float(
        string='Unpaid Absent Days',
        readonly=True,
    )

    # ── Print format: date the payslip was actually confirmed ──────────────
    # Distinct from date_from/date_to (the pay PERIOD) — this is "Pay Date"
    # on the printed payslip per SMS Enterprises' official format. Stamped
    # the moment action_payslip_done() succeeds; stays blank for draft/verify
    # payslips, which is intentional — an unconfirmed payslip has no real
    # "pay date" yet.
    confirmed_date = fields.Date(
        string='Confirmed Date',
        readonly=True,
        copy=False,
    )

    def action_payslip_done(self):
        res = super().action_payslip_done()
        for slip in self:
            if not slip.confirmed_date:
                slip.confirmed_date = fields.Date.context_today(self)
        return res

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
        year = self.date_from.year

        # ── Try both string and integer month (defensive) ─────────────
        summary = Summary.search([
            ('employee_id', '=', self.employee_id.id),
            ('month', '=', month_str),
            ('year', '=', year),
            ('state', '=', 'confirmed'),
        ], limit=1)

        if not summary:
            summary = Summary.search([
                ('employee_id', '=', self.employee_id.id),
                ('month', '=', month_int),
                ('year', '=', year),
                ('state', '=', 'confirmed'),
            ], limit=1)

        if not summary:
            _logger.warning(
                'Payslip %s: No confirmed summary for employee "%s" '
                'month=%s year=%s — deduction will be 0, per-day rate '
                'will fall back to wage/30.',
                self.id, self.employee_id.name, month_str, year,
            )

        unpaid_days = summary.unpaid_absent_days if summary else 0.0

        # working_days comes from the confirmed monthly summary — it already
        # excludes Sundays, 2nd/4th Saturdays, and any declared company.holiday
        # records, so it shifts automatically whenever HR adds/removes a holiday.
        # Fall back to 30 only when no confirmed summary exists yet for the period.
        working_days = summary.working_days if (summary and summary.working_days) else 30

        _logger.info(
            'Payslip %s | employee: %s (id=%s) | %s/%s | summary found: %s | '
            'unpaid_absent_days: %s | working_days: %s',
            self.id, self.employee_id.name, self.employee_id.id,
            month_str, year, bool(summary), unpaid_days, working_days,
        )

        self.attendance_summary_id = summary.id if summary else False
        self.unpaid_absent_days = unpaid_days

        if not self.contract_id:
            _logger.warning('Payslip %s: no contract — cannot inject inputs.', self.id)
            return

        Input = self.env['hr.payslip.input'].sudo()

        # ── Remove stale inputs ────────────────────────────────────────
        Input.search([
            ('payslip_id', '=', self.id),
            ('code', 'in', ['ABSENT_DAYS', 'WORKING_DAYS']),
        ]).unlink()

        # ── Inject fresh inputs ──────────────────────────────────────────
        Input.create({
            'name': 'Unpaid Absent Days',
            'code': 'ABSENT_DAYS',
            'amount': unpaid_days,
            'contract_id': self.contract_id.id,
            'payslip_id': self.id,
            'sequence': 5,
        })
        Input.create({
            'name': 'Working Days in Month',
            'code': 'WORKING_DAYS',
            'amount': working_days,
            'contract_id': self.contract_id.id,
            'payslip_id': self.id,
            'sequence': 6,
        })

        _logger.info(
            'Payslip %s: ABSENT_DAYS=%s, WORKING_DAYS=%s injected',
            self.id, unpaid_days, working_days,
        )

    # ── Print template helpers ──────────────────────────────────────────────
    # All amounts the printed payslip needs are pulled live from the
    # confirmed salary rule lines (line_ids) rather than recomputed here —
    # line_ids IS the source of truth for what was actually calculated for
    # this payslip. If a rule hasn't fired yet (payslip not computed), these
    # safely return 0.0 instead of raising.

    def _get_salary_line_amount(self, code):
        """Total for a single salary rule, identified by its rule code
        (e.g. 'BASIC', 'GROSS', 'NET', 'ABSENT_DED')."""
        self.ensure_one()
        line = self.line_ids.filtered(lambda l: l.code == code)
        return line.total if line else 0.0

    def _get_salary_category_amount(self, category_code):
        """Summed total across every salary rule line under a given
        category code (e.g. 'DED' — covers ALL deduction rules combined,
        not just ABSENT_DED, so this stays correct if another deduction
        rule is added later)."""
        self.ensure_one()
        lines = self.line_ids.filtered(lambda l: l.category_id.code == category_code)
        return sum(lines.mapped('total'))

    def _get_pay_period_label(self):
        """e.g. 'May 2026' — derived from slip_month / slip_year."""
        self.ensure_one()
        if not self.slip_month or not self.slip_year:
            return ''
        month_label = dict(self._fields['slip_month'].selection).get(self.slip_month, '')
        return f'{month_label} {self.slip_year}'

    @staticmethod
    def _fmt_amount(value):
        """Plain comma-grouped integer, no currency symbol, no decimals —
        matches the official payslip format exactly (e.g. '12,000')."""
        return '{:,.0f}'.format(value or 0.0)

    def _get_amount_in_words(self, amount):
        """'Rupees Twelve Thousand Only' — matches the official format.

        KNOWN LIMITATION: uses standard English (thousand/million) numbering
        via num2words, not the Indian lakh/crore system. For amounts under
        ₹1,00,000 both systems produce identical wording (e.g. 12,000 is
        'twelve thousand' either way), so this is safe at current salary
        levels. If Net Pay ever exceeds ₹99,999, this will NOT say
        'one lakh' — swap in a lakh-aware converter if/when that happens.
        """
        self.ensure_one()
        if not NUM2WORDS_AVAILABLE:
            _logger.warning(
                'Payslip %s: num2words not installed — amount-in-words '
                'left blank on printed payslip.', self.id
            )
            return ''
        words = num2words(int(round(amount or 0.0)), lang='en')
        words = words.replace('-', ' ').title()
        return f'Rupees {words} Only'