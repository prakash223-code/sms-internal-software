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

    leave_days = fields.Integer(
        string='Approved Leave Days',
        readonly=True,
        default=0,
        help='Approved paid leaves intersected with working days. Does not count as absent.',
    )

    unpaid_leave_days = fields.Integer(
        string='Unpaid Leave Days',
        readonly=True,
        default=0,
        help='Approved unpaid leaves — counted in salary deduction.',
    )

    absent_days = fields.Integer(
        string='Absent Days',
        readonly=True,
        default=0,
        help='working_days - present_days - leave_days',
    )

    unpaid_absent_days = fields.Integer(
        string='Unpaid Absent Days',
        readonly=True,
        default=0,
        help='absent_days + unpaid_leave_days — used for payroll deduction.',
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

        # --- 4. Leave days ---
        leave_days_count, unpaid_leave_days_count, leave_date_set = \
            self._get_leave_data(employee, year, month, working_day_dates, tz)

        # --- 5. Absent days ---
        effective_present = present_date_set & working_day_dates
        effective_leave = leave_date_set & working_day_dates
        covered_days = effective_present | effective_leave
        absent_date_set = working_day_dates - covered_days
        absent_days_count = len(absent_date_set)

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
        num_days   = calendar.monthrange(year, month)[1]
        date_from  = date(year, month, 1)
        date_to    = date(year, month, num_days)

        # Fetch all holidays for the month (declared + 2nd/4th Saturdays)
        holiday_dates = self.env['company.holiday'].get_holidays_in_range(
            date_from, date_to
        )

        working_dates = set()
        for day in range(1, num_days + 1):
            d = date(year, month, day)
            if d.weekday() == 6:        # Sunday — always off
                continue
            if d in holiday_dates:      # declared holiday or 2nd/4th Saturday
                continue
            working_dates.add(d)

        return working_dates

    def _get_leave_data(self, employee, year, month, working_day_dates, tz):
        """
        Returns:
            leave_days_count     : approved paid leave days on working days
            unpaid_leave_days    : approved unpaid leave days on working days
            leave_date_set       : full set of dates covered by any approved leave
                                   (used upstream to subtract from absent calculation)

        Holiday-aware: days that fall on a company holiday or 2nd/4th Saturday
        are excluded from leave consumption — the employee should not lose a
        leave day for a day that was already a holiday.
        """
        num_days  = calendar.monthrange(year, month)[1]
        first_day = date(year, month, 1)
        last_day  = date(year, month, num_days)

        # Fetch all holidays in the month once (declared + 2nd/4th Saturdays)
        holiday_dates = self.env['company.holiday'].get_holidays_in_range(
            first_day, last_day
        )

        hr_leaves = self.env['hr.leave'].search([
            ('employee_id', '=', employee.id),
            ('state',       '=', 'validate'),
            ('date_from',   '<=', datetime(year, month, num_days, 23, 59, 59)),
            ('date_to',     '>=', datetime(year, month, 1, 0, 0, 0)),
        ])

        leave_date_set        = set()
        unpaid_leave_date_set = set()

        for leave in hr_leaves:
            date_from_utc = leave.date_from
            date_to_utc   = leave.date_to

            if date_from_utc.tzinfo is None:
                date_from_utc = pytz.utc.localize(date_from_utc)
            if date_to_utc.tzinfo is None:
                date_to_utc = pytz.utc.localize(date_to_utc)

            date_from_local = date_from_utc.astimezone(tz).date()
            date_to_local   = date_to_utc.astimezone(tz).date()

            # Clamp to the current month
            date_from_local = max(date_from_local, first_day)
            date_to_local   = min(date_to_local,   last_day)

            is_unpaid = (
                'unpaid' in (leave.holiday_status_id.name or '').lower()
                or (leave.holiday_status_id.name or '').lower() in ('unpaid', 'unpaid leave')
            )

            current = date_from_local
            while current <= date_to_local:
                # Skip Sundays
                if current.weekday() == 6:
                    current = date.fromordinal(current.toordinal() + 1)
                    continue
                # Skip holidays and 2nd/4th Saturdays —
                # employee should not lose a leave day on an already-off day
                if current in holiday_dates:
                    current = date.fromordinal(current.toordinal() + 1)
                    continue
                leave_date_set.add(current)
                if is_unpaid:
                    unpaid_leave_date_set.add(current)
                current = date.fromordinal(current.toordinal() + 1)

        # Intersect with working days only
        leave_working        = leave_date_set        & working_day_dates
        unpaid_leave_working = unpaid_leave_date_set & working_day_dates
        paid_leave_working   = leave_working - unpaid_leave_working

        return len(paid_leave_working), len(unpaid_leave_working), leave_date_set

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
            target_year  = today.year - 1
        else:
            target_month = today.month - 1
            target_year  = today.year

        active_employees = self.env['hr.employee'].search([('active', '=', True)])

        for employee in active_employees:
            existing = self.search([
                ('employee_id', '=', employee.id),
                ('month',       '=', str(target_month)),
                ('year',        '=', target_year),
            ], limit=1)

            if existing:
                if existing.state == 'draft':
                    existing._compute_summary()
                # Confirmed records are never overwritten
            else:
                new_record = self.create({
                    'employee_id': employee.id,
                    'month':       str(target_month),
                    'year':        target_year,
                    'state':       'draft',
                })
                new_record._compute_summary()