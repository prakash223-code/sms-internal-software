# -*- coding: utf-8 -*-
from odoo import models, fields


class WelcomeQuote(models.Model):
    _name = 'welcome.quote'
    _description = 'Welcome Quote'
    _order = 'sequence asc, id asc'
    _rec_name = 'author'

    text = fields.Text(string='Quote', required=True)
    author = fields.Char(string='Author', default='Unknown')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)