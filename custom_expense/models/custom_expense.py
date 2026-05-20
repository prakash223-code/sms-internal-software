# custom_expense/models/custom_expense.py

from odoo import models, fields, api
from odoo.exceptions import ValidationError, UserError


class CustomExpense(models.Model):
    _name = 'custom.expense'
    _description = 'Company Expense'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    # ── Identity ──────────────────────────────────────────────────────────────
    name = fields.Char(
        string='Reference',
        readonly=True,
        copy=False,
        default='New',
    )
    submitted_by = fields.Many2one(
        'hr.employee',
        string='Submitted By',
        required=True,
        default=lambda self: self.env['hr.employee'].search(
            [('user_id', '=', self.env.uid)], limit=1
        ),
        tracking=True,
    )

    # ── Core Fields ───────────────────────────────────────────────────────────
    category_id = fields.Many2one(
        'custom.expense.category',
        string='Expense Category',
        required=True,
        tracking=True,
    )
    project_id = fields.Many2one(
        'project.project',
        string='Related Project',
        tracking=True,
        help='Link this expense to a project if applicable.',
    )
    amount = fields.Monetary(
        string='Amount',
        required=True,
        tracking=True,
        currency_field='currency_id',
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        required=True,
        default=lambda self: self.env.company.currency_id,
    )
    date = fields.Date(
        string='Expense Date',
        required=True,
        default=fields.Date.today,
        tracking=True,
    )
    description = fields.Text(
        string='Description',
        required=True,
    )

    # ── Attachments ───────────────────────────────────────────────────────────
    attachment_ids = fields.Many2many(
        'ir.attachment',
        'custom_expense_attachment_rel',
        'expense_id',
        'attachment_id',
        string='Attachments',
        help='Attach bill or invoice proof. Mandatory before submission.',
    )
    attachment_count = fields.Integer(
        string='Attachment Count',
        compute='_compute_attachment_count',
    )

    # ── Status ────────────────────────────────────────────────────────────────
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('submitted', 'Submitted'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected'),
        ],
        string='Status',
        default='draft',
        required=True,
        readonly=True,
        tracking=True,
        copy=False,
    )
    rejection_reason = fields.Text(
        string='Rejection Reason',
        readonly=True,
        copy=False,
    )

    # ── Phase 2 Placeholders (hidden in UI, ready for accounting upgrade) ─────
    payment_state = fields.Selection(
        selection=[
            ('unpaid', 'Unpaid'),
            ('paid', 'Paid'),
        ],
        string='Payment Status',
        default='unpaid',
        copy=False,
    )
    account_move_id = fields.Many2one(
        'account.move',
        string='Journal Entry',
        readonly=True,
        copy=False,
    )

    # ── Computed ──────────────────────────────────────────────────────────────
    @api.depends('attachment_ids')
    def _compute_attachment_count(self):
        for rec in self:
            rec.attachment_count = len(rec.attachment_ids)

    # ── Sequence Generation ───────────────────────────────────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'custom.expense')
        return super().create(vals_list)

    # ── State Transitions ─────────────────────────────────────────────────────
    def action_submit(self):
        """Manager submits the expense."""
        for rec in self:
            if rec.state != 'draft':
                raise UserError('Only Draft expenses can be submitted.')
            rec.state = 'submitted'
            rec.message_post(body='Expense submitted for approval.')

    def action_approve(self):
        """Manager approves the expense."""
        for rec in self:
            if rec.state != 'submitted':
                raise UserError('Only Submitted expenses can be approved.')
            rec.state = 'approved'
            rec.message_post(body='Expense approved.')

    def action_reject(self):
        """Opens rejection wizard to capture mandatory reason."""
        self.ensure_one()
        if self.state != 'submitted':
            raise UserError('Only Submitted expenses can be rejected.')
        return {
            'type': 'ir.actions.act_window',
            'name': 'Reject Expense',
            'res_model': 'custom.expense.reject.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_expense_id': self.id},
        }

    def action_reset_draft(self):
        """HR resets rejected expense back to draft for correction."""
        for rec in self:
            if rec.state != 'rejected':
                raise UserError('Only Rejected expenses can be reset to Draft.')
            rec.rejection_reason = False
            rec.state = 'draft'
            rec.message_post(body='Expense reset to Draft.')

    # ── Constraints ───────────────────────────────────────────────────────────
    @api.constrains('amount')
    def _check_amount(self):
        for rec in self:
            if rec.amount <= 0:
                raise ValidationError('Expense amount must be greater than zero.')