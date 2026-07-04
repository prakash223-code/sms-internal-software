# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from dateutil.relativedelta import relativedelta
from datetime import date
import logging

_logger = logging.getLogger(__name__)

PERMISSION_XMLID = 'custom_attendance.leave_type_permission'
PERMISSION_MINUTES = 240  # 4 hours, flat, no carry-forward


class HrEmployeePermissionPolicy(models.Model):
    _inherit = 'hr.employee'

    @api.model
    def _cron_generate_monthly_permission_allocation(self):
        """
        Runs on the 1st of each month. Grants a flat 240-minute (4hr)
        Permission allocation to every active employee for the current
        calendar month.

        No carry-forward — every employee gets exactly 240 fresh minutes,
        every month, including mid-month joiners (full 240, no proration)
        and employees who were on leave the previous month (still full
        240 this month).

        number_of_days is computed dynamically per employee using their
        resource_calendar_id.hours_per_day, so the "4 hours" display stays
        correct regardless of calendar configuration (confirmed via shell:
        4 / 9.0 hours_per_day = 0.4444... days -> displays as 4.0 hours).
        """
        leave_type = self._get_permission_leave_type()
        if not leave_type:
            _logger.warning(
                'Permission allocation: leave type not found (%s) — cron skipped.',
                PERMISSION_XMLID
            )
            return

        today = date.today()
        month_start = today.replace(day=1)
        month_end = month_start + relativedelta(months=1) - relativedelta(days=1)

        Allocation = self.env['hr.leave.allocation'].sudo()
        employees = self.search([('active', '=', True)])

        created = 0
        for employee in employees:
            # Idempotency guard — safe to re-run the cron without double-granting
            existing = Allocation.search([
                ('employee_id', '=', employee.id),
                ('holiday_status_id', '=', leave_type.id),
                ('date_from', '=', month_start),
            ], limit=1)
            if existing:
                continue

            hours_per_day = employee.resource_calendar_id.hours_per_day or 8.0
            number_of_days = (PERMISSION_MINUTES / 60.0) / hours_per_day

            Allocation.create({
                'name': f'Permission — {month_start.strftime("%B %Y")}',
                'employee_id': employee.id,
                'holiday_status_id': leave_type.id,
                'number_of_days': number_of_days,
                'date_from': month_start,
                'date_to': month_end,
                'state': 'confirm',
            })
            created += 1

        _logger.info(
            'Permission allocation: granted %s min (%.4f days) to %d employee(s) for %s',
            PERMISSION_MINUTES, number_of_days if created else 0, created,
            month_start.strftime('%B %Y')
        )

    @api.model
    def _get_permission_leave_type(self):
        try:
            return self.env.ref(PERMISSION_XMLID)
        except Exception:
            return False