from odoo import models, fields


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    document_ids = fields.One2many(
        'hr.employee.document', 'employee_id', string='Documents',
    )
    document_count = fields.Integer(
        string='Document Count', compute='_compute_document_count', compute_sudo=True,
    )

    def _compute_document_count(self):
        for employee in self:
            employee.document_count = self.env['hr.employee.document'].sudo().search_count(
                [('employee_id', '=', employee.id)]
            )

    def action_view_employee_documents(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Employee Documents',
            'res_model': 'hr.employee.document',
            'view_mode': 'kanban,list,form',
            'domain': [('employee_id', '=', self.id)],
            'context': {'default_employee_id': self.id},
        }