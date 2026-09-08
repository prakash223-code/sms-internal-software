# -*- coding: utf-8 -*-
import logging
from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Fields employees are allowed to write
EMPLOYEE_EDITABLE_FIELDS = {
    'methodology',
    'challenges',
    'results',
    'conclusion',
}

# Fields only HR can write
HR_ONLY_FIELDS = {
    'problem_statement',
    'objective',
    'document_requirement',
    'is_locked',
}


class ProjectProject(models.Model):
    _inherit = 'project.project'

    # ── Timesheet ─────────────────────────────────────────────
    timesheet_ids = fields.One2many(
        'account.analytic.line', 'project_id',
        string='Timesheet Entries',
    )
    total_time_spent = fields.Float(
        string='Total Hours Spent',
        compute='_compute_time_spent',
        store=True,
    )
    remaining_time = fields.Float(
        string='Remaining Hours',
        compute='_compute_time_spent',
        store=True,
    )

    @api.depends('timesheet_ids.unit_amount', 'allocated_hours')
    def _compute_time_spent(self):
        for rec in self:
            spent = sum(rec.timesheet_ids.mapped('unit_amount'))
            rec.total_time_spent = spent
            rec.remaining_time   = max(0.0, rec.allocated_hours - spent)

    # ── Project Details ───────────────────────────────────────
    # HR only edit
    problem_statement    = fields.Html(string='Problem Statement')
    objective            = fields.Html(string='Objective / Scope')
    document_requirement = fields.Html(string='Document Requirement')

    # All users edit when not locked
    methodology = fields.Html(string='Methodology / Approach')
    challenges  = fields.Html(string='Challenges Faced')
    results     = fields.Html(string='Results / Outcome')
    conclusion  = fields.Html(string='Conclusion')

    # ── Lock ─────────────────────────────────────────────────
    is_locked = fields.Boolean(string='Locked', default=False)

    def action_confirm_lock(self):
        self.write({'is_locked': True})

    def action_unlock(self):
        self.write({'is_locked': False})

    def write(self, vals):
        # superuser and HR bypass all checks
        if self.env.su or self.env.user.has_group('hr.group_hr_user'):
            return super().write(vals)

        incoming = set(vals.keys())

        # Block employee from writing HR-only fields
        blocked = incoming & HR_ONLY_FIELDS
        if blocked:
            raise UserError(
                _('You do not have permission to edit: %s')
                % ', '.join(sorted(blocked))
            )

        # Block employee from writing any other project fields
        # (name, date_start, privacy, etc.) — only allow details fields
        allowed = EMPLOYEE_EDITABLE_FIELDS
        not_allowed = incoming - allowed
        if not_allowed:
            raise UserError(
                _('You can only edit Project Details fields. '
                  'Restricted fields: %s') % ', '.join(sorted(not_allowed))
            )

        return super().write(vals)


from odoo import SUPERUSER_ID, _, api, fields, models
from odoo.exceptions import UserError


class IrAttachment(models.Model):
    _inherit = 'ir.attachment'

    project_id = fields.Many2one(
        'project.project',
        string='Linked Project',
        compute='_compute_project_id',
        store=True,
    )

    @api.depends('res_model', 'res_id')
    def _compute_project_id(self):
        for attachment in self:
            if attachment.res_model == 'project.project' and attachment.res_id:
                attachment.project_id = attachment.res_id
            else:
                attachment.project_id = False

    def _check_project_attachment_access(self, action):
        # Only the TRUE system superuser (uid=1) bypasses this check.
        # self.env.su alone is NOT safe here — Odoo's own mail/chatter
        # module calls attachment.sudo().unlink() internally when a
        # regular logged-in user clicks the trash icon on an
        # attachment, which sets env.su=True while env.uid stays the
        # real user. Checking env.su would silently let that bypass
        # our restriction — checking the actual uid does not.
        if self.env.uid == SUPERUSER_ID:
            return
        user = self.env.user
        is_hr = user.has_group('hr.group_hr_user')
        is_manager = user.has_group('custom_project.group_team_manager')
        if is_hr or is_manager:
            return
        for attachment in self:
            if (attachment.res_model == 'project.project'
                    and attachment.create_uid != user):
                raise UserError(_(
                    'You can only %s attachments that you uploaded '
                    'yourself. HR/Manager can %s any file.'
                ) % (action, action))

    def write(self, vals):
        self._check_project_attachment_access('edit')
        return super().write(vals)

    def unlink(self):
        self._check_project_attachment_access('delete')
        return super().unlink()