from odoo import models, fields

class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    # ── Fields accessed by bi_hr_payroll views/reports ───────────────────────

    private_phone = fields.Char(
        string='Private Phone',
        groups=False
    )
    address_id = fields.Many2one(
        'res.partner',
        string='Work Address',
        groups=False
    )
    identification_id = fields.Char(
        string='Identification No',
        groups=False
    )
    work_email = fields.Char(
        string='Work Email',
        groups=False
    )

    # Exact definition copied from core hr — only groups changed to False
    bank_account_ids = fields.Many2many(
        'res.partner.bank',
        relation='employee_bank_account_rel',
        column1='employee_id',
        column2='bank_account_id',
        domain="[('partner_id', '=', work_contact_id), '|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        groups=False,
        copy=False,
        tracking=True,
        string='Bank Accounts',
        help='Employee bank accounts to pay salaries'
    )
    is_trusted_bank_account = fields.Boolean(
        compute='_compute_is_trusted_bank_account',
        groups=False
    )

    # ── Contract linking fields ───────────────────────────────────────────────
    version_id = fields.Many2one(
        'hr.version',
        groups=False
    )
    contract_date_start = fields.Date(
        readonly=False,
        related='version_id.contract_date_start',
        inherited=True,
        groups=False
    )
    contract_date_end = fields.Date(
        readonly=False,
        related='version_id.contract_date_end',
        inherited=True,
        groups=False
    )

    # ── Currency for monetary field rendering ─────────────────────────────────
    currency_id = fields.Many2one(
        'res.currency',
        related='company_id.currency_id',
        readonly=True,
        groups=False
    )

    # ── bi_hr_payroll specific ────────────────────────────────────────────────
    payslip_count = fields.Integer(
        compute='_compute_payslip_count',
        string='Payslip Count',
        groups=False
    )
    address_home_id = fields.Many2one(
        'res.partner',
        string='Private Address',
        groups=False
    )