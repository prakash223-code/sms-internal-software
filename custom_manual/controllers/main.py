# -*- coding: utf-8 -*-
import json
import logging

from odoo import http, tools
from odoo.http import request

_logger = logging.getLogger(__name__)

VALID_ROLES = ('employee', 'manager', 'hr')


class ManualController(http.Controller):

    # ------------------------------------------------------------------
    # PAGE — serves the static manual shell.
    # auth='user' means an unauthenticated request never reaches here;
    # Odoo's login flow handles that before this method runs.
    # ------------------------------------------------------------------
    @http.route('/manual', type='http', auth='user', website=False)
    def manual_page(self, **kwargs):
        with tools.file_open(
            'custom_manual/static/src/manual/index.html', 'r'
        ) as f:
            content = f.read()
        return request.make_response(
            content,
            headers=[('Content-Type', 'text/html; charset=utf-8')],
        )

    # ------------------------------------------------------------------
    # ROLE — the page calls this on load. The role comes from the
    # server's own read of hr.employee.employee_role for whoever is
    # actually logged in (request.env.uid). There is no client input
    # here at all, so there is nothing for the browser to spoof.
    #
    # Admins (base.group_system) commonly have no linked hr.employee
    # record, or one with employee_role unset — without this, they'd
    # silently fall through to the employee-level default. Since admins
    # need visibility into approvals and policy content to configure and
    # test the system, they're floored at 'manager' level regardless of
    # their employee record (unless that record explicitly says 'hr',
    # which is left alone).
    # ------------------------------------------------------------------
    @http.route('/manual/my_role', type='http', auth='user', csrf=False)
    def my_role(self, **kwargs):
        employee = request.env['hr.employee'].sudo().search(
            [('user_id', '=', request.env.uid)], limit=1
        )

        role = 'employee'
        if employee and getattr(employee, 'employee_role', False):
            candidate = employee.employee_role
            if candidate in VALID_ROLES:
                role = candidate
            else:
                _logger.warning(
                    'Manual: unrecognized employee_role "%s" for %s — '
                    'defaulting to employee-level access.',
                    candidate, employee.name,
                )

        is_admin = request.env.user.has_group('base.group_system')
        if is_admin and role == 'employee':
            role = 'manager'

        data = {
            'role': role,
            'name': employee.name if employee else request.env.user.name,
        }
        return request.make_response(
            json.dumps(data),
            headers=[('Content-Type', 'application/json')],
        )