from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.osv import expression


class ProjectProject(models.Model):
    _inherit = 'project.project'

    # ── Fields ──────────────────────────────────────────────────────────────

    project_number = fields.Char(
        string='Project Number',
        readonly=True,
        copy=False,
        help='Auto-generated sequential project number (e.g. 001, 002, …).',
    )

    crm_lead_id = fields.Many2one(
        'crm.lead',
        string='Source Query',
        readonly=True,
        copy=False,
    )

    team_id = fields.Many2one(
        'team.team',
        string='Project Team',
        tracking=True,
        domain=[('active', '=', True)],
        help='The team responsible for this project.',
    )

    # ── Visibility: Python-level filter (bypasses record rule noupdate issues) ──

    def _is_privileged(self):
        """Managers and HR see all projects — no team restriction."""
        return (
            self.env.user.has_group('custom_project.group_team_manager')
            or self.env.user.has_group('hr.group_hr_user')
        )

    @api.model
    def _search(self, domain, offset=0, limit=None, order=None):
        """
        Enforce team-based project visibility at the ORM level.
        This fires on every search (list, kanban, Many2one dropdowns, etc.)
        and is immune to record rule noupdate issues.

        Employees see:
          - Projects with no team assigned (visible to everyone)
          - Projects where they are a member of the assigned team
          - Projects where they are the team lead of the assigned team

        Managers and HR see everything.
        sudo() calls (self.env.su) are never restricted.
        """
        if not self.env.su and not self._is_privileged():
            employee = self.env['hr.employee'].search(
                [('user_id', '=', self.env.uid)], limit=1
            )
            if employee:
                team_domain = [
                    '|', ('team_id', '=', False),
                    '|', ('team_id.member_ids', 'in', [employee.id]),
                         ('team_id.team_lead_id', '=', employee.id),
                ]
                domain = expression.AND([list(domain), team_domain])
        return super()._search(domain, offset=offset, limit=limit, order=order)

    # ── ORM override: auto-assign project number on every create ────────────

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('project_number'):
                vals['project_number'] = (
                    self.env['ir.sequence'].next_by_code('custom.project.number')
                    or ''
                )
        return super().create(vals_list)

    # ── Actions ─────────────────────────────────────────────────────────────

    def action_open_source_query(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Source Query'),
            'res_model': 'crm.lead',
            'res_id': self.crm_lead_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    # ── Guards ───────────────────────────────────────────────────────────────

    def unlink(self):
        if any(p.crm_lead_id for p in self):
            raise UserError(
                _('Projects created from a CRM opportunity cannot be deleted.')
            )
        return super().unlink()

    def write(self, vals):
        if 'active' in vals and not vals['active']:
            if any(p.crm_lead_id for p in self):
                raise UserError(
                    _('Projects linked to a CRM opportunity cannot be archived.')
                )
        return super().write(vals)