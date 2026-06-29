from odoo import models, fields, api, _
from odoo.exceptions import UserError
from dateutil.relativedelta import relativedelta
from datetime import date
import logging

_logger = logging.getLogger(__name__)


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    # ── Identity ──────────────────────────────────────────────────────────────

    custom_production_ref = fields.Char(
        string='Production Reference',
        readonly=True,
        copy=False,
        index=True,
    )

    manufacturing_type = fields.Selection(
        selection=[
            ('assembly', 'Assembly'),
            ('production', 'Production'),
            ('both', 'Assembly + Production'),
        ],
        string='Manufacturing Type',
        compute='_compute_manufacturing_type',
        store=True,
    )

    # ── Client ────────────────────────────────────────────────────────────────

    client_id = fields.Many2one(
        'res.partner',
        string='Client',
        help='Client this order is built for.',
    )

    client_requirements = fields.Text(string='Client Requirements')

    # ── Assembly fields ───────────────────────────────────────────────────────

    assembly_start_date = fields.Datetime(string='Assembly Start')
    assembly_end_date = fields.Datetime(string='Assembly End')
    assembly_notes = fields.Text(string='Assembly Instructions')

    # ── Production fields ─────────────────────────────────────────────────────

    production_start_date = fields.Datetime(string='Production Start')
    production_end_date = fields.Datetime(string='Production End')
    production_notes = fields.Text(string='Production Notes')

    # ── Quality ───────────────────────────────────────────────────────────────

    quality_checked = fields.Boolean(string='Quality Checked', default=False)
    quality_notes = fields.Text(string='Quality Notes')

    # ── Cost analysis ─────────────────────────────────────────────────────────

    total_component_cost = fields.Float(
        string='Component Cost (₹)',
        compute='_compute_cost_analysis',
        store=True,
        digits=(16, 2),
    )

    labour_cost = fields.Float(
        string='Labour Cost (₹)',
        default=0.0,
        digits=(16, 2),
    )

    overhead_cost = fields.Float(
        string='Overhead Cost (₹)',
        default=0.0,
        digits=(16, 2),
    )

    total_production_cost = fields.Float(
        string='Total Cost (₹)',
        compute='_compute_cost_analysis',
        store=True,
        digits=(16, 2),
    )

    selling_price = fields.Float(
        string='Selling Price (₹)',
        digits=(16, 2),
    )

    profit_amount = fields.Float(
        string='Profit (₹)',
        compute='_compute_cost_analysis',
        store=True,
        digits=(16, 2),
    )

    profit_percentage = fields.Float(
        string='Profit %',
        compute='_compute_cost_analysis',
        store=True,
        digits=(16, 2),
    )

    profit_status = fields.Selection(
        selection=[
            ('profit', 'Profit'),
            ('loss', 'Loss'),
            ('breakeven', 'Break Even'),
        ],
        string='Profit Status',
        compute='_compute_cost_analysis',
        store=True,
    )

    # ── Component tracking ────────────────────────────────────────────────────

    component_status = fields.Selection(
        selection=[
            ('pending', 'Components Pending'),
            ('partial', 'Partially Available'),
            ('ready', 'All Components Ready'),
        ],
        string='Component Status',
        compute='_compute_component_status',
        store=True,
    )

    total_components = fields.Integer(
        string='Total Components',
        compute='_compute_component_status',
        store=True,
    )

    available_components = fields.Integer(
        string='Available Components',
        compute='_compute_component_status',
        store=True,
    )

    # ── Serials & warranty ────────────────────────────────────────────────────

    serial_number_ids = fields.One2many(
        'mrp.production.serial',
        'production_id',
        string='Serial Numbers',
    )

    serial_count = fields.Integer(
        string='Serials',
        compute='_compute_serial_count',
    )

    warranty_ids = fields.One2many(
        'mrp.warranty',
        'production_id',
        string='Warranties',
    )
    valuation_count = fields.Integer(
        compute="_compute_valuation_count"
    )

    # ── Compute ───────────────────────────────────────────────────────────────

    @api.depends('bom_id', 'bom_id.manufacturing_type')
    def _compute_manufacturing_type(self):
        for rec in self:
            rec.manufacturing_type = (
                rec.bom_id.manufacturing_type if rec.bom_id else 'assembly'
            )

    @api.depends('serial_number_ids')
    def _compute_serial_count(self):
        for rec in self:
            rec.serial_count = len(rec.serial_number_ids)

    @api.depends(
        'move_raw_ids',
        'move_raw_ids.state',
        'move_raw_ids.product_uom_qty',
        'move_raw_ids.quantity',
    )
    def _compute_component_status(self):
        for rec in self:
            pending_moves = rec.move_raw_ids.filtered(
                lambda m: m.state not in ('done', 'cancel')
            )
            total = len(pending_moves)
            available = sum(
                1 for m in pending_moves if m.quantity >= m.product_uom_qty
            )
            rec.total_components = total
            rec.available_components = available
            if total == 0 or available == 0:
                rec.component_status = 'pending'
            elif available < total:
                rec.component_status = 'partial'
            else:
                rec.component_status = 'ready'

    @api.depends(
        'move_raw_ids.product_id',
        'move_raw_ids.product_uom_qty',
        'labour_cost',
        'overhead_cost',
        'selling_price',
    )
    def _compute_cost_analysis(self):
        for rec in self:
            component_cost = sum(
                move.product_id.standard_price * move.product_uom_qty
                for move in rec.move_raw_ids
                if move.product_id
            )
            total_cost = component_cost + rec.labour_cost + rec.overhead_cost
            profit = rec.selling_price - total_cost

            rec.total_component_cost = component_cost
            rec.total_production_cost = total_cost
            rec.profit_amount = profit
            rec.profit_percentage = (profit / total_cost * 100) if total_cost else 0.0

            if profit > 0:
                rec.profit_status = 'profit'
            elif profit < 0:
                rec.profit_status = 'loss'
            else:
                rec.profit_status = 'breakeven'

    # ── ORM ───────────────────────────────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            if not record.custom_production_ref:
                seq = self.env['ir.sequence'].sudo().next_by_code(
                    'custom.mrp.production'
                )
                record.sudo().write({'custom_production_ref': seq})
        return records

    # ── Action overrides ──────────────────────────────────────────────────────

    def action_confirm(self):
        for rec in self:
            missing = [
                f'{m.product_id.name} — need {m.product_uom_qty}, '
                f'available {m.quantity}'
                for m in rec.move_raw_ids
                if m.quantity < m.product_uom_qty
            ]
            if missing:
                _logger.warning(
                    'Missing components for %s:\n%s',
                    rec.name, '\n'.join(missing),
                )
        return super().action_confirm()

    def action_validate_mo(self):
        self.ensure_one()
        if self.state not in ('confirmed', 'progress'):
            raise UserError(
                _('Only confirmed or in-progress orders can be validated.')
            )
        return self.env.ref('mrp.action_mrp_immediate_production').read()[0]

    # ── Button actions ────────────────────────────────────────────────────────

    def action_check_components(self):
        self.ensure_one()
        lines = []
        for move in self.move_raw_ids:
            ok = move.quantity >= move.product_uom_qty
            lines.append(
                f'{"✅" if ok else "❌"} {move.product_id.name} — '
                f'Need: {move.product_uom_qty} | Available: {move.quantity}'
            )
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Component Status'),
                'message': '\n'.join(lines) or _('No components found.'),
                'type': 'info',
                'sticky': True,
            },
        }

    def action_open_serial_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Generate Serial Numbers & Warranties'),
            'res_model': 'mrp.serial.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_production_id': self.id,
                'default_quantity': int(self.product_qty),
                'default_warranty_years': (
                    self.bom_id.warranty_years if self.bom_id else 1
                ),
            },
        }

    def action_print_job_card(self):
        return self.env.ref(
            'custom_manufacturing.action_report_mrp_job_card'
        ).report_action(self)

    def action_view_warranties(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Warranties'),
            'res_model': 'mrp.warranty',
            'view_mode': 'list,form',
            'domain': [('production_id', '=', self.id)],
        }


class MrpProductionSerial(models.Model):
    _name = 'mrp.production.serial'
    _description = 'Production Serial Number'
    _rec_name = 'serial_number'

    _constraints = [
        models.Constraint(
            'unique(serial_number)',
            'This serial number already exists.',
        ),
    ]

    production_id = fields.Many2one(
        'mrp.production',
        string='Manufacturing Order',
        ondelete='cascade',
        required=True,
        index=True,
    )

    serial_number = fields.Char(
        string='Serial Number',
        readonly=True,
        index=True,
    )

    product_id = fields.Many2one('product.product', string='Product')
    client_id = fields.Many2one('res.partner', string='Client')
    notes = fields.Char(string='Notes')