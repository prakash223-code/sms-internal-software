# account_analytic_line.py
# PURPOSE: Extend timesheet entries (account.analytic.line) with a
#   "Software Used" free-text field so employees can log which tool
#   or application they worked with during each timesheet entry.
#   Also adds a per-row "can I edit this line" flag so the UI can make
#   other people's lines readonly instead of letting users hit Save
#   and get a raw Access Error, plus a friendlier server-side message
#   as a safety net for any other path into this model (e.g. the
#   Timesheets menu, not just the task form).
#
#   FINAL POLICY: an employee may create/edit/delete only their OWN
#   timesheet line. HR and Manager are exempted — either can view AND
#   edit/delete ANY employee's line. Team Lead is view-only on
#   everyone's entries. Admin/superuser always bypasses via env.su.
#
#   WHY _apply_ir_rules IS OVERRIDDEN BELOW:
#   security/record_rules.xml already grants Employees an unrestricted
#   read ir.rule ([(1, '=', 1)]). In testing this was still not enough
#   for some employees to see teammates' entries. Root cause found:
#   visibility depended on the user being correctly added to the custom
#   custom_project.group_team_employee group — a manual setup step that
#   kept being missed/misconfigured, making it an unreliable single
#   point of failure. HR/Manager/Team Lead all worked correctly because
#   THEIR groups happened to be assigned right; plain employees kept
#   losing visibility whenever their custom group assignment was off.
#
#   FIX: stop depending on the custom group entirely for READ. Instead,
#   check base.group_user — the standard group every internal/employee
#   login already has automatically, with no manual setup needed. Any
#   internal user gets guaranteed full read on every timesheet line, no
#   matter what other ir.rule exists (ours, hr_timesheet's, or anything
#   hidden in the database) and no matter whether a custom group was
#   ever assigned. Write/create/unlink modes are NOT touched here (they
#   still run through every ir.rule as normal), and are additionally
#   hard-enforced by the write()/unlink() overrides further down — so
#   widening read this way cannot expand anyone's edit rights.

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AccountAnalyticLine(models.Model):
    _inherit = 'account.analytic.line'

    software_used = fields.Char(
        string='Software Used',
        help='The software or tool used during this timesheet entry.',
    )

    # Drives readonly on the inline timesheet list so a user can SEE
    # every line on a shared task but can only type into their own —
    # unless they're HR or Manager, who can edit any row. New/unsaved
    # rows are always editable (nothing to protect yet — ownership is
    # only meaningful once a line belongs to somebody).
    can_edit_line = fields.Boolean(
        string='Can Edit This Line',
        compute='_compute_can_edit_line',
        store=False,
    )

    def _is_timesheet_privileged(self):
        """HR or Manager may edit/delete any employee's timesheet line."""
        return (
            self.env.user.has_group('hr.group_hr_user')
            or self.env.user.has_group('custom_project.group_team_manager')
        )

    def _apply_ir_rules(self, query, mode='read'):
        # Guarantee unrestricted READ for every internal user
        # (base.group_user — assigned automatically, no custom group
        # setup required), no matter what other ir.rule records exist.
        # Only 'read' is bypassed — create/write/unlink still go
        # through every rule normally, and are separately hard-enforced
        # below by write()/unlink().
        if (
            mode == 'read'
            and not self.env.su
            and self.env.user.has_group('base.group_user')
        ):
            return
        return super()._apply_ir_rules(query, mode=mode)

    @api.depends('employee_id')
    @api.depends_context('uid')
    def _compute_can_edit_line(self):
        is_privileged = self._is_timesheet_privileged()
        current_user = self.env.user
        for line in self:
            if is_privileged:
                line.can_edit_line = True
            elif not line.employee_id or not line.employee_id.user_id:
                line.can_edit_line = True  # nothing saved / no owner yet
            else:
                line.can_edit_line = line.employee_id.user_id == current_user

    # Friendly message instead of the generic ir.rule Access Error, for
    # any write that DOES reach the server (e.g. if someone bypasses
    # the readonly view via another screen, like the Timesheets menu).
    # The view-level readonly (can_edit_line) is the main defense; this
    # is the safety net. HR and Manager are exempt from this check.
    def write(self, vals):
        if not self.env.su and not self._is_timesheet_privileged():
            current_user = self.env.user
            for line in self:
                if line.employee_id and line.employee_id.user_id and line.employee_id.user_id != current_user:
                    raise UserError(
                        _('You can only edit your own timesheet entries. '
                          '"%s" belongs to %s.') % (line.name or _('This entry'), line.employee_id.name)
                    )
        return super().write(vals)

    def unlink(self):
        if not self.env.su and not self._is_timesheet_privileged():
            current_user = self.env.user
            for line in self:
                if line.employee_id and line.employee_id.user_id and line.employee_id.user_id != current_user:
                    raise UserError(
                        _('You can only delete your own timesheet entries. '
                          '"%s" belongs to %s.') % (line.name or _('This entry'), line.employee_id.name)
                    )
        return super().unlink()