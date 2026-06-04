from odoo import _, api, fields, models
from odoo.exceptions import UserError


class TaskAssignmentRequest(models.Model):
    _name = 'task.assignment.request'
    _description = 'Task Assignment Request'
    _rec_name = 'name'
    _order = 'create_date desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    # ── Core fields ───────────────────────────────────────────────────────────

    name = fields.Char(
        string='Reference',
        readonly=True,
        default='New',
        copy=False,
    )

    task_id = fields.Many2one(
        'project.task',
        string='Task',
        required=True,
        ondelete='cascade',
    )

    task_state = fields.Selection(
        related='task_id.task_state',
        string='Task State',
        readonly=True,
        store=False,
    )

    requested_by = fields.Many2one(
        'hr.employee',
        string='Requested By',
        required=True,
        default=lambda self: self.env['hr.employee'].search(
            [('user_id', '=', self.env.uid)], limit=1
        ),
    )

    requesting_team_id = fields.Many2one(
        'team.team',
        string='Requesting Team',
    )

    target_employee_id = fields.Many2one(
        'hr.employee',
        string='Target Employee',
        required=True,
    )

    target_team_id = fields.Many2one(
        'team.team',
        string='Target Team',
    )

    # ── Request details ───────────────────────────────────────────────────────

    reason = fields.Text(
        string='Reason for Request',
        help='Explain why this task needs to go to a different team.',
    )

    # ── Workflow ──────────────────────────────────────────────────────────────

    state = fields.Selection(
        selection=[
            ('pending',  'Pending'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected'),
        ],
        string='Status',
        default='pending',
        tracking=True,
        copy=False,
        group_expand='_group_expand_states',
    )

    manager_comment = fields.Text(
        string='Manager Comment',
        help='Comment from the manager when approving or rejecting.',
    )

    approved_by = fields.Many2one(
        'hr.employee',
        string='Decided By',
        readonly=True,
        copy=False,
    )

    decision_date = fields.Datetime(
        string='Decision Date',
        readonly=True,
        copy=False,
    )

    # ── Sequence ──────────────────────────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = (
                    self.env['ir.sequence'].next_by_code('task.assignment.request')
                    or 'New'
                )
        return super().create(vals_list)

    # ── Business actions ──────────────────────────────────────────────────────

    def _check_manager(self):
        if not (
            self.env.user.has_group('custom_project.group_team_manager')
            or self.env.user.has_group('project.group_project_manager')
        ):
            raise UserError(
                _('Only Managers can approve or reject assignment requests.')
            )

    def action_approve(self):
        """
        Manager approves the cross-team request:
        • Assign the task to the target employee
        • Set the task state to Assigned
        • Move the request to Approved
        """
        self.ensure_one()
        self._check_manager()

        if self.state != 'pending':
            raise UserError(_('Only Pending requests can be approved.'))

        deciding_employee = self.env['hr.employee'].search(
            [('user_id', '=', self.env.uid)], limit=1
        )

        self.task_id.sudo().write({
            'assigned_to': self.target_employee_id.id,
            'team_id':     self.target_team_id.id if self.target_team_id else False,
            'task_state':  'assigned',
        })

        self.write({
            'state':         'approved',
            'approved_by':   deciding_employee.id if deciding_employee else False,
            'decision_date': fields.Datetime.now(),
        })

        return {
            'type': 'ir.actions.client',
            'tag':  'display_notification',
            'params': {
                'title':   _('Request Approved'),
                'message': _(
                    'Task "%s" has been assigned to %s.'
                ) % (self.task_id.name, self.target_employee_id.name),
                'type':    'success',
                'sticky':  False,
            },
        }

    def action_reject(self):
        """
        Manager rejects the request:
        • Task remains unassigned (state stays Draft)
        • Request moves to Rejected
        """
        self.ensure_one()
        self._check_manager()

        if self.state != 'pending':
            raise UserError(_('Only Pending requests can be rejected.'))

        deciding_employee = self.env['hr.employee'].search(
            [('user_id', '=', self.env.uid)], limit=1
        )

        self.write({
            'state':         'rejected',
            'approved_by':   deciding_employee.id if deciding_employee else False,
            'decision_date': fields.Datetime.now(),
        })

        return {
            'type': 'ir.actions.client',
            'tag':  'display_notification',
            'params': {
                'title':   _('Request Rejected'),
                'message': _('The assignment request has been rejected.'),
                'type':    'warning',
                'sticky':  False,
            },
        }

    # ── Kanban group expander ─────────────────────────────────────────────────

    @api.model
    def _group_expand_states(self, states, domain):
        return [key for key, _label in self._fields['state'].selection]