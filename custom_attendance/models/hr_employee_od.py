# -*- coding: utf-8 -*-
import pytz
from odoo import models
from datetime import datetime, time


OD_XMLID = 'custom_attendance.leave_type_od'


class HrEmployeeOd(models.Model):
    _inherit = 'hr.employee'

    def _is_on_od(self, check_date):
        """Return True if the employee has an approved On Duty leave covering check_date."""
        self.ensure_one()
        if hasattr(check_date, 'date'):
            check_date = check_date.date()

        try:
            od_type = self.env.ref(OD_XMLID)
        except Exception:
            return False

        tz_name = self.tz or 'Asia/Kolkata'
        try:
            tz = pytz.timezone(tz_name)
        except pytz.UnknownTimeZoneError:
            tz = pytz.timezone('Asia/Kolkata')

        day_start_local = tz.localize(datetime.combine(check_date, time(0, 0, 0)))
        day_end_local = tz.localize(datetime.combine(check_date, time(23, 59, 59)))

        day_start_utc = day_start_local.astimezone(pytz.utc).replace(tzinfo=None)
        day_end_utc = day_end_local.astimezone(pytz.utc).replace(tzinfo=None)

        return bool(self.env['hr.leave'].sudo().search_count([
            ('employee_id', '=', self.id),
            ('holiday_status_id', '=', od_type.id),
            ('state', '=', 'validate'),
            ('date_from', '<=', day_end_utc),
            ('date_to', '>=', day_start_utc),
        ], limit=1))
