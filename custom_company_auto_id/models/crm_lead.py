from odoo import models, fields, api

class CrmLead(models.Model):
    _inherit = 'crm.lead'

    partner_company_id_display = fields.Char(
        string='Auto Company ID',
        compute='_compute_partner_company_id_display',
        store=False,
    )

    @api.depends('partner_id', 'partner_id.company_custom_id')
    def _compute_partner_company_id_display(self):
        for lead in self:
            if lead.partner_id and lead.partner_id.company_custom_id:
                lead.partner_company_id_display = lead.partner_id.company_custom_id
            else:
                lead.partner_company_id_display = ''