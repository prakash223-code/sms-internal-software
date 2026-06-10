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

    # ------------------------------------------------------------------
    # name_create — guard quick creates from many2one dropdowns
    # ------------------------------------------------------------------

    @api.model
    def name_create(self, name):
        """Prevent ID generation when a partner is quick-created from a
        many2one field (e.g. partner_id on a CRM lead).
        ID will be generated when the company is saved from its own form.
        """
        record = self.with_context(skip_company_id_generation=True).create(
            {'name': name}
        )
        return record.id, record.display_name

    # ------------------------------------------------------------------
    # create — NO automatic ID generation here.
    #
    # Reason: Odoo 19 partner_autocomplete calls web_save() -> create()
    # immediately when the user clicks an IAP suggestion, before the user
    # has explicitly clicked Save.  Generating the ID here would fire on
    # every autocomplete selection, not just on intentional saves.
    #
    # ID generation is handled by the JS FormController (saveButtonClicked)
    # which calls action_generate_company_id() only on explicit Save.
    # ------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        return super().create(vals_list)

    # ------------------------------------------------------------------
    # write — only regenerates when user changes National <-> International
    # ------------------------------------------------------------------

    def write(self, vals):
        result = super().write(vals)

        if 'company_type_selection' in vals:
            # Intentional user action — always regenerate the ID.
            for record in self:
                new_id = record._generate_company_id(
                    company_name=record.name or '',
                    company_type=vals.get(
                        'company_type_selection',
                        record.company_type_selection or 'national',
                    ),
                )
                super(ResPartner, record).write({'company_custom_id': new_id})

        return result

    # ------------------------------------------------------------------
    # action_generate_company_id — called by the JS FormController
    # after an explicit Save button click, and available as a fallback
    # button in the view for contacts converted to companies.
    # ------------------------------------------------------------------

    def action_generate_company_id(self):
        for record in self:
            if record.is_company and not record.company_custom_id:
                record.sudo().write({
                    'company_custom_id': record._generate_company_id(
                        company_name=record.name or '',
                        company_type=record.company_type_selection or 'national',
                    )
                })

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_company_id(self, company_name='', company_type='national'):
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