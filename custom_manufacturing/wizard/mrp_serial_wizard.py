from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import date
from dateutil.relativedelta import relativedelta


class MrpSerialWizard(models.TransientModel):
    _name = 'mrp.serial.wizard'
    _description = 'Generate Serial Numbers & Warranties Wizard'

    production_id = fields.Many2one(
        'mrp.production',
        string='Manufacturing Order',
        required=True,
        default=lambda self: self.env.context.get('default_production_id'),
    )
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        related='production_id.product_id',
        readonly=True,
    )
    qty = fields.Integer(
        string='Quantity',
        required=True,
        default=1,
    )
    client_id = fields.Many2one(
        'res.partner',
        string='Client',
        related='production_id.client_id',
        readonly=False,
    )
    warranty_years = fields.Integer(
        string='Warranty Years',
        default=1,
    )
    warranty_start = fields.Date(
        string='Warranty Start',
        default=fields.Date.today,
    )
    line_ids = fields.One2many(
        'mrp.serial.wizard.line',
        'wizard_id',
        string='Preview Lines',
    )

    def action_generate(self):
        self.ensure_one()
        if self.qty <= 0:
            raise UserError(_('Quantity must be greater than 0.'))

        self.line_ids.unlink()

        lines = []
        for i in range(self.qty):
            serial = self.env['ir.sequence'].sudo().next_by_code(
                'custom.mrp.serial'
            ) or f'SN{i + 1:06d}'
            lines.append({
                'wizard_id': self.id,
                'serial_number': serial,
                'product_id': self.product_id.id,
                'client_id': self.client_id.id if self.client_id else False,
            })

        self.env['mrp.serial.wizard.line'].create(lines)

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'mrp.serial.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_confirm(self):
        self.ensure_one()

        if not self.line_ids:
            raise UserError(_(
                'No serial numbers to apply.\n\n'
                'Click "Generate Preview" first to create serial numbers, '
                'then click "Confirm & Create".'
            ))

        today = self.warranty_start or date.today()
        warranty_end = today + relativedelta(years=self.warranty_years)

        for line in self.line_ids:
            self.env['mrp.production.serial'].create({
                'production_id': self.production_id.id,
                'serial_number': line.serial_number,
                'product_id': line.product_id.id,
                'client_id': line.client_id.id if line.client_id else False,
                'notes': line.notes or '',
            })
            self.env['mrp.warranty'].create({
                'production_id': self.production_id.id,
                'serial_number': line.serial_number,
                'product_id': line.product_id.id,
                'client_id': line.client_id.id if line.client_id else False,
                'warranty_start': today,
                'warranty_end': warranty_end,
                'warranty_years': self.warranty_years,
            })

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Done'),
                'message': _(
                    '%d serial numbers and warranties created for %s.'
                ) % (len(self.line_ids), self.production_id.name),
                'type': 'success',
                'sticky': False,
            },
        }


class MrpSerialWizardLine(models.TransientModel):
    _name = 'mrp.serial.wizard.line'
    _description = 'Serial Number Wizard Preview Line'

    wizard_id = fields.Many2one('mrp.serial.wizard', ondelete='cascade')
    serial_number = fields.Char(string='Serial Number', required=True)
    product_id = fields.Many2one('product.product', string='Product')
    client_id = fields.Many2one('res.partner', string='Client')
    notes = fields.Char(string='Notes')