from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ProjectTask(models.Model):
    _inherit = 'project.task'

    # ── Custom fields ─────────────────────────────────────────────────────────

    assigned_by = fields.Many2one(
        'hr.employee',
        string='Assigned By',
        copy=False,
        tracking=True,
        readonly=True,
        help='The employee who created / assigned this task.',
    )

    assigned_to = fields.Many2one(
        'hr.employee',
        string='Assigned To',
        copy=False,
        tracking=True,
        help='The employee responsible for completing this task.',
    )

    team_id = fields.Many2one(
        'team.team',
        string='Team',
        tracking=True,
        help='The team this task belongs to.',
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
        """Always show all state columns in the Kanban even if empty."""
        return [key for key, _label in self._fields['task_state'].selection]

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _get_current_employee(self):
        """Return the hr.employee record linked to the current user, or False."""
        return self.env['hr.employee'].search(
            [('user_id', '=', self.env.uid)], limit=1
        )

    def _get_employee_teams(self, employee):
        """
        Return all teams the employee belongs to — either as a member
        or as the designated Team Lead.
        """
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

    # ── ORM override: business rule on create ─────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        """
        Enforce team-based assignment rules on task creation.

        • Same-team assignment  → task created with state = Assigned
        • Cross-team assignment → task created in Draft (assigned_to cleared),
                                   a TaskAssignmentRequest is auto-created
        • Manager / no employee → no restriction, state left as-is
        """
        current_employee = self._get_current_employee()
        is_manager = self._is_manager()

        pending_requests = []   # list of (index_in_vals, request_info_dict)

        if not is_manager and current_employee:
            for i, vals in enumerate(vals_list):
                assigned_to_id = vals.get('assigned_to')
                if not assigned_to_id:
                    continue

                target_emp = self.env['hr.employee'].browse(assigned_to_id)
                assigner_teams = self._get_employee_teams(current_employee)
                assignee_teams = self._get_employee_teams(target_emp)
                common_teams   = assigner_teams & assignee_teams

                # Always record who is assigning
                vals['assigned_by'] = current_employee.id

                if common_teams:
                    # ── Same-team: assign directly ───────────────────────────
                    vals['task_state'] = 'assigned'
                    vals.setdefault('team_id', common_teams[0].id)
                else:
                    # ── Cross-team: hold for manager approval ────────────────
                    vals['task_state'] = 'draft'
                    # Remove the direct assignment — will be set after approval
                    vals['assigned_to'] = False

                    pending_requests.append((i, {
                        'target_employee_id': assigned_to_id,
                        'assigner_teams':     assigner_teams,
                        'assignee_teams':     assignee_teams,
                    }))

        tasks = super().create(vals_list)

        # Create assignment requests AFTER the task records exist
        for task_idx, req_info in pending_requests:
            task = tasks[task_idx]
            assigner_teams = req_info['assigner_teams']
            assignee_teams = req_info['assignee_teams']
            self.env['task.assignment.request'].create({
                'task_id':            task.id,
                'requested_by':       current_employee.id,
                'requesting_team_id': assigner_teams[0].id if assigner_teams else False,
                'target_employee_id': req_info['target_employee_id'],
                'target_team_id':     assignee_teams[0].id if assignee_teams else False,
            })

        return tasks

    # ── State-transition actions ───────────────────────────────────────────────

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
        """Allow manager to reset a task back to Draft."""
        if not self._is_manager():
            raise UserError(_('Only managers can reset a task to Draft.'))
        for task in self:
            task.task_state = 'draft'

    # ── Smart-button action ───────────────────────────────────────────────────

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