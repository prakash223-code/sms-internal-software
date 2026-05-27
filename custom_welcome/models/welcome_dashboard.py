# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import pytz
from datetime import datetime, time, date


class WelcomeDashboard(models.TransientModel):
    _name = 'welcome.dashboard'
    _description = 'Welcome Dashboard'

    # ------------------------------------------------------------------
    # FIELDS
    # ------------------------------------------------------------------

    # Greeting
    greeting_full = fields.Char(readonly=True)   # "Good Morning, Alex!"
    today_label   = fields.Char(readonly=True)   # "Wednesday, 28 May 2025"

    # Quote
    quote_text   = fields.Text(readonly=True)
    quote_author = fields.Char(readonly=True)

    # Employee (kept for Many2one widget rendering; hidden internally)
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
    # DEFAULT GET — populates every field on form open
    # ------------------------------------------------------------------

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        res['name'] = 'Welcome'

        # ── 1. Quote of the day (deterministic: same for all users today) ──
        quotes = self.env['welcome.quote'].search([('active', '=', True)])
        if quotes:
            idx = date.today().toordinal() % len(quotes)
            q = quotes[idx]
            res['quote_text']   = q.text
            res['quote_author'] = q.author

        # ── 2. Greeting (uses IST for label; employee tz used for attendance) ──
        ist = pytz.timezone('Asia/Kolkata')
        now_ist = datetime.now(ist)
        hour = now_ist.hour

        if 5 <= hour < 12:
            salutation = 'Good Morning'
        elif 12 <= hour < 17:
            salutation = 'Good Afternoon'
        else:
            salutation = 'Good Evening'

        res['today_label'] = now_ist.strftime('%A, %d %B %Y')

        # ── 3. Employee lookup ──
        employee = self.env['hr.employee'].search(
            [('user_id', '=', self.env.uid)], limit=1
        )
        if not employee:
            res['greeting_full'] = f'{salutation}!'
            res['status'] = 'no_employee'
            return res

        first_name = employee.name.split()[0] if employee.name else employee.name
        res['greeting_full'] = f'{salutation}, {first_name}!'
        res['employee_id'] = employee.id

        # ── 4. Timezone-aware "today" boundaries ──
        tz_name = employee.tz or 'Asia/Kolkata'
        try:
            tz = pytz.timezone(tz_name)
        except pytz.UnknownTimeZoneError:
            tz = pytz.timezone('Asia/Kolkata')

        now_utc     = pytz.utc.localize(fields.Datetime.now())
        today_local = now_utc.astimezone(tz).date()

        # ── 5. Open attendance session? ──
        Attendance = self.env['hr.attendance'].sudo()
        open_session = Attendance.search([
            ('employee_id', '=', employee.id),
            ('check_out',   '=', False),
        ], limit=1)

        if open_session:
            res['status']        = 'in'
            res['last_check_in'] = open_session.check_in
            res['is_late']       = open_session.is_late
            res['late_minutes']  = open_session.late_minutes
            return res

        # ── 6. Holiday check (only blocks check-in, not check-out) ──
        Holiday = self.env['company.holiday'].sudo()
        if Holiday.is_holiday(today_local):
            res['status']       = 'holiday'
            res['holiday_name'] = (
                self.env['hr.attendance'].sudo()._get_holiday_name(today_local)
            )
            return res

        # ── 7. Already completed a full cycle today? ──
        today_start_utc = tz.localize(
            datetime.combine(today_local, time(0, 0, 0))
        ).astimezone(pytz.utc).replace(tzinfo=None)
        today_end_utc = tz.localize(
            datetime.combine(today_local, time(23, 59, 59))
        ).astimezone(pytz.utc).replace(tzinfo=None)

        completed = Attendance.search([
            ('employee_id', '=', employee.id),
            ('check_in',    '>=', today_start_utc),
            ('check_in',    '<=', today_end_utc),
            ('check_out',   '!=', False),
        ], limit=1, order='check_in desc')

        if completed:
            res['status']         = 'done'
            res['last_check_in']  = completed.check_in
            res['last_check_out'] = completed.check_out
            res['is_late']        = completed.is_late
            res['late_minutes']   = completed.late_minutes
            return res

        # ── 8. Free to check in ──
        res['status'] = 'out'
        return res

    # ------------------------------------------------------------------
    # TOGGLE ACTION
    # ------------------------------------------------------------------

    def action_toggle(self):
        self.ensure_one()
        # sudo() keeps env.uid (the logged-in user) but bypasses ACL.
        # action_toggle_attendance() resolves the employee via env.uid internally.
        try:
            self.env['hr.attendance'].sudo().action_toggle_attendance()
        except UserError:
            raise

        # Reload the welcome dashboard so status refreshes
        return {
            'type':      'ir.actions.act_window',
            'res_model': 'welcome.dashboard',
            'view_mode': 'form',
            'target':    'main',
            'name':      'Welcome',
        }

    # ------------------------------------------------------------------
    # QUICK NAV — open full attendance view
    # ------------------------------------------------------------------

    def action_view_my_attendance(self):
        return self.env.ref('custom_attendance.action_my_attendance').read()[0]