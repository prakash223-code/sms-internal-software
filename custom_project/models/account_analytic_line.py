# account_analytic_line.py
# PURPOSE: Extend timesheet entries (account.analytic.line) with a
#   "Software Used" free-text field so employees can log which tool
#   or application they worked with during each timesheet entry.

from odoo import fields, models


class AccountAnalyticLine(models.Model):
    _inherit = 'account.analytic.line'

    software_used = fields.Char(
        string='Software Used',
        help='The software or tool used during this timesheet entry.',
    )