# custom_expense/models/custom_expense_category.py

from odoo import models, fields


class CustomExpenseCategory(models.Model):
    _name = 'custom.expense.category'
    _description = 'Expense Category'
    _order = 'name asc'

    name = fields.Char(
        string='Category Name',
        required=True,
    )
    description = fields.Text(
        string='Description',
    )
    active = fields.Boolean(
        default=True,
    )

    _sql_constraints = [
        ('name_unique', 'UNIQUE(name)', 'Expense category name must be unique.'),
    ]
