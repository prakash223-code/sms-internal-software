from odoo import _, fields, models
from odoo.exceptions import UserError


class ProjectProject(models.Model):
    _inherit = 'project.project'

    # ── Fields ──────────────────────────────────────────────────────────────

    project_number = fields.Char(
        string='Project Number',
        readonly=True,
        copy=False,
        help='Auto-generated sequential project number (e.g. 001, 002, …). '
             'Assigned at the time of conversion from a CRM query.',
    )

    crm_lead_id = fields.Many2one(
        'crm.lead',
        string='Source Query',
        readonly=True,
        copy=False,
        help='The CRM query that was converted into this project.',
    )

    # ── Actions ─────────────────────────────────────────────────────────────

    def action_open_source_query(self):
        """Smart-button action: open the originating CRM query."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Source Query'),
            'res_model': 'crm.lead',
            'res_id': self.crm_lead_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    # ── Override: block delete / archive of CRM-linked projects ─────────────

    def unlink(self):
        """
        Prevent deletion of projects that were created from a CRM query.
        These must be preserved for CRM ↔ Project traceability.
        """
        if any(p.crm_lead_id for p in self):
            raise UserError(
                _('Projects created from a CRM opportunity cannot be deleted. '
                  'They are linked to a query and must be kept for traceability.')
            )
        return super().unlink()

    def write(self, vals):
        """
        Block archiving (active=False) of CRM-linked projects.
        Narrow guard — only 'active' is checked so normal Odoo writes pass through.
        """
        if 'active' in vals and not vals['active']:
            if any(p.crm_lead_id for p in self):
                raise UserError(
                    _('Projects linked to a CRM opportunity cannot be archived. '
                      'They must remain active for traceability.')
                )
        return super().write(vals)