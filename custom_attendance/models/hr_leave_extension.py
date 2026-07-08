# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import timedelta
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
                # Auto-generated Permission deductions (late-arrival buffer)
                # are never employee-submitted requests, so the standard
                # "Your time off request has been approved" notification is
                # misleading here — skip it. A dedicated late-arrival
                # notification is handled separately in permission_deduction.py
                # (_notify_permission_low / _notify_permission_exhausted).
                if leave.is_auto_permission:
                    continue
                if new_state == 'validate':
                    leave.sudo()._notify_leave_decision('approved')
                elif new_state == 'refuse':
                    leave.sudo()._notify_leave_decision('refused')

        return res

    # ------------------------------------------------------------------
    # NOTIFICATION HELPERS
    # ------------------------------------------------------------------

    def _get_leave_notification_recipients(self):
        """HR group users + employees with employee_role = 'manager'.
        Excludes the requesting employee themselves."""
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

        requester_user_id = self.employee_id.user_id.id
        all_users = (hr_users | manager_users).filtered(
            lambda u: u.id != requester_user_id
        )

        return all_users.mapped('partner_id')

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

    @api.constrains('date_from', 'date_to', 'state', 'employee_id',
                    'request_unit_half', 'request_date_from_period', 'request_date_to_period')
    def _check_no_overlapping_half_day_leave(self):
        for leave in self:
            if leave.state in ('refuse', 'cancel'):
                continue
            if not leave.date_from or not leave.date_to:
                continue

            # Find other active leaves for the same employee overlapping this date range
            others = self.search([
                ('id', '!=', leave.id),
                ('employee_id', '=', leave.employee_id.id),
                ('state', 'not in', ('refuse', 'cancel')),
                ('date_from', '<=', leave.date_to),
                ('date_to', '>=', leave.date_from),
            ])

            for other in others:
                if leave.request_unit_half and other.request_unit_half:
                    # Both half-day — only a conflict if same period (am/am or pm/pm)
                    # on the same calendar date
                    if (leave.request_date_from_period == other.request_date_from_period
                            and leave.date_from.date() == other.date_from.date()):
                        raise ValidationError(_(
                            'This half-day leave conflicts with an existing '
                            'leave request for %s on %s (%s).'
                        ) % (leave.employee_id.name, leave.date_from.date(),
                             dict(leave._fields['request_date_from_period'].selection).get(
                                 leave.request_date_from_period)))
                else:
                    # At least one is a full-day leave — any date overlap is a conflict
                    raise ValidationError(_(
                        'This leave request overlaps with an existing leave for '
                        '%s between %s and %s.'
                    ) % (leave.employee_id.name, other.date_from.date(), other.date_to.date()))
