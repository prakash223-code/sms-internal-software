# custom_expense/wizard/expense_reject_wizard.py

from odoo import models, fields, api
from odoo.exceptions import ValidationError


class CustomExpenseRejectWizard(models.TransientModel):
    _name = 'custom.expense.reject.wizard'
    _description = 'Expense Rejection Reason'

    expense_id = fields.Many2one(
        'custom.expense',
        string='Expense',
        required=True,
        readonly=True,
    )
    rejection_reason = fields.Text(
        string='Rejection Reason',
        required=True,
        help='Provide a clear reason for rejecting this expense.',
    )

    def action_confirm_reject(self):
        """Applies rejection reason, sets expense to Rejected, and notifies the submitter."""
        self.ensure_one()
        if not self.rejection_reason or not self.rejection_reason.strip():
            raise ValidationError('Rejection reason cannot be empty.')
        reason = self.rejection_reason.strip()
        self.expense_id.write({
            'state': 'rejected',
            'rejection_reason': reason,
        })
        submitter_partner = self.expense_id.submitted_by.user_id.partner_id
        self.expense_id.message_post(
            body=f'Expense rejected. Reason: {reason}',
            partner_ids=submitter_partner.ids,
        )
        return {'type': 'ir.actions.act_window_close'}