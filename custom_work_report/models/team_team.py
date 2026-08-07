from odoo import models, api


class TeamTeam(models.Model):
    _inherit = 'team.team'

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._sync_work_report_team_lead_group()
        return records

    def write(self, vals):
        res = super().write(vals)
        if 'team_lead_id' in vals:
            self._sync_work_report_team_lead_group()
        return res

    def _sync_work_report_team_lead_group(self):
        """
        Keeps custom_work_report.group_work_report_team_lead in sync with
        who actually leads a team.team right now, so the 'My Team's
        Reports' menu is only visible to current leads, not every
        employee. Adds the current lead's user, and removes anyone who
        no longer leads any team.
        """
        group = self.env.ref(
            'custom_work_report.group_work_report_team_lead',
            raise_if_not_found=False,
        )
        if not group:
            return

        all_teams = self.sudo().search([])
        current_lead_users = all_teams.mapped('team_lead_id.user_id')

        existing_group_users = self.env['res.users'].sudo().search(
            [('group_ids', 'in', group.id)]
        )

        stale_users = existing_group_users - current_lead_users
        for u in stale_users:
            u.sudo().write({'group_ids': [(3, group.id)]})

        for u in current_lead_users:
            u.sudo().write({'group_ids': [(4, group.id)]})