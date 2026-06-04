from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.osv import expression


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

    task_priority = fields.Selection(
        selection=[
            ('low',      'Low'),
            ('normal',   'Normal'),
            ('high',     'High'),
            ('critical', 'Critical'),
        ],
        string='Task Priority',
        default='normal',
        tracking=True,
    )

    task_state = fields.Selection(
        selection=[
            ('draft',       'Draft'),
            ('assigned',    'Assigned'),
            ('in_progress', 'In Progress'),
            ('completed',   'Completed'),
            ('verified',    'Verified'),
            ('closed',      'Closed'),
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

    # ── Computes ──────────────────────────────────────────────────────────────

    def _compute_assignment_request_count(self):
        for task in self:
            task.assignment_request_count = self.env[
                'task.assignment.request'
            ].sudo().search_count([('task_id', '=', task.id)])

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
        """Managers and HR bypass all team restrictions."""
        return (
            self.env.user.has_group('custom_project.group_team_manager')
            or self.env.user.has_group('hr.group_hr_user')
        )

    # ── Visibility: Python-level filter ───────────────────────────────────────

    @api.model
    def _search(self, domain, offset=0, limit=None, order=None):
        """
        Enforce team-based task visibility at the ORM level.

        Employees see:
          - Tasks with no team assigned
          - Tasks in their team
          - Tasks assigned TO them (cross-team approved tasks)
          - Tasks they created/assigned (assigned_by)

        Managers and HR see everything.
        sudo() calls are never restricted.
        """
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
                         ('assigned_by', '=', employee.id),
                ]
                domain = expression.AND([list(domain), team_domain])
        return super()._search(domain, offset=offset, limit=limit, order=order)

    # ── Resolve team from project ─────────────────────────────────────────────

    def _resolve_task_team(self, vals):
        if vals.get('team_id'):
            return self.env['team.team'].browse(vals['team_id'])
        project_id = vals.get('project_id') or (self.project_id.id if self else False)
        if project_id:
            project = self.env['project.project'].browse(project_id)
            if project.team_id:
                return project.team_id
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

        target_emp    = self.env['hr.employee'].browse(assigned_to_id)
        task_team     = self._resolve_task_team(vals)
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
                'assigner_teams':     assigner_teams,
                'assignee_teams':     assignee_teams,
                'task_team':          task_team,
            }
            vals['assigned_to'] = False
            vals['task_state']  = 'draft'
            return vals, pending_info

    def _create_assignment_request(self, task, pending_info, current_employee):
        assigner_teams = pending_info['assigner_teams']
        assignee_teams = pending_info['assignee_teams']
        task_team      = pending_info.get('task_team')
        self.env['task.assignment.request'].sudo().create({
            'task_id':            task.id,
            'requested_by':       current_employee.id,
            'requesting_team_id': task_team.id if task_team
                                  else (assigner_teams[0].id if assigner_teams else False),
            'target_employee_id': pending_info['target_employee_id'],
            'target_team_id':     assignee_teams[0].id if assignee_teams else False,
        })

    # ── ORM: create ───────────────────────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        current_employee = self._get_current_employee()
        pending_requests = []

        for i, vals in enumerate(vals_list):
            if not vals.get('team_id') and vals.get('project_id'):
                project = self.env['project.project'].browse(vals['project_id'])
                if project.team_id:
                    vals['team_id'] = project.team_id.id

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

        return tasks

    # ── ORM: write ────────────────────────────────────────────────────────────

    def write(self, vals):
        if 'project_id' in vals and not vals.get('team_id'):
            project = self.env['project.project'].browse(vals['project_id'])
            if project.team_id:
                vals['team_id'] = project.team_id.id

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

        return result

    # ── State transitions ─────────────────────────────────────────────────────

    def action_start_progress(self):
        for task in self:
            if task.task_state == 'assigned':
                task.task_state = 'in_progress'

    def action_mark_completed(self):
        for task in self:
            if task.task_state == 'in_progress':
                task.task_state = 'completed'

    def action_verify(self):
        for task in self:
            if task.task_state == 'completed':
                task.task_state = 'verified'

    def action_close(self):
        for task in self:
            if task.task_state == 'verified':
                task.task_state = 'closed'

    def action_reset_to_draft(self):
        if not self._is_manager():
            raise UserError(_('Only managers can reset a task to Draft.'))
        for task in self:
            task.task_state = 'draft'

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