# -*- coding: utf-8 -*-
from odoo import models, fields


class WelcomeQuote(models.Model):
    _name = 'welcome.quote'
    _description = 'Welcome Quote'
    _order = 'kural_number asc, id asc'
    _rec_name = 'kural_number'

    text          = fields.Text(string='Kural (Tamil)', required=True)
    kural_number  = fields.Integer(string='Kural Number', default=0)
    active        = fields.Boolean(default=True)
    # keep sequence + author for backward compat during migration, or drop them