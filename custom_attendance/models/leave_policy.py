# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from dateutil.relativedelta import relativedelta
from datetime import datetime, time
import logging

_logger = logging.getLogger(__name__)

# ── Annual leave policy ─────────────────────────────────────────────────
# code -> xmlid, annual quota, carry-forward cap
# CL carry-forward capped at 50% of quota (company policy).
# EL / ML carry forward in full — cap == quota, i.e. no extra ceiling.
LEAVE_POLICY = {
    'casual':  {'xmlid': 'custom_attendance.leave_type_casual',  'quota': 12.0, 'carry_cap': 6.0},
    'earned':  {'xmlid': 'custom_attendance.leave_type_earned',  'quota': 3.0,  'carry_cap': 3.0},
    'medical': {'xmlid': 'custom_attendance.leave_type_medical', 'quota': 3.0,  'carry_cap': 3.0},
}

# XML IDs of the three managed leave types — used in monthly_summary.py
# to identify whether a leave is within policy (paid vs unpaid distinction
# is handled via holiday_status_id.unpaid directly).
CL_EL_ML_XMLIDS = [p['xmlid'] for p in LEAVE_POLICY.values()]


def _is_leap_year(year):
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


class HrEmployeeLeavePolicy(models.Model):
    _inherit = 'hr.employee'

    # ------------------------------------------------------------------
    # INITIAL ALLOCATION — bootstraps current cycle, no carry-forward
    # (covers brand-new employees AND one-time backfill for existing ones)
    # ------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        employees = super().create(vals_list)
        employees._create_initial_leave_allocations()
        return employees

    def _create_initial_leave_allocations(self):
        Allocation = self.env['hr.leave.allocation'].sudo()
        today = fields.Date.context_today(self)

        for employee in self:
            join_date = self._get_join_date(employee)
            if not join_date:
                _logger.warning(
                    'Leave policy: no joining date resolved for %s — skipped', employee.name
                )
                continue

            cycle_start = self._get_current_cycle_start(join_date, today)

            for code, policy in LEAVE_POLICY.items():
                leave_type = self._get_leave_type(policy['xmlid'])
                if not leave_type:
                    continue

                existing = Allocation.search([
                    ('employee_id', '=', employee.id),
                    ('holiday_status_id', '=', leave_type.id),
                ], limit=1)
                if existing:
                    continue  # already has an allocation history — skip

                Allocation.create(self._allocation_vals(
                    employee, leave_type, cycle_start, policy['quota']
                ))
                _logger.info(
                    'Leave policy: initial allocation — %s — %s — %s days from %s',
                    employee.name, leave_type.name, policy['quota'], cycle_start,
                )

    # ------------------------------------------------------------------
    # CRON — anniversary carry-forward
    # ------------------------------------------------------------------

    @api.model
    def _cron_process_leave_anniversaries(self):
        """
        Runs daily. For every active employee whose joining-date month/day
        matches today, closes the previous leave-year and opens a new one
        with carry-forward applied per LEAVE_POLICY.
        """
        today = fields.Date.context_today(self)
        employees = self.search([('active', '=', True)])

        for employee in employees:
            join_date = self._get_join_date(employee)
            if not join_date:
                continue
            if not self._is_anniversary_today(join_date, today):
                continue
            employee._process_leave_carry_forward(today)

    def _process_leave_carry_forward(self, cycle_start):
        self.ensure_one()
        Allocation = self.env['hr.leave.allocation'].sudo()
        cycle_end_prev = cycle_start - relativedelta(days=1)

        for code, policy in LEAVE_POLICY.items():
            leave_type = self._get_leave_type(policy['xmlid'])
            if not leave_type:
                continue

            # Idempotency guard — don't double-process if cron runs twice
            already = Allocation.search([
                ('employee_id', '=', self.id),
                ('holiday_status_id', '=', leave_type.id),
                ('date_from', '=', cycle_start),
            ], limit=1)
            if already:
                continue

            prev_allocation = Allocation.search([
                ('employee_id', '=', self.id),
                ('holiday_status_id', '=', leave_type.id),
                ('date_to', '<', cycle_start),
                ('state', '=', 'validate'),
            ], limit=1, order='date_to desc')

            quota = policy['quota']
            carry_cap = policy['carry_cap']
            carry_forward = 0.0

            if prev_allocation:
                used = self._get_used_days(leave_type, prev_allocation)
                unused = max(prev_allocation.number_of_days - used, 0.0)
                carry_forward = min(unused, carry_cap)

            Allocation.create(self._allocation_vals(
                self, leave_type, cycle_start, quota + carry_forward
            ))

            _logger.info(
                'Leave carry-forward: %s — %s — quota=%s carry=%s -> new allocation=%s',
                self.name, leave_type.name, quota, carry_forward, quota + carry_forward,
            )

    # ------------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------------

    @api.model
    def _get_leave_type(self, xmlid):
        try:
            return self.env.ref(xmlid)
        except Exception:
            _logger.warning('Leave policy: leave type not found — %s', xmlid)
            return False

    @api.model
    def _get_join_date(self, employee):
        # ⚠️ CONFIRM WITH EZIO: which field is actually "joining date"?
        # Falls back through likely candidates, in priority order.
        version = getattr(employee, 'version_id', False)
        if version and getattr(version, 'contract_date_start', False):
            return version.contract_date_start
        if getattr(employee, 'first_contract_date', False):
            return employee.first_contract_date
        if employee.create_date:
            return employee.create_date.date()
        return False

    @staticmethod
    def _get_current_cycle_start(join_date, today):
        try:
            anniversary_this_year = join_date.replace(year=today.year)
        except ValueError:
            # Feb 29 joiner, non-leap current year
            anniversary_this_year = join_date.replace(year=today.year, day=28)
        if anniversary_this_year <= today:
            return anniversary_this_year
        return anniversary_this_year.replace(year=today.year - 1)

    @staticmethod
    def _is_anniversary_today(join_date, today):
        if join_date.month == 2 and join_date.day == 29 and not _is_leap_year(today.year):
            return today.month == 3 and today.day == 1
        return join_date.month == today.month and join_date.day == today.day

    @staticmethod
    def _allocation_vals(employee, leave_type, date_from, number_of_days):
        date_to = date_from + relativedelta(years=1) - relativedelta(days=1)
        return {
            'name': f'{leave_type.name} — {date_from} to {date_to}',
            'employee_id': employee.id,
            'holiday_status_id': leave_type.id,
            'number_of_days': number_of_days,
            'date_from': date_from,
            'date_to': date_to,
            'state': 'confirm',   # Odoo auto-validates for no_validation leave types
        }

    @staticmethod
    def _get_used_days(leave_type, allocation):
        Leave = allocation.env['hr.leave'].sudo()

        # allocation.date_from/date_to are Date; hr.leave.date_from is Datetime.
        # Widen the boundary to a full-day datetime range so the comparison
        # is apples-to-apples instead of comparing Date against Datetime.
        range_start = datetime.combine(allocation.date_from, time(0, 0, 0))
        range_end = datetime.combine(allocation.date_to, time(23, 59, 59))

        leaves = Leave.search([
            ('employee_id', '=', allocation.employee_id.id),
            ('holiday_status_id', '=', leave_type.id),
            ('state', '=', 'validate'),
            ('date_from', '>=', range_start),
            ('date_from', '<=', range_end),
        ])
        return sum(leaves.mapped('number_of_days'))