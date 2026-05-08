from odoo import models, fields

class HrVersion(models.Model):
    _inherit = 'hr.version'

    # ── Payroll-related fields restricted by core hr module ──────────────────
    # Unlocking ONLY fields needed for payslip computation and display
    # Private fields (passport, SSN, address etc.) remain restricted

    # hr.group_hr_user restricted — needed for payslip line display
    date_version = fields.Date(groups=False)

    # hr.group_hr_manager restricted — needed for HR to create payslips
    contract_date_start = fields.Date(groups=False)
    contract_date_end = fields.Date(groups=False)
    trial_date_end = fields.Date(groups=False)
    structure_type_id = fields.Many2one(
        'hr.payroll.structure.type',
        groups=False
    )
    contract_type_id = fields.Many2one(
        'hr.contract.type',
        groups=False
    )
    date_start = fields.Date(groups=False)
    date_end = fields.Date(groups=False)

    # bi_hr_payroll restricted — needed for salary calculation
    wage = fields.Monetary(groups=False)