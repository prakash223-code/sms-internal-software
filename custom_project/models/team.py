from odoo import _, api, fields, models


class Team(models.Model):
    _name = 'team.team'
    _description = 'Project Team'
    _rec_name = 'name'
    _order = 'name'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    # ── Core fields ──────────────────────────────────────────────────────────

    name = fields.Char(string='Team Name', required=True, tracking=True)

    team_lead_id = fields.Many2one(
        'hr.employee',
        string='Team Lead',
        tracking=True,
        help='The employee responsible for this team. '
             'Team leads can view all tasks inside the team.',
    )

    member_ids = fields.Many2many(
        'hr.employee',
        'team_member_rel',
        'team_id',
        'employee_id',
        string='Members',
        help='All employees who belong to this team.',
    )

    active = fields.Boolean(default=True, string='Active')

    description = fields.Text(string='Description')

    # ── Computed / stat fields ───────────────────────────────────────────────

    member_count = fields.Integer(
        compute='_compute_member_count',
        string='Member Count',
    )

    task_count = fields.Integer(
        compute='_compute_task_count',
        string='Task Count',
    )

    # ── Computes ─────────────────────────────────────────────────────────────

    @api.depends('member_ids')
    def _compute_member_count(self):
        for team in self:
            # sudo() is required: Odoo 19's hr.employee._check_private_fields()
            # raises AccessError for non-HR users even when the ORM only needs
            # the 'active' field (used internally by filtered(active) during
            # Many2many resolution). sudo() propagates to the resulting
            # hr.employee recordset, bypassing the private-field check while
            # still correctly excluding archived employees.
            team.member_count = len(team.sudo().member_ids)

    def _compute_task_count(self):
        Task = self.env['project.task']
        for team in self:
            team.task_count = Task.search_count([('team_id', '=', team.id)])

    # ── Smart-button actions ──────────────────────────────────────────────────

    def action_view_tasks(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('%s – Tasks') % self.name,
            'res_model': 'project.task',
            'view_mode': 'kanban,list,form',
            'domain': [('team_id', '=', self.id)],
            'context': {
                'default_team_id': self.id,
                'search_default_team_id': self.id,
            },
        }

    def action_view_members(self):
        self.ensure_one()
        # sudo() required for the same reason as _compute_member_count:
        # accessing .member_ids on a non-HR user context triggers
        # hr.employee._check_private_fields() via filtered(active).
        member_ids = self.sudo().member_ids.ids
        return {
            'type': 'ir.actions.act_window',
            'name': _('%s – Members') % self.name,
            'res_model': 'hr.employee',
            'view_mode': 'list,form',
            'domain': [('id', 'in', member_ids)],
        }

    # ── Unique name constraint ────────────────────────────────────────────────

    @api.constrains('name')
    def _constrains_unique_name(self):
        for team in self:
            domain = [('name', '=', team.name), ('id', '!=', team.id)]
            if self.search_count(domain):
                raise models.ValidationError(
                    _('A team named "%s" already exists.') % team.name
                )