# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import pytz
import calendar
from datetime import datetime, time


class CustomAttendance(models.Model):
    _inherit = 'hr.attendance'

    is_late = fields.Boolean(
        string='Late Entry',
        default=False,
        readonly=True,
        store=True,
        compute='_compute_is_late',
    )

    late_minutes = fields.Integer(
        string='Late By (Minutes)',
        compute='_compute_is_late',
        store=True,
        readonly=True,
    )

    auto_checkout = fields.Boolean(
        string='Auto Checkout Applied',
        default=False,
        readonly=True,
        help='Set to True if checkout was done automatically by the system cron.',
    )

    permission_overflow_minutes = fields.Integer(
        string='Permission Overflow (Minutes)',
        default=0,
        readonly=True,
        help='Late minutes that could not be covered by the Permission '
             'pool (manual request + auto-deduction combined). Feeds '
             'the payroll salary-deduction rule.',
    )

    # ------------------------------------------------------------------
    # COMPUTE: Late detection (timezone-aware)
    # ------------------------------------------------------------------

    @api.depends('check_in', 'employee_id')
    def _compute_is_late(self):
        LATE_HOUR = 9
        LATE_MINUTE = 30  # After 09:30 AM = late

        for record in self:
            if not record.check_in or not record.employee_id:
                record.is_late = False
                record.late_minutes = 0
                continue

            tz_name = record.employee_id.tz or 'Asia/Kolkata'
            try:
                tz = pytz.timezone(tz_name)
            except pytz.UnknownTimeZoneError:
                tz = pytz.timezone('Asia/Kolkata')

            check_in_utc = record.check_in
            if check_in_utc.tzinfo is None:
                check_in_utc = pytz.utc.localize(check_in_utc)

            check_in_local = check_in_utc.astimezone(tz)

            late_threshold = tz.localize(
                datetime.combine(check_in_local.date(), time(LATE_HOUR, LATE_MINUTE))
            )

            if check_in_local > late_threshold:
                record.is_late = True
                delta = check_in_local - late_threshold
                record.late_minutes = int(delta.total_seconds() // 60)
            else:
                record.is_late = False
                record.late_minutes = 0

    # ------------------------------------------------------------------
    # CONSTRAINTS
    # ------------------------------------------------------------------

    @api.constrains('check_in', 'check_out', 'employee_id')
    def _check_no_future_attendance(self):
        now = fields.Datetime.now()
        for record in self:
            if record.check_in and record.check_in > now:
                raise ValidationError(_('Check-in time cannot be in the future.'))
            if record.check_out and record.check_out > now:
                raise ValidationError(_('Check-out time cannot be in the future.'))

    @api.constrains('check_in', 'check_out')
    def _check_checkout_after_checkin(self):
        for record in self:
            if record.check_in and record.check_out:
                if record.check_out < record.check_in:
                    raise ValidationError(_('Check-out time must be after check-in time.'))

    # ------------------------------------------------------------------
    # TOGGLE ACTION (single entry point for employee check-in / check-out)
    # ------------------------------------------------------------------

    def action_toggle_attendance(self):
        """
        Single entry point for employee check-in / check-out.
        Rules:
          - If today is a company holiday or 2nd/4th Saturday → block check-in.
          - If open session exists → check out.
          - If no open session → check in, only if no completed session exists today.
        """
        employee = self._get_current_employee()
        if not employee:
            raise UserError(_(
                'No employee record is linked to your user account. '
                'Please contact HR or the system administrator.'
            ))

        now = fields.Datetime.now()

        # ── Resolve employee local date ────────────────────────────────
        tz_name = employee.tz or 'Asia/Kolkata'
        try:
            tz = pytz.timezone(tz_name)
        except pytz.UnknownTimeZoneError:
            tz = pytz.timezone('Asia/Kolkata')

        now_utc = pytz.utc.localize(now)
        today_local = now_utc.astimezone(tz).date()

        # ── HOLIDAY CHECK — block check-in only, allow check-out ──────
        open_attendance = self._get_open_session(employee)

        if not open_attendance:
            # Only block check-in, not check-out (employee already inside)
            Holiday = self.env['company.holiday'].sudo()
            if Holiday.is_holiday(today_local):
                # Build a friendly message explaining WHY it's a holiday
                holiday_name = self._get_holiday_name(today_local)
                raise UserError(_(
                    'Check-in is not allowed today.\n\n'
                    'Reason: %s\n\n'
                    'Enjoy your day off!'
                ) % holiday_name)

        if open_attendance:
            # ── CHECKOUT ──────────────────────────────────────────────
            open_attendance.write({'check_out': now})
            return {
                'status': 'checked_out',
                'check_out': now,
                'employee': employee.name,
                'is_late': open_attendance.is_late,
                'late_minutes': open_attendance.late_minutes,
            }

        # ── PRE-CHECKIN: block if already completed a cycle today ──────
        today_start_utc = tz.localize(
            datetime.combine(today_local, time(0, 0, 0))
        ).astimezone(pytz.utc).replace(tzinfo=None)

        today_end_utc = tz.localize(
            datetime.combine(today_local, time(23, 59, 59))
        ).astimezone(pytz.utc).replace(tzinfo=None)

        completed_today = self.search([
            ('employee_id', '=', employee.id),
            ('check_in', '>=', today_start_utc),
            ('check_in', '<=', today_end_utc),
            ('check_out', '!=', False),
        ], limit=1)

        if completed_today:
            raise UserError(_(
                'You have already completed your attendance for today. '
                'Check-in is allowed only once per day.'
            ))

        # ── CHECKIN ───────────────────────────────────────────────────
        new_record = self.create({
            'employee_id': employee.id,
            'check_in': now,
        })
        new_record._apply_permission_deduction()

        return {
            'status': 'checked_in',
            'check_in': now,
            'employee': employee.name,
            'attendance_id': new_record.id,
        }

    # ------------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------------

    def _get_holiday_name(self, check_date):
        """
        Returns a human-readable reason string for why today is a holiday.
        Covers declared holidays and 2nd/4th Saturday rule.
        """
        from datetime import date as date_type
        from odoo.addons.custom_attendance.models.company_holiday import CompanyHoliday

        # 2nd / 4th Saturday check
        if check_date.weekday() == 5:
            from odoo.addons.custom_attendance.models.company_holiday import CompanyHoliday as CH
            occ = CH._saturday_occurrence(check_date)
            if occ in (2, 4):
                ordinal = {2: '2nd', 4: '4th'}.get(occ, str(occ))
                return f'{ordinal} Saturday — Weekly Off'

        # Declared holiday record
        holiday = self.env['company.holiday'].sudo().search([
            ('date', '=', check_date),
            ('active', '=', True),
        ], limit=1)
        if holiday:
            return f'{holiday.name} ({dict(self.env["company.holiday"]._fields["holiday_type"].selection).get(holiday.holiday_type, "")})'

        return 'Company Holiday'

    def _get_current_employee(self):
        return self.env['hr.employee'].search(
            [('user_id', '=', self.env.uid)], limit=1
        )

    def _get_open_session(self, employee):
        """Return the open (no check_out) attendance record for an employee, if any."""
        return self.search([
            ('employee_id', '=', employee.id),
            ('check_out', '=', False),
        ], limit=1)

    # ------------------------------------------------------------------
    # CRON: Auto checkout at 19:00 employee local time
    # ------------------------------------------------------------------

    @api.model
    def _cron_auto_checkout(self):
        """
        Runs daily. Finds all open sessions and closes them at 19:00
        in the employee's local timezone.
        """
        open_sessions = self.search([('check_out', '=', False)])

        for attendance in open_sessions:
            tz_name = attendance.employee_id.tz or 'Asia/Kolkata'
            try:
                tz = pytz.timezone(tz_name)
            except pytz.UnknownTimeZoneError:
                tz = pytz.timezone('Asia/Kolkata')

            check_in_utc = attendance.check_in
            if check_in_utc.tzinfo is None:
                check_in_utc = pytz.utc.localize(check_in_utc)

            check_in_local = check_in_utc.astimezone(tz)
            auto_checkout_local = tz.localize(
                datetime.combine(check_in_local.date(), time(19, 0))
            )
            auto_checkout_utc = auto_checkout_local.astimezone(pytz.utc).replace(tzinfo=None)

            now_utc = fields.Datetime.now()
            if now_utc >= auto_checkout_utc:
                attendance.write({
                    'check_out': auto_checkout_utc,
                    'auto_checkout': True,
                })

    # ------------------------------------------------------------------
    # UTILITY: get present days / late days for monthly summary
    # ------------------------------------------------------------------

    @api.model
    def get_present_days(self, employee_id, year, month):
        import calendar
        from datetime import date

        first_day = datetime(year, month, 1, 0, 0, 0)
        last_day_num = calendar.monthrange(year, month)[1]
        last_day = datetime(year, month, last_day_num, 23, 59, 59)

        attendances = self.search_read(
            domain=[
                ('employee_id', '=', employee_id),
                ('check_in', '>=', first_day),
                ('check_in', '<=', last_day),
            ],
            fields=['check_in', 'employee_id'],
        )

        employee = self.env['hr.employee'].browse(employee_id)
        tz_name = employee.tz or 'Asia/Kolkata'
        try:
            tz = pytz.timezone(tz_name)
        except pytz.UnknownTimeZoneError:
            tz = pytz.timezone('Asia/Kolkata')

        present_dates = set()
        for att in attendances:
            check_in_utc = att['check_in']
            if check_in_utc.tzinfo is None:
                check_in_utc = pytz.utc.localize(check_in_utc)
            local_date = check_in_utc.astimezone(tz).date()

            if local_date.weekday() != 6:  # exclude Sundays
                present_dates.add(local_date)

        return present_dates

    @api.model
    def get_late_days(self, employee_id, year, month):
        import calendar

        first_day = datetime(year, month, 1, 0, 0, 0)
        last_day_num = calendar.monthrange(year, month)[1]
        last_day = datetime(year, month, last_day_num, 23, 59, 59)

        return self.search_count([
            ('employee_id', '=', employee_id),
            ('check_in', '>=', first_day),
            ('check_in', '<=', last_day),
            ('is_late', '=', True),
        ])

    @api.model
    def get_permission_overflow_minutes(self, employee_id, year, month):
        """Sum of permission_overflow_minutes across all attendance
        records in the given month — feeds the monthly summary, which
        in turn feeds the payroll deduction."""
        first_day = datetime(year, month, 1, 0, 0, 0)
        last_day_num = calendar.monthrange(year, month)[1]
        last_day = datetime(year, month, last_day_num, 23, 59, 59)

        records = self.search([
            ('employee_id', '=', employee_id),
            ('check_in', '>=', first_day),
            ('check_in', '<=', last_day),
        ])
        return sum(records.mapped('permission_overflow_minutes'))
