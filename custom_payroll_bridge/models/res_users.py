from odoo import models, api


class ResUsers(models.Model):
    _inherit = 'res.users'

    @api.model_create_multi
    def create(self, vals_list):
        # The simplified "Create User" form (custom_payroll_bridge's
        # view_users_simple_form_password) adds an optional password field
        # with placeholder "leave blank to send reset email". When left
        # blank, the web client still sends 'password': False in the create
        # payload, which crashes passlib's ctx.hash() (expects str/bytes,
        # not bool). Strip the key here so an empty password is treated as
        # "not provided" rather than a literal False value.
        for vals in vals_list:
            if 'password' in vals and not vals['password']:
                vals.pop('password')
        return super().create(vals_list)