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
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        readonly=True,
    )
    submitted_by = fields.Many2one(
        'hr.employee',
        string='Employee Name',
        required=True,
        default=lambda self: self.env['hr.employee'].search(
            [('user_id', '=', self.env.uid)], limit=1
        ),
        tracking=True,
    )
    employee_code = fields.Char(
        string='Employee ID',
        related='submitted_by.employee_code',
        store=True,
        readonly=True,
    )
    department_id = fields.Many2one(
        'hr.department',
        string='Department',
        compute='_compute_department',
        store=True,
        readonly=False,
        tracking=True,
    )

    # ── Core Fields ───────────────────────────────────────────────────────────
    category_id = fields.Many2one(
        'custom.expense.category',
        string='Expense Category',
        required=True,
        tracking=True,
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
        string='Bill / Receipt',
        help='Attach bill or invoice proof. Mandatory before submission.',
    )
    attachment_count = fields.Integer(
        string='Expense Attachments',
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
        string='Approval Status',
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

    # ── Phase 2 Placeholders ──────────────────────────────────────────────────
    payment_state = fields.Selection(
        selection=[('unpaid', 'Unpaid'), ('paid', 'Paid')],
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

    @api.depends('submitted_by')
    def _compute_department(self):
        for rec in self:
            rec.department_id = rec.submitted_by.sudo().department_id

    # ── Sequence Generation ───────────────────────────────────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'custom.expense')
        return super().create(vals_list)

    # ── Notification Helpers ──────────────────────────────────────────────────
    def _get_approver_partners(self):
        """Partners of all HR + Manager users, excluding the submitter."""
        self.ensure_one()
        group_ids = []
        for xml_id in ('hr.group_hr_user', 'hr.group_hr_manager'):
            group = self.env.ref(xml_id, raise_if_not_found=False)
            if group:
                group_ids.append(group.id)
        if not group_ids:
            return self.env['res.partner']
        users = self.env['res.users'].sudo().search([('group_ids', 'in', group_ids)])
        partners = users.mapped('partner_id')
        submitter_partner = self.submitted_by.sudo().user_id.partner_id
        if submitter_partner:
            partners -= submitter_partner
        return partners

    def _check_approver(self):
        if not self.env.user.has_group('hr.group_hr_user'):
            raise UserError('Only HR or Managers can approve or reject expenses.')

    # ── State Transitions ─────────────────────────────────────────────────────
    def action_submit(self):
        """Employee submits the expense; notifies HR and Manager users."""
        for rec in self:
            if rec.state != 'draft':
                raise UserError('Only Draft expenses can be submitted.')
            if not rec.attachment_ids:
                raise UserError('Please attach the bill / receipt before submitting.')
            rec.state = 'submitted'
            partners = rec._get_approver_partners()
            rec.message_post(
                body=f'Expense submitted for approval by {rec.submitted_by.name}.',
                partner_ids=partners.ids,
            )

    def action_approve(self):
        """HR / Manager approves the expense; notifies the submitter."""
        self._check_approver()
        for rec in self:
            if rec.state != 'submitted':
                raise UserError('Only Submitted expenses can be approved.')
            rec.state = 'approved'
            rec.message_post(
                body='Expense approved.',
                partner_ids=rec.submitted_by.sudo().user_id.partner_id.ids,
            )

    def action_reject(self):
        """Opens rejection wizard to capture mandatory reason."""
        self.ensure_one()
        self._check_approver()
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
        """Resets a rejected expense back to draft for correction."""
        for rec in self:
            if rec.state != 'rejected':
                raise UserError('Only Rejected expenses can be reset to Draft.')
            rec.rejection_reason = False
            rec.state = 'draft'
            rec.message_post(body='Expense reset to Draft.')

    def action_print_expense(self):
        self.ensure_one()
        return self.env.ref('custom_expense.action_report_custom_expense').report_action(self)

    # ── Constraints ───────────────────────────────────────────────────────────
    @api.constrains('amount')
    def _check_amount(self):
        for rec in self:
            if rec.amount <= 0:
                raise ValidationError('Expense amount must be greater than zero.')