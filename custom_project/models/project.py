# -*- coding: utf-8 -*-
from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class ProjectProject(models.Model):
    _inherit = 'project.project'

    # ─────────────────────────────────────
    # Timesheet Fields
    # ─────────────────────────────────────

    timesheet_ids = fields.One2many(
        'account.analytic.line',
        'project_id',
        string='Timesheets',
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

    # ⚠️ Uncomment ONLY if your Odoo version does not already have
    # 'allocated_hours' on project.project (check Settings > Technical > Fields).
    # allocated_hours = fields.Float(
    #     string='Allocated Hours',
    #     default=0.0,
    # )

    # ─────────────────────────────────────
    # Compute
    # ─────────────────────────────────────

    @api.depends('timesheet_ids.unit_amount', 'allocated_hours')
    def _compute_time_spent(self):
        for rec in self:
            spent = sum(rec.timesheet_ids.mapped('unit_amount'))
            rec.total_time_spent = spent
            rec.remaining_time = max(0.0, rec.allocated_hours - spent)

    # ─────────────────────────────────────
    # Default Stages on Project Create
    # ─────────────────────────────────────

    _DEFAULT_STAGE_NAMES = [
        'Requirement',
        'Analysis & Planning',
        'Design / Layout',
        'Development / Execution',
        'Internal Testing',
        'Client Review / Approval',
        'Implementation',
        'Maintenance & Support',
        'Done',
    ]

    def _get_default_stages(self):
        stages = self.env['project.task.type'].search([
            ('name', 'in', self._DEFAULT_STAGE_NAMES)
        ], order='sequence')

        found_names = stages.mapped('name')
        missing = set(self._DEFAULT_STAGE_NAMES) - set(found_names)
        if missing:
            _logger.warning(
                "ProjectProject: default stages not found in DB: %s", missing
            )
        return stages

    @api.model_create_multi
    def create(self, vals_list):
        projects = super().create(vals_list)
        stages = self._get_default_stages()
        if stages:
            for project in projects:
                project.type_ids = [(6, 0, stages.ids)]
        else:
            _logger.warning(
                "ProjectProject: no default stages found — "
                "ensure stages are created before projects."
            )
        return projects