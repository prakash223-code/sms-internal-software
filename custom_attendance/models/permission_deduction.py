# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from datetime import datetime, time
import pytz
import logging

_logger = logging.getLogger(__name__)

PERMISSION_XMLID = 'custom_attendance.leave_type_permission'
LATE_HOUR_THRESHOLD = 9.5  # 9:30 AM — matches attendance.py's late-detection threshold


class HrAttendancePermissionDeduction(models.Model):
    _inherit = 'hr.attendance'

    def _apply_permission_deduction(self):
        self.ensure_one()
        if not self.is_late or self.late_minutes <= 0:
            return

        leave_type = self._get_permission_leave_type()
        if not leave_type:
            _logger.warning(
                'Permission deduction: leave type not found — skipped for attendance %s',
                self.id
            )
            return

        employee = self.employee_id
        local_date = self._get_local_check_in_date()

        manual_minutes = self._get_manual_permission_minutes(employee, leave_type, local_date)
        excess_minutes = max(0, self.late_minutes - manual_minutes)

        if excess_minutes <= 0:
            self.permission_overflow_minutes = 0
            return

        excess_hours = excess_minutes / 60.0
        remaining_hours = self._get_permission_remaining_hours(employee, leave_type, local_date)

        EPSILON_HOURS = 0.001
        safe_remaining_hours = max(0.0, remaining_hours - EPSILON_HOURS)

        consumed_hours = min(excess_hours, safe_remaining_hours)
        overflow_minutes = round((excess_hours - consumed_hours) * 60)

        if consumed_hours > 0:
            # Auto block starts AFTER whatever the manual request already
            # covers, so the two never overlap in wall-clock time.
            auto_start_offset_hours = manual_minutes / 60.0
            self._create_auto_permission_leave(
                employee, leave_type, local_date, consumed_hours, auto_start_offset_hours
            )

        self.permission_overflow_minutes = overflow_minutes

        _logger.info(
            'Permission deduction: attendance %s — late=%s manual_covered=%s '
            'excess_hours=%.4f consumed_hours=%.4f overflow_min=%s',
            self.id, self.late_minutes, manual_minutes,
            excess_hours, consumed_hours, overflow_minutes
        )

        new_remaining = remaining_hours - consumed_hours
        if new_remaining <= 0:
            self._notify_permission_exhausted(employee)
        elif new_remaining * 60 <= 30:
            self._notify_permission_low(employee, round(new_remaining * 60))

    # ------------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------------

    def _get_permission_leave_type(self):
        try:
            return self.env.ref(PERMISSION_XMLID)
        except Exception:
            return False

    def _get_local_check_in_date(self):
        tz_name = self.employee_id.tz or 'Asia/Kolkata'
        try:
            tz = pytz.timezone(tz_name)
        except pytz.UnknownTimeZoneError:
            tz = pytz.timezone('Asia/Kolkata')
        check_in_utc = self.check_in
        if check_in_utc.tzinfo is None:
            check_in_utc = pytz.utc.localize(check_in_utc)
        return check_in_utc.astimezone(tz).date()

    def _get_manual_permission_minutes(self, employee, leave_type, local_date):
        """Sum of MANUAL (is_auto_permission=False) validated Permission
        leave covering local_date, converted to minutes."""
        Leave = self.env['hr.leave'].sudo()
        day_start = datetime.combine(local_date, time(0, 0, 0))
        day_end = datetime.combine(local_date, time(23, 59, 59))

        manual_leaves = Leave.search([
            ('employee_id', '=', employee.id),
            ('holiday_status_id', '=', leave_type.id),
            ('state', '=', 'validate'),
            ('is_auto_permission', '=', False),
            ('date_from', '<=', day_end),
            ('date_to', '>=', day_start),
        ])
        total_hours = sum(manual_leaves.mapped('number_of_hours'))
        return round(total_hours * 60)

    def _get_permission_remaining_hours(self, employee, leave_type, local_date):
        """Remaining balance in hours — kept as float, no premature rounding."""
        Allocation = self.env['hr.leave.allocation'].sudo()
        month_start = local_date.replace(day=1)

        allocation = Allocation.search([
            ('employee_id', '=', employee.id),
            ('holiday_status_id', '=', leave_type.id),
            ('date_from', '=', month_start),
        ], limit=1)

        if not allocation:
            return 0.0

        return max(0.0, allocation.virtual_remaining_leaves)

    def _create_auto_permission_leave(self, employee, leave_type, local_date, hours, start_offset_hours=0.0):
        """
        start_offset_hours shifts the block later than LATE_HOUR_THRESHOLD,
        so it lands immediately after any manual Permission request already
        covering the start of the late window — avoids the two overlapping
        in wall-clock time (Odoo's native _check_date rejects same-employee
        overlapping leave requests, confirmed via shell test).
        """
        Leave = self.env['hr.leave'].sudo()
        hour_from = LATE_HOUR_THRESHOLD + start_offset_hours
        hour_to = hour_from + hours

        leave = Leave.create({
            'employee_id': employee.id,
            'holiday_status_id': leave_type.id,
            'request_date_from': local_date,
            'request_date_to': local_date,
            'request_unit_hours': True,
            'request_hour_from': hour_from,
            'request_hour_to': hour_to,
            'is_auto_permission': True,
        })
        leave.action_approve()

        _logger.info(
            'Permission deduction: auto-created leave %s for %s — %.4f hrs '
            '(%.2f-%.2f) on %s',
            leave.id, employee.name, hours, hour_from, hour_to, local_date
        )
        return leave

    def _notify_permission_low(self, employee, remaining_minutes):
        from markupsafe import Markup
        if not employee.user_id:
            return
        body = Markup(
            '<p>Your <strong>Permission</strong> balance is running low: '
            '<strong>%s minutes remaining</strong> this month.</p>'
        ) % remaining_minutes
        self.message_notify(
            partner_ids=[employee.user_id.partner_id.id],
            subject=_('Permission Balance Low'),
            body=body,
            subtype_xmlid='mail.mt_comment',
        )

    def _notify_permission_exhausted(self, employee):
        from markupsafe import Markup
        if not employee.user_id:
            return
        body = Markup(
            '<p>Your <strong>Permission</strong> balance for this month is '
            '<strong>exhausted</strong>. Further late arrivals will be '
            'deducted from your salary.</p>'
        )
        self.message_notify(
            partner_ids=[employee.user_id.partner_id.id],
            subject=_('Permission Balance Exhausted'),
            body=body,
            subtype_xmlid='mail.mt_comment',
        )