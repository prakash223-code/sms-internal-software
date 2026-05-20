from odoo import models, fields


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    is_team_lead = fields.Boolean(
        string='Team Lead',
        default=False,
        tracking=True,
        help='If enabled, this employee can create and assign tasks in projects.\n'
             'Plain employees (without this flag) can only view and work on '
             'tasks assigned to them.'
    )
