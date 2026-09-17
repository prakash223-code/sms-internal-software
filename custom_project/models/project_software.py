from odoo import _, api, fields, models


class ProjectSoftware(models.Model):
    _name = 'project.software'
    _description = 'Software Used (Timesheet Dropdown)'
    _rec_name = 'name'
    _order = 'name'

    name = fields.Char(string='Software Name', required=True)

    active = fields.Boolean(default=True, string='Active')

    _sql_constraints = [
        (
            'project_software_name_unique',
            'unique(name)',
            'A software with this name already exists.',
        ),
    ]

    @api.constrains('name')
    def _constrains_unique_name_ci(self):
        # Case-insensitive duplicate check — the SQL unique constraint above
        # only catches exact-case duplicates (e.g. "Figma" vs "figma" would
        # otherwise both pass).
        for rec in self:
            domain = [('name', '=ilike', rec.name), ('id', '!=', rec.id)]
            if self.search_count(domain):
                raise models.ValidationError(
                    _('A software named "%s" already exists (name matching '
                      'is case-insensitive).') % rec.name
                )