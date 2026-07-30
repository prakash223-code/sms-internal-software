# -*- coding: utf-8 -*-
from . import models


def post_init_hook(env):
    """
    Runs after module install and upgrade.
    Restricts Kiosk and Apps menus to system admin only.
    Uses name search instead of XML IDs because both changed in Odoo 19.
    """
    system_group = env.ref('base.group_system')
    restrict = [(6, 0, [system_group.id])]

    # --- Kiosk menus ---
    # Kiosk bypasses our one-cycle-per-day rule so must be hidden from all users
    kiosk_menus = env['ir.ui.menu'].search([
        ('name', 'ilike', 'Kiosk')
    ])
    if kiosk_menus:
        kiosk_menus.write({'group_ids': restrict})

    # --- Apps / Settings menus ---
    # Employees, HR, and Managers have no need to access module management
    # Search for the top-level "Apps" and "Settings" menus by name
    apps_menus = env['ir.ui.menu'].search([
        ('name', 'in', ['Apps', 'Settings']),
        ('parent_id', '=', False),   # top-level only
    ])
    if apps_menus:
        apps_menus.write({'group_ids': restrict})

    # --- Saturday working hours setup ---
    # Adds Saturday (dayofweek=5) as a working day to the company's resource
    # calendar so 1st/3rd/5th Saturdays render as normal working days in the
    # Time Off calendar. Without this, ALL Saturdays show grey (like Sunday)
    # regardless of the 2nd/4th [SAT-OFF] holiday logic, since the calendar
    # has no working hours defined for Saturday at all by default.
    # Idempotent — setup_saturday_in_calendar() only adds if not already present.
    env['company.holiday'].setup_saturday_in_calendar()