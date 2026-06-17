from odoo import _, api, fields, models


class ProjectProject(models.Model):
    _inherit = 'project.project'

    team_id = fields.Many2one(
        'team.team',
        string='Team',
        tracking=True,
        help='The team responsible for this project. '
             'Tasks created under this project inherit this team automatically.',
    )
    # ── Category & estimation fields ──────────────────────────────────────────

    project_category_id = fields.Many2one(
        'project.category',
        string='Project Category',
        tracking=True,
        help='Category used to group similar projects for estimation purposes.',
    )

    planned_hours = fields.Float(
        string='Planned Hours',
        digits=(10, 1),
        help='Estimated total hours to complete this project. '
             'Use the historical average from similar past projects as a guide.',
    )

    # ── Computed: total hours logged across all tasks ─────────────────────────

    total_hours_spent = fields.Float(
        string='Hours Logged',
        compute='_compute_total_hours_spent',
        store=True,
        digits=(10, 1),
        help='Sum of all timesheet hours logged across every task in this project.',
    )

    hours_progress = fields.Integer(
        string='Hours Progress (%)',
        compute='_compute_hours_progress',
        store=False,
        help='Percentage of planned hours consumed.',
    )

    # ── Computed: estimation helper (similar completed projects) ──────────────

    similar_project_count = fields.Integer(
        compute='_compute_similar_stats',
        string='Similar Projects',
        store=False,
        help='Number of completed projects in the same category.',
    )

    avg_hours_similar = fields.Float(
        compute='_compute_similar_stats',
        string='Avg Hours (Similar)',
        digits=(10, 1),
        store=False,
        help='Average total hours logged across completed projects '
             'in the same category — useful as a delivery estimate baseline.',
    )

    min_hours_similar = fields.Float(
        compute='_compute_similar_stats',
        string='Min Hours (Similar)',
        digits=(10, 1),
        store=False,
    )

    max_hours_similar = fields.Float(
        compute='_compute_similar_stats',
        string='Max Hours (Similar)',
        digits=(10, 1),
        store=False,
    )

    # ── Computes ──────────────────────────────────────────────────────────────

    @api.depends('task_ids.effective_hours')
    def _compute_total_hours_spent(self):
        for project in self:
            project.total_hours_spent = sum(
                task.effective_hours for task in project.sudo().task_ids
            )

    @api.depends('planned_hours', 'total_hours_spent')
    def _compute_hours_progress(self):
        for project in self:
            if project.planned_hours > 0:
                project.hours_progress = int(
                    (project.total_hours_spent / project.planned_hours) * 100
                )
            else:
                project.hours_progress = 0

    @api.depends('project_category_id')
    def _compute_similar_stats(self):
        for project in self:
            if not project.project_category_id:
                project.similar_project_count = 0
                project.avg_hours_similar    = 0.0
                project.min_hours_similar    = 0.0
                project.max_hours_similar    = 0.0
                continue

            similar = self.search([
                ('project_category_id', '=', project.project_category_id.id),
                ('last_update_status',  '=', 'done'),
                ('id',                  '!=', project.id),
            ])

            if not similar:
                project.similar_project_count = 0
                project.avg_hours_similar    = 0.0
                project.min_hours_similar    = 0.0
                project.max_hours_similar    = 0.0
                continue

            hours_list = [p.total_hours_spent for p in similar]
            project.similar_project_count = len(similar)
            project.avg_hours_similar     = sum(hours_list) / len(hours_list)
            project.min_hours_similar     = min(hours_list)
            project.max_hours_similar     = max(hours_list)

    # ── Smart button: open similar completed projects ─────────────────────────

    def action_view_similar_projects(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Similar Completed Projects — %s') % self.project_category_id.name,
            'res_model': 'project.project',
            'view_mode': 'list,form',
            'domain': [
                ('project_category_id', '=', self.project_category_id.id),
                ('last_update_status',  '=', 'done'),
                ('id',                  '!=', self.id),
            ],
            'context': {
                'create': False,  # read-only reference view
            },
        }

    # ── Project create: auto-link default stages ──────────────────────────────

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

        return super(ProjectProject, self.sudo()).create(vals_list)