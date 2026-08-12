# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from odoo.exceptions import ValidationError, UserError
from datetime import timedelta
from datetime import datetime, time
from markupsafe import Markup
import pytz


class HrLeave(models.Model):
    _inherit = 'hr.leave'

    is_auto_permission = fields.Boolean(
        string='Auto-Generated (Permission Deduction)',
        default=False,
        copy=False,
        help='True only for Permission leave records created automatically '
             'by a late check-in. Manual employee-submitted Permission '
             'requests are always False — this is how the double-deduction '
             'guard tells them apart.',
    )

    @api.constrains('date_from', 'state')
    def _check_no_past_leave_request(self):
        today = fields.Date.context_today(self)
        for leave in self:
            if leave.state in ('refuse', 'cancel'):
                continue
            if not leave.date_from:
                continue
            # HR and managers can backdate leaves
            if self.env.user.has_group('hr.group_hr_user'):
                continue
            leave_date = leave.date_from.date()
            if leave_date < today:
                raise ValidationError(_(
                    'Leave requests cannot be submitted for past dates (%s). '
                    'Please contact HR if you need to record a past leave.'
                ) % leave_date.strftime('%d %b %Y'))

    @api.constrains('date_from', 'date_to', 'state', 'employee_id')
    def _check_leave_against_company_holidays(self):
        Holiday = self.env['company.holiday'].sudo()

        for leave in self:
            # Only validate active leave requests
            if leave.state in ('refuse', 'cancel'):
                continue
            if not leave.date_from or not leave.date_to:
                continue

            # Convert UTC datetimes to employee local date
            tz_name = (leave.employee_id.tz or 'Asia/Kolkata')
            try:
                tz = pytz.timezone(tz_name)
            except pytz.UnknownTimeZoneError:
                tz = pytz.timezone('Asia/Kolkata')

            date_from = leave.date_from
            date_to = leave.date_to

            if date_from.tzinfo is None:
                date_from = pytz.utc.localize(date_from)
            if date_to.tzinfo is None:
                date_to = pytz.utc.localize(date_to)

            date_from_local = date_from.astimezone(tz).date()
            date_to_local = date_to.astimezone(tz).date()

            # Walk each day in the requested range
            holiday_days = []
            valid_working_days = []
            current = date_from_local

            while current <= date_to_local:
                if current.weekday() == 6:
                    # Sunday — skip, already a non-working day
                    current += timedelta(days=1)
                    continue

                if Holiday.is_holiday(current):
                    holiday_days.append(current)
                else:
                    valid_working_days.append(current)

                current += timedelta(days=1)

            # ── Block: ALL requested days are holidays ────────────────
            if holiday_days and not valid_working_days:
                day_list = '\n'.join(
                    f'  • {d.strftime("%d %b %Y")} ({self._day_name(d)})'
                    for d in holiday_days
                )
                raise ValidationError(_(
                    'Leave request blocked — all selected days are company holidays:\n\n'
                    '%s\n\n'
                    'Please select working days only.'
                ) % day_list)

    @api.model_create_multi
    def create(self, vals_list):
        leaves = super().create(vals_list)
        for leave in leaves:
            if leave.is_auto_permission:
                continue
            if leave.state in ('confirm', 'validate1'):
                leave.sudo()._notify_leave_request_submitted()
        return leaves

    def write(self, vals):
        old_states = {}
        if 'state' in vals:
            old_states = {leave.id: leave.state for leave in self}

        res = super().write(vals)

        if 'state' in vals:
            for leave in self:
                old_state = old_states.get(leave.id)
                new_state = leave.state
                if old_state == new_state:
                    continue
                if new_state == 'validate':
                    leave.sudo()._notify_leave_decision('approved')
                    leave.flush_recordset(['state'])
                    leave.sudo()._recompute_attendance_lateness_for_date()
                elif new_state == 'refuse':
                    leave.sudo()._notify_leave_decision('refused')
                    leave.flush_recordset(['state'])
                    leave.sudo()._recompute_attendance_lateness_for_date()

        return res

    def _recompute_attendance_lateness_for_date(self):
        self.ensure_one()
        if not self.request_unit_half or self.request_date_from_period != 'am':
            return
        if not self.date_from:
            return

        leave_date = self.date_from.date()

        Attendance = self.env['hr.attendance'].sudo()
        same_day_attendance = Attendance.search([
            ('employee_id', '=', self.employee_id.id),
            ('check_in', '>=', datetime.combine(leave_date, time(0, 0, 0))),
            ('check_in', '<=', datetime.combine(leave_date, time(23, 59, 59))),
        ])
        if not same_day_attendance:
            return

        same_day_attendance._compute_is_late()

        for attendance in same_day_attendance:
            attendance._apply_permission_deduction()

    WFH_XMLID = 'custom_attendance.leave_type_wfh'

    def _get_wfh_leave_type_id(self):
        try:
            return self.env.ref(self.WFH_XMLID).id
        except Exception:
            return False

    def _check_wfh_date_lock(self, action_label):
        """
        Blocks employees (non-HR/Manager) from editing or deleting a WFH
        record once its date has passed. HR and Manager (both covered by
        hr.group_hr_user) can always override — matches the same role
        pattern used throughout custom_attendance for HR/Manager exceptions.
        """
        wfh_type_id = self._get_wfh_leave_type_id()
        if not wfh_type_id or self.env.user.has_group('hr.group_hr_user'):
            return

        today = fields.Date.context_today(self)
        for leave in self:
            if (leave.holiday_status_id.id == wfh_type_id
                    and leave.date_from
                    and leave.date_from.date() < today):
                raise UserError(_(
                    "This Work From Home request is for %(date)s, which has already "
                    "passed, so it can no longer be %(action)s.\n\n"
                    "If something needs to change, please reach out to HR."
                ) % {
                                    'date': leave.date_from.date().strftime('%d %b %Y'),
                                    'action': action_label,
                                })

    def write(self, vals):
        self._check_wfh_date_lock('edited')
        return super().write(vals)

    def unlink(self):
        self._check_wfh_date_lock('deleted')
        return super().unlink()

    @api.depends('employee_id', 'leave_type_request_unit', 'request_date_from', 'request_date_to',
                 'request_hour_from', 'request_hour_to', 'request_date_from_period', 'request_date_to_period')
    def _compute_dashboard_warning_message(self):
        # Core Odoo computes the standard overlap-conflict message for every
        # leave type. allow_request_on_top=True on the WFH type (set in
        # leave_type_data.xml) already prevents WFH from appearing as a
        # "conflicting" candidate against OTHER leave requests — but it does
        # NOT prevent a *new* WFH request from being blocked by an existing
        # leave of another type, since the core search domain filters
        # candidates by their own allow_request_on_top, not by the type of
        # the record being validated. This override closes that gap: after
        # the core computation runs, force-clear the warning for any WFH
        # leave in this recordset, allowing it to coexist with CL/EL/ML/
        # Permission on the same dates in both directions.
        super(HrLeave, self)._compute_dashboard_warning_message()
        wfh_type_id = self._get_wfh_leave_type_id()
        if not wfh_type_id:
            return
        for holiday in self:
            if holiday.holiday_status_id.id == wfh_type_id:
                holiday.dashboard_warning_message = False

    # ------------------------------------------------------------------
    # NOTIFICATION HELPERS
    # ------------------------------------------------------------------

    def _get_leave_notification_recipients(self):
        """HR group users + employees with employee_role = 'manager'
        + the Team Lead(s) of the requesting employee's team(s).
        Excludes the requesting employee themselves.

        Team Leads are notification-only here — no ir.rule or access entry
        anywhere grants team.team leads write/approve access on hr.leave
        (see custom_attendance/security/*.xml and
        custom_project/security/record_rules.xml), so adding them as
        recipients cannot expand their rights."""
        self.ensure_one()

        hr_group = self.env.ref('hr.group_hr_user')
        hr_users = self.env['res.users'].sudo().search([
            ('group_ids', 'in', [hr_group.id]),
        ])

        manager_employees = self.env['hr.employee'].sudo().search([
            ('employee_role', '=', 'manager'),
            ('user_id', '!=', False),
            ('active', '=', True),
        ])
        manager_users = manager_employees.mapped('user_id')

        team_lead_users = self._get_team_lead_users()

        requester_user_id = self.employee_id.user_id.id
        all_users = (hr_users | manager_users | team_lead_users).filtered(
            lambda u: u.id != requester_user_id
        )

        return all_users.mapped('partner_id')

    def _get_team_lead_users(self):
        """Resolve the res.users of the Team Lead(s) of the requesting
        employee's team(s), via team.team (custom_project module).
        Returns an empty recordset if team.team isn't installed, the
        employee belongs to no team, or the employee IS the lead
        (avoid self-notification) — never raises."""
        self.ensure_one()
        if 'team.team' not in self.env:
            return self.env['res.users']

        employee = self.employee_id.sudo()
        teams = getattr(employee, 'team_ids', False)
        if not teams:
            return self.env['res.users']

        team_leads = teams.mapped('team_lead_id').filtered(
            lambda e: e.user_id and e != employee
        )
        return team_leads.mapped('user_id')

    def _notify_leave_request_submitted(self):
        self.ensure_one()
        recipients = self._get_leave_notification_recipients()
        if not recipients:
            return

        date_from = self.date_from.strftime('%d %b %Y') if self.date_from else ''
        date_to = self.date_to.strftime('%d %b %Y') if self.date_to else ''

        body = Markup(
            '<p><strong>%s</strong> has requested time off and is awaiting approval.</p>'
            '<ul>'
            '<li>Leave Type: %s</li>'
            '<li>From: %s</li>'
            '<li>To: %s</li>'
            '<li>Days: %s</li>'
            '</ul>'
        ) % (
                   self.employee_id.name,
                   self.holiday_status_id.name,
                   date_from,
                   date_to,
                   self.number_of_days,
               )

        self.message_notify(
            partner_ids=recipients.ids,
            subject=_('Time Off Request: %s') % self.employee_id.name,
            body=body,
            subtype_xmlid='mail.mt_comment',
        )

    def _notify_leave_decision(self, decision):
        self.ensure_one()
        partner = self.employee_id.user_id.partner_id
        if not partner:
            return

        date_from = self.date_from.strftime('%d %b %Y') if self.date_from else ''
        date_to = self.date_to.strftime('%d %b %Y') if self.date_to else ''

        if decision == 'approved':
            subject = _('Time Off Request Approved')
            status_label = 'approved'
        else:
            subject = _('Time Off Request Refused')
            status_label = 'refused'

        body = Markup(
            '<p>Your time off request has been <strong>%s</strong>.</p>'
            '<ul>'
            '<li>Leave Type: %s</li>'
            '<li>From: %s</li>'
            '<li>To: %s</li>'
            '</ul>'
        ) % (
                   status_label,
                   self.holiday_status_id.name,
                   date_from,
                   date_to,
               )

        self.message_notify(
            partner_ids=[partner.id],
            subject=subject,
            body=body,
            subtype_xmlid='mail.mt_comment',
        )

    @staticmethod
    def _day_name(d):
        return ['Monday', 'Tuesday', 'Wednesday', 'Thursday',
                'Friday', 'Saturday', 'Sunday'][d.weekday()]
