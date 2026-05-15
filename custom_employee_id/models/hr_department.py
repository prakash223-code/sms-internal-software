from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError


class HrDepartment(models.Model):
    _inherit = 'hr.department'

    dept_code = fields.Char(
        string='Department Code',
        size=10,
        help='Short code used in Employee ID (e.g. CFD, IT, HR). '
             'Cannot be changed once employees are assigned.'
    )
    has_employees = fields.Boolean(
        string='Has Employees',
        compute='_compute_has_employees',
        store=True
    )

    @api.depends('member_ids')
    def _compute_has_employees(self):
        for dept in self:
            dept.has_employees = bool(dept.member_ids)

    @api.constrains('dept_code')
    def _check_dept_code_unique(self):
        for dept in self:
            if dept.dept_code:
                duplicate = self.search([
                    ('dept_code', '=ilike', dept.dept_code),
                    ('id', '!=', dept.id)
                ], limit=1)
                if duplicate:
                    raise ValidationError(
                        f'Department code "{dept.dept_code}" is already used by '
                        f'"{duplicate.name}". Each department must have a unique code.'
                    )

    def write(self, vals):
        if 'dept_code' in vals:
            for dept in self:
                if dept.has_employees:
                    raise UserError(
                        f'Department code for "{dept.name}" cannot be changed '
                        f'because employees are already assigned to it.'
                    )
        return super().write(vals)