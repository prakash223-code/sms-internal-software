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

    filename = fields.Char(
        string='File Name',
    )

    file_type = fields.Char(
        string='File Type',
        compute='_compute_file_type',
        store=True,
        help='File extension extracted from the uploaded filename (e.g. PDF, PNG, DOCX).',
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

    # ------------------------------------------------------------------
    # COMPUTED
    # ------------------------------------------------------------------

    @api.depends('filename')
    def _compute_file_type(self):
        """
        Extracts the file extension from the uploaded filename.
        Examples: contract.pdf → PDF, blueprint.png → PNG, report.docx → DOCX
        """
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

    # ------------------------------------------------------------------
    # ACCESS HELPERS
    # ------------------------------------------------------------------

    def _user_can_write(self):
        """
        Only Manager (project.group_project_manager) or HR (hr.group_hr_user)
        can create / edit / delete project documents.
        Employees and Team Leads are read-only.
        """
        user = self.env.user
        return (
            user.has_group('project.group_project_manager')
            or user.has_group('hr.group_hr_user')
        )

    # ------------------------------------------------------------------
    # ORM OVERRIDES
    # ------------------------------------------------------------------

    def write(self, vals):
        if not self._user_can_write():
            raise UserError('Only Manager or HR can edit project documents.')
        return super().write(vals)

    def unlink(self):
        if not self._user_can_write():
            raise UserError('Only Manager or HR can delete project documents.')
        return super().unlink()
