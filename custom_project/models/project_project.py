import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ProjectProject(models.Model):
    _inherit = 'project.project'

    team_id = fields.Many2one(
        'team.team',
        string='Team',
        tracking=True,
        help='The team responsible for this project. '
             'Tasks created under this project will inherit this team.',
    )

    # ── Completion lock ───────────────────────────────────────────────────────

    is_locked = fields.Boolean(
        string='Locked (Completed)',
        default=False,
        copy=False,
        tracking=True,
        help='When set, only Managers can edit this project or its tasks. '
             'Set automatically when a completion request is approved.',
    )

    locked_by = fields.Many2one(
        'hr.employee',
        string='Locked By',
        readonly=True,
        copy=False,
    )

    locked_date = fields.Datetime(
        string='Locked On',
        readonly=True,
        copy=False,
    )

    stage_id_before_lock = fields.Many2one(
        'project.project.stage',
        string='Stage Before Lock',
        readonly=True,
        copy=False,
        help='The project stage at the moment a completion request was '
             'approved. Restored automatically when the project is reopened.',
    )

    completion_request_count = fields.Integer(
        compute='_compute_completion_request_count',
        string='Completion Requests',
    )

    has_pending_completion_request = fields.Boolean(
        compute='_compute_completion_request_count',
        string='Has Pending Completion Request',
    )

    can_request_completion = fields.Boolean(
        compute='_compute_can_request_completion',
        string='Can Request Completion',
    )

    # ── Computes ──────────────────────────────────────────────────────────────

    def _compute_completion_request_count(self):
        Request = self.env['project.completion.request'].sudo()
        for project in self:
            requests = Request.search([('project_id', '=', project.id)])
            project.completion_request_count = len(requests)
            project.has_pending_completion_request = bool(
                requests.filtered(lambda r: r.state == 'pending')
            )

    @api.depends_context('uid')
    def _compute_can_request_completion(self):
        employee = self.env['hr.employee'].search(
            [('user_id', '=', self.env.uid)], limit=1
        )
        for project in self:
            project.can_request_completion = bool(
                employee
                and project.team_id
                and project.team_id.team_lead_id == employee
                and not project.is_locked
                and not project.has_pending_completion_request
            )

    # ── Access guard ──────────────────────────────────────────────────────────

    def _is_completion_manager(self):
        return self.env.user.has_group('custom_project.group_team_manager')

    def _check_lock_access(self):
        """
        When a project is locked, ONLY Managers (custom_project.group_team_manager)
        may write to it — this intentionally has no HR exemption, unlike most
        other access checks in this module.
        """
        if self.env.su or self._is_completion_manager():
            return
        for project in self:
            if project.is_locked:
                raise UserError(
                    _('"%s" is locked as completed. Only a Manager can '
                      'edit it. Ask a Manager to Reopen the project first.')
                    % project.name
                )

    def write(self, vals):
        # Allow the lock/unlock flow itself (set via sudo() from the
        # completion request / reopen action) to go through, but block
        # everyone else from writing to an already-locked project,
        # regardless of which fields they're touching (including kanban
        # drag-and-drop stage changes, which route through this same
        # write() via the web_save RPC).
        if not self.env.su and not self._is_completion_manager():
            self._check_lock_access()
        return super().write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        default_stages = self.env['project.task.type'].sudo().search(
            [('is_default_stage', '=', True)],
            order='sequence asc',
        )

        if default_stages:
            stage_ids = default_stages.ids
            for vals in vals_list:
                existing = vals.get('type_ids') or []
                has_real_stages = any(
                    isinstance(cmd, (list, tuple)) and (
                        (cmd[0] == 6 and cmd[2])
                        or cmd[0] == 4
                    )
                    for cmd in existing
                )
                if not has_real_stages:
                    vals['type_ids'] = [(6, 0, stage_ids)]

        return super().create(vals_list)

    # ── Actions ───────────────────────────────────────────────────────────────

    def action_request_completion(self):
        self.ensure_one()
        if self.is_locked:
            raise UserError(_('This project is already locked as completed.'))

        self.env['project.completion.request'].create({
            'project_id': self.id,
        })

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Completion Requested'),
                'message': _(
                    'A completion request for "%s" has been sent to '
                    'Managers for approval.'
                ) % self.name,
                'type': 'success',
                'sticky': False,
            },
        }

    def action_reopen(self):
        """
        Manager-only: clears the lock so the project can be edited again,
        and restores the stage it was on before the completion request
        was approved (falls back to leaving it on the current/Done stage
        if no prior stage was recorded — e.g. very old locked records).
        """
        if not self._is_completion_manager():
            raise UserError(_('Only Managers can reopen a locked project.'))
        for project in self:
            vals = {
                'is_locked': False,
                'locked_by': False,
                'locked_date': False,
                'stage_id_before_lock': False,
            }
            if project.stage_id_before_lock:
                vals['stage_id'] = project.stage_id_before_lock.id
            project.write(vals)
            _logger.info(
                'Project "%s" (id=%s) reopened by uid=%s',
                project.name, project.id, self.env.uid,
            )

    def action_view_completion_requests(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Completion Requests'),
            'res_model': 'project.completion.request',
            'view_mode': 'list,form',
            'domain': [('project_id', '=', self.id)],
            'context': {'default_project_id': self.id},
        }