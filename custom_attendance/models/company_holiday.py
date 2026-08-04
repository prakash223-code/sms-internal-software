# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import date, timedelta, datetime, time
import pytz


class CompanyHoliday(models.Model):
    _name = 'company.holiday'
    _description = 'Company Holiday'
    _order = 'date asc'
    _rec_name = 'name'

    name = fields.Char(string='Holiday Name', required=True)
    date = fields.Date(string='Date', required=True)
    holiday_type = fields.Selection([
        ('public', 'Public Holiday'),
        ('event', 'Company Event'),
        ('emergency', 'Emergency Closure'),
        ('other', 'Other'),
    ], string='Type', default='public')
    is_working_override = fields.Boolean(
        string='Mark as Compensatory Working Day',
        default=False,
        help='Enable to declare a specific Saturday as a working day to '
             'compensate for a holiday. Can be any Saturday — same week, '
             'next week, or even next month.',
    )
    description = fields.Text(string='Notes')
    active = fields.Boolean(default=True)

    day_label = fields.Char(
        string='Day',
        compute='_compute_day_label',
        store=False,
    )

    # ------------------------------------------------------------------
    # COMPUTED
    # ------------------------------------------------------------------

    @api.depends('date')
    def _compute_day_label(self):
        days = ['Monday', 'Tuesday', 'Wednesday',
                'Thursday', 'Friday', 'Saturday', 'Sunday']
        for rec in self:
            rec.day_label = days[rec.date.weekday()] if rec.date else ''

    # ------------------------------------------------------------------
    # CONSTRAINTS
    # ------------------------------------------------------------------

    @api.constrains('date', 'is_working_override')
    def _check_working_override_must_be_saturday(self):
        for rec in self:
            if rec.is_working_override and rec.date:
                if rec.date.weekday() != 5:
                    raise ValidationError(_(
                        '"%s" is a %s, not a Saturday.\n\n'
                        'Compensatory Working Day can only be declared on a Saturday.'
                    ) % (rec.date, rec.day_label))

    @api.constrains('date')
    def _check_duplicate(self):
        for rec in self:
            duplicate = self.search([
                ('date', '=', rec.date),
                ('id', '!=', rec.id),
                ('active', '=', True),
            ], limit=1)
            if duplicate:
                raise ValidationError(_(
                    'A record already exists on %s (%s).'
                ) % (rec.date, duplicate.name))

    # ------------------------------------------------------------------
    # ORM OVERRIDES
    # ------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            rec._sync_resource_leave()
        return records

    def write(self, vals):
        res = super().write(vals)
        for rec in self:
            rec._remove_resource_leave()
            rec._sync_resource_leave()
        return res

    def unlink(self):
        for rec in self:
            rec._remove_resource_leave()
        return super().unlink()

    # ------------------------------------------------------------------
    # RESOURCE CALENDAR HELPERS
    # ------------------------------------------------------------------

    def _get_company_calendar(self):
        return self.sudo().env.company.resource_calendar_id

    def _date_to_utc_range(self, d):
        """
        Explicit, deterministic UTC conversion — do NOT use with_context(tz=...)
        anywhere for this. It has proven unreliable (sometimes shifts correctly,
        sometimes not at all, sometimes double-shifts) across repeated testing.
        """
        calendar = self._get_company_calendar()
        tz_name = calendar.tz if calendar and calendar.tz else 'Asia/Kolkata'
        try:
            tz = pytz.timezone(tz_name)
        except pytz.UnknownTimeZoneError:
            tz = pytz.timezone('Asia/Kolkata')

        local_from = tz.localize(datetime.combine(d, time(0, 1, 0)))
        local_to = tz.localize(datetime.combine(d, time(23, 58, 0)))

        return (
            local_from.astimezone(pytz.utc).replace(tzinfo=None),
            local_to.astimezone(pytz.utc).replace(tzinfo=None),
        )

    def _get_resource_leave_name(self):
        return f'[CH-{self.id}] {self.name}'

    def _sync_resource_leave(self):
        self.ensure_one()
        if not self.active:
            return
        calendar = self._get_company_calendar()
        if not calendar:
            return

        # Always act as base.user_root for this write, regardless of who
        # triggered it. This sidesteps Odoo core's hr_holidays
        # _prepare_public_holidays_values(), which silently re-shifts
        # date_from/date_to whenever the ACTING user's personal tz field
        # differs from the calendar's tz. By fixing the acting user to one
        # we control and keep permanently set to the calendar's tz, this
        # class of bug can never resurface regardless of what tz any other
        # user account does or doesn't have.
        root_user = self.env.ref('base.user_root')
        ResLeave = self.env['resource.calendar.leaves'].sudo().with_user(root_user)

        if self.is_working_override:
            self._remove_saturday_off_leave_for_date(self.date)
        else:
            date_from_utc, date_to_utc = self._date_to_utc_range(self.date)
            ResLeave.create({
                'name': self._get_resource_leave_name(),
                'calendar_id': calendar.id,
                'date_from': date_from_utc,
                'date_to': date_to_utc,
                'resource_id': False,
            })

    def _remove_resource_leave(self):
        """Remove synced resource.calendar.leaves for this holiday record."""
        self.ensure_one()
        self.env['resource.calendar.leaves'].sudo().search([
            ('name', '=', self._get_resource_leave_name()),
        ]).unlink()

    def _remove_saturday_off_leave_for_date(self, target_date):
        calendar = self._get_company_calendar()
        if not calendar:
            return

        date_from_utc, date_to_utc = self._date_to_utc_range(target_date)

        self.env['resource.calendar.leaves'].sudo().search([
            ('calendar_id', '=', calendar.id),
            ('name', 'like', '[SAT-OFF]'),
            ('date_from', '<=', date_to_utc),
            ('date_to', '>=', date_from_utc),
        ]).unlink()

    # ------------------------------------------------------------------
    # SETUP: Add Saturday to resource calendar working hours
    # Called once via shell after upgrade
    # ------------------------------------------------------------------

    @api.model
    def setup_saturday_in_calendar(self):
        """
        Adds Saturday (dayofweek=5) as a working day to the company's
        resource calendar so 1st, 3rd, 5th Saturdays appear as working
        days in the Time Off calendar.

        Only adds if not already present.
        Run once from shell:
          env['company.holiday'].setup_saturday_in_calendar()
          env.cr.commit()
        """
        calendar = self.env.company.resource_calendar_id
        if not calendar:
            return

        # Check if Saturday already exists in attendance lines
        existing_saturday = self.env['resource.calendar.attendance'].search([
            ('calendar_id', '=', calendar.id),
            ('dayofweek', '=', '5'),
        ])
        if existing_saturday:
            return  # already set up

        # Add Saturday morning and afternoon lines (same as other days)
        self.env['resource.calendar.attendance'].create([
            {
                'name': 'Saturday Morning',
                'calendar_id': calendar.id,
                'dayofweek': '5',
                'hour_from': 9.25,  # 9:15 AM
                'hour_to': 13.0,
                'day_period': 'morning',
            },
            {
                'name': 'Saturday Afternoon',
                'calendar_id': calendar.id,
                'dayofweek': '5',
                'hour_from': 14.0,
                'hour_to': 18.25,  # 6:15 PM
                'day_period': 'afternoon',
            },
        ])

    # ------------------------------------------------------------------
    # CRON: Generate 2nd/4th Saturday resource leaves
    # ------------------------------------------------------------------

    @api.model
    def _cron_generate_saturday_resource_leaves(self):
        """
        Generates resource.calendar.leaves for every 2nd and 4th Saturday
        in the next 2 years so they appear greyed out in Time Off calendar.
        Skips Saturdays that have a working override.
        """
        import calendar as cal_module

        today = date.today()
        years = [today.year, today.year + 1]
        calendar = self.env.company.resource_calendar_id

        if not calendar:
            return

        # Must match _sync_resource_leave()'s tz context exactly, or the
        # UTC-shifted date_from/date_to on these records use a different
        # offset than holidays created via company.holiday, causing false
        # "holidays overlap" validation errors on adjacent dates.
        ResLeave = self.env['resource.calendar.leaves'].sudo().with_user(self.env.ref('base.user_root'))

        existing = ResLeave.search([
            ('name', 'like', '[SAT-OFF]'),
            ('calendar_id', '=', calendar.id),
        ])
        existing_names = {r.name for r in existing}

        override_dates = {
            rec.date for rec in self.search([
                ('is_working_override', '=', True),
                ('active', '=', True),
            ])
        }

        for year in years:
            for month in range(1, 13):
                num_days = cal_module.monthrange(year, month)[1]
                saturdays = [
                    date(year, month, d)
                    for d in range(1, num_days + 1)
                    if date(year, month, d).weekday() == 5
                ]
                for idx, sat in enumerate(saturdays, 1):
                    if idx not in (2, 4):
                        continue
                    if sat in override_dates:
                        continue

                    ordinal = '2nd' if idx == 2 else '4th'
                    name = f'[SAT-OFF] {sat.strftime("%Y-%m")} {ordinal} Saturday'

                    if name in existing_names:
                        continue

                    date_from_utc, date_to_utc = self._date_to_utc_range(sat)
                    try:
                        ResLeave.create({
                            'name': name,
                            'calendar_id': calendar.id,
                            'date_from': date_from_utc,
                            'date_to': date_to_utc,
                            'resource_id': False,
                        })
                        existing_names.add(name)
                    except Exception as e:
                        import logging
                        logging.getLogger(__name__).warning(
                            'SKIPPED SAT-OFF %s due to collision: %s', name, e
                        )

    # ------------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------------

    @api.model
    def is_holiday(self, check_date):
        if hasattr(check_date, 'date'):
            check_date = check_date.date()

        override = self.search([
            ('date', '=', check_date),
            ('is_working_override', '=', True),
            ('active', '=', True),
        ], limit=1)
        if override:
            return False

        if check_date.weekday() == 5:
            occ = self._saturday_occurrence(check_date)
            if occ in (2, 4):
                return True

        return bool(self.search([
            ('date', '=', check_date),
            ('is_working_override', '=', False),
            ('active', '=', True),
        ], limit=1))

    @api.model
    def get_holidays_in_range(self, date_from, date_to):
        holidays = set()

        overrides = self.search([
            ('date', '>=', date_from),
            ('date', '<=', date_to),
            ('is_working_override', '=', True),
            ('active', '=', True),
        ])
        override_dates = {rec.date for rec in overrides}

        records = self.search([
            ('date', '>=', date_from),
            ('date', '<=', date_to),
            ('is_working_override', '=', False),
            ('active', '=', True),
        ])
        for rec in records:
            holidays.add(rec.date)

        current = date_from
        while current <= date_to:
            if current.weekday() == 5:
                occ = self._saturday_occurrence(current)
                if occ in (2, 4) and current not in override_dates:
                    holidays.add(current)
            current += timedelta(days=1)

        return holidays

    @staticmethod
    def _saturday_occurrence(d):
        return (d.day - 1) // 7 + 1
