from odoo import api, fields, models, _
from odoo.exceptions import UserError


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    # ── Fields ──────────────────────────────────────────────────────────────

    is_converted = fields.Boolean(
        string='Converted to Project',
        default=False,
        copy=False,
        help='Set to True after this query has been converted to a project. '
             'Once set, the record becomes read-only and cannot be converted again.',
    )

    project_id = fields.Many2one(
        'project.project',
        string='Linked Project',
        readonly=True,
        copy=False,
        help='The project that was created from this CRM query.',
    )

    project_count = fields.Integer(
        string='Project Count',
        compute='_compute_project_count',
    )

    # ── Compute ─────────────────────────────────────────────────────────────

    @api.depends('project_id')
    def _compute_project_count(self):
        for lead in self:
            lead.project_count = 1 if lead.project_id else 0

    # ── Business Logic ───────────────────────────────────────────────────────

    def action_convert_to_project(self):
        """
        Manual one-time conversion of a Won CRM opportunity into a Project.

        Rules (from V3 spec §10):
        - Only HR or Manager can trigger this (enforced via groups= on the button).
        - Opportunity MUST be in a Won stage (stage_id.is_won = True).
        - Conversion can occur only once.
        - Client details + query description are copied to the project.
        - Project number is auto-generated from a simple running sequence.
        - After conversion the query is linked to the project.
        - Returns an action that redirects the user to the new project form.
        """
        self.ensure_one()

        # Guard 1: opportunity must be Won before conversion is allowed
        if not self.stage_id.is_won:
            raise UserError(
                _('Only Won opportunities can be converted to a project.\n\n'
                  'Please mark this opportunity as Won before converting.')
            )

        # Guard 2: prevent duplicate conversion
        if self.is_converted:
            raise UserError(
                _('This query has already been converted to a project. '
                  'No further conversion is allowed.')
            )

        # Generate project number from sequence (001, 002, …)
        project_number = self.env['ir.sequence'].next_by_code('custom.project.number')
        if not project_number:
            raise UserError(
                _('Project number sequence not found. '
                  'Please contact your system administrator.')
            )

        # Build project values — copy client details and description from query
        project_vals = {
            'name': self.name,
            'partner_id': self.partner_id.id if self.partner_id else False,
            'description': self.description or '',
            'project_number': project_number,
            'crm_lead_id': self.id,
        }

        project = self.env['project.project'].create(project_vals)

        # Mark the query as converted and store the link.
        # sudo() ensures this internal write is never blocked by record rules
        # on won/closed leads in certain Odoo configurations.
        self.sudo().write({
            'is_converted': True,
            'project_id': project.id,
        })

        # Redirect user to the newly created project form
        return {
            'type': 'ir.actions.act_window',
            'name': _('Project'),
            'res_model': 'project.project',
            'res_id': project.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_open_linked_project(self):
        """Smart-button action: open the linked project."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Project'),
            'res_model': 'project.project',
            'res_id': self.project_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    # ── Override: block delete / archive after conversion ────────────────────
    #
    # WHY the previous write() override was removed:
    #   Odoo calls write() internally during unlink() (to clear Many2one
    #   back-references on related records). A broad write() guard intercepts
    #   those system writes and raises a UserError BEFORE unlink() is reached,
    #   so the actual delete guard never fires. The ORM catches the error in some
    #   code paths and the deletion still appears to succeed from the UI.
    #
    #   The correct Odoo-idiomatic approach is:
    #     • UI read-only  → handled via readonly="is_converted" in the VIEW
    #     • Delete guard  → unlink() override (below)
    #     • Archive guard → narrow write() override that only checks 'active'

    def unlink(self):
        """Prevent deletion of converted opportunities (spec §10)."""
        if any(lead.is_converted for lead in self):
            raise UserError(
                _('Converted opportunities cannot be deleted. '
                  'They must be kept for traceability with the linked project.')
            )
        return super().unlink()

    def write(self, vals):
        """
        Block archiving (active=False) of converted opportunities.
        This is deliberately narrow — only the 'active' key is checked,
        so all other Odoo-internal writes pass through normally.
        """
        if 'active' in vals and not vals['active']:
            if any(lead.is_converted for lead in self):
                raise UserError(
                    _('Converted opportunities cannot be archived. '
                      'They must remain visible for traceability.')
                )
        return super().write(vals)