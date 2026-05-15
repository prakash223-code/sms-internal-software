from odoo import models, fields, api
from odoo.exceptions import UserError
import datetime


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    employee_code = fields.Char(
        string='Employee ID',
        readonly=True,
        copy=False,
        index=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('employee_code'):
                vals['employee_code'] = self._generate_employee_code(vals)
        return super().create(vals_list)

    def write(self, vals):
        if 'employee_code' in vals:
            raise UserError('Employee ID cannot be modified after it has been assigned.')
        return super().write(vals)

    def _generate_employee_code(self, vals):
        year_prefix = str(datetime.datetime.now().year)[2:]
        dept_code = 'GEN'

        if vals.get('department_id'):
            dept = self.env['hr.department'].browse(vals['department_id'])
            if dept.exists() and dept.dept_code:
                dept_code = dept.dept_code.upper().strip()

        seq = self.env['ir.sequence'].next_by_code('hr.employee.global.seq')

        # Safety check — sequence missing
        if not seq:
            raise UserError(
                'Employee ID sequence not found. '
                'Please contact your system administrator.'
            )

        return f'{year_prefix}{dept_code}{seq}'

    def unlink(self):
        raise UserError(
            'Employees cannot be deleted. Archive them instead.'
        )