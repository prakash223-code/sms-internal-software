from odoo import models, fields, api
import re


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # ✅ Single definition — no duplicates
    company_custom_id = fields.Char(
        string='Auto Company ID',
        readonly=True,
        copy=False,
        index=True,
        tracking=True,
        help='Auto-generated Company ID (e.g., N001SMSTECHGARMENTS)',
    )

    company_type_selection = fields.Selection([
        ('national', 'National'),
        ('international', 'International'),
    ],
        string='Company Type',
        default='national',
    )

    contact_company_id_display = fields.Char(
        string='Contact Auto Company ID',
        compute='_compute_contact_company_id',
        store=False,
    )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            # ✅ Generate for ALL partners — company and individual
            if not record.company_custom_id:
                record.sudo().write({
                    'company_custom_id': record._generate_company_id(
                        company_name=record.name or '',
                        company_type=record.company_type_selection or 'national',
                    )
                })
        return records

    def write(self, vals):
        result = super().write(vals)
        # ✅ Regenerate when company_type_selection changes
        if 'company_type_selection' in vals:
            for record in self:
                new_id = record._generate_company_id(
                    company_name=record.name or '',
                    company_type=vals.get('company_type_selection', record.company_type_selection or 'national'),
                )
                super(ResPartner, record).write({'company_custom_id': new_id})
        # ✅ Generate if missing when is_company is set
        elif 'is_company' in vals and vals.get('is_company'):
            for record in self:
                if not record.company_custom_id:
                    new_id = record._generate_company_id(
                        company_name=record.name or '',
                        company_type=record.company_type_selection or 'national',
                    )
                    super(ResPartner, record).write({'company_custom_id': new_id})
        return result

    def _generate_company_id(self, company_name='', company_type='national'):
        # Step 1: Get or create sequence
        sequence = self.env['ir.sequence'].sudo().search([
            ('code', '=', 'res.partner.company.id')
        ], limit=1)

        if not sequence:
            self.env['ir.sequence'].sudo().create({
                'name': 'Company Auto ID Sequence',
                'code': 'res.partner.company.id',
                'prefix': '',
                'suffix': '',
                'padding': 3,
                'number_increment': 1,
                'number_next_actual': 1,
            })
        else:
            # Clear any old prefix/suffix
            sequence.sudo().write({'prefix': '', 'suffix': ''})

        seq_number = self.env['ir.sequence'].sudo().next_by_code(
            'res.partner.company.id'
        )

        # Step 2: Clean company name
        clean_name = re.sub(r'\s+', '', company_name.upper())
        clean_name = re.sub(r'[^A-Z0-9]', '', clean_name)

        # Step 3: Prefix
        prefix = 'IN' if company_type == 'international' else 'N'

        # Step 4: Final → N001SMSTECHGARMENTS
        return f'{prefix}{seq_number}{clean_name}'

    @api.depends('parent_id', 'parent_id.company_custom_id', 'is_company', 'company_custom_id')
    def _compute_contact_company_id(self):
        for rec in self:
            if rec.is_company:
                rec.contact_company_id_display = rec.company_custom_id or ''
            elif rec.parent_id and rec.parent_id.company_custom_id:
                rec.contact_company_id_display = rec.parent_id.company_custom_id
            else:
                rec.contact_company_id_display = ''