from odoo import _, api, fields, models


class ProjectCategory(models.Model):
    _name = 'project.category'
    _description = 'Project Category'
    _rec_name = 'name'
    _order = 'name'

    name = fields.Char(
        string='Category Name',
        required=True,
    )

    description = fields.Text(
        string='Description',
        help='Describe the type of projects that fall under this category.',
    )

    active = fields.Boolean(
        default=True,
    )

    # ── Computed stats ────────────────────────────────────────────────────────

    project_count = fields.Integer(
        compute='_compute_project_count',
        string='Projects',
    )

    avg_hours = fields.Float(
        compute='_compute_avg_hours',
        string='Avg Hours (Completed)',
        digits=(10, 1),
        help='Average total hours logged across all completed projects '
             'in this category.',
    )

    @api.depends('name')
    def _compute_project_count(self):
        Project = self.env['project.project']
        for cat in self:
            cat.project_count = Project.search_count([
                ('project_category_id', '=', cat.id),
            ])

    @api.depends('name')
    def _compute_avg_hours(self):
        Project = self.env['project.project']
        for cat in self:
            completed = Project.search([
                ('project_category_id', '=', cat.id),
                ('last_update_status', '=', 'done'),
            ])
            if completed:
                cat.avg_hours = sum(
                    p.total_hours_spent for p in completed
                ) / len(completed)
            else:
                cat.avg_hours = 0.0

    # ── Smart button action ───────────────────────────────────────────────────

    def action_view_projects(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('%s – Projects') % self.name,
            'res_model': 'project.project',
            'view_mode': 'list,form',
            'domain': [('project_category_id', '=', self.id)],
        }

    # ── Unique name constraint ────────────────────────────────────────────────

    @api.constrains('name')
    def _constrains_unique_name(self):
        for cat in self:
            if self.search_count([('name', '=', cat.name), ('id', '!=', cat.id)]):
                raise models.ValidationError(
                    _('A category named "%s" already exists.') % cat.name
                )