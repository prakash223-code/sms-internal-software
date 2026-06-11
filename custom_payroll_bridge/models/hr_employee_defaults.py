from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)

# ── Role → Group mapping ──────────────────────────────────────────────────────
#
# All XML IDs verified against test_db via ir_model_data.
#
# Removed (do not exist in Odoo 19 / these modules have no custom groups):
#   ✗ custom_expense.group_expense_user    → no groups defined in custom_expense
#   ✗ custom_attendance.group_attendance_user → no groups defined in custom_attendance
#   ✗ crm.group_crm_user                  → Odoo 19 CRM uses sales_team groups
#
# CRM access in Odoo 19:
#   sales_team.group_sale_salesman             = Own documents only
#   sales_team.group_sale_salesman_all_leads   = All documents (HR needs this)
#   sales_team.group_sale_manager              = Administrator (Manager needs this)
#
_ROLE_GROUPS = {
    'employee': [
        'base.group_user',                                # internal user login
        'hr_attendance.group_hr_attendance_officer',      # check in / check out
        'project.group_project_user',                     # view assigned tasks
        'custom_work_report.group_work_report_employee',  # submit daily work reports
    ],
    'hr': [
        # ── Base ──────────────────────────────────────────────────────────────
        'base.group_user',
        'hr_attendance.group_hr_attendance_officer',
        'project.group_project_user',
        'custom_work_report.group_work_report_employee',
        # ── Work report ───────────────────────────────────────────────────────
        'custom_work_report.group_work_report_hr',        # review all work reports
        # ── HR management ─────────────────────────────────────────────────────
        'hr.group_hr_user',                               # manage employees
        'hr.group_hr_manager',                            # create/manage contracts
        'hr_attendance.group_hr_attendance_user',         # manage all attendance
        # ── Leave ─────────────────────────────────────────────────────────────
        'hr_holidays.group_hr_holidays_manager',          # approve / reject leave
        # ── Payroll (admin level) ─────────────────────────────────────────────
        'bi_hr_payroll.group_hr_payroll_manager',         # generate payslips for all
        # ── Project (needed to create projects from won leads) ───────────────────
        'project.group_project_manager',                  # create / manage projects
        # ── CRM (query to project conversion) ─────────────────────────────────
        'sales_team.group_sale_salesman_all_leads',       # view all leads/opportunities
    ],
    'manager': [
        # ── Base ──────────────────────────────────────────────────────────────
        'base.group_user',
        'hr_attendance.group_hr_attendance_officer',
        'project.group_project_user',
        'custom_work_report.group_work_report_employee',
        # ── Work report ───────────────────────────────────────────────────────
        'custom_work_report.group_work_report_hr',
        'custom_work_report.group_work_report_manager',   # full work report control
        # ── HR management ─────────────────────────────────────────────────────
        'hr.group_hr_user',
        'hr.group_hr_manager',
        'hr_attendance.group_hr_attendance_user',
        'hr_attendance.group_hr_attendance_manager',      # full attendance control
        # ── Leave ─────────────────────────────────────────────────────────────
        'hr_holidays.group_hr_holidays_manager',
        # ── Payroll ───────────────────────────────────────────────────────────
        'bi_hr_payroll.group_hr_payroll_manager',
        # ── CRM (full control) ────────────────────────────────────────────────
        'sales_team.group_sale_salesman_all_leads',
        'sales_team.group_sale_manager',                  # CRM administrator
        # ── Project ───────────────────────────────────────────────────────────
        'project.group_project_manager',                  # full project visibility
    ],
}


class HrEmployeeDefaults(models.Model):
    _inherit = 'hr.employee'

    # ── Role field ────────────────────────────────────────────────────────────
    employee_role = fields.Selection(
        selection=[
            ('employee', 'Employee'),
            ('hr', 'HR'),
            ('manager', 'Manager'),
        ],
        string='System Role',
        default='employee',
        required=True,
        help='Controls which system permissions are assigned via the Setup Permissions button.',
    )

    # ── Core assignment method ────────────────────────────────────────────────
    def _assign_role_groups(self):
        """Assign groups to the linked user based on employee_role."""
        for employee in self:
            user = employee.user_id
            if not user:
                _logger.info(
                    'Role groups: skipping %s — no linked user', employee.name
                )
                continue

            role = employee.employee_role or 'employee'
            xml_ids = _ROLE_GROUPS.get(role, _ROLE_GROUPS['employee'])

            group_ids = []
            skipped = []
            for xml_id in xml_ids:
                try:
                    group = self.env.ref(xml_id)
                    group_ids.append((4, group.id))
                except Exception:
                    skipped.append(xml_id)
                    _logger.warning(
                        'Role groups: group not found — %s (skipped)', xml_id
                    )

            if group_ids:
                user.sudo().write({'group_ids': group_ids})
                _logger.info(
                    'Role groups: assigned %d group(s) to user "%s" '
                    '(employee: "%s", role: %s)',
                    len(group_ids), user.login, employee.name, role,
                )
            if skipped:
                _logger.warning(
                    'Role groups: %d group(s) skipped for "%s": %s',
                    len(skipped), employee.name, skipped,
                )

    # ── Backward-compat alias ─────────────────────────────────────────────────
    def _assign_default_employee_groups(self):
        self._assign_role_groups()

    # ── Auto-assign on create ─────────────────────────────────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        employees = super().create(vals_list)
        employees.filtered('user_id')._assign_role_groups()
        return employees

    # ── Auto-assign when user_id is linked later ──────────────────────────────
    def write(self, vals):
        password = vals.pop('new_password', None)  # ← add this line
        res = super().write(vals)
        if 'user_id' in vals and vals['user_id']:
            self._assign_role_groups()
        if password:  # ← add this block
            for emp in self:
                if emp.user_id:
                    emp.user_id.sudo().write({'password': password})
                    _logger.info(
                        'Password set for user "%s" (employee: "%s")',
                        emp.user_id.login, emp.name,
                    )
        return res

    # ── Button action ─────────────────────────────────────────────────────────
    def action_setup_employee_permissions(self):
        self.ensure_one()

        if not self.user_id:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'No Linked User',
                    'message': (
                        f'{self.name} has no linked user. '
                        'Link a user first, then run Setup Permissions.'
                    ),
                    'type': 'warning',
                    'sticky': True,
                },
            }

        self._assign_role_groups()

        role_labels = dict(self._fields['employee_role'].selection)
        role_label = role_labels.get(self.employee_role, 'Employee')

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Permissions Updated',
                'message': f'{role_label} permissions assigned to {self.name}.',
                'type': 'success',
                'sticky': False,
            },
        }