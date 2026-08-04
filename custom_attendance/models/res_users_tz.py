# -*- coding: utf-8 -*-
from odoo import models, api


class ResUsersDefaultTz(models.Model):
    _inherit = 'res.users'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('tz'):
                vals['tz'] = 'Asia/Kolkata'
        return super().create(vals_list)