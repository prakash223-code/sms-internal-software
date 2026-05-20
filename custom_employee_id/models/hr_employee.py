from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError
import datetime


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    employee_code = fields.Char(
        string='Employee ID',
        readonly=True,
        copy=False,
        index=True,
    )

    draft_reserved_code = fields.Char(
        string='Reserved Employee Code',
        copy=False,
        groups='base.group_system',
        help='Stores the previous Employee ID when reset to Draft. '
             'Restored on re-confirmation if the department has not changed. '
             'Hidden from all normal users.'
    )

    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
    ], string='Status', default='draft', readonly=True, copy=False,
       tracking=True,
       help='Draft: Record is incomplete, no ID assigned, can be deleted.\n'
            'Confirmed: Employee ID is generated and record is locked.')

    _sql_constraints = [
        ('employee_code_unique', 'UNIQUE(employee_code)',
         'Employee ID must be unique.'),
    ]

    # ------------------------------------------------------------------
    # ORM overrides
    # ------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        # Records start in Draft — NO sequence consumed yet.
        # HR can freely review and correct all fields before confirming.
        return super().create(vals_list)

    def write(self, vals):
        # Block manual edits to employee_code at all times.
        # Only internal system assignment (via context flag) is allowed.
        if 'employee_code' in vals:
            if not self.env.context.get('_system_assign_emp_code'):
                raise UserError(
                    'Employee ID cannot be modified after it has been assigned.'
                )

        # Block department change after confirmation.
        # The Employee ID is already generated from the department code —
        # changing it would create a mismatch between the ID and the department.
        if 'department_id' in vals:
            for emp in self:
                if emp.state == 'confirmed':
                    raise UserError(
                        f'Department cannot be changed for "{emp.name}" '
                        f'because their Employee ID ({emp.employee_code}) '
                        'is already generated from the current department.\n\n'
                        'If this is a genuine department transfer, please '
                        'archive this record and create a new employee entry.'
                    )
        return super().write(vals)

    def unlink(self):
        # Draft: freely deletable — no ID has been consumed yet.
        # Confirmed: permanently blocked — archive instead.
        for emp in self:
            if emp.state == 'confirmed':
                raise UserError(
                    f'"{emp.name}" ({emp.employee_code}) is a confirmed employee '
                    'and cannot be deleted.\n\n'
                    'Please archive them instead to preserve data integrity.'
                )
        return super().unlink()

    # ------------------------------------------------------------------
    # Button actions
    # ------------------------------------------------------------------

    def action_confirm(self):
        """
        Confirms the employee and generates their permanent Employee ID.
        Triggered by the Confirm Employee button — only available in Draft state.

        Reuse logic:
        - If the employee was previously confirmed (draft_reserved_code exists)
          AND the department has not changed since the original ID was generated,
          the same Employee ID is restored. No new sequence number is consumed.
        - If the department changed, a new ID is generated. The old reserved
          code is discarded (that sequence slot is permanently retired).
        """
        for emp in self:
            if emp.state != 'draft':
                raise UserError(f'"{emp.name}" is already confirmed.')

            # Validate all required fields before touching the sequence
            emp._validate_before_confirm()

            current_dept_code = emp.department_id.dept_code.upper().strip()
            reserved = emp.draft_reserved_code

            # Check if we can reuse the previously reserved code.
            # The reserved code encodes the dept code (e.g. 25CFD001),
            # so we verify the current dept code is still present in it.
            if reserved and current_dept_code in reserved:
                code = reserved
            else:
                # Department changed or first-time confirmation — generate new ID
                code = emp._generate_employee_code()

            emp.with_context(_system_assign_emp_code=True).write({
                'employee_code': code,
                'draft_reserved_code': False,   # clear reservation
                'state': 'confirmed',
            })

    def action_reset_to_draft(self):
        """
        Resets a confirmed employee back to Draft.
        Restricted to Managers only.
        Blocked if the employee already has payroll, attendance, or leave data.

        The current Employee ID is saved to draft_reserved_code so it can be
        restored if the same department is kept on re-confirmation.
        """
        self._check_manager_access('reset an employee to Draft')
        for emp in self:
            emp._check_no_business_data()
            emp.with_context(_system_assign_emp_code=True).write({
                'draft_reserved_code': emp.employee_code,  # save for potential reuse
                'employee_code': False,
                'state': 'draft',
            })

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _validate_before_confirm(self):
        """Ensure all fields required for ID generation are present."""
        if not self.name:
            raise ValidationError(
                'Employee name is required before confirming.'
            )
        if not self.department_id:
            raise ValidationError(
                f'Please assign a Department to "{self.name}" before confirming.\n'
                'The Employee ID is generated from the department code.'
            )
        if not self.department_id.dept_code:
            raise ValidationError(
                f'Department "{self.department_id.name}" has no Department Code.\n'
                'Please set the department code first, then confirm the employee.'
            )

    def _generate_employee_code(self):
        """Generate Employee ID: YY + DEPT_CODE + 3-digit global sequence."""
        year_prefix = str(datetime.datetime.now().year)[2:]
        dept_code = self.department_id.dept_code.upper().strip()

        seq = self.env['ir.sequence'].next_by_code('hr.employee.global.seq')
        if not seq:
            raise UserError(
                'Employee ID sequence not found. '
                'Please contact your system administrator.'
            )
        return f'{year_prefix}{dept_code}{seq}'

    def _check_manager_access(self, action_label):
        """Ensure the current user is an HR Manager."""
        if not self.env.user.has_group('hr.group_hr_manager'):
            raise UserError(
                f'Only a Manager can {action_label}. '
                'Please contact your Manager.'
            )

    def _check_no_business_data(self):
        """
        Block reset-to-draft if the employee has any real operational data.
        Uses search_count directly on each model instead of relational field
        names, which vary across Odoo versions and may not exist on hr.employee.
        """
        for emp in self:
            if self.env['hr.payslip'].search_count(
                [('employee_id', '=', emp.id)], limit=1
            ):
                raise UserError(
                    f'"{emp.name}" has payslip records — '
                    'cannot reset to Draft. Archive instead.'
                )
            if self.env['hr.attendance'].search_count(
                [('employee_id', '=', emp.id)], limit=1
            ):
                raise UserError(
                    f'"{emp.name}" has attendance records — '
                    'cannot reset to Draft. Archive instead.'
                )
            if self.env['hr.leave.allocation'].search_count(
                [('employee_id', '=', emp.id)], limit=1
            ):
                raise UserError(
                    f'"{emp.name}" has leave allocations — '
                    'cannot reset to Draft. Archive instead.'
                )