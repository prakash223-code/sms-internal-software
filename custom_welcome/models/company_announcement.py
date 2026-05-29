# -*- coding: utf-8 -*-
from odoo import models, fields, api


class CompanyAnnouncement(models.Model):
    _name        = 'company.announcement'
    _description = 'Company Announcement'
    _order       = 'is_pinned desc, date desc, id desc'
    _rec_name    = 'title'

    # ------------------------------------------------------------------
    # FIELDS
    # ------------------------------------------------------------------

    title = fields.Char(
        string='Title',
        required=True,
    )

    body = fields.Text(
        string='Details',
        help='Optional longer description shown as a sub-line on the dashboard.',
    )

    date = fields.Date(
        string='Posted On',
        required=True,
        default=fields.Date.today,
    )

    posted_by = fields.Char(
        string='Posted By',
        default=lambda self: self.env.user.name,
    )

    is_pinned = fields.Boolean(
        string='Pinned',
        default=False,
        help='Pinned announcements always appear at the top of the dashboard.',
    )

    active = fields.Boolean(
        string='Active',
        default=True,
        help='Uncheck to hide this announcement from the welcome dashboard.',
    )

    # ------------------------------------------------------------------
    # COMPUTED
    # ------------------------------------------------------------------

    date_label = fields.Char(
        string='Date Label',
        compute='_compute_date_label',
        store=False,
    )

    @api.depends('date')
    def _compute_date_label(self):
        """
        Returns a friendly label: 'Today', 'Yesterday', or 'DD Mon YYYY'.
        Used on the dashboard for a cleaner look than a raw date.
        """
        from datetime import date as date_type
        today     = fields.Date.today()
        yesterday = fields.Date.subtract(today, days=1)

        for rec in self:
            if not rec.date:
                rec.date_label = ''
            elif rec.date == today:
                rec.date_label = 'Today'
            elif rec.date == yesterday:
                rec.date_label = 'Yesterday'
            else:
                rec.date_label = rec.date.strftime('%-d %b %Y')