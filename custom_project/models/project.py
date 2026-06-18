# -*- coding: utf-8 -*-
# project.py
# PURPOSE: Timesheet integration for project.project
#   • Adds timesheet summary fields (total hours spent, remaining hours)
#   • Computes against account.analytic.line records linked to the project
#   • No create() override — default stage logic lives in project_project.py

import logging
from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class ProjectProject(models.Model):
    _inherit = 'project.project'

    timesheet_ids = fields.One2many(
        'account.analytic.line',
        'project_id',
        string='Timesheets Entries',
    )

    total_time_spent = fields.Float(
        string='Total Hours Spent',
        compute='_compute_time_spent',
        store=True,
    )

    remaining_time = fields.Float(
        string='Remaining Hours',
        compute='_compute_time_spent',
        store=True,
    )

    @api.depends('timesheet_ids.unit_amount', 'allocated_hours')
    def _compute_time_spent(self):
        for rec in self:
            spent = sum(rec.timesheet_ids.mapped('unit_amount'))
            rec.total_time_spent = spent
            rec.remaining_time = max(0.0, rec.allocated_hours - spent)

