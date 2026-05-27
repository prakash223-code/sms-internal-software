# -*- coding: utf-8 -*-
from . import models


def post_init_hook(env):
    """
    Sets the Welcome Dashboard as the home action for all internal users
    so it appears automatically on login.

    Odoo 19 removed both res.users.groups_id domain searching AND
    res.groups.users reverse relation. We identify internal users via
    share=False + active=True instead — this is the canonical way Odoo
    itself distinguishes internal users from portal/public users.
    """
    action = env.ref('custom_welcome.action_welcome_dashboard')

    # share=False  → excludes portal and public users
    # active=True  → excludes archived users
    # Using sudo() to ensure we see all users regardless of calling context
    internal_users = env['res.users'].sudo().search([
        ('share',  '=', False),
        ('active', '=', True),
    ])
    internal_users.write({'action_id': action.id})