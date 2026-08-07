from odoo import models, fields, api


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    work_report_team_lead_user_ids = fields.Many2many(
        'res.users',
        compute='_compute_work_report_team_lead_user_ids',
        store=True,
        string='Work Report Team Leads (technical)',
        help='Technical bridge field: users who lead a team.team this '
             'employee belongs to. Used only to make team-lead visibility '
             'searchable in ir.rule, since team.team.team_lead_id is not '
             'reachable via the non-stored team_ids field on hr.employee.',
    )

    @api.depends('team_ids.team_lead_id.user_id')
    def _compute_work_report_team_lead_user_ids(self):
        for emp in self:
            emp.work_report_team_lead_user_ids = emp.team_ids.mapped('team_lead_id.user_id')