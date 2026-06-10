from odoo import models, fields, api
import re


class ResPartner(models.Model):
    _inherit = 'res.partner'

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

    @api.model
    def name_create(self, name):
        """Override to prevent auto-ID generation during quick-create.

        When a user types a company name in a many2one field (e.g. partner_id on
        a CRM lead) and clicks "Create 'XYZ'" from the dropdown, Odoo calls
        name_create() → create() immediately — before the user ever opens or
        saves a proper company form.  We suppress ID generation here; the ID
        will be assigned only when the company record is explicitly saved from
        its own form view.
        """
        record = self.with_context(skip_company_id_generation=True).create(
            {'name': name}
        )
        return record.id, record.display_name

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)

        # Skip entirely when called from name_create() or any other context
        # that signals an intermediate / automated creation (not an explicit Save).
        if self.env.context.get('skip_company_id_generation'):
            return records

        for record in records:
            if not record.company_custom_id and record.name:
                record.sudo().write({
                    'company_custom_id': record._generate_company_id(
                        company_name=record.name,
                        company_type=record.company_type_selection or 'national',
                    )
                })
        return records

    def write(self, vals):
        result = super().write(vals)

        skip = self.env.context.get('skip_company_id_generation')

        if 'company_type_selection' in vals:
            # User explicitly changed National ↔ International → always regenerate.
            # This is never triggered by autocomplete, so no skip-guard needed.
            for record in self:
                new_id = record._generate_company_id(
                    company_name=record.name or '',
                    company_type=vals.get(
                        'company_type_selection',
                        record.company_type_selection or 'national',
                    ),
                )
                super(ResPartner, record).write({'company_custom_id': new_id})

        elif 'is_company' in vals and vals.get('is_company') and not skip:
            # Existing contact being converted to a company (user toggled the
            # "Company" switch and clicked Save).
            # Guarded by skip_company_id_generation so that partner_autocomplete
            # enrichment — which also writes is_company=True — does NOT trigger
            # premature generation.
            for record in self:
                if not record.company_custom_id:
                    new_id = record._generate_company_id(
                        company_name=record.name or '',
                        company_type=record.company_type_selection or 'national',
                    )
                    super(ResPartner, record).write({'company_custom_id': new_id})

        return result

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_company_id(self, company_name='', company_type='national'):
        """Return a unique ID string, e.g. N001SMSTECHGARMENTS."""
        # Ensure sequence exists
        sequence = self.env['ir.sequence'].sudo().search(
            [('code', '=', 'res.partner.company.id')], limit=1
        )
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
            # Clear any stale prefix/suffix from older config
            sequence.sudo().write({'prefix': '', 'suffix': ''})

        seq_number = self.env['ir.sequence'].sudo().next_by_code(
            'res.partner.company.id'
        )

        clean_name = re.sub(r'\s+', '', company_name.upper())
        clean_name = re.sub(r'[^A-Z0-9]', '', clean_name)

        prefix = 'IN' if company_type == 'international' else 'N'
        return f'{prefix}{seq_number}{clean_name}'

    # ------------------------------------------------------------------
    # Compute
    # ------------------------------------------------------------------

    @api.depends(
        'parent_id', 'parent_id.company_custom_id',
        'is_company', 'company_custom_id',
    )
    def _compute_contact_company_id(self):
        for rec in self:
            if rec.is_company:
                rec.contact_company_id_display = rec.company_custom_id or ''
            elif rec.parent_id and rec.parent_id.company_custom_id:
                rec.contact_company_id_display = rec.parent_id.company_custom_id
            else:
                rec.contact_company_id_display = ''