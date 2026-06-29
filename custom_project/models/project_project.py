import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from markupsafe import Markup

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
        """
        Show "Request Completion" button to:
          • The project's own Team Lead
          • HR officers (hr.group_hr_user)
          • Managers (custom_project.group_team_manager)

        Plain employees (group_team_employee) never see the button.
        The button is also hidden when the project is already locked or
        has a pending request outstanding.
        """
        user = self.env.user
        is_manager = user.has_group('custom_project.group_team_manager')
        is_hr = user.has_group('hr.group_hr_user')
        employee = self.env['hr.employee'].search(
            [('user_id', '=', self.env.uid)], limit=1
        )

        for project in self:
            # Common blockers — apply to all roles
            if project.is_locked or project.has_pending_completion_request:
                project.can_request_completion = False
                continue

            # Managers and HR: always eligible (project-level checks still
            # apply in Python create() — e.g. duplicate pending detection)
            if is_manager or is_hr:
                project.can_request_completion = True
                continue

            # Team Lead: only for their own project's team
            is_team_lead = bool(
                employee
                and project.team_id
                and project.team_id.team_lead_id == employee
            )
            project.can_request_completion = is_team_lead

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
        # Capture each project's current team BEFORE the write, so after
        # super().write() we can tell whether team_id actually changed (and
        # to what) — needed to fire the notification exactly once, only on a
        # real change to a non-empty team.
        team_changing = 'team_id' in vals
        old_team_by_project = (
            {project.id: project.team_id.id for project in self}
            if team_changing else {}
        )

        if not self.env.su and not self._is_completion_manager():
            self._check_lock_access()

        result = super().write(vals)

        if team_changing:
            new_team_id = vals.get('team_id')
            if new_team_id:
                for project in self:
                    if new_team_id != old_team_by_project.get(project.id):
                        project._notify_team_project_assigned()

        return result

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

        projects = super().create(vals_list)

        # Notify the team lead + members for any project created with a team
        # already set (e.g. picked on the creation form before first save).
        for project in projects:
            if project.team_id:
                project._notify_team_project_assigned()

        return projects

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

    # ── Team notification ────────────────────────────────────────────────────

    def _notify_team_project_assigned(self):
        """
        Notify the team lead and every member of project.team_id that this
        project has been assigned to their team. Fired from create() (when a
        project is created with a team already set) and from write() (when
        team_id is changed to a new, non-empty value).

        sudo() on member_ids / team_lead_id mirrors team.py's
        _compute_member_count pattern: hr.employee._check_private_fields()
        can raise an AccessError for non-HR users even on this simple
        Many2many read, so we resolve the roster under sudo and only use it
        to collect partner ids — no extra employee data is exposed beyond
        what message_notify already shows.
        """
        for project in self:
            team = project.team_id
            if not team:
                continue

            employees = team.sudo().member_ids
            if team.team_lead_id:
                employees |= team.sudo().team_lead_id

            partners = employees.mapped('user_id.partner_id').filtered(lambda p: p)
            if not partners:
                continue

            project.message_subscribe(partner_ids=partners.ids)
            project.message_notify(
                partner_ids=partners.ids,
                subject=_('Project Assigned to Your Team: %s') % project.name,
                body=Markup(
                    '<p>Hi,</p>'
                    '<p>The project <b>%s</b> has been assigned to your '
                    'team <b>%s</b>.</p>'
                ) % (project.name, team.name),
            )