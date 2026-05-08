from odoo import models, fields

class HrEmployeePublic(models.Model):
    _inherit = 'hr.employee.public'

    # Adding bank_account_ids to public profile so employees can
    # read their own bank accounts on payslip reports
    # _check_private_fields blocks any field not present in this model
    bank_account_ids = fields.Many2many(
        'res.partner.bank',
        relation='employee_bank_account_rel',
        column1='employee_id',
        column2='bank_account_id',
        string='Bank Accounts',
    )