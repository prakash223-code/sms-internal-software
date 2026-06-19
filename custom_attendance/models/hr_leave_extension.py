# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import timedelta
import pytz


class HrLeave(models.Model):
    _inherit = 'hr.leave'

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
            date_to   = leave.date_to

            if date_from.tzinfo is None:
                date_from = pytz.utc.localize(date_from)
            if date_to.tzinfo is None:
                date_to = pytz.utc.localize(date_to)

            date_from_local = date_from.astimezone(tz).date()
            date_to_local   = date_to.astimezone(tz).date()

            # Walk each day in the requested range
            holiday_days       = []
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

    @staticmethod
    def _day_name(d):
        return ['Monday', 'Tuesday', 'Wednesday', 'Thursday',
                'Friday', 'Saturday', 'Sunday'][d.weekday()]