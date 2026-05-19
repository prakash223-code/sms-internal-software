from odoo import models, fields, api
from odoo.exceptions import UserError


class HrEmployeeDocument(models.Model):
    _name = 'hr.employee.document'
    _description = 'Employee Document'
    _order = 'upload_date desc, id desc'
    _rec_name = 'name'

    # ------------------------------------------------------------------
    # FIELDS
    # ------------------------------------------------------------------

    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        required=True,
        ondelete='cascade',
        index=True,
    )

    name = fields.Char(
        string='Document Name',
        required=True,
        help='e.g. Aadhar Card, PAN Card, Offer Letter, Degree Certificate',
    )

    document_type = fields.Selection([
        ('id_proof',     'ID Proof'),
        ('educational',  'Educational Certificate'),
        ('contract',     'Contract / Agreement'),
        ('experience',   'Experience Letter'),
        ('medical',      'Medical Certificate'),
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
        Examples: aadhar.pdf → PDF, photo.png → PNG, contract.docx → DOCX
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
                rec.file_url = f'{base_url}/hr/document/preview/{rec.id}'
            else:
                rec.file_url = False

    # ------------------------------------------------------------------
    # ORM OVERRIDES
    # ------------------------------------------------------------------

    def write(self, vals):
        if not self.env.user.has_group('hr.group_hr_user'):
            raise UserError('Only HR can edit employee documents.')
        return super().write(vals)

    def unlink(self):
        if not self.env.user.has_group('hr.group_hr_user'):
            raise UserError('Only HR can delete employee documents.')
        return super().unlink()