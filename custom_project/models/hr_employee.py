from odoo import _, api, fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    team_ids = fields.Many2many(
        'team.team',
        'team_member_rel',
        'employee_id',
        'team_id',
        string='Teams',
        readonly=True,
        help='Teams this employee belongs to (managed from the Team form).',
    )

    team_count = fields.Integer(
        compute='_compute_team_count',
        string='Team Count',
    )

    is_team_lead_of_any = fields.Boolean(
        compute='_compute_is_team_lead_of_any',
        string='Is Team Lead',
        store=False,
        help='True when this employee is the Team Lead of at least one team.',
    )

    @api.depends('team_ids')
    def _compute_team_count(self):
        for emp in self:
            emp.team_count = len(emp.team_ids)

    @api.depends('team_ids.team_lead_id')
    def _compute_is_team_lead_of_any(self):
        for emp in self:
            emp.is_team_lead_of_any = any(
                t.team_lead_id == emp for t in emp.team_ids
            )

    def action_view_my_tasks(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('%s – Tasks') % self.name,
            'res_model': 'project.task',
            'view_mode': 'kanban,list,form',
            'domain': [
                '|',
                ('assigned_to', '=', self.id),
                ('assigned_by', '=', self.id),
            ],
        }

    def action_view_teams(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('%s – Teams') % self.name,
            'res_model': 'team.team',
            'view_mode': 'list,form',
            'domain': [('member_ids', 'in', self.id)],
        }


class HrEmployeePublic(models.Model):
    """
    Mirror team_ids onto hr.employee.public so that domain filters
    using team_ids work correctly when many2one_avatar_employee widgets
    run their name_search against the public model.
    Uses the identical relation table (team_member_rel) so no extra
    DB columns are created — it's just a second ORM-level declaration
    over the same join table.
    """
    _inherit = 'hr.employee.public'

    team_ids = fields.Many2many(
        'team.team',
        'team_member_rel',
        'employee_id',
        'team_id',
        string='Teams',
        readonly=True,
    )