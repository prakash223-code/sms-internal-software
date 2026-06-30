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
        'base.group_user',  # internal user login
        'hr_attendance.group_hr_attendance_officer',  # check in / check out
        'project.group_project_user',  # view assigned tasks
        'custom_work_report.group_work_report_employee',  # submit daily work reports
        'hr_timesheet.group_hr_timesheet_user',
        # NOTE: manufacturing group is NOT listed here for all employees.
        # It is granted selectively in _assign_role_groups() to employees
        # whose department name contains "manufacturing" (case-insensitive).
    ],
    'hr': [
        # ── Base ──────────────────────────────────────────────────────────────
        'base.group_user',
        'hr_attendance.group_hr_attendance_officer',
        'project.group_project_user',
        'custom_work_report.group_work_report_employee',
        # ── Work report ───────────────────────────────────────────────────────
        'custom_work_report.group_work_report_hr',  # review all work reports
        # ── HR management ─────────────────────────────────────────────────────
        'hr.group_hr_user',  # manage employees
        'hr.group_hr_manager',  # create/manage contracts
        'hr_attendance.group_hr_attendance_user',  # manage all attendance
        # ── Leave ─────────────────────────────────────────────────────────────
        'hr_holidays.group_hr_holidays_manager',  # approve / reject leave
        # ── Payroll (admin level) ─────────────────────────────────────────────
        'bi_hr_payroll.group_hr_payroll_manager',  # generate payslips for all
        # ── Project (needed to create projects from won leads) ───────────────────
        'project.group_project_manager',  # create / manage projects
        # ── CRM (query to project conversion) ─────────────────────────────────
        'sales_team.group_sale_salesman_all_leads',  # view all leads/opportunities
        'hr_timesheet.group_hr_timesheet_approver',  # ← all timesheets
        # ── Sales ─────────────────────────────────────────────────────────────
        # group_sale_salesman_all_leads (already listed above) implies
        # group_sale_salesman, but we list the base group explicitly so the
        # Sales menu and sale order creation are always guaranteed even if
        # Odoo ever changes the implied_ids chain.
        'sales_team.group_sale_salesman',
        # ── Purchase ──────────────────────────────────────────────────────────
        # HR needs visibility into purchase orders for budget / vendor oversight.
        'purchase.group_purchase_user',
        # ── Manufacturing ─────────────────────────────────────────────────────
        # HR must be able to view manufacturing orders, BOMs, warranties, and
        # serial numbers for workforce / production oversight.
        'custom_manufacturing.group_mrp_custom_user',
        # NOTE: custom_project.group_team_manager is intentionally NOT
        # granted to the HR role. Per spec, project completion-request
        # approval/rejection and editing a locked (completed) project are
        # Manager-only actions — HR is explicitly excluded from both, even
        # though HR has broad access elsewhere in this module (tasks,
        # stages, etc. via hr.group_hr_user checks). If that ever needs to
        # change, add 'custom_project.group_team_manager' here too.
    ],
    'manager': [
        # ── Base ──────────────────────────────────────────────────────────────
        'base.group_user',
        'hr_attendance.group_hr_attendance_officer',
        'project.group_project_user',
        'custom_work_report.group_work_report_employee',
        # ── Work report ───────────────────────────────────────────────────────
        'custom_work_report.group_work_report_hr',
        'custom_work_report.group_work_report_manager',  # full work report control
        # ── HR management ─────────────────────────────────────────────────────
        'hr.group_hr_user',
        'hr.group_hr_manager',
        'hr_attendance.group_hr_attendance_user',
        'hr_attendance.group_hr_attendance_manager',  # full attendance control
        # ── Leave ─────────────────────────────────────────────────────────────
        'hr_holidays.group_hr_holidays_manager',
        # ── Payroll ───────────────────────────────────────────────────────────
        'bi_hr_payroll.group_hr_payroll_manager',
        # ── CRM (full control) ────────────────────────────────────────────────
        'sales_team.group_sale_salesman_all_leads',
        'sales_team.group_sale_manager',  # CRM administrator
        # Sales menu — base group listed explicitly (implied by the groups
        # above, but explicit is safer against future Odoo implied_ids changes)
        'sales_team.group_sale_salesman',
        # ── Purchase ──────────────────────────────────────────────────────────
        # Manager has full purchase control — approve orders, manage vendors.
        'purchase.group_purchase_manager',
        # ── Project ───────────────────────────────────────────────────────────
        'project.group_project_manager',  # full project visibility
        'hr_timesheet.group_timesheet_manager',
        # ── Team Management (custom_project) ──────────────────────────────────
        # Grants Team Project / Manager — required to:
        #   • approve/reject task assignment requests
        #   • approve/reject project completion requests
        #   • edit a locked (completed) project or its tasks
        #   • reopen a locked project
        #   • manage task stages (Configuration > Task Stages)
        # implied_ids on this group already pulls in Team Lead + Employee
        # tiers (see custom_project/security/security_groups.xml), so
        # listing those separately here isn't necessary.
        'custom_project.group_team_manager',
        # ── Manufacturing ─────────────────────────────────────────────────────
        # Manager needs full visibility across manufacturing: orders, BOMs,
        # cost analysis, warranties, serial numbers.
        # group_mrp_custom_manager implied_ids already pulls in
        # group_mrp_custom_user, so all menus/views are covered.
        'custom_manufacturing.group_mrp_custom_manager',
    ],
}

# ── Department-based manufacturing access ────────────────────────────────────
# Any department whose name contains one of these strings (case-insensitive)
# will automatically receive custom_manufacturing.group_mrp_custom_user,
# regardless of employee_role.  This means an employee-role user in the
# Manufacturing department will see the manufacturing menu just like an HR or
# Manager user would — without being promoted to a higher role.
_MANUFACTURING_DEPT_KEYWORDS = ['manufacturing']


def _is_manufacturing_dept(department):
    """Return True if the department name contains any manufacturing keyword."""
    if not department:
        return False
    name_lower = (department.name or '').lower()
    return any(kw in name_lower for kw in _MANUFACTURING_DEPT_KEYWORDS)


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

    # ── Admin safety check ───────────────────────────────────────────────────
    def _is_admin_account(self, user):
        """
        True if the given res.users record is the database superuser (uid=1)
        or holds Settings/Administrator access (base.group_system).
        Used to exclude admin accounts from all role-based group automation.
        """
        if not user:
            return False
        if user.id == 1:  # the bootstrap superuser, e.g. odoobot/admin uid=1
            return True
        try:
            return user.sudo().has_group('base.group_system')
        except Exception:
            return False

    # ── Core assignment method ────────────────────────────────────────────────
    def _assign_role_groups(self):
        """
        Assign groups to the linked user based on employee_role.
        First strips ALL role-managed groups from the user, then applies
        only the groups for the current role — ensures clean role switching
        with no leftover permissions from a previous role.

        Additionally, employees whose department name contains "manufacturing"
        (case-insensitive) receive custom_manufacturing.group_mrp_custom_user
        regardless of their role.  This is additive — the department check
        never removes groups that the role already granted.

        SAFETY: Administrator / superuser accounts are NEVER touched by this
        method, regardless of their employee_role value. Role-based group
        management is meant for ordinary employee/hr/manager accounts only —
        an admin's permissions are a deliberate manual decision, not
        something a role dropdown should be able to overwrite. Without this
        guard, an admin employee record left on the default 'employee' role
        would get stripped down to the minimal employee group set on the
        next Setup Permissions click or module upgrade resync — which is
        exactly what happened before this guard was added.
        """
        # Resolve every group that appears in ANY role so we know
        # exactly which ones this module manages.
        all_managed_ids = set()
        for xml_ids in _ROLE_GROUPS.values():
            for xml_id in xml_ids:
                try:
                    all_managed_ids.add(self.env.ref(xml_id).id)
                except Exception:
                    pass

        # Also treat the manufacturing groups as managed so they are stripped
        # cleanly when an employee moves out of the manufacturing department.
        for xml_id in (
            'custom_manufacturing.group_mrp_custom_user',
            'custom_manufacturing.group_mrp_custom_manager',
        ):
            try:
                all_managed_ids.add(self.env.ref(xml_id).id)
            except Exception:
                pass

        for employee in self:
            user = employee.user_id
            if not user:
                _logger.info(
                    'Role groups: skipping %s — no linked user', employee.name
                )
                continue

            if self._is_admin_account(user):
                _logger.info(
                    'Role groups: skipping %s — linked user "%s" is an '
                    'Administrator/superuser account, never managed by role '
                    'automation.', employee.name, user.login
                )
                continue

            role = employee.employee_role or 'employee'
            xml_ids = _ROLE_GROUPS.get(role, _ROLE_GROUPS['employee'])

            # Resolve target groups for this role
            target_ids = set()
            skipped = []
            for xml_id in xml_ids:
                try:
                    target_ids.add(self.env.ref(xml_id).id)
                except Exception:
                    skipped.append(xml_id)
                    _logger.warning(
                        'Role groups: group not found — %s (skipped)', xml_id
                    )

            # ── Department-based manufacturing access ─────────────────────
            # Grant group_mrp_custom_user to any employee whose department
            # name contains "manufacturing" (case-insensitive), even if
            # their role is plain 'employee'.  HR already has this group
            # via _ROLE_GROUPS; Manager gets group_mrp_custom_manager
            # (which implies user), so this extra step is a no-op for them
            # but harmless.
            if _is_manufacturing_dept(employee.department_id):
                try:
                    mfg_group_id = self.env.ref(
                        'custom_manufacturing.group_mrp_custom_user'
                    ).id
                    target_ids.add(mfg_group_id)
                    _logger.info(
                        'Role groups: granting manufacturing access to "%s" '
                        '(department: "%s")',
                        employee.name,
                        employee.department_id.name,
                    )
                except Exception:
                    _logger.warning(
                        'Role groups: custom_manufacturing.group_mrp_custom_user '
                        'not found — manufacturing department access skipped for "%s".',
                        employee.name,
                    )

            # Current groups on user
            current_ids = set(user.sudo().group_ids.ids)

            # Keep groups we don't manage (system/odoo internal groups)
            unmanaged_ids = current_ids - all_managed_ids

            # Final set: unmanaged groups + target role groups
            final_ids = list(unmanaged_ids | target_ids)

            user.sudo().write({'group_ids': [(6, 0, final_ids)]})

            _logger.info(
                'Role groups: applied role "%s" to user "%s" (employee: "%s") '
                '— %d group(s) set, %d skipped',
                role, user.login, employee.name,
                len(target_ids), len(skipped),
            )
            if skipped:
                _logger.warning(
                    'Role groups: skipped for "%s": %s', employee.name, skipped
                )

    # ── Backward-compat alias ─────────────────────────────────────────────────
    def _assign_default_employee_groups(self):
        self._assign_role_groups()

    # ── Bulk re-sync (called automatically on every module upgrade) ───────────
    @api.model
    def _resync_all_role_groups(self):
        """
        Re-applies role-based groups to EVERY employee with a linked user,
        regardless of their employee_role (employee / hr / manager).

        Wired up via a <function> call in data/role_groups_resync.xml with
        noupdate="0", so it re-runs automatically on every
        `-u custom_payroll_bridge` upgrade — not just on fresh install.

        This means: whenever _ROLE_GROUPS is edited (e.g. a new group is
        added to the 'manager' role), the next module upgrade will apply
        it to all existing employees without anyone needing to open each
        employee form and click "Setup Permissions" by hand.

        Safe to run repeatedly — _assign_role_groups() is idempotent per
        employee (it always recomputes the full target set from scratch).
        """
        employees = self.search([('user_id', '!=', False)])
        if not employees:
            _logger.info('Role groups resync: no linked-user employees found — skipping.')
            return

        employees._assign_role_groups()

        _logger.info(
            'Role groups resync: re-applied role-based groups to %d employee(s) '
            '(roles: employee / hr / manager) on module upgrade.',
            len(employees),
        )

    # ── Auto-assign on create ─────────────────────────────────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        employees = super().create(vals_list)
        employees.filtered('user_id')._assign_role_groups()
        return employees

    # ── Auto-assign when user_id or department_id changes ────────────────────
    def write(self, vals):
        password = vals.pop('new_password', None)
        res = super().write(vals)
        # Re-apply groups whenever the linked user OR the department changes,
        # so that moving an employee into/out of Manufacturing automatically
        # grants/revokes the manufacturing menu access.
        if 'user_id' in vals and vals['user_id']:
            self._assign_role_groups()
        elif 'department_id' in vals:
            self.filtered('user_id')._assign_role_groups()
        if password:
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

        dept_note = ''
        if _is_manufacturing_dept(self.department_id):
            dept_note = ' Manufacturing menu access granted (department match).'

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Permissions Updated',
                'message': f'{role_label} permissions assigned to {self.name}.{dept_note}',
                'type': 'success',
                'sticky': False,
            },
        }