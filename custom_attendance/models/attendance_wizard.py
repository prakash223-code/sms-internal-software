# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class AttendanceCheckInWizard(models.TransientModel):
    _name = 'attendance.checkin.wizard'
    _description = 'Employee Check In / Check Out'

    employee_id = fields.Many2one('hr.employee', string='Employee', readonly=True)
    status = fields.Selection([
        ('out', 'Not Checked In'),
        ('in', 'Checked In'),
        ('done', 'Completed for Today'),
    ], string='Status', readonly=True)
    last_check_in = fields.Datetime(string='Checked In At', readonly=True)
    last_check_out = fields.Datetime(string='Checked Out At', readonly=True)
    is_late = fields.Boolean(string='Late Entry', readonly=True)
    late_minutes = fields.Integer(string='Late By (Minutes)', readonly=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        employee = self.env['hr.employee'].search(
            [('user_id', '=', self.env.uid)], limit=1
        )
        if not employee:
            raise UserError(_(
                'No employee record is linked to your user account. '
                'Please contact HR or the system administrator.'
            ))
        res['employee_id'] = employee.id

        # sudo() — employee may not have hr.attendance read access
        Attendance = self.env['hr.attendance'].sudo()

        # Check for open session (currently checked in)
        open_session = Attendance.search([
            ('employee_id', '=', employee.id),
            ('check_out', '=', False),
        ], limit=1)

        if open_session:
            res['status'] = 'in'
            res['last_check_in'] = open_session.check_in
            res['is_late'] = open_session.is_late
            res['late_minutes'] = open_session.late_minutes
            return res

        # Check if already completed a cycle today
        import pytz
        from datetime import datetime, time

        tz_name = employee.tz or 'Asia/Kolkata'
        try:
            tz = pytz.timezone(tz_name)
        except pytz.UnknownTimeZoneError:
            tz = pytz.timezone('Asia/Kolkata')

        now_utc = pytz.utc.localize(fields.Datetime.now())
        today_local = now_utc.astimezone(tz).date()
        today_start_utc = tz.localize(
            datetime.combine(today_local, time(0, 0, 0))
        ).astimezone(pytz.utc).replace(tzinfo=None)
        today_end_utc = tz.localize(
            datetime.combine(today_local, time(23, 59, 59))
        ).astimezone(pytz.utc).replace(tzinfo=None)

        completed_today = Attendance.search([
            ('employee_id', '=', employee.id),
            ('check_in', '>=', today_start_utc),
            ('check_in', '<=', today_end_utc),
            ('check_out', '!=', False),
        ], limit=1, order='check_in desc')

        if completed_today:
            res['status'] = 'done'
            res['last_check_in'] = completed_today.check_in
            res['last_check_out'] = completed_today.check_out
            res['is_late'] = completed_today.is_late
            res['late_minutes'] = completed_today.late_minutes
            return res

        # Neither checked in nor completed — free to check in
        res['status'] = 'out'
        return res

    def action_toggle(self):
        self.ensure_one()
        # sudo() — employee user doesn't have hr.attendance create access
        self.env['hr.attendance'].sudo().action_toggle_attendance()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'attendance.checkin.wizard',
            'view_mode': 'form',
            'target': 'new',
            'name': 'Check In / Check Out',
        }