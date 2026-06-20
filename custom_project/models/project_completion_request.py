from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ProjectCompletionRequest(models.Model):
    _name = 'project.completion.request'
    _description = 'Project Completion Request'
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

    project_id = fields.Many2one(
        'project.project',
        string='Project',
        required=True,
        ondelete='cascade',
    )

    project_stage_id = fields.Many2one(
        related='project_id.stage_id',
        string='Current Project Stage',
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
        string='Team',
        related='project_id.team_id',
        store=True,
        readonly=True,
    )

    # ── Request details ──────────────────────────────────────────────────────

    reason = fields.Text(
        string='Reason for Request',
        help='Explain why this project is ready to be marked complete.',
    )

    # ── Workflow ──────────────────────────────────────────────────────────────

    state = fields.Selection(
        selection=[
            ('pending', 'Pending'),
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
            project = self.env['project.project'].browse(vals.get('project_id'))
            self._check_requester(project, vals)

            if vals.get('name', 'New') == 'New':
                vals['name'] = (
                        self.env['ir.sequence'].next_by_code('project.completion.request')
                        or 'New'
                )
        return super().create(vals_list)

    # ── Access helpers ───────────────────────────────────────────────────────

    def _check_requester(self, project, vals=None):
        """
        Only the project's own Team Lead (project.team_id.team_lead_id) may
        request completion for that project. Superuser (internal/system
        writes) bypasses this check.
        """
        if self.env.su:
            return

        if not project or not project.team_id:
            raise UserError(
                _('This project has no team assigned, so a completion '
                  'request cannot be submitted.')
            )

        current_employee = self.env['hr.employee'].search(
            [('user_id', '=', self.env.uid)], limit=1
        )
        if not current_employee or project.team_id.team_lead_id != current_employee:
            raise UserError(
                _('Only the Team Lead of "%s" can request completion '
                  'for this project.') % project.team_id.name
            )

        if project.is_locked:
            raise UserError(
                _('This project is already locked as completed.')
            )

        existing_pending = self.search_count([
            ('project_id', '=', project.id),
            ('state', '=', 'pending'),
        ])
        if existing_pending:
            raise UserError(
                _('There is already a pending completion request for '
                  'this project.')
            )

    def _is_approver(self):
        """Only Managers may approve / reject completion requests."""
        return self.env.user.has_group('custom_project.group_team_manager')

    def _check_manager(self):
        if not self._is_approver():
            raise UserError(
                _('Only Managers can approve or reject project '
                  'completion requests.')
            )

    # ── Done-stage resolution ──────────────────────────────────────────────────

    def _get_done_project_stage(self):
        """
        Resolve which project.project.stage represents "Done" for the
        purpose of locking a project on completion approval.

        Odoo's project.project.stage model does not reliably ship an
        is_closed flag across all editions/versions, so we resolve it
        with a few safe fallbacks, in order:

          1. An explicit XML-ID, if you've created/labelled one yourself
             — set DONE_STAGE_XMLID below once you know it (e.g. after
             checking Settings > Technical > Project Stages), e.g.
             'project.project_project_stage_3' or a custom data record.
          2. A stage literally named "Done" (case-insensitive exact match).
          3. The last folded stage (fold=True) ordered by sequence — this
             mirrors Odoo's own kanban convention where folded columns
             represent finished/inactive items.
          4. The highest-sequence stage overall, as a last resort.
        """
        Stage = self.env['project.project.stage'].sudo()

        # 1. Explicit override — fill this in once you've confirmed the
        #    XML-ID of your "Done" stage, then this always wins.
        DONE_STAGE_XMLID = False  # e.g. 'custom_project.project_stage_done'
        if DONE_STAGE_XMLID:
            try:
                return self.env.ref(DONE_STAGE_XMLID)
            except ValueError:
                pass

        # 2. Match by name
        stage = Stage.search([('name', '=ilike', 'Done')], limit=1)
        if stage:
            return stage

        # 3. Last folded stage by sequence
        if 'fold' in Stage._fields:
            stage = Stage.search(
                [('fold', '=', True)], order='sequence desc', limit=1
            )
            if stage:
                return stage

        # 4. Highest-sequence stage as a last resort
        return Stage.search([], order='sequence desc', limit=1)

    # ── Business actions ──────────────────────────────────────────────────────

    def action_approve(self):
        self.ensure_one()
        self._check_manager()

        if self.state != 'pending':
            raise UserError(_('Only Pending requests can be approved.'))

        deciding_employee = self.env['hr.employee'].search(
            [('user_id', '=', self.env.uid)], limit=1
        )

        done_stage = self._get_done_project_stage()
        if not done_stage:
            raise UserError(
                _('No "Done" project stage could be determined. Please '
                  'set one explicitly — see _get_done_project_stage() in '
                  'project_completion_request.py.')
            )

        self.project_id.sudo().write({
            'stage_id': done_stage.id,
            'is_locked': True,
            'locked_by': deciding_employee.id if deciding_employee else False,
            'locked_date': fields.Datetime.now(),
        })

        self.sudo().write({
            'state': 'approved',
            'approved_by': deciding_employee.id if deciding_employee else False,
            'decision_date': fields.Datetime.now(),
        })

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Request Approved'),
                'message': _(
                    'Project "%s" has been marked complete and locked.'
                ) % self.project_id.name,
                'type': 'success',
                'sticky': False,
                'next': {
                    'type': 'ir.actions.act_window',
                    'res_model': 'project.completion.request',
                    'res_id': self.id,
                    'view_mode': 'form',
                    'views': [(False, 'form')],
                    'target': 'current',
                },
            },
        }

    def action_reject(self):
        self.ensure_one()
        self._check_manager()

        if self.state != 'pending':
            raise UserError(_('Only Pending requests can be rejected.'))

        deciding_employee = self.env['hr.employee'].search(
            [('user_id', '=', self.env.uid)], limit=1
        )

        self.sudo().write({
            'state': 'rejected',
            'approved_by': deciding_employee.id if deciding_employee else False,
            'decision_date': fields.Datetime.now(),
        })
        # Project intentionally untouched — stays on its current stage.

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Request Rejected'),
                'message': _('The project completion request has been rejected.'),
                'type': 'warning',
                'sticky': False,
                'next': {
                    'type': 'ir.actions.act_window',
                    'res_model': 'project.completion.request',
                    'res_id': self.id,
                    'view_mode': 'form',
                    'views': [(False, 'form')],
                    'target': 'current',
                },
            },
        }

    # ── Kanban group expander ─────────────────────────────────────────────────

    @api.model
    def _group_expand_states(self, states, domain):
        return [key for key, _label in self._fields['state'].selection]