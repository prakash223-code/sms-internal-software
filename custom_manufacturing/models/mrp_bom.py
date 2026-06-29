from odoo import models, fields, api


class MrpBom(models.Model):
    _inherit = 'mrp.bom'

    manufacturing_type = fields.Selection(
        selection=[
            ('assembly', 'Assembly'),
            ('production', 'Production'),
            ('both', 'Assembly + Production'),
        ],
        string='Manufacturing Type',
        default='assembly',
        required=True,
    )

    custom_bom_ref = fields.Char(
        string='BOM Reference',
        readonly=True,
        copy=False,
        index=True,
    )

    assembly_notes = fields.Text(string='Assembly Instructions')
    production_notes = fields.Text(string='Production Notes')
    estimated_hours = fields.Float(string='Estimated Hours', default=1.0)

    warranty_years = fields.Integer(
        string='Warranty Years',
        default=1,
        help='Warranty period (years) applied when generating warranty records.',
    )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            if not record.custom_bom_ref:
                seq = self.env['ir.sequence'].sudo().next_by_code('custom.mrp.bom')
                record.sudo().write({'custom_bom_ref': seq})
        return records


class MrpBomLine(models.Model):
    _inherit = 'mrp.bom.line'

    component_type = fields.Selection(
        selection=[
            ('raw_material', 'Raw Material'),
            ('sub_assembly', 'Sub Assembly'),
            ('bought_out', 'Bought Out Part'),
            ('consumable', 'Consumable'),
        ],
        string='Component Type',
        default='bought_out',
    )

    component_notes = fields.Char(string='Notes')
    is_critical = fields.Boolean(string='Critical', default=False)