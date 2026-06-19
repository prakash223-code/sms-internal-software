from odoo import models, fields

class HrEmployeePublic(models.Model):
    _inherit = 'hr.employee.public'

    # ── Fields unlocked on hr.employee (groups=False) must be mirrored
    # here or _check_private_fields blocks reads on the public model.
    # Triggered whenever hr.leave.type._compute_leaves() resolves
    # employee.company_id while an employee is in the context.

    bank_account_ids = fields.Many2many(
        'res.partner.bank',
        relation='employee_bank_account_rel',
        column1='employee_id',
        column2='bank_account_id',
        string='Bank Accounts',
    )

    employee_role = fields.Selection(
        selection=[
            ('employee', 'Employee'),
            ('hr', 'HR'),
            ('manager', 'Manager'),
        ],
        string='System Role',
    )

    # From hr_employee.py (groups=False) — needed for payslip reports
    private_phone = fields.Char(string='Private Phone')
    address_home_id = fields.Many2one('res.partner', string='Private Address')
    identification_id = fields.Char(string='Identification No')

    # From bi_hr_payroll — added to hr.employee but not to public model
    employee_code = fields.Char(string='Employee Code')
    state = fields.Selection(
        selection=[
            ('new', 'New'),
            ('open', 'Running'),
            ('close', 'Expired'),
            ('cancel', 'Cancelled'),
        ],
        string='Status',
    )