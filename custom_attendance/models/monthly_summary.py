# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from odoo.models import Constraint
import pytz
import calendar
from datetime import datetime, date, timedelta


class AttendanceMonthlySummary(models.Model):
    _name = 'attendance.monthly.summary'
    _description = 'Attendance Monthly Summary'
    _order = 'year desc, month desc, employee_id'
    _rec_name = 'display_name'

    # ------------------------------------------------------------------
    # FIELDS
    # ------------------------------------------------------------------

    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        required=True,
        ondelete='cascade',
        index=True,
    )

    month = fields.Selection(
        selection=[
            ('1', 'January'), ('2', 'February'), ('3', 'March'),
            ('4', 'April'), ('5', 'May'), ('6', 'June'),
            ('7', 'July'), ('8', 'August'), ('9', 'September'),
            ('10', 'October'), ('11', 'November'), ('12', 'December'),
        ],
        string='Month',
        required=True,
    )

    year = fields.Integer(
        string="Year",
        required=True,
        default=lambda self: fields.Date.today().year,
    )

    working_days = fields.Integer(
        string='Working Days',
        readonly=True,
        default=0,
        help='Total working days after excluding Sundays, 2nd/4th Saturdays, and company holidays.',
    )

    present_days = fields.Integer(
        string='Present Days',
        readonly=True,
        default=0,
    )

    late_days = fields.Integer(
        string='Late Days',
        readonly=True,
        default=0,
    )

    leave_days = fields.Float(
        string='Approved Leave Days',
        readonly=True,
        default=0.0,
        help='Approved paid leaves intersected with working days (fractional for half-days). Does not count as absent.',
    )

    unpaid_leave_days = fields.Float(
        string='Unpaid Leave Days',
        readonly=True,
        default=0.0,
        help='Approved unpaid leaves — counted in salary deduction (fractional for half-days).',
    )

    absent_days = fields.Float(
        string='Absent Days',
        readonly=True,
        default=0.0,
        help='working_days - present_days - leave_days (fractional for half-day gaps).',
    )

    unpaid_absent_days = fields.Float(
        string='Unpaid Absent Days',
        readonly=True,
        default=0.0,
        help='absent_days + unpaid_leave_days — used for payroll deduction (fractional for half-days).',
    )

    permission_overflow_minutes = fields.Integer(
        string='Permission Overflow (Minutes)',
        readonly=True,
        default=0,
        help='Total late minutes this month that exceeded the employee\'s '
             'Permission pool (manual + auto combined). Feeds the payroll '
             'overflow deduction salary rule.',
    )

    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('confirmed', 'Confirmed'),
        ],
        string='Status',
        default='draft',
        required=True,
        index=True,
    )

    display_name = fields.Char(
        string='Summary',
        compute='_compute_display_name',
        store=True,
    )

    # ------------------------------------------------------------------
    # UNIQUE CONSTRAINT
    # ------------------------------------------------------------------

    _constraints = [
        Constraint(
            'UNIQUE(employee_id, month, year)',
            'A summary record already exists for this employee '
            'for the selected month and year.',
        )
    ]

    # ------------------------------------------------------------------
    # COMPUTED
    # ------------------------------------------------------------------

    @api.depends('employee_id', 'month', 'year')
    def _compute_display_name(self):
        month_map = {
            '1': 'Jan', '2': 'Feb', '3': 'Mar', '4': 'Apr',
            '5': 'May', '6': 'Jun', '7': 'Jul', '8': 'Aug',
            '9': 'Sep', '10': 'Oct', '11': 'Nov', '12': 'Dec',
        }
        for rec in self:
            month_label = month_map.get(rec.month, rec.month)
            employee_name = rec.employee_id.name or ''
            rec.display_name = f"{employee_name} – {month_label} {rec.year}"

    # ------------------------------------------------------------------
    # STATE ACTIONS
    # ------------------------------------------------------------------

    def action_confirm(self):
        for rec in self:
            if rec.state == 'confirmed':
                raise UserError(_('This summary is already confirmed.'))
            rec.state = 'confirmed'

    def action_reset_to_draft(self):
        for rec in self:
            rec.state = 'draft'

    # ------------------------------------------------------------------
    # CORE: COMPUTE SUMMARY
    # ------------------------------------------------------------------

    def action_compute(self):
        for rec in self:
            if rec.state == 'confirmed':
                raise UserError(_(
                    'Cannot recompute a confirmed summary. '
                    'Reset to draft first.'
                ))
            rec._compute_summary()

    def _compute_summary(self):
        self.ensure_one()

        # --- Guards ---
        if not self.year or not self.month:
            raise UserError(_('Please set Employee, Month, and Year before computing.'))
        if self.year < 2020 or self.year > 2100:
            raise UserError(_('Year %s is out of valid range (2020–2100).') % self.year)
        if not self.employee_id:
            raise UserError(_('Please set an Employee before computing.'))

        year = self.year
        month = int(self.month)
        employee = self.employee_id

        tz_name = employee.tz or 'Asia/Kolkata'
        try:
            tz = pytz.timezone(tz_name)
        except pytz.UnknownTimeZoneError:
            tz = pytz.timezone('Asia/Kolkata')

        # --- 1. Working days ---
        working_day_dates = self._get_working_day_dates(year, month)
        working_days_count = len(working_day_dates)

        # --- 2. Present days ---
        attendance_model = self.env['hr.attendance']
        present_date_set = attendance_model.get_present_days(employee.id, year, month)

        # --- 3. Late days ---
        late_days_count = attendance_model.get_late_days(employee.id, year, month)

        # --- 3b. Permission overflow minutes ---
        permission_overflow_count = attendance_model.get_permission_overflow_minutes(
            employee.id, year, month
        )

        # --- 4. Leave days ---
        leave_days_count, unpaid_leave_days_count, leave_date_fractions = \
            self._get_leave_data(employee, year, month, working_day_dates, tz)

        # --- 5. Absent days (fractional) ---
        # present_date_set from hr.attendance is still whole-date granularity
        # (Decision 8 simplification) — any check-in that date = 1.0 presence.
        effective_present = present_date_set & working_day_dates

        absent_fraction_total = 0.0
        for working_date in working_day_dates:
            present_fraction = 1.0 if working_date in effective_present else 0.0
            leave_fraction = leave_date_fractions.get(working_date, 0.0)
            covered = min(1.0, present_fraction + leave_fraction)
            absent_fraction_total += (1.0 - covered)

        absent_days_count = absent_fraction_total

        # --- 6. Unpaid absent (for payroll deduction) ---
        unpaid_absent_days_count = absent_days_count + unpaid_leave_days_count

        self.write({
            'working_days': working_days_count,
            'present_days': len(effective_present),
            'late_days': late_days_count,
            'leave_days': leave_days_count,
            'unpaid_leave_days': unpaid_leave_days_count,
            'absent_days': absent_days_count,
            'unpaid_absent_days': unpaid_absent_days_count,
            'permission_overflow_minutes': permission_overflow_count,
        })

    # ------------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------------

    def _get_working_day_dates(self, year, month):
        """
        Returns a set of date objects that are genuine working days:
          - Monday to Friday: always included
          - Saturday: included ONLY if it is the 1st, 3rd, or 5th Saturday
            (2nd and 4th Saturdays are company off days)
          - Sunday: always excluded
          - Any date matching an active company.holiday record: excluded
          - Any 2nd/4th Saturday already excluded by the Saturday rule above

        The company.holiday model's get_holidays_in_range() covers both
        declared holidays AND 2nd/4th Saturdays, so we call it once and
        subtract the full holiday set.
        """
        num_days = calendar.monthrange(year, month)[1]
        date_from = date(year, month, 1)
        date_to = date(year, month, num_days)

        # Fetch all holidays for the month (declared + 2nd/4th Saturdays)
        holiday_dates = self.env['company.holiday'].get_holidays_in_range(
            date_from, date_to
        )

        working_dates = set()
        for day in range(1, num_days + 1):
            d = date(year, month, day)
            if d.weekday() == 6:  # Sunday — always off
                continue
            if d in holiday_dates:  # declared holiday or 2nd/4th Saturday
                continue
            working_dates.add(d)

        return working_dates

    def _get_leave_data(self, employee, year, month, working_day_dates, tz):
        """
        Returns:
            leave_days_count     : approved paid leave — SUM of fractions (0.5/1.0 per date)
            unpaid_leave_days    : approved unpaid leave — SUM of fractions
            leave_date_fractions : dict[date, float] — fraction of that date covered by
                                   approved leave (0.5 for a single half-day, 1.0 for a
                                   full day, or 1.0 if both halves are separately covered
                                   by two half-day leaves on the same date)

        Holiday-aware: days that fall on a company holiday or 2nd/4th Saturday
        are excluded from leave consumption — the employee should not lose a
        leave day (or half-day) for a day that was already a holiday.
        """
        num_days = calendar.monthrange(year, month)[1]
        first_day = date(year, month, 1)
        last_day = date(year, month, num_days)

        holiday_dates = self.env['company.holiday'].get_holidays_in_range(
            first_day, last_day
        )

        hr_leaves = self.env['hr.leave'].search([
            ('employee_id', '=', employee.id),
            ('state', '=', 'validate'),
            ('date_from', '<=', datetime(year, month, num_days, 23, 59, 59)),
            ('date_to', '>=', datetime(year, month, 1, 0, 0, 0)),
        ])

        # date -> accumulated fraction (paid + unpaid combined, capped at 1.0)
        leave_date_fractions = {}
        unpaid_leave_date_fractions = {}

        for leave in hr_leaves:
            date_from_utc = leave.date_from
            date_to_utc = leave.date_to

            if date_from_utc.tzinfo is None:
                date_from_utc = pytz.utc.localize(date_from_utc)
            if date_to_utc.tzinfo is None:
                date_to_utc = pytz.utc.localize(date_to_utc)

            date_from_local = date_from_utc.astimezone(tz).date()
            date_to_local = date_to_utc.astimezone(tz).date()

            # Clamp to the current month
            date_from_local = max(date_from_local, first_day)
            date_to_local = min(date_to_local, last_day)

            is_unpaid = bool(leave.holiday_status_id.unpaid)

            # Fraction this specific leave record contributes per date it touches.
            # Half-day leaves are always single-date (date_from == date_to), so
            # the fraction applies to that one date only. Multi-day leaves
            # (full-day) contribute 1.0 to every date in their range.
            record_fraction = 0.5 if leave.request_unit_half else 1.0

            current = date_from_local
            while current <= date_to_local:
                # Skip Sundays
                if current.weekday() == 6:
                    current = date.fromordinal(current.toordinal() + 1)
                    continue
                # Skip holidays and 2nd/4th Saturdays
                if current in holiday_dates:
                    current = date.fromordinal(current.toordinal() + 1)
                    continue

                existing = leave_date_fractions.get(current, 0.0)
                # Cap at 1.0 — two half-day leaves (AM + PM) on the same date
                # should combine to a full day, never exceed it.
                leave_date_fractions[current] = min(1.0, existing + record_fraction)

                if is_unpaid:
                    existing_unpaid = unpaid_leave_date_fractions.get(current, 0.0)
                    unpaid_leave_date_fractions[current] = min(
                        1.0, existing_unpaid + record_fraction
                    )

                current = date.fromordinal(current.toordinal() + 1)

        # Intersect with working days only, and split paid vs unpaid
        leave_days_total = 0.0
        unpaid_leave_days_total = 0.0

        for d, fraction in leave_date_fractions.items():
            if d not in working_day_dates:
                continue
            unpaid_fraction = unpaid_leave_date_fractions.get(d, 0.0)
            paid_fraction = fraction - unpaid_fraction
            leave_days_total += paid_fraction
            unpaid_leave_days_total += unpaid_fraction

        return leave_days_total, unpaid_leave_days_total, leave_date_fractions

    # ------------------------------------------------------------------
    # CRON
    # ------------------------------------------------------------------

    @api.model
    def _cron_generate_monthly_summary(self):
        """
        Runs on the 1st of each month.
        Generates (or recomputes draft) summary for the PREVIOUS month
        for all active employees.
        """
        today = date.today()

        if today.month == 1:
            target_month = 12
            target_year = today.year - 1
        else:
            target_month = today.month - 1
            target_year = today.year

        active_employees = self.env['hr.employee'].search([('active', '=', True)])

        for employee in active_employees:
            existing = self.search([
                ('employee_id', '=', employee.id),
                ('month', '=', str(target_month)),
                ('year', '=', target_year),
            ], limit=1)

            if existing:
                if existing.state == 'draft':
                    existing._compute_summary()
                # Confirmed records are never overwritten
            else:
                new_record = self.create({
                    'employee_id': employee.id,
                    'month': str(target_month),
                    'year': target_year,
                    'state': 'draft',
                })
                new_record._compute_summary()
