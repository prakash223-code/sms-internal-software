# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from markupsafe import Markup
from .leave_policy import CL_EL_ML_XMLIDS
import logging

_logger = logging.getLogger(__name__)


class HrLeaveAllocation(models.Model):
    _inherit = 'hr.leave.allocation'

    @api.model_create_multi
    def create(self, vals_list):
        managed_type_ids = self._get_managed_leave_type_ids()
        internal = self.env.context.get('leave_policy_internal')

        final_records = self.browse()
        remaining_vals = []

        if managed_type_ids and not internal:
            for vals in vals_list:
                leave_type_id = vals.get('holiday_status_id')
                employee_id = vals.get('employee_id')
                merged = False
                if leave_type_id in managed_type_ids and employee_id:
                    merged = self._merge_into_current_cycle(
                        vals, employee_id, leave_type_id
                    )
                if merged:
                    final_records |= merged
                else:
                    remaining_vals.append(vals)
        else:
            remaining_vals = vals_list

        if remaining_vals:
            created = super().create(remaining_vals)
            for allocation in created:
                if allocation.state in ('confirm', 'validate1'):
                    allocation.sudo()._notify_allocation_request_submitted()
            final_records |= created

        return final_records

    # ------------------------------------------------------------------
    # MANUAL ALLOCATION MERGE — keeps the "one record per cycle" invariant
    # that leave_policy.py's carry-forward logic depends on.
    # ------------------------------------------------------------------

    def _get_managed_leave_type_ids(self):
        ids = []
        for xmlid in CL_EL_ML_XMLIDS:
            try:
                ids.append(self.env.ref(xmlid).id)
            except Exception:
                continue
        return ids

    def _merge_into_current_cycle(self, vals, employee_id, leave_type_id):
        """If a validated cycle-anchor allocation already exists for this
        employee/leave-type's CURRENT cycle, fold the manually-requested
        days into it instead of creating a second record. Returns the
        anchor record on success, False if no anchor exists (falls back
        to normal create)."""
        Employee = self.env['hr.employee']
        employee = Employee.browse(employee_id)
        if not employee.exists():
            return False

        join_date = employee._get_join_date(employee)
        if not join_date:
            return False

        today = fields.Date.context_today(self)
        cycle_start = employee._get_current_cycle_start(join_date, today)

        anchor = self.sudo().search([
            ('employee_id', '=', employee_id),
            ('holiday_status_id', '=', leave_type_id),
            ('date_from', '=', cycle_start),
        ], limit=1)

        if not anchor:
            _logger.warning(
                'Allocation merge: no cycle anchor found for employee=%s '
                'leave_type=%s cycle_start=%s — creating standalone record.',
                employee.name, leave_type_id, cycle_start
            )
            return False

        added_days = vals.get('number_of_days') or 0.0
        if not added_days:
            return False

        new_total = anchor.number_of_days + added_days
        anchor.sudo().write({'number_of_days': new_total})

        _logger.info(
            'Allocation merge: %s — %s — +%s days -> new total %s (anchor id=%s)',
            employee.name, anchor.holiday_status_id.name,
            added_days, new_total, anchor.id
        )

        anchor.sudo()._notify_allocation_topped_up(added_days, new_total)
        return anchor

    def _notify_allocation_topped_up(self, added_days, new_total):
        self.ensure_one()
        partner = self.employee_id.user_id.partner_id
        if not partner:
            return
        body = Markup(
            '<p>Your <strong>%s</strong> balance was topped up by '
            '<strong>%s day(s)</strong>.</p>'
            '<p>New total for this cycle: <strong>%s day(s)</strong>.</p>'
        ) % (self.holiday_status_id.name, added_days, new_total)
        self.message_notify(
            partner_ids=[partner.id],
            subject=_('Leave Allocation Topped Up'),
            body=body,
            subtype_xmlid='mail.mt_comment',
        )

    # ------------------------------------------------------------------
    # (existing write() override for approve/refuse notifications stays
    # exactly as it was)
    # ------------------------------------------------------------------
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
