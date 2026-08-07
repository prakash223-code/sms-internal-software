# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from markupsafe import Markup


class HrLeaveAllocation(models.Model):
    _inherit = 'hr.leave.allocation'

    @api.model_create_multi
    def create(self, vals_list):
        allocations = super().create(vals_list)
        for allocation in allocations:
            if allocation.state in ('confirm', 'validate1'):
                allocation.sudo()._notify_allocation_request_submitted()
        return allocations

    def write(self, vals):
        old_states = {}
        if 'state' in vals:
            old_states = {alloc.id: alloc.state for alloc in self}

        res = super().write(vals)

        if 'state' in vals:
            for allocation in self:
                old_state = old_states.get(allocation.id)
                new_state = allocation.state
                if old_state == new_state:
                    continue
                if new_state == 'validate':
                    allocation.sudo()._notify_allocation_decision('approved')
                elif new_state == 'refuse':
                    allocation.sudo()._notify_allocation_decision('refused')

        return res

    # ------------------------------------------------------------------
    # NOTIFICATION HELPERS
    # ------------------------------------------------------------------

    def _get_allocation_notification_recipients(self):
        """HR group users + employees with employee_role = 'manager'
        + the Team Lead(s) of the requesting employee's team(s).
        Excludes the requesting employee themselves.
        Team Leads are notification-only — see hr_leave_extension.py for
        the full rationale (identical policy applied here)."""
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

        team_lead_users = self._get_team_lead_users()

        requester_user_id = self.employee_id.user_id.id
        all_users = (hr_users | manager_users | team_lead_users).filtered(
            lambda u: u.id != requester_user_id
        )

        return all_users.mapped('partner_id')

    def _get_team_lead_users(self):
        """Same helper as hr.leave — resolve Team Lead user(s) for this
        allocation's employee. Duplicated intentionally (small, self-
        contained, avoids a cross-model mixin for two call sites)."""
        self.ensure_one()
        if 'team.team' not in self.env:
            return self.env['res.users']

        employee = self.employee_id.sudo()
        teams = getattr(employee, 'team_ids', False)
        if not teams:
            return self.env['res.users']

        team_leads = teams.mapped('team_lead_id').filtered(
            lambda e: e.user_id and e != employee
        )
        return team_leads.mapped('user_id')

    def _notify_allocation_request_submitted(self):
        self.ensure_one()
        recipients = self._get_allocation_notification_recipients()
        if not recipients:
            return

        body = Markup(
            '<p><strong>%s</strong> has requested additional leave allocation '
            'and is awaiting approval.</p>'
            '<ul>'
            '<li>Leave Type: %s</li>'
            '<li>Requested: %s</li>'
            '</ul>'
        ) % (
                   self.employee_id.name,
                   self.holiday_status_id.name,
                   self.number_of_days,
               )

        self.message_notify(
            partner_ids=recipients.ids,
            subject=_('Allocation Request: %s') % self.employee_id.name,
            body=body,
            subtype_xmlid='mail.mt_comment',
        )

    def _notify_allocation_decision(self, decision):
        self.ensure_one()
        partner = self.employee_id.user_id.partner_id
        if not partner:
            return

        if decision == 'approved':
            subject = _('Allocation Request Approved')
            status_label = 'approved'
        else:
            subject = _('Allocation Request Refused')
            status_label = 'refused'

        body = Markup(
            '<p>Your leave allocation request has been <strong>%s</strong>.</p>'
            '<ul>'
            '<li>Leave Type: %s</li>'
            '<li>Requested: %s</li>'
            '</ul>'
        ) % (
                   status_label,
                   self.holiday_status_id.name,
                   self.number_of_days,
               )

        self.message_notify(
            partner_ids=[partner.id],
            subject=subject,
            body=body,
            subtype_xmlid='mail.mt_comment',
        )
