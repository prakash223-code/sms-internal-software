from odoo import models, fields, api
from odoo.exceptions import UserError


class ProjectDocument(models.Model):
    _name = 'project.document'
    _description = 'Project Document'
    _order = 'upload_date desc, id desc'
    _rec_name = 'name'

    # ------------------------------------------------------------------
    # FIELDS
    # ------------------------------------------------------------------

    project_id = fields.Many2one(
        'project.project',
        string='Project',
        required=True,
        ondelete='cascade',
        index=True,
    )

    name = fields.Char(
        string='Document Name',
        required=True,
        help='e.g. Project Contract, Design Blueprint, Client Approval',
    )

    document_type = fields.Selection([
        ('contract',     'Contract / Agreement'),
        ('blueprint',    'Blueprint / Design'),
        ('report',       'Report'),
        ('invoice',      'Invoice / Quotation'),
        ('approval',     'Client Approval'),
        ('minutes',      'Meeting Minutes'),
        ('handover',     'Handover Document'),
        ('other',        'Other'),
    ], string='Document Type', required=True, default='other')

    file = fields.Binary(
        string='File',
        required=True,
        attachment=True,
    )

    filename = fields.Char(string='File Name')

    file_type = fields.Char(
        string='File Type',
        compute='_compute_file_type',
        store=True,
        help='File extension extracted from the uploaded filename.',
    )

    file_url = fields.Char(
        string='Preview',
        compute='_compute_file_url',
        help='Opens the file inline in the browser without downloading.',
    )

    upload_date = fields.Date(
        string='Upload Date',
        default=fields.Date.today,
        readonly=True,
    )

    uploaded_by = fields.Many2one(
        'res.users',
        string='Uploaded By',
        default=lambda self: self.env.uid,
        readonly=True,
    )

    notes = fields.Text(
        string='Notes',
        help='Optional remarks about this document.',
    )

    # Computed flag exposed to the view layer so fields can be made
    # readonly without duplicating the group-check logic in XML.
    can_write = fields.Boolean(
        compute='_compute_can_write',
        help='True when the current user may create / edit / delete documents.',
    )

    # ------------------------------------------------------------------
    # COMPUTED
    # ------------------------------------------------------------------

    @api.depends('filename')
    def _compute_file_type(self):
        for rec in self:
            if rec.filename and '.' in rec.filename:
                rec.file_type = rec.filename.rsplit('.', 1)[-1].upper()
            else:
                rec.file_type = '—'

    @api.depends('file', 'filename')
    def _compute_file_url(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        for rec in self:
            if rec.file and rec.id:
                rec.file_url = f'{base_url}/project/document/preview/{rec.id}'
            else:
                rec.file_url = False

    def _compute_can_write(self):
        result = self._user_can_write()
        for rec in self:
            rec.can_write = result

    # ------------------------------------------------------------------
    # ACCESS HELPERS
    # ------------------------------------------------------------------

    def _user_can_write(self):
        """
        Returns True for Manager, HR, and Team Lead employees.
        Plain project users are read-only.

        Team Lead status is NOT a stored field on hr.employee — it is
        derived from team.team.team_lead_id (defined in custom_project).
        An employee is a team lead if they are set as team_lead_id on
        at least one team.team record.
        """
        user = self.env.user

        if user.has_group('project.group_project_manager'):
            return True

        if user.has_group('hr.group_hr_user'):
            return True

        employee = self.env['hr.employee'].sudo().search(
            [('user_id', '=', user.id)], limit=1
        )
        if employee:
            is_lead = self.env['team.team'].sudo().search_count(
                [('team_lead_id', '=', employee.id)]
            )
            if is_lead:
                return True

        return False

    # ------------------------------------------------------------------
    # ORM OVERRIDES
    # ------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        if not self._user_can_write():
            raise UserError('Only Manager, HR, or Team Lead can upload project documents.')
        return super().create(vals_list)

    def write(self, vals):
        if not self._user_can_write():
            raise UserError('Only Manager, HR, or Team Lead can edit project documents.')
        return super().write(vals)

    def unlink(self):
        if not self._user_can_write():
            raise UserError('Only Manager, HR, or Team Lead can delete project documents.')
        return super().unlink()