# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import date, timedelta


class CompanyHoliday(models.Model):
    _name = 'company.holiday'
    _description = 'Company Holiday'
    _order = 'date asc'
    _rec_name = 'name'

    name = fields.Char(string='Holiday Name', required=True)
    date = fields.Date(string='Date', required=True)
    holiday_type = fields.Selection([
        ('public',    'Public Holiday'),
        ('event',     'Company Event'),
        ('emergency', 'Emergency Closure'),
        ('other',     'Other'),
    ], string='Type', required=True, default='public')
    description = fields.Text(string='Notes')
    active = fields.Boolean(default=True)

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
                    'A holiday already exists on %s (%s). '
                    'You cannot declare two holidays on the same date.'
                ) % (rec.date, duplicate.name))

    # ----------------------------------------------------------------
    # Static helpers — called from monthly_summary and attendance models
    # ----------------------------------------------------------------

    @api.model
    def is_holiday(self, check_date):
        """
        Returns True if check_date is:
          - A declared company holiday (active record exists), OR
          - A 2nd or 4th Saturday of its month (company weekly off policy)
        check_date can be a date or datetime object.
        """
        if hasattr(check_date, 'date'):
            check_date = check_date.date()

        # 2nd and 4th Saturday rule
        if check_date.weekday() == 5:   # Saturday = 5
            week_number = self._saturday_occurrence(check_date)
            if week_number in (2, 4):
                return True

        # Declared company holiday
        return bool(self.search([
            ('date', '=', check_date),
            ('active', '=', True),
        ], limit=1))

    @api.model
    def get_holidays_in_range(self, date_from, date_to):
        """
        Returns a set of date objects that are holidays between
        date_from and date_to inclusive (both are date objects).
        Includes declared holidays + all 2nd & 4th Saturdays in range.
        """
        holidays = set()

        # Declared holidays
        records = self.search([
            ('date', '>=', date_from),
            ('date', '<=', date_to),
            ('active', '=', True),
        ])
        for rec in records:
            holidays.add(rec.date)

        # 2nd and 4th Saturdays
        current = date_from
        while current <= date_to:
            if current.weekday() == 5:
                if self._saturday_occurrence(current) in (2, 4):
                    holidays.add(current)
            current += timedelta(days=1)

        return holidays

    @staticmethod
    def _saturday_occurrence(d):
        """Returns which occurrence of Saturday this date is in its month (1st, 2nd, etc.)."""
        day = d.day
        return (day - 1) // 7 + 1