import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain
from markupsafe import Markup

_logger = logging.getLogger(__name__)


class ProjectTask(models.Model):
    _inherit = 'project.task'

    # ── Custom fields ─────────────────────────────────────────────────────────

    assigned_by = fields.Many2one(
        'hr.employee',
        string='Assigned By',
        copy=False,
        tracking=True,
        readonly=True,
    )

    assigned_to = fields.Many2one(
        'hr.employee',
        string='Assigned To',
        copy=False,
        tracking=True,
    )

    team_id = fields.Many2one(
        'team.team',
        string='Team',
        tracking=True,
        help='Auto-populated from the project team.',
    )

    task_state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('assigned', 'Assigned'),
            ('in_progress', 'In Progress'),
            ('completed', 'Completed'),
            ('verified', 'Verified'),
            ('closed', 'Closed'),
        ],
        string='Task State',
        default='draft',
        tracking=True,
        copy=False,
        group_expand='_group_expand_states',
    )

    assignment_request_count = fields.Integer(
        compute='_compute_assignment_request_count',
        string='Assignment Requests',
    )

    can_change_state = fields.Boolean(
        compute='_compute_can_change_state',
        store=False,
    )

    # Drives readonly on the form for non-privileged, non-creator users.
    # Managers, Team Leads, and HR may edit any task. Regular employees
    # may only edit tasks they personally created — everything else is
    # read-only to them (they can still progress task_state on tasks
    # assigned to them via the dedicated state-transition buttons, which
    # are governed separately by can_change_state / _check_state_transition_access).
    can_edit_task = fields.Boolean(
        compute='_compute_can_edit_task',
        store=False,
    )

    # Mirrors project_id.is_locked so the form can show a banner / drive
    # readonly without an extra round trip.
    project_is_locked = fields.Boolean(
        related='project_id.is_locked',
        string='Project Locked',
        readonly=True,
        store=False,
    )

    # ── Computes ──────────────────────────────────────────────────────────────

    def _compute_assignment_request_count(self):
        for task in self:
            task.assignment_request_count = self.env[
                'task.assignment.request'
            ].sudo().search_count([('task_id', '=', task.id)])

    @api.depends('assigned_to')
    @api.depends_context('uid')
    def _compute_can_change_state(self):
        is_priv = self._is_privileged()
        employee = self._get_current_employee()
        for task in self:
            task.can_change_state = is_priv or (task.assigned_to == employee)

    @api.depends('create_uid')
    @api.depends_context('uid')
    def _compute_can_edit_task(self):
        is_priv = self._is_privileged()
        uid = self.env.uid
        for task in self:
            task.can_edit_task = is_priv or task.create_uid.id == uid

    @api.model
    def _group_expand_states(self, states, domain):
        return [key for key, _label in self._fields['task_state'].selection]

    # ── Onchange ──────────────────────────────────────────────────────────────

    @api.onchange('project_id')
    def _onchange_project_id_team(self):
        if self.project_id and self.project_id.team_id:
            self.team_id = self.project_id.team_id
        elif not self.project_id:
            self.team_id = False

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _get_current_employee(self):
        return self.env['hr.employee'].search(
            [('user_id', '=', self.env.uid)], limit=1
        )

    def _get_employee_teams(self, employee):
        return self.env['team.team'].search([
            '|',
            ('member_ids', 'in', employee.id),
            ('team_lead_id', '=', employee.id),
        ])

    def _is_manager(self):
        return (
                self.env.user.has_group('custom_project.group_team_manager')
                or self.env.user.has_group('project.group_project_manager')
        )

    def _is_privileged(self):
        """Managers, Team Leads, and HR bypass all team/creator restrictions."""
        return (
                self.env.user.has_group('custom_project.group_team_manager')
                or self.env.user.has_group('custom_project.group_team_lead')
                or self.env.user.has_group('hr.group_hr_user')
        )

    def _is_completion_manager(self):
        """
        Stricter than _is_privileged(): used only for the project-lock
        freeze, where even HR is NOT exempt — only Managers are.
        """
        return self.env.user.has_group('custom_project.group_team_manager')

    def _check_project_lock_access(self, project):
        """
        When a project is locked (completed), no one may create or edit
        tasks under it except a Manager. This applies even to HR and
        Team Leads, unlike _is_privileged() / _check_edit_access().

        Reads project.is_locked / project.name via sudo(). This method is
        an internal authorization gate — it should work the same way
        regardless of whether the current user happens to have ir.rule
        read access to the project record itself. Without sudo(), an
        employee with valid task-level access (e.g. cross-team assigned
        via an approved task.assignment.request) but who is NOT a member
        of the project's own team trips project.project's "team members
        see own team only" rule the instant we touch project.is_locked —
        turning a routine task save into an unrelated AccessError instead
        of either passing cleanly or raising our own clear UserError.
        """
        if self.env.su or self._is_completion_manager():
            return
        project_sudo = project.sudo() if project else project
        if project_sudo and project_sudo.is_locked:
            raise UserError(
                _('"%s" is locked as completed. Tasks cannot be created '
                  'or edited until a Manager reopens the project.')
                % project_sudo.name
            )

    def _check_state_transition_access(self):
        """
        Only the employee assigned to a task may advance its state.
        Managers, Team Leads, and HR are exempt.
        """
        if self._is_privileged():
            _logger.warning("STATE CHECK: uid=%s is privileged — bypassing", self.env.uid)
            return
        current_employee = self._get_current_employee()
        _logger.warning("STATE CHECK: uid=%s employee=%s", self.env.uid, current_employee)
        if not current_employee:
            raise UserError(
                _('Your user account is not linked to an employee record.')
            )
        for task in self:
            _logger.warning(
                "STATE CHECK: task=%s assigned_to=%s match=%s",
                task.name, task.assigned_to, task.assigned_to == current_employee
            )
            if task.assigned_to != current_employee:
                raise UserError(
                    _('Only the assigned employee (%s) can change '
                      'the state of task "%s".')
                    % (
                        task.assigned_to.name if task.assigned_to else _('nobody'),
                        task.name,
                    )
                )

    _ASSIGNEE_EDITABLE_FIELDS = {'task_state', 'timesheet_ids', 'state'}

    def _check_edit_access(self, vals):
        """
        Enforce creator-only editing for regular employees.

        • Managers, Team Leads, and HR: unrestricted — may edit any task.
        • Regular employees: may edit any field ONLY on tasks they
          personally created (create_uid == current user).
        • Exception: the employee a task is assigned to may still write
          to _ASSIGNEE_EDITABLE_FIELDS (task_state, timesheet_ids) even
          if they didn't create the task — this preserves the core
          task-progression workflow AND timesheet logging. That narrower
          check is layered on top of (not instead of)
          _check_state_transition_access, which already validates the
          assigned_to match for task_state changes specifically.

        Internal/system writes (sudo, e.g. assignment-request approval)
        bypass this check entirely via self.env.su.

        NOTE: this is layered UNDER the project-lock check
        (_check_project_lock_access), which runs first in write()/create()
        and blocks everyone but a Manager when the project is locked.
        """
        if self.env.su or self._is_privileged():
            return

        current_employee = self._get_current_employee()
        assignee_editable_only = set(vals.keys()) <= self._ASSIGNEE_EDITABLE_FIELDS

        for task in self:
            if task.create_uid.id == self.env.uid:
                continue  # creator may edit freely

            if assignee_editable_only and current_employee and task.assigned_to == current_employee:
                continue  # assignee may still progress state / log timesheets

            raise UserError(
                _('You can only edit tasks you created. "%s" was created '
                  'by someone else — contact your Team Lead, HR, or a '
                  'Manager for changes to this task.') % task.name
            )

    # ── Visibility: Python-level filter ───────────────────────────────────────

    @api.model
    def _search(self, domain, offset=0, limit=None, order=None, **kwargs):
        if not self.env.su and not self._is_privileged():
            employee = self.env['hr.employee'].search(
                [('user_id', '=', self.env.uid)], limit=1
            )
            if employee:
                team_domain = [
                    '|', ('team_id', '=', False),
                    '|', ('team_id.member_ids', 'in', [employee.id]),
                    '|', ('team_id.team_lead_id', '=', employee.id),
                    '|', ('assigned_to', '=', employee.id),
                    '|', ('assigned_by', '=', employee.id),
                    ('create_uid', '=', self.env.uid),
                ]
                domain = Domain(list(domain)) & Domain(team_domain)
        return super()._search(domain, offset=offset, limit=limit, order=order, **kwargs)

    # ── Resolve team from project ─────────────────────────────────────────────

    def _resolve_task_team(self, vals):
        if vals.get('team_id'):
            return self.env['team.team'].browse(vals['team_id'])
        project_id = vals.get('project_id') or (self.project_id.id if self else False)
        if project_id:
            project = self.env['project.project'].browse(project_id)
            team = getattr(project, 'team_id', False)
            if team:
                return team
        if self and self.team_id:
            return self.team_id
        return False

    def _handle_cross_team_assignment(self, vals, current_employee):
        assigned_to_id = vals.get('assigned_to')
        if not assigned_to_id:
            return vals, None

        if self._is_manager():
            if 'task_state' not in vals:
                vals['task_state'] = 'assigned'
            return vals, None

        if not current_employee:
            return vals, None

        target_emp = self.env['hr.employee'].browse(assigned_to_id)
        task_team = self._resolve_task_team(vals)
        assignee_teams = self._get_employee_teams(target_emp)

        vals['assigned_by'] = current_employee.id

        if task_team and not vals.get('team_id'):
            vals['team_id'] = task_team.id

        if task_team and task_team in assignee_teams:
            vals['task_state'] = 'assigned'
            return vals, None

        else:
            assigner_teams = self._get_employee_teams(current_employee)
            pending_info = {
                'target_employee_id': assigned_to_id,
                'assigner_teams': assigner_teams,
                'assignee_teams': assignee_teams,
                'task_team': task_team,
            }
            # DO NOT clear assigned_to — keep it visible so the creator
            # can see who the task is intended for while approval is pending.
            # task_state = 'draft' is the signal that it's not yet confirmed.
            vals['task_state'] = 'draft'
            return vals, pending_info

    def _create_assignment_request(self, task, pending_info, current_employee):
        assigner_teams = pending_info['assigner_teams']
        assignee_teams = pending_info['assignee_teams']
        task_team = pending_info.get('task_team')
        self.env['task.assignment.request'].sudo().create({
            'task_id': task.id,
            'requested_by': current_employee.id,
            'requesting_team_id': task_team.id if task_team
            else (assigner_teams[0].id if assigner_teams else False),
            'target_employee_id': pending_info['target_employee_id'],
            'target_team_id': assignee_teams[0].id if assignee_teams else False,
        })

    # ── ORM: create ───────────────────────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        # Project-lock guard: block task creation under a locked project
        # for everyone except a Manager (even HR / Team Lead).
        if not self.env.su and not self._is_completion_manager():
            for vals in vals_list:
                project_id = vals.get('project_id')
                if project_id:
                    project = self.env['project.project'].browse(project_id)
                    self._check_project_lock_access(project)

        current_employee = self._get_current_employee()
        pending_requests = []

        for i, vals in enumerate(vals_list):
            if current_employee and not vals.get('assigned_by'):
                vals['assigned_by'] = current_employee.id

            if not vals.get('team_id') and vals.get('project_id'):
                project = self.env['project.project'].browse(vals['project_id'])
                project_team = getattr(project, 'team_id', False)
                if project_team:
                    vals['team_id'] = project_team.id

            # Bridge user_ids (quick-create "Assignees") → assigned_to
            if 'user_ids' in vals and not vals.get('assigned_to'):
                user_id = None
                for cmd in (vals['user_ids'] or []):
                    if isinstance(cmd, (list, tuple)):
                        if cmd[0] == 6 and cmd[2]:
                            user_id = cmd[2][0]
                            break
                        elif cmd[0] == 4:
                            user_id = cmd[1]
                            break
                if user_id:
                    emp = self.env['hr.employee'].search(
                        [('user_id', '=', user_id)], limit=1
                    )
                    if emp:
                        vals['assigned_to'] = emp.id

            if 'assigned_to' in vals:
                vals, pending_info = self._handle_cross_team_assignment(
                    vals, current_employee
                )
                if pending_info:
                    pending_requests.append((i, pending_info))

        tasks = super().create(vals_list)

        for task_idx, pending_info in pending_requests:
            self._create_assignment_request(
                tasks[task_idx], pending_info, current_employee
            )

        # Deferred notifications — fresh cursor to avoid dead-cursor issues
        notify_pairs = [
            (task.id, task.assigned_to.id)
            for task in tasks
            if task.assigned_to
        ]
        if notify_pairs:
            uid = self.env.uid
            context = dict(self.env.context)
            registry = self.env.registry

            def _send():
                try:
                    with registry.cursor() as cr:
                        env = api.Environment(cr, uid, context)
                        for task_id, emp_id in notify_pairs:
                            t = env['project.task'].browse(task_id)
                            emp = env['hr.employee'].browse(emp_id)
                            t._notify_assigned_employee(emp)
                except Exception as e:
                    _logger.warning("Task assignment notification failed: %s", e)

            self.env.cr.postcommit.add(_send)

        return tasks  # ← must always be the last line, never inside an if block

    # ── ORM: write ────────────────────────────────────────────────────────────

    def write(self, vals):
        # Project-lock guard runs first, and applies even to HR/Team Leads —
        # only a Manager may write to tasks under a locked project.
        if not self.env.su and not self._is_completion_manager():
            for task in self:
                self._check_project_lock_access(task.project_id)
            # Also guard against moving a task INTO a locked project.
            if vals.get('project_id'):
                new_project = self.env['project.project'].browse(vals['project_id'])
                self._check_project_lock_access(new_project)

        self._check_edit_access(vals)

        if 'project_id' in vals and not vals.get('team_id'):
            project = self.env['project.project'].browse(vals['project_id'])
            project_team = getattr(project, 'team_id', False)
            if project_team:
                vals['team_id'] = project_team.id

        # Capture previous assigned_to before the write so we can detect changes
        old_assigned = {task.id: task.assigned_to for task in self} \
            if 'assigned_to' in vals else {}

        if 'assigned_to' not in vals:
            return super().write(vals)

        current_employee = self._get_current_employee()
        vals, pending_info = self._handle_cross_team_assignment(
            vals, current_employee
        )

        result = super().write(vals)

        if pending_info:
            for task in self:
                self._create_assignment_request(
                    task, pending_info, current_employee
                )

        # Notify if assigned_to changed to a real employee
        if old_assigned:
            notify_pairs = [
                (task.id, task.assigned_to.id)
                for task in self
                if task.assigned_to and task.assigned_to != old_assigned.get(task.id)
            ]
            if notify_pairs:
                def _send():
                    for task_id, emp_id in notify_pairs:
                        t = self.env['project.task'].browse(task_id)
                        emp = self.env['hr.employee'].browse(emp_id)
                        t._notify_assigned_employee(emp)

                self.env.cr.postcommit.add(_send)

        return result

    # ── State transitions ─────────────────────────────────────────────────────

    def action_start_progress(self):
        self._check_state_transition_access()
        for task in self:
            if task.task_state == 'assigned':
                task.task_state = 'in_progress'

    def action_mark_completed(self):
        self._check_state_transition_access()
        for task in self:
            if task.task_state == 'in_progress':
                task.task_state = 'completed'

    def action_verify(self):
        self._check_state_transition_access()
        for task in self:
            if task.task_state == 'completed':
                task.task_state = 'verified'

    def action_close(self):
        self._check_state_transition_access()
        for task in self:
            if task.task_state == 'verified':
                # 'state' is Odoo's own native field driving the kanban ball
                # widget and the fade-out/Open-filter exclusion seen when a
                # task is marked Done — setting it here piggybacks on that
                # built-in behavior instead of reimplementing it. task_state
                # stays the source of truth for our own workflow/permissions.
                task.write({
                    'task_state': 'closed',
                    'state': '1_done',
                })

    def action_reset_to_draft(self):
        if not self._is_manager():
            raise UserError(_('Only managers can reset a task to Draft.'))
        for task in self:
            # Symmetric reset — otherwise a reopened task still shows as
            # natively "Done" (faded, hidden from Open filter) even though
            # our own task_state says Draft.
            task.write({
                'task_state': 'draft',
                'state': '01_in_progress',
            })

    def action_view_assignment_requests(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Assignment Requests'),
            'res_model': 'task.assignment.request',
            'view_mode': 'list,form',
            'domain': [('task_id', '=', self.id)],
            'context': {'default_task_id': self.id},
        }

    # ── Notification helper ───────────────────────────────────────────────────

    # In _notify_assigned_employee — remove message_subscribe entirely,
    # just post the message (follower auto-add is less critical)

    # ── Notifications ─────────────────────────────────────────────────────────

    def _notify_assigned_employee(self, employee):
        """Send an inbox notification to the assigned employee."""
        if not employee or not employee.user_id:
            return
        partner = employee.user_id.partner_id
        if not partner:
            return
        self.message_subscribe(partner_ids=[partner.id])
        self.message_notify(
            partner_ids=[partner.id],
            subject=_('Task Assigned to You: %s') % self.name,
            # Markup() marks the static <p>/<b> template as trusted-safe HTML.
            # The %-substitution still escapes each dynamic value
            # individually (employee.name, task name, project name), so
            # this stays safe even if one of those ever contains '<' or
            # '&'. Without Markup(), message_notify can't tell this body
            # apart from plain text and HTML-escapes the whole thing,
            # which is why the tags were showing up literally instead of
            # being rendered.
            body=Markup(
                '<p>Hi %s,</p>'
                '<p>You have been assigned to task <b>%s</b>.</p>'
                '<p>Project: %s</p>'
            ) % (
                employee.name,
                self.name,
                self.project_id.name if self.project_id else _('N/A'),
            ),
        )