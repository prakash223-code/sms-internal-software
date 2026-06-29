# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from datetime import date
import logging

_logger = logging.getLogger(__name__)


class MrpWarranty(models.Model):
    _name        = 'mrp.warranty'
    _description = 'Product Warranty'
    _rec_name    = 'serial_number'
    _order       = 'warranty_end asc'
    _inherit     = ['mail.thread', 'mail.activity.mixin']

    production_id = fields.Many2one(
        'mrp.production',
        string='Manufacturing Order',
        ondelete='cascade',
    )
    serial_number = fields.Char(
        string='Serial Number',
        readonly=True,
        index=True,
    )
    product_id = fields.Many2one(
        'product.product',
        string='Product',
    )
    client_id = fields.Many2one(
        'res.partner',
        string='Client',
    )
    warranty_start = fields.Date(string='Warranty Start')
    warranty_end   = fields.Date(string='Warranty End')
    warranty_years = fields.Integer(string='Warranty Years', default=1)
    notes          = fields.Text(string='Notes')

    warranty_status = fields.Selection([
        ('active',   'Active'),
        ('expiring', 'Expiring Soon'),
        ('expired',  'Expired'),
    ],
        string='Warranty Status',
        compute='_compute_warranty_status',
        store=True,
        tracking=True,
    )
    days_remaining = fields.Integer(
        string='Days Remaining',
        compute='_compute_warranty_status',
        store=True,
    )

    @api.depends('warranty_end')
    def _compute_warranty_status(self):
        today = date.today()
        for rec in self:
            if not rec.warranty_end:
                rec.warranty_status = 'active'
                rec.days_remaining  = 0
                continue
            days               = (rec.warranty_end - today).days
            rec.days_remaining = days
            if days < 0:
                rec.warranty_status = 'expired'
            elif days <= 30:
                rec.warranty_status = 'expiring'
            else:
                rec.warranty_status = 'active'

    # ── Print Certificate ─────────────────────────────────────
    def action_print_warranty_certificate(self):
        """Print PDF warranty certificate."""
        self.ensure_one()
        return self.env.ref(
            'custom_manufacturing.action_report_warranty_certificate'
        ).report_action(self)

    # ── Cron ──────────────────────────────────────────────────
    @api.model
    def action_send_expiry_alerts(self):
        """Called by cron — logs expiring warranties."""
        today    = date.today()
        expiring = self.search([('warranty_status', '=', 'expiring')])
        expired  = self.search([('warranty_status', '=', 'expired')])

        _logger.info(
            'WARRANTY CHECK %s — Expiring: %d | Expired: %d',
            today, len(expiring), len(expired)
        )
        for rec in expiring:
            _logger.warning(
                'EXPIRING: %s | %s | Client: %s | Days left: %d',
                rec.serial_number,
                rec.product_id.name,
                rec.client_id.name if rec.client_id else 'N/A',
                rec.days_remaining,
            )
        return True