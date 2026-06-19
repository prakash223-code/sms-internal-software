# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import pytz
from datetime import datetime, time, date, timedelta


class WelcomeDashboard(models.TransientModel):
    _name = 'welcome.dashboard'
    _description = 'Welcome Dashboard'
    _rec_name = 'name'

    # ------------------------------------------------------------------
    # FIELDS
    # ------------------------------------------------------------------

    name = fields.Char(default='Welcome', readonly=True)

    # Greeting
    greeting_full = fields.Char(readonly=True)
    today_label   = fields.Char(readonly=True)

    # Quote
    quote_text   = fields.Text(readonly=True)
    quote_author = fields.Char(readonly=True)

    # Employee
    employee_id = fields.Many2one('hr.employee', readonly=True)

    # Attendance state
    status = fields.Selection([
        ('out',         'Not Checked In'),
        ('in',          'Checked In'),
        ('done',        'All Done Today'),
        ('holiday',     'Holiday Today'),
        ('no_employee', 'No Employee Linked'),
    ], readonly=True)

    last_check_in  = fields.Datetime(readonly=True)
    last_check_out = fields.Datetime(readonly=True)
    is_late        = fields.Boolean(readonly=True)
    late_minutes   = fields.Integer(readonly=True)
    holiday_name   = fields.Char(readonly=True)

    # ------------------------------------------------------------------
    # WEEKLY SUMMARY FIELDS
    # ------------------------------------------------------------------

    week_present_days = fields.Integer(
        string='Days Present (Week)',
        readonly=True,
        help='Number of distinct days the employee checked in this week (Mon–today).',
    )
    week_working_days = fields.Integer(
        string='Working Days (Week)',
        readonly=True,
        help='Total working days for the full week Mon–Sat (excludes holidays, '
             '2nd/4th Saturdays, and Sundays).',
    )
    week_hours = fields.Float(
        string='Hours Logged (Week)',
        readonly=True,
        digits=(6, 1),
        help='Total worked hours from Monday to today.',
    )
    week_late_count = fields.Integer(
        string='Late Arrivals (Week)',
        readonly=True,
    )

    # ------------------------------------------------------------------
    # ANNOUNCEMENT FIELDS
    # ------------------------------------------------------------------

    announcement_ids = fields.Many2many(
        'company.announcement',
        string='Announcements',
        readonly=True,
    )

    # ------------------------------------------------------------------
    # DEFAULT GET
    # ------------------------------------------------------------------

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        res['name'] = 'Welcome'

        # ── 1. Quote of the day ────────────────────────────────────────
        quotes = self.env['welcome.quote'].search([('active', '=', True)])
        if quotes:
            idx = date.today().toordinal() % len(quotes)
            q = quotes[idx]
            res['quote_text'] = q.text
            # Show  "குறள் #42"  in the author slot
            res['quote_author'] = f'"குறள் #{q.kural_number}'

        # ── 2. Greeting ────────────────────────────────────────────────
        ist      = pytz.timezone('Asia/Kolkata')
        now_ist  = datetime.now(ist)
        hour     = now_ist.hour

        if 5 <= hour < 12:
            salutation = 'Good Morning'
        elif 12 <= hour < 17:
            salutation = 'Good Afternoon'
        else:
            salutation = 'Good Evening'

        res['today_label'] = now_ist.strftime('%A, %d %B %Y')

        # ── 3. Employee lookup ─────────────────────────────────────────
        employee = self.env['hr.employee'].search(
            [('user_id', '=', self.env.uid)], limit=1
        )
        if not employee:
            res['greeting_full'] = f'{salutation}!'
            res['status']        = 'no_employee'
            self._load_announcements(res)
            return res

        first_name = employee.name.split()[0] if employee.name else employee.name
        res['greeting_full'] = f'{salutation}, {first_name}!'
        res['employee_id']   = employee.id

        # ── 4. Timezone helpers ────────────────────────────────────────
        tz_name = employee.tz or 'Asia/Kolkata'
        try:
            tz = pytz.timezone(tz_name)
        except pytz.UnknownTimeZoneError:
            tz = pytz.timezone('Asia/Kolkata')

        now_utc     = pytz.utc.localize(fields.Datetime.now())
        today_local = now_utc.astimezone(tz).date()

        # ── 5. Weekly summary ──────────────────────────────────────────
        self._compute_weekly_stats(res, employee, today_local, tz)

        # ── 6. Open attendance session? ────────────────────────────────
        Attendance   = self.env['hr.attendance'].sudo()
        open_session = Attendance.search([
            ('employee_id', '=', employee.id),
            ('check_out',   '=', False),
        ], limit=1)

        if open_session:
            res['status']        = 'in'
            res['last_check_in'] = open_session.check_in
            res['is_late']       = open_session.is_late
            res['late_minutes']  = open_session.late_minutes
            self._load_announcements(res)
            return res

        # ── 7. Holiday check ───────────────────────────────────────────
        Holiday = self.env['company.holiday'].sudo()
        if Holiday.is_holiday(today_local):
            res['status']       = 'holiday'
            res['holiday_name'] = (
                self.env['hr.attendance'].sudo()._get_holiday_name(today_local)
            )
            self._load_announcements(res)
            return res

        # ── 8. Already completed today? ────────────────────────────────
        today_start_utc = tz.localize(
            datetime.combine(today_local, time(0, 0, 0))
        ).astimezone(pytz.utc).replace(tzinfo=None)
        today_end_utc   = tz.localize(
            datetime.combine(today_local, time(23, 59, 59))
        ).astimezone(pytz.utc).replace(tzinfo=None)

        completed = Attendance.search([
            ('employee_id', '=', employee.id),
            ('check_in',    '>=', today_start_utc),
            ('check_in',    '<=', today_end_utc),
            ('check_out',   '!=', False),
        ], limit=1, order='check_in desc')

        if completed:
            res['status']        = 'done'
            res['last_check_in']  = completed.check_in
            res['last_check_out'] = completed.check_out
            res['is_late']        = completed.is_late
            res['late_minutes']   = completed.late_minutes
            self._load_announcements(res)
            return res

        # ── 9. Free to check in ────────────────────────────────────────
        res['status'] = 'out'
        self._load_announcements(res)
        return res

    # ------------------------------------------------------------------
    # WEEKLY STATS HELPER
    # ------------------------------------------------------------------

    def _compute_weekly_stats(self, res, employee, today_local, tz):
        """
        Populates week_present_days, week_working_days, week_hours,
        and week_late_count in the result dict.

        Attendance range : Monday 00:00 → today 23:59 (employee local time).
        Working days     : Full week Monday → Saturday, excluding Sundays,
                           2nd/4th Saturdays, and declared company holidays.
                           This gives the correct denominator regardless of
                           which day of the week it currently is.
        """
        # Monday of the current week
        days_since_monday = today_local.weekday()   # 0 = Monday
        week_start_local  = today_local - timedelta(days=days_since_monday)

        # End of the working week = Saturday (weekday 5)
        week_end_local = week_start_local + timedelta(days=5)

        # ── Attendance query: Mon → today only ─────────────────────────
        week_start_utc = tz.localize(
            datetime.combine(week_start_local, time(0, 0, 0))
        ).astimezone(pytz.utc).replace(tzinfo=None)

        today_end_utc = tz.localize(
            datetime.combine(today_local, time(23, 59, 59))
        ).astimezone(pytz.utc).replace(tzinfo=None)

        Attendance = self.env['hr.attendance'].sudo()
        week_atts  = Attendance.search([
            ('employee_id', '=', employee.id),
            ('check_in',    '>=', week_start_utc),
            ('check_in',    '<=', today_end_utc),
        ])

        present_dates  = set()
        total_hours    = 0.0
        late_count     = 0

        now_utc_naive = datetime.utcnow()

        for att in week_atts:
            ci = att.check_in
            if ci.tzinfo is None:
                ci = pytz.utc.localize(ci)
            local_date = ci.astimezone(tz).date()
            present_dates.add(local_date)

            if att.check_out:
                total_hours += att.worked_hours or 0.0
            else:
                # Open session — count hours up to now
                delta = now_utc_naive - att.check_in.replace(tzinfo=None)
                total_hours += delta.total_seconds() / 3600.0

            if att.is_late:
                late_count += 1

        # ── Working days: full week Mon → Sat ──────────────────────────
        # Uses the same holiday logic as the monthly summary so 2nd/4th
        # Saturdays and declared holidays are automatically excluded.
        Holiday = self.env['company.holiday'].sudo()
        working_days = 0
        cursor = week_start_local
        while cursor <= week_end_local:
            # Sunday is never a working day
            if cursor.weekday() == 6:
                cursor += timedelta(days=1)
                continue
            # Skip 2nd/4th Saturdays and declared holidays
            if Holiday.is_holiday(cursor):
                cursor += timedelta(days=1)
                continue
            working_days += 1
            cursor += timedelta(days=1)

        res['week_present_days'] = len(present_dates)
        res['week_working_days'] = working_days
        res['week_hours']        = round(total_hours, 1)
        res['week_late_count']   = late_count

    # ------------------------------------------------------------------
    # ANNOUNCEMENTS HELPER
    # ------------------------------------------------------------------

    def _load_announcements(self, res):
        """
        Fetches up to 4 active announcements (pinned first, then newest).
        """
        announcements = self.env['company.announcement'].sudo().search(
            [('active', '=', True)],
            order='is_pinned desc, date desc',
            limit=4,
        )
        res['announcement_ids'] = [(6, 0, announcements.ids)]

    # ------------------------------------------------------------------
    # TOGGLE ACTION
    # ------------------------------------------------------------------

    def action_toggle(self):
        self.ensure_one()
        try:
            self.env['hr.attendance'].sudo().action_toggle_attendance()
        except UserError:
            raise

        return {
            'type':       'ir.actions.act_window',
            'res_model':  'welcome.dashboard',
            'view_mode':  'form',
            'target':     'main',
            'name':       'Welcome',
        }

    # ------------------------------------------------------------------
    # QUICK NAV
    # ------------------------------------------------------------------

    def action_view_my_attendance(self):
        return self.env['ir.actions.actions']._for_xml_id('custom_attendance.action_my_attendance')

    def action_view_my_leaves(self):
        return self.env['ir.actions.actions']._for_xml_id('hr_holidays.hr_leave_action_my')

    def action_view_payslips(self):
        # Works when hr_payroll is installed; gracefully returns False if not.
        try:
            return self.env['ir.actions.actions']._for_xml_id('hr_payroll.action_hr_payslip_my_list')
        except Exception:
            return False

    def action_view_my_profile(self):
        employee = self.env['hr.employee'].search(
            [('user_id', '=', self.env.uid)], limit=1
        )
        if not employee:
            return False
        return {
            'type':      'ir.actions.act_window',
            'res_model': 'hr.employee',
            'res_id':    employee.id,
            'view_mode': 'form',
            'target':    'current',
        }

    def action_view_my_monthly_summary(self):
        return self.env['ir.actions.actions']._for_xml_id(
            'custom_attendance.action_monthly_summary_employee'
        )