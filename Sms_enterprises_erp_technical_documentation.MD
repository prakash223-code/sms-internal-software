# SMS Enterprises ERP — Technical Documentation

**Audience:** Developers inheriting, maintaining, or extending this system.
**Scope:** Architecture, module inventory, data flows, Odoo 19 gotchas, and operational notes for the custom addon suite built on Odoo 19 Community Edition.

---

## 1. Tech Stack

| Layer | Technology |
|---|---|
| Application framework | Odoo 19.0 Community Edition |
| Language | Python 3 |
| Database | PostgreSQL |
| Frontend | Odoo's OWL framework (JS), QWeb templates, XML views |
| Third-party payroll | `bi_hr_payroll` (BrowseInfo) |
| Third-party UI theme | MuK Web suite (`muk_web_appsbar`, `muk_web_chatter`, `muk_web_colors`, `muk_web_dialog`, `muk_web_group`, `muk_web_refresh`, `muk_web_theme`) |
| IDE / dev environment | PyCharm |
| Amount-in-words (payslip) | `num2words` (Python package) |
| PDF rendering | wkhtmltopdf via Odoo's QWeb-PDF report engine |

**Dev launch command:**
```
odoo-bin --addons-path=odoo/addons,custom_addons -d test_db --dev=all --config=/home/sms-enterprises/Workspace/odoo19/odoo.conf
```

**Paths:**
- Custom addons: `/home/sms-enterprises/Workspace/odoo19/custom_addons/`
- Odoo core: `/home/sms-enterprises/Workspace/odoo19/odoo/`
- Database: `test_db`

**Third-party (not authored in-house, not covered in depth below):**
- `bi_hr_payroll` — BrowseInfo payroll engine. Uses `hr.version` (not `hr.contract`), has no `hr.payslip.input.type` model, and `input_line_ids` on `hr.payslip.input` is `readonly=True` requiring `sudo().create()`.
- MuK Web theme suite — cosmetic/UX layer (appsbar navigation, chatter redesign, color editor, dialog styling, kanban group collapse/expand, page refresh helpers, overall theme). No business logic lives here.

---

## 2. Role System — The Foundation Everything Else Builds On

Three roles drive the entire system's access control: **Employee**, **Manager**, **HR**.

- Stored as `hr.employee.employee_role` (Selection: `employee` / `hr` / `manager`), defined in `custom_payroll_bridge/models/hr_employee_defaults.py`.
- Role → Odoo security group mapping lives in a Python dict, `_ROLE_GROUPS`, in that same file — **not** in XML data, so it survives module upgrades without `noupdate` complications, but also means it's not visible/editable from the UI.
- Applying a role is a **manual, per-employee action**: HR/Manager clicks **Setup Permissions** on the employee form, which calls `_assign_role_groups()`. This strips all role-managed groups from the linked `res.users` record, then re-applies the full set for the current role.
- **This is deliberate, not an oversight.** An earlier version auto-resynced every employee's groups on every module upgrade (`_resync_all_role_groups`, wired via `data/role_groups_resync.xml`). It was removed after it stripped permissions from an Administrator account on a live system. The method still exists in code (dead code, kept for reference/manual shell use) but the data file that triggered it automatically is no longer loaded in `__manifest__.py`.
- **Administrator accounts are hard-excluded** from all role automation via `_is_admin_account()` (checks `uid == 1` or `base.group_system` membership) — this guard exists specifically because of the incident above.
- Department-based bonus: any employee in a department whose name contains "manufacturing" (case-insensitive) gets `custom_manufacturing.group_mrp_custom_user` automatically appended, regardless of role.

**Module load-order dependency:** `custom_payroll_bridge` depends on `custom_project` specifically so that `custom_project.group_team_manager` exists before `_ROLE_GROUPS` references it — install/upgrade order between unrelated-looking modules matters here.

---

## 3. Module Inventory

### 3.1 `custom_attendance` (v19.0.2.1.0)
**Purpose:** Check-in/check-out, late detection, leave (Casual/Earned/Medical/Permission), company holidays, monthly attendance summaries — the data backbone for payroll.

**Depends on:** `hr`, `hr_attendance`, `hr_holidays`

**Key models:**
- `hr.attendance` (extended) — `is_late`, `late_minutes` (computed via `_compute_is_late`), `auto_checkout`, `permission_overflow_minutes`
- `company.holiday` — declared holidays + "Compensatory Working Day" flag (Saturday-only), auto-syncs `resource.calendar.leaves`
- `attendance.monthly.summary` — working/present/late/leave/absent days per employee per month, `draft`/`confirmed` state machine
- `hr.leave` (extended) — `is_auto_permission` flag distinguishes system-generated Permission deductions from manual requests
- Leave policy logic (`leave_policy.py`) — anniversary-based allocation + carry-forward
- Permission logic (`permission_deduction.py`, `permission_policy.py`) — the 4-hour monthly buffer

**Business logic highlights:**
- **Late threshold:** 9:30 AM, computed timezone-aware per employee (`pytz`, falls back to `Asia/Kolkata`). Shifts to the resource calendar's afternoon start time (read from `resource.calendar.attendance`, hardcoded fallback 14:00) on any date with an **approved AM half-day leave**.
- **`_check_and_revert_conflicting_half_leave`** exists in code (auto-refuses an AM leave if the employee checks in during the AM window) but per later product decisions this auto-revert behavior was **explicitly abandoned** in favor of a simpler manual workflow: the system does nothing automatically, and HR must manually refuse the leave from Time Off to trigger a lateness recompute. Confirm whether this method is still wired into the live code path or has become dead code before relying on it — check call sites in `attendance.py`.
- **2nd/4th Saturday rule:** computed via `_saturday_occurrence()` (`(day-1)//7 + 1`), no data stored — pure calculation, backed by a yearly cron (`_cron_generate_saturday_resource_leaves`) that also writes `[SAT-OFF]`-named `resource.calendar.leaves` records so the Time Off calendar shows them greyed out.
- **Permission deduction math** (`permission_deduction.py`): on late check-in, subtracts any same-day manual Permission request (`is_auto_permission=False`) from late minutes first; only the remainder draws from the monthly allocation; anything beyond the remaining allocation becomes `permission_overflow_minutes`, which flows into payroll.
- **Leave carry-forward policy** (hardcoded in `leave_policy.py`'s `LEAVE_POLICY` dict): Casual 12 days/50% cap, Earned 3 days/full carry, Medical 3 days/full carry. Anniversary date resolved from `contract_date_start` → `first_contract_date` → `create_date`, in that priority order.

**Five cron jobs** (`data/attendance_cron.xml`), staggered by priority and time:
1. `_cron_auto_checkout` — daily, closes open sessions at 19:00 local
2. `_cron_generate_monthly_summary` — monthly, generates previous month's summary
3. `_cron_generate_saturday_resource_leaves` — monthly, refreshes 2nd/4th Saturday calendar entries for current+next year
4. `_cron_process_leave_anniversaries` — daily, carry-forward on matching join-date anniversaries
5. `_cron_generate_monthly_permission_allocation` — monthly, grants flat 240-minute Permission allocation

**Post-init hook:** restricts Kiosk and Apps/Settings menus to `base.group_system` only, found by name search (not XML ID) since both changed in Odoo 19.

---

### 3.2 `custom_payroll_bridge` (v19.0.1.2.0)
**Purpose:** Bridges `custom_attendance`'s monthly summary into `bi_hr_payroll`'s salary computation; owns the role system; owns the branded payslip print template.

**Depends on:** `bi_hr_payroll`, `custom_attendance`, `custom_project`

**Key models:**
- `hr.payslip` (extended) — `slip_month`/`slip_year` (computed+inverse pair driving `date_from`/`date_to`), `attendance_summary_id`, `unpaid_absent_days`, `confirmed_date`. Overrides `compute_sheet()` to inject `ABSENT_DAYS`/`WORKING_DAYS`/`PERMISSION_OVERFLOW` payslip inputs from the confirmed monthly summary *before* salary rules run.
- `hr.employee` (extended, split across `hr_employee.py` and `hr_employee_defaults.py`) — unlocks payroll-restricted fields via `groups=False` overrides (private_phone, bank accounts, contract dates, etc.) so HR/Manager can see them without granting broader Accounting/HR-Manager group membership; owns `employee_role` and the Setup Permissions button.
- `hr.version` (extended) — same `groups=False` unlock pattern for contract/wage fields restricted by core `hr`/`bi_hr_payroll`.
- `res.partner` (extended) — unlocks `credit_limit` read access to avoid an AccessError when `res.users.create()` touches it indirectly via `parent.write()`.
- `res.users` (extended) — strips a blank `password: False` from the simplified Create User form so passlib doesn't crash on a non-string value.

**Salary rules** (`data/payroll_bridge_data.xml`, `noupdate="0"` so edits redeploy on upgrade):
- `ABSENT_DED`: `-(contract.wage / working_days * absent_days)`
- `PERM_OVERFLOW_DED`: per-minute rate = `(wage / working_days) / 540` (540 = 9-hour day), multiplied by overflow minutes

**Print template:** `report_payslip_custom_template.xml` fully bypasses `web.external_layout`, hand-draws the SMS Enterprises letterhead. A dedicated `report.paperformat` (`data/payslip_paperformat.xml`) with near-zero margins was created specifically because the default paperformat's 84mm margin reserve (for the external layout header/footer this template doesn't use) caused content overflow onto a second page.

---

### 3.3 `custom_project` (v19.0.3.0.0)
**Purpose:** Team-based task management, timesheets, cross-team assignment approval, project completion locking.

**Depends on:** `hr`, `project`, `mail`, `custom_employee_id`, `hr_timesheet`, `analytic`

**Key models:**
- `team.team` — custom model (not Odoo's `crm.team`), `team_lead_id` + `member_ids`
- `project.task` (extended) — `assigned_to_ids` (**Many2many**, not Many2one — supports multiple assignees), `assigned_by`, `team_id`, `task_state` (custom Selection: draft/assigned/in_progress/completed/verified/closed, distinct from native `state`), `can_edit_task`/`can_change_state` (computed access flags)
- `project.project` (extended, split across `project.py` and `project_project.py`) — `team_id`, `is_locked`/`locked_by`/`locked_date`/`stage_id_before_lock`, timesheet rollup fields (`total_time_spent`, `remaining_time`)
- `task.assignment.request` — cross-team assignment approval workflow
- `project.completion.request` — project-completion approval workflow, **Manager-only approval** (HR can submit but not approve — deliberately narrower than most other approvals in the system)
- `account.analytic.line` (extended) — `software_used` field, `can_edit_line` computed flag, overridden `_apply_ir_rules` (see below)

**Access model (Python-enforced, layered on top of `ir.rule`):**
- `_is_privileged()`: Manager, Team Lead, or HR bypass most restrictions.
- `_is_completion_manager()`: **stricter** — Manager only, used specifically for the project-lock freeze (even HR is blocked from editing a locked project).
- Regular employees can only fully edit tasks they created (`create_uid`); an assignee who didn't create the task may still write to `task_state` and `timesheet_ids` (the `_ASSIGNEE_EDITABLE_FIELDS` allowlist) so task progression and time logging still work.
- Visibility is enforced by overriding `_search()` on `project.task` directly in Python (a `Domain` intersection), not purely via `ir.rule` — this is on top of, not instead of, the record rules in `security/record_rules.xml`.

**Cross-team assignment logic** (`_handle_cross_team_assignment` in `project_task.py`): when `assigned_to_ids` gains a new employee not on the task's team, a `task.assignment.request` is created instead of assigning immediately; the task's `task_state` becomes `'assigned'` only if *at least one* newly-added employee could be assigned immediately (same team), else stays `'draft'`. Managers bypass this entirely.

**Notable Odoo 19 gotcha found here:** notifications fired from inside `create()`/`write()` use a **fresh cursor via `self.env.cr.postcommit.add()`** rather than reusing `self.env` — postcommit callbacks run after the original cursor has closed, so reusing `self.env` silently fails with no visible error. This was diagnosed as the reason task-assignment notifications worked from `create()` (which already used this pattern) but silently failed from `write()` until fixed.

**Timesheet access policy** (`account_analytic_line.py`): every internal user (`base.group_user`) can **read** all timesheet lines company-wide (needed for team coordination), but may only create/edit/delete their own. HR and Manager have full CRUD on any line. This is enforced via an **overridden `_apply_ir_rules()`** that unconditionally bypasses the read-mode rule check for any internal user — added after the equivalent `ir.rule`-only approach proved unreliable because it depended on manual custom-group assignment (`group_team_employee`) that kept being missed. `base.group_user` membership is automatic for every internal login, so this fix removed that single point of failure. Write/create/unlink are still hard-enforced by `write()`/`unlink()` overrides, independent of the read bypass.

**Kanban stage handling:** `project.task.type.name_create()` is overridden so adding a new kanban column by typing a name **links an existing stage** (by case-insensitive match) rather than creating a new one; if no match exists, it raises `UserError` — employees cannot invent new stages from the kanban board. Stage CRUD from Configuration is gated to Manager/HR via `_check_stage_access()`.

---

### 3.4 `custom_project_document`
**Purpose:** File upload + inline browser preview for project-level documents.

**Depends on:** `project`, `hr`, `custom_project`

**Key models:** `project.document` — Binary file storage (`attachment=True`), `_user_can_write()` gate: Manager, HR, or the project's Team Lead (resolved dynamically via `team.team.team_lead_id`, not a stored field on the employee).

**Preview mechanism:** custom controller (`/project/document/preview/<id>`) builds a raw `werkzeug.Response` with `Content-Disposition: inline`, reading through `ir.attachment` first (more reliable than the field directly when `attachment=True`) and falling back to mimetype guessing from the filename extension. Same pattern reused in `custom_hr_document` and `custom_work_report`.

---

### 3.5 `case_study` (v1.0, `application: True`)
**Purpose:** Standalone knowledge-base/portfolio module — completed work write-ups organized by department, with timesheets and documents, separate from `custom_project`.

**Depends on:** `base`, `mail`, `hr`, `project`, `hr_timesheet`

**Key models:** `case.study`, `case.study.stage`, `case.study.department`, `case.study.timesheet`, `case.study.document`, `case.study.tag`; `case.study.software` exists in code but is no longer exposed in Configuration menus (kept for data integrity of any existing records only).

**Access model:** every internal user can read all case studies (`rule_case_study_employee_read_all`, `domain_force=[(1,'=',1)]`, `perm_write=False`); a **separate** rule (`rule_case_study_employee_write_own`) grants write only if the user's employee record appears in `assigned_employee_ids`. HR gets an unrestricted third rule. This read/write split-rule pattern is repeated identically for `case.study.timesheet` and `case.study.document`.

**Lock workflow:** `action_confirm()`/`action_draft()` toggle a simple `locked` boolean — no state machine, just a Boolean gate on `readonly` throughout the form.

---

### 3.6 `custom_crm_project`
**Purpose:** One-way, one-time conversion of a Won CRM opportunity into a `project.project`.

**Depends on:** `crm`, `project`, `hr`, `custom_project`

**Key models:**
- `crm.lead` (extended) — `is_converted` (Boolean gate, permanent once set), `project_id` (link), guards on `unlink()`/`write()` (`active=False`) blocking deletion/archiving of converted leads.
- `project.project` (extended, second file also named `project_project.py` alongside `custom_project`'s — Odoo merges the `_inherit`, this is normal but worth knowing when grepping) — `project_number` (auto-sequence on create), `crm_lead_id`, same visibility `_search()` override pattern as `custom_project`.

**Conversion guard:** `action_convert_to_project()` requires `stage_id.is_won == True`; blocked entirely if already converted. Button visible only to `hr.group_hr_user` in the view (`crm_lead_views.xml`) — Manager also implicitly has this via group inheritance since `custom_payroll_bridge` grants HR-level groups to Manager role, but confirm current XML `groups=` attribute state before assuming Manager sees it (memory conflicts slightly with the manual text, which the person edited to say "HR officers and Managers" — worth reconciling against the actual `groups="hr.group_hr_user"` attribute in the file, which does **not** currently include a Manager group).

**Deactivated core rules:** `project.project_public_members_rule` and `project.project_project_manager_rule` are explicitly disabled (`active=False`) in `security/record_rules.xml` because they would otherwise OR against and override this module's own team-scoped visibility rules.

---

### 3.7 `custom_expense`
**Purpose:** Internal expense submission/approval, decoupled from Odoo's Accounting `hr.expense` (this is a from-scratch model, not an extension).

**Depends on:** `hr`, `project`, `mail`

**Key models:**
- `custom.expense` — state machine `draft → submitted → approved`/`rejected`, `category_id` (M2O to `custom.expense.category`, seeded with 6 default categories), `attachment_ids` (M2M to `ir.attachment`), optional `project_id` link.
- `custom.expense.reject.wizard` — enforces a mandatory, non-blank rejection reason.
- Phase-2 placeholder fields (`payment_state`, `account_move_id`) exist on the model but are unused — reserved for a future Accounting integration that has not been built.

**Approval gate:** `action_approve()`/`action_reject()` restricted to `hr.group_hr_manager` (i.e., HR Manager tier specifically) — plain HR officers (`hr.group_hr_user`) can view/submit but not decide, mirrored in both `ir.model.access.csv` (create/write only on `hr.group_hr_user`, full CRUD on `hr.group_hr_manager`) and `security/expense_security.xml` record rules.

---

### 3.8 `custom_hr_document`
**Purpose:** Employee-record document upload with inline preview. HR-only — employees have zero access.

**Depends on:** `hr`

**Key model:** `hr.employee.document` — same Binary+preview-controller pattern as `custom_project_document`. `write()`/`unlink()` hard-restricted to `hr.group_hr_user` in Python (redundant with, but not solely reliant on, the `ir.model.access.csv` grants).

**Access split:** `hr.group_hr_user` gets full CRUD; `hr.group_hr_manager` gets read-only only (`access_hr_employee_document_manager` row: `1,0,0,0`) — note this means a Manager who is *not* also in `hr.group_hr_user` cannot edit documents, only view them. Since the role system grants Manager role members `hr.group_hr_user` too (see `_ROLE_GROUPS['manager']`), this is moot in practice for anyone provisioned through Setup Permissions, but matters if groups are ever assigned manually outside that flow.

---

### 3.9 `custom_work_report`
**Purpose:** Daily work-log with a simple submit/reset workflow, no approval step.

**Depends on:** `hr`, `project`, `mail`

**Key model:** `work.report` — `draft`/`submitted` states only. `action_submit()` notifies the `group_work_report_manager` group. `action_reset_draft()` is Manager-only (in the view; not additionally hard-gated in Python beyond the `ir.model.access.csv`/group visibility).

**Three custom groups** (`group_work_report_employee`/`_hr`/`_manager`), auto-populated via a **`post_init_hook`** that writes `implied_ids` onto `base.group_user`, `hr.group_hr_user`, and `hr.group_hr_manager` respectively — meaning every internal user gets the employee tier automatically at install time without needing Setup Permissions to run first. This is a different mechanism from the main role system in `custom_payroll_bridge`.

**Attachment access fix** (`_reparent_attachments()`): attachments uploaded via the standard `many2many_binary` widget default to `res_model='ir.ui.view'` with no `res_id`, which under Odoo's own `ir.attachment` access rules is readable **only by the uploader**. This method re-points `res_model`/`res_id` to the actual `work.report` record after save so the report's own `ir.rule` (employee-own / HR-all / Manager-all) governs attachment visibility instead — same underlying problem and fix pattern independently discovered and solved in the preview-controller modules.

---

### 3.10 `custom_welcome`
**Purpose:** Post-login home dashboard — greeting, live clock, quote of the day (a rotating Thirukkural couplet, `welcome.quote` seeded via CSV with ~1330 records), check-in/out toggle, weekly attendance stats, pinned announcements.

**Depends on:** `hr`, `hr_attendance`, `hr_holidays`, `custom_attendance`

**Key models:**
- `welcome.dashboard` (`TransientModel`) — computed entirely in `default_get()`, no persisted state; re-derives everything (greeting, quote-of-day index via `date.today().toordinal() % len(quotes)`, attendance status, weekly stats) on every open.
- `company.announcement` — simple pinned/dated notice board, HR-manageable.
- `welcome.quote` — the Thirukkural dataset (1330 couplets), read-only to regular users, editable by `base.group_system`.

**Post-init hook:** sets `action_id` on every internal (`share=False`, `active=True`) user to the Welcome dashboard action, so it opens automatically on login. Explicitly notes in a comment that Odoo 19 removed both `res.users.groups_id` domain searching *and* `res.groups.users`' reverse relation as ways to enumerate users by group — `share=False` is used instead as the canonical internal-user filter.

**Weekly stats logic** (`_compute_weekly_stats`): working-day denominator is the **full Monday–Saturday week** (not just days elapsed so far), reusing `company.holiday.is_holiday()` so 2nd/4th Saturdays and declared holidays are excluded consistently with the monthly summary logic in `custom_attendance`.

---

### 3.11 `custom_login_theme`
**Purpose:** Cosmetic only — dark green gradient / glassmorphic branding on the login screen.

**Depends on:** `web`

Single template inheriting `web.login_layout`, injects a CSS body class (`o_sms_login`) via SCSS asset. No models, no logic.

---

### 3.12 `custom_session_expire`
**Purpose:** Logs users out when the browser (not just the tab) is actually closed, distinguishing that from a page refresh or bfcache restore.

**Depends on:** `web`

**Mechanism:** JS listens for `pagehide`/`pageshow`. On `pagehide`, calls `/web/session/request_logout` which stamps `pending_logout_at` in the session. On `pageshow` (fires on refresh/bfcache restore, i.e. tab is still alive), calls `/web/session/cancel_logout` to clear that stamp. An `ir.http._authenticate()` override checks: if `pending_logout_at` is set and more than 5 seconds have elapsed on the *next* request, the session is force-logged-out (`request.session.logout(keep_db=True)`). The 5-second grace window is calibrated so a same-tab refresh (cancel arrives in under a second) survives, while an actual browser close (next visit is minutes/hours later) always exceeds it.

`cancel_logout`'s route uses `auth='public'` deliberately — by the time it fires the session may already be gone, and the route is written to no-op safely rather than error.

---

### 3.13 `custom_manual`
**Purpose:** Serves the in-app role-filtered user manual (the HTML file iterated on extensively in this project) at `/manual`.

**Depends on:** `hr`, `custom_payroll_bridge`

**Architecture:** Two routes only —
- `GET /manual` (`auth='user'`) — serves the static HTML file via `tools.file_open` (the Odoo-19-safe way to read a module-bundled static file; do not use raw Python `open()` on a computed path, since that breaks under multi-addons-path or zipped-module deployments).
- `GET /manual/my_role` (`auth='user'`) — the **sole source of truth** for which role the manual shows. Reads `hr.employee.employee_role` for `request.env.uid` server-side; there is no client-side role selector anywhere. Admins (`base.group_system`) are floored at `'manager'` level if their own employee record would otherwise resolve to `'employee'` (e.g. no linked record, or unset role) — this exists purely so admins can see and QA the Manager/HR content without needing a dummy employee role set.

All actual role-based content filtering happens client-side in the served HTML/JS (`data-role="employee,manager,hr"` attributes + `applyRoleVisibility()`), driven by the server-verified role returned from `/manual/my_role`.

---

### 3.14 `custom_company_auto_id`
**Purpose:** Auto-generates a unique, country-prefixed ID for every Company-type contact.

**Depends on:** `base`, `contacts`, `crm`

**Key model:** `res.partner` (extended) — `company_custom_id`. Format: `{prefix}{seq}{cleaned_name}`, e.g. `N001SMSTECHGARMENTS`. Prefix logic: `country.code == 'IN'` → `N`; anything else → `IN`. Sequence code `res.partner.company.id`, padding 3, prefix/suffix forced empty on every generation call (defensive against the sequence record's own prefix/suffix drifting).

**Generation timing:** deliberately **not** triggered inside `create()`/`write()` — a comment explicitly notes ID generation happens via the frontend `FormController` JS **after an explicit Save**, with `action_generate_company_id()` as a Python fallback button for records that slipped through without one (e.g. converted from individual, or pre-dating this module). `name_create()` (used by many2one quick-create dropdowns) is special-cased to skip ID generation and the country constraint entirely, since those quick-creates are typically individuals, not companies.

**Constraint:** `Country` is mandatory for any `is_company=True` record (`_check_company_country_required`), enforced both client-side (`required="is_company"` in XML) and as a model `@api.constrains`.

Also touches `crm.lead` — a computed, read-only `partner_company_id_display` mirrors the linked partner's ID onto the lead/opportunity form.

---

### 3.15 `custom_employee_id`
**Purpose:** Generates the permanent Employee ID (format `YY` + department code + 3-digit global sequence, e.g. `25CFD003`) and manages the Draft → Confirmed employee lifecycle.

**Depends on:** `hr`

**Key models:**
- `hr.department` (extended) — `dept_code` (uppercase-forced, unique, locked once any employee — including archived — is assigned to that department via `_compute_has_employees`, which deliberately checks the DB directly with `search_count` rather than trusting the `member_ids` cache, since that can be stale during batch operations).
- `hr.employee` (extended) — `employee_code`, `draft_reserved_code` (hidden from all normal users via `groups='base.group_system'`), `state` (`draft`/`confirmed`).

**Confirm/reset lifecycle:**
- `action_confirm()`: validates name + department + department code are all present, then generates or **reuses** an ID. Reuse logic: if `draft_reserved_code` is set and the current department code is still embedded in it, the same code is restored (no new sequence number consumed); otherwise a fresh ID is generated via `_generate_employee_code()`.
- `action_reset_to_draft()`: **Manager-only** (`hr.group_hr_manager` specifically, not just HR), blocked entirely if the employee has any payslip, attendance, or leave-allocation records (`_check_no_business_data`, checked via direct `search_count` on each model rather than relying on relational field names, which the code notes vary across Odoo versions).
- `write()` blocks manual edits to `employee_code` outside the internal `_system_assign_emp_code` context flag, and blocks changing `department_id` once `state == 'confirmed'` (the ID is derived from the department code — changing it would desync them).
- `unlink()` blocks deletion of any confirmed employee; Draft employees remain freely deletable.

---

### 3.16 `custom_manufacturing` (v19.0.2.0.0)
**Purpose:** Extends standard Odoo `mrp` with Assembly/Production BOM typing, component criticality tracking, cost analysis, serial number generation, and warranty management.

**Depends on:** `base`, `mrp`, `stock`, `product`, `mail`, `account`, `stock_account`

**Key models:**
- `mrp.bom` (extended) — `manufacturing_type` (assembly/production/both), `custom_bom_ref` (auto-sequence), `warranty_years` (default carried onto generated warranties), `assembly_notes`/`production_notes`.
- `mrp.bom.line` (extended) — `component_type` (raw_material/sub_assembly/bought_out/consumable), `is_critical`, `component_notes`.
- `mrp.production` (extended, largest model in the module) — inherits `manufacturing_type` from its BOM (computed, stored); Client fields; Assembly/Production detail fields (separate date ranges + notes per type); **cost analysis** (`total_component_cost` computed live from `move_raw_ids` × `standard_price`, plus manually-entered `labour_cost`/`overhead_cost`, yielding `total_production_cost`, `profit_amount`, `profit_percentage`, `profit_status`); **component readiness** (`component_status`: pending/partial/ready, computed from `move_raw_ids.quantity` vs `product_uom_qty`).
- `mrp.production.serial` — one row per generated unit, linked to the MO.
- `mrp.warranty` — `warranty_status` (active/expiring/expired) computed from `warranty_end` vs today, `days_remaining`, with a daily cron (`action_send_expiry_alerts`) that currently only **logs** expiring/expired warranties (no actual notification/email is sent — the cron is a logging placeholder, not a working alert system as the docstring name implies).
- `mrp.serial.wizard` / `mrp.serial.wizard.line` (`TransientModel`) — two-step preview-then-confirm flow: `action_generate()` builds N preview rows client-side without persisting, `action_confirm()` writes both `mrp.production.serial` and `mrp.warranty` records together.

**Security:** two custom groups, `group_mrp_custom_user` (implies `mrp.group_mrp_user`) and `group_mrp_custom_manager` (implies `mrp.group_mrp_manager` + the user tier). Every custom-manufacturing model also grants access to the *native* `mrp.group_mrp_user`/`mrp.group_mrp_manager` groups directly in `ir.model.access.csv` — meaning a plain Odoo Manufacturing user (not provisioned through this system's role flow) still sees these custom models, which is worth knowing if manufacturing access ever needs auditing.

**Reports:** two QWeb-PDF reports, both **fully bypass `web.external_layout`** (same pattern as the payslip template) — Job Card (`report_mrp_job_card`, components/cost/serials/instructions) and Warranty Certificate (`report_mrp_warranty_certificate`).

**Known Community-edition gaps** (confirmed via official Odoo 19 docs during the manual-writing phase, not present in this codebase): no Shop Floor tablet app, no Quality app, no PLM, no advanced MRP-II scheduling — all Enterprise-only. This module's serial/warranty/job-card system exists specifically to cover the gap left by the missing Enterprise Quality/Shop-Floor tooling.

---

## 4. Third-Party / Vendor Modules (not authored in-house)

| Module | Role |
|---|---|
| `bi_hr_payroll` | Core payroll engine (BrowseInfo) — salary structures, rules, payslips |
| `muk_web_appsbar` | Left-hand app switcher bar UI |
| `muk_web_chatter` | Redesigned chatter/messaging panel |
| `muk_web_colors` | Theme color editor |
| `muk_web_dialog` | Dialog/modal styling |
| `muk_web_group` | Kanban group collapse/expand controls |
| `muk_web_refresh` | Manual/automatic page refresh helpers |
| `muk_web_theme` | Overall visual theme (navbar, layout) |

None of these were modified — treat upgrades to them as vendor updates, not local changes to review line-by-line.

---

## 5. Cross-Module Data Flow — Attendance to Payslip

```
Employee checks in/out (custom_attendance: hr.attendance)
        │
        ▼
Late detection + Permission deduction (custom_attendance: permission_deduction.py)
        │
        ▼
Monthly Summary generated (cron or manual batch wizard) — attendance.monthly.summary
        │
        ▼
HR confirms Monthly Summary (state: draft → confirmed) — LOCKS the numbers
        │
        ▼
Payslip created, month/year set (custom_payroll_bridge: hr.payslip.slip_month/slip_year)
        │
        ▼
compute_sheet() → _sync_absent_days_input() reads the CONFIRMED summary,
injects ABSENT_DAYS / WORKING_DAYS / PERMISSION_OVERFLOW as hr.payslip.input
        │
        ▼
Salary rules ABSENT_DED / PERM_OVERFLOW_DED fire against those inputs
        │
        ▼
Payslip confirmed → confirmed_date stamped → Print Payslip (branded template)
```

**Critical failure mode:** if the Monthly Summary is not `confirmed` at the moment `compute_sheet()` runs, `_sync_absent_days_input()` silently falls back to `working_days=30` and zero deductions — it does **not** wait for confirmation or retroactively recompute. Confirming the summary *after* computing the payslip requires manually recomputing the payslip again.

---

## 6. Odoo 19 Confirmed Breaking Changes / Gotchas

Compiled from direct debugging across this project — verify against official changelogs before assuming these hold on future point releases:

- `res.groups` no longer has a `.users` inverse relation → query `res.users` via `('group_ids', 'in', [group_id])` domain instead.
- `groups_id` on `res.users` renamed to `group_ids`.
- Kanban views require `<templates><t t-name="card">...</t></templates>`, not the old `<t t-name="kanban-box">`.
- `hr.leave.allocation.remaining_leaves` does not exist → use `virtual_remaining_leaves` (returns **hours** directly for hour-unit leave types, not a fraction-of-day value).
- `hr.leave.allocation.number_of_hours_display` exists only on `hr.leave.allocation`, not on `hr.leave`.
- `project.task.state` uses values like `'1_done'`, `'01_in_progress'` — not the older `kanban_state` field.
- `ir.actions.actions._for_xml_id()` is the correct API for resolving action dicts from a button method (not `.read()[0]`).
- `web_read_group` calls `_where_calc` directly, **bypassing `_search` overrides** — Python-level visibility filters implemented by overriding `_search()` (as done throughout `custom_project`) must also override `_read_group` if kanban grouped views need the same filtering.
- `requires_allocation` / `employee_requests` on `hr.leave.type` are Booleans requiring `eval="True"`/`eval="False"` in XML, not string values.
- `allocation_validation_type` valid value is `'no_validation'`, not `'no'`.
- `ir.cron` no longer has a `numbercall` field.
- Search views: no Python expressions in domains, no `<separator/>`, no `<group>` wrappers inside `<search>` — filters must be flat, direct children.
- `<menuitem>` `group_ids` **accumulates** across upgrades rather than replacing — requires direct psql cleanup if stale groups pile up over many upgrades.
- `arch_db` columns are stored as `jsonb`, requiring `::text` casting for raw SQL queries against view architecture.
- OWL template expressions use JavaScript syntax (`!x`, `&&`, `||`), not Python (`not`, `and`, `or`) — caught in `custom_project`'s `project_stage_selector.xml` OWL extension.
- `standardFieldProps` no longer exposes `props.value` for X2Many fields → use `this.props.record.data[this.props.name]` and `useX2ManyCrud()`.
- `@route(type='json')` → renamed to `type='jsonrpc'` in controller decorators.
- Attachments created with no `res_id` are only readable by their creator (`_check_private_fields`-style access) → must reparent via a `_reparent_attachments()`-style fix on `create()`/`write()` if a many2many_binary upload needs to be visible to more than the uploader. This exact fix was independently applied in `custom_work_report`, and the same underlying constraint drove the custom preview-controller pattern in `custom_project_document`/`custom_hr_document`.

---

## 7. Deliberate Design Decisions That Look Like Bugs But Aren't

| Behavior | Why |
|---|---|
| Setup Permissions is a manual button, not automatic on role change | Auto-resync on upgrade once stripped an Administrator's access on a live system |
| Checking in during an approved AM leave does nothing automatically | Simpler, more predictable manual workflow chosen over the more complex auto-revert (`_check_and_revert_conflicting_half_leave`) that was originally built |
| HR cannot approve project completion (Manager-only) | Deliberate spec: project completion is treated as a heavier, Manager-tier decision than most other approvals |
| HR *can* edit a locked project's tasks... wait, no — even HR is blocked | `_check_project_lock_access` / `_is_completion_manager()` intentionally exclude HR, unlike almost every other permission check in `custom_project` which treats HR as privileged |
| Employees can view ALL timesheets company-wide, not just their team's | Explicit product decision for cross-team coordination visibility; write access remains own-only |
| `custom_expense` approval requires HR **Manager**, not plain HR officer | Separate tier from most of this system's "HR-can-do-it" pattern |
| Case study documents/timesheets have identical split-rule (read-all / write-if-assigned) pattern repeated three times | Consistent access model across `case.study`, `case.study.timesheet`, `case.study.document` rather than a single shared mixin — three separate rule sets, watch for drift if the policy changes |
| Warranty expiry cron only logs, doesn't email/notify | `action_send_expiry_alerts` is a monitoring placeholder as implemented — do not assume warranty holders or staff are actually notified without checking current code |
| CRM→Project conversion button's visible groups may not match written manual text | Manual content says "HR officers and Managers"; the view XML's `groups=` attribute as captured says `hr.group_hr_user` only — reconcile before treating either as ground truth |

---

## 8. Deployment / Ops Reference

**Module upgrade command pattern:**
```
odoo-bin --addons-path=odoo/addons,custom_addons -d test_db -u <module_name> --stop-after-init
```

**Deployment decision matrix:**
| Change type | Required action |
|---|---|
| Pure Python logic change | Server restart only |
| New field / view change | `-u <module>` |
| CSS/asset change | Delete `ir_attachment` records matching `/web/assets/%`, then `-u <module>`, then hard browser refresh |
| `bi_hr_payroll` bridge data change | Upgrade **both** `bi_hr_payroll` and `custom_payroll_bridge` together |

**Shell hygiene** (established during development, still applies for future maintenance):
- One statement at a time in `odoo-bin shell` — multiline paste can silently fail.
- Re-fetch all variables at the start of each new shell session (no hot reload of `.py` changes — `exit()` and relaunch after editing).
- `env.cr.commit()` after every meaningful write in a shell session.
- Stop the web server before direct DB operations to avoid Postgres serialization conflicts.
- `ValidationError` during an interactive `create()` doesn't guarantee a clean rollback — call `env.cr.rollback()` and `env.clear()` before retrying.

**Cloud hosting:** decision was pending as of the last product discussion — DigitalOcean or Hetzner VPS preferred over GoDaddy (assessed as hardware-equivalent but lower reliability); avoid this being stale by the time of actual deployment — re-confirm current status before acting on it.

---

## 9. Suggested Next Steps for a New Developer

1. Read this document alongside the in-app manual at `/manual` (role-filtered walkthrough of every feature from a user's perspective — useful for understanding intended behavior, not implementation).
2. Stand up a local instance following the launch command in §1, load `test_db` or a recent backup.
3. Trace one full cycle manually in the ORM shell: create a test employee → confirm them (`custom_employee_id`) → assign a role and Setup Permissions (`custom_payroll_bridge`) → check them in late (`custom_attendance`) → generate + confirm a monthly summary → create + compute a payslip (`custom_payroll_bridge` + `bi_hr_payroll`). This single walkthrough touches the module boundaries that matter most.
4. Before changing any security/access-rule file, search for the model's `ir.rule` records across *all* modules — several models (`project.task`, `account.analytic.line`, `case.study`) have multiple layered rules across different files, and Python-level overrides (`_search`, `_apply_ir_rules`) that are easy to miss if you only grep XML.
5. Confirm the two flagged discrepancies in §7 (CRM conversion button's visible groups; the dormant `_check_and_revert_conflicting_half_leave` method) against current production code before making assumptions in either direction.

---

*Document generated from direct source inspection of all 16 custom modules (`custom_attendance`, `custom_payroll_bridge`, `custom_project`, `custom_project_document`, `case_study`, `custom_crm_project`, `custom_expense`, `custom_hr_document`, `custom_work_report`, `custom_welcome`, `custom_login_theme`, `custom_session_expire`, `custom_manual`, `custom_company_auto_id`, `custom_employee_id`, `custom_manufacturing`) plus the third-party dependency list, as of the module versions stated in each section. No content here was inferred without a corresponding code reference.*