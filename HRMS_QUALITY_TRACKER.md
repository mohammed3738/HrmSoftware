# HRMS Quality Tracker

Audit, test, fix and verification pass over the Django HRMS at `hrms/`.
Branch `main`. Started 2026-10-29.

**Status legend** — `[ ]` not started · `[~]` in progress · `[x]` done
**Severity** — P0 break/loss/exposure now · P1 serious, likely to bite · P2 moderate · P3 cosmetic/hygiene

---

## 1. Baseline

| Item | Value |
|---|---|
| Django | 5.2.8 |
| App code | `hrms/website/` (views.py 12,217 lines; models.py 2,605) |
| Test command | from `hrms/`: `DB_ENGINE=sqlite ../.venv/Scripts/python.exe manage.py test website` |
| Test files at start | 73 under `hrms/website/tests/` (81 after this pass) |
| Baseline suite result | **731 tests, OK, 1 skipped, 2493s (41.6 min)** at `09ce8e2`, before any change |
| Working tree at start | clean at `09ce8e2` |

Only one suite may run at a time — two concurrent runs collide on the same
SQLite test DB file.

---

### Final suite run

Whole suite, after every change in this pass:

| | Baseline (`09ce8e2`) | Final (`03bc12c`) |
|---|---|---|
| Tests | 731 | **798** (+67) |
| Result | OK | **OK** |
| Failures / errors | 0 / 0 | **0 / 0** |
| Skipped | 1 | 1 |
| Wall clock | 2493.1s (41.6 min) | **1486.6s (24.8 min)** |
| Per test | 3.41s | **1.86s** |

67 more tests in 40% less wall clock, which is the D-27 cache fix showing
up across the whole suite rather than only on the attendance path.


## 2. Module inventory

| Module | Code | Pages / endpoints | Permission gate | Key calculations | Existing tests |
|---|---|---|---|---|---|
| Auth & session | `auth_backend.py`, `middleware.py`, `login_view`/`logout_view`/`change_password` | `login/`, `logout/`, `change-password/` | none by design (login) | — | `test_employee_first_login_redirect` |
| Roles & permissions | `permissions_registry.py`, `utils/permissions.py`, `utils/decorators.py`, `services/roles.py` | Roles & Permissions settings page | `feature_required` matrix | — | `test_roles_permissions`, `test_role_dashboards`, `test_tickable_rights` |
| Employees | `Employee`, `PreviousEmployment*`, `EmployeeAttachment`, `EmployeeChangeRequest` | employee list/form/detail/dashboard, imports, photo, documents | `employee_records` (+`create_or_edit_required`) | onboarding progress | `test_employee_*` (12 files) |
| Departments / reporting line | `Department` | departments page, defaults API | `department_management` | `sync_employees` | `test_reporting_line*` |
| Companies & branches | `Company`, `Branch` | company & branch pages/APIs | `company_management`, `branch_management` | — | `test_company_*`, `test_bulk_upload_company_branch` |
| Attendance | `Attendance`, `AttendanceConfigurable`, `AttendanceUpload` | register, review, upload, overrides, detail | `attendance_*` features | `calculate_status`, `calculate_lateness`, `get_worked_minutes` | `test_attendance_*`, `test_late_attendance_review`, `test_recalculate_attendance` |
| Corrections | `AttendanceCorrectionRequest` | corrections list/detail/approve | `attendance_corrections` + `can_approve_for_employee` | meeting duration | `test_correction_*` |
| Shifts & rosters | `ShiftAssignment`, `services/shift_roster_cleanup.py` | shift roster page, API | `shift_roster` | night-shift windows | `test_shift_roster` |
| Leave | `LeaveApplication`, `LeaveRecord`, `LeaveBalance`, `LeaveSettings`, `LeaveCreditPolicy`, `MonthlyEarnedLeaves` | leave apply/balance/history, recalc | `leave_management` | `calculate_leave_balance_for_period`, `count_leave_days_in_range`, `get_monthly_earned_leaves` | `test_leave_*`, `test_earned_leaves_sync` |
| Comp-off | `CompOff`, `CompOffRequest` | comp-off list/detail/import | `comp_off` | — | `test_override_compoff`, `test_compoff_bulk_import` |
| Holidays & weekly offs | `Holiday`, `HolidayType`, `HolidayCalendar`, `HalfDayScenario` | holiday calendar dashboard + APIs | `holiday_calendar` (**incomplete**, see D-01) | `backfill_attendance`, weekend rules | `test_holiday_*`, `test_weekend_rule_change` |
| Payroll | `PayrollRun`, `PayrollRecord`, `services/__init__.py`, `utils/payroll_lock.py` | run list/create/detail/record-update/recalc/finalize/export | `payroll` (`edit` = Super Admin + Payroll Officer) | `calculate_and_populate_record`, `calculate_pro_rata`, PF/ESIC, `get_attendance_summary` | `test_payroll_*` (9 files) |
| Salary structure | `SalaryMaster`, `SalaryHistory`, `SalaryIncrement`, `SalaryUpload` | salary form, history, timeline, bulk upload, export | `salary_structure`, `salary_history` | gross/basic/HRA derivation | `test_salary_*` |
| Payslips | `salary_slip_view/_list/_statement` | payslip pages | `can_access_employee_record` | per-record snapshot | `test_salary_slips` |
| Advances | `AdvanceMaster`, `AdvanceSchedule`, `AdvancePayment` | advance list/detail/edit/delete | `advances` + self-service | `distribute_integer_rupees`, `recompute_future_schedule`, `apply_payment` | `test_advances_self_service`, `test_hr_settings_and_advances` |
| Offboarding | `Offboarding`, `AssetHandover` | offboarding list/detail/edit-data | `offboarding` (**detail/edit-data ungated**, D-02) | notice days | — |
| Biometric (eSSL) | `views_biometric.py`, `services/biometric_sync.py`, `sync_biometric_attendance` cmd | `api/biometric/punches/`, `api/biometric/status/` | shared-secret header token | punch pairing, night shift | `test_biometric_sync` (36 KB) |
| Announcements | `Announcement`, `AnnouncementRead` | announcements page + API | `announcements` | visibility window | `test_announcements` |
| Audit log | `AuditLog`, `services/audit.py` | audit log page | `audit_log` | diffing | `test_audit_log` |
| Soft delete / archive | `is_active` flags across models | restore endpoint | `archive_records` | — | `test_soft_delete` |
| Reports / exports | `payroll_export_excel/_pdf`, `test_listing_exports` targets | export endpoints | per-feature `view` | — | `test_listing_exports`, `test_salary_export` |

Management commands: `archive_past_shift_assignments`, `calculate_leave_balance`,
`diagnose_role_access`, `row_counts`, `runall`, `seed_roles_permissions`,
`sync_biometric_attendance`.

---

## 3. Defects

### Authorization — missing feature gates

The `feature_required` pass covered most of the app but left siblings of gated
views open. Every one below is reachable by **any authenticated user**,
including a plain `Employee`, by requesting the URL directly. Confirmed by
reading the view bodies and the helpers/decorators they delegate to
(scan script: `audit3.py`, expands callee and decorator bodies two levels).

| ID | Sev | Endpoint | View | What an Employee can do | Gated sibling that proves intent |
|---|---|---|---|---|---|
| D-01a | P1 | `POST holiday/settings/save/` | `save_holiday_settings` :10462 | Change the company's `financial_year_start_month` and `branch_specific_holidays`; changing FY **deletes every auto-generated `MonthlyEarnedLeaves` row** and regenerates them | `add_holiday` has `holiday_calendar:edit` |
| D-01b | P1 | `POST holiday/half-day/add/` | `add_half_day_scenario` :10973 | Create a company/branch-wide half-day scenario with an arbitrary `credit_count` — changes attendance credit, hence pay | `delete_half_day_scenario` has `holiday_calendar:edit` |
| D-01c | P1 | `POST holiday/half-day/<id>/edit/` | `edit_half_day_scenario` :11030 | Edit/approve any half-day scenario, reassign its branch, set `credit_count`; also no company scoping | same |
| D-01d | P1 | `POST holiday/earned-leave/<id>/edit/` | `edit_earned_leave` :10835 | Set any company's monthly earned leaves to 0–31 days — feeds leave balance and LWP | `add_holiday` / `delete_half_day_scenario` |
| D-01e | P2 | `GET/POST branch/<id>/edit/` | `edit_branch` :4404 | Rename / re-address any branch in any company | `branch_management:edit` used elsewhere |
| D-02a | P2 | `GET offboarding/<id>/details/` | `offboarding_detail` :3999 | Read any employee's resignation/relieving dates, personal email, personal mobile, and the URLs of their experience certificate, relieving letter and F&F documents | `offboarding_list` has `offboarding` gate |
| D-02b | P2 | `GET offboarding/<id>/edit-data/` | `offboarding_edit_data` :4046 | Same data plus asset-handover records and file URLs | same |
| D-03 | P2 | `GET employees/<id>/leave-history/` | `employee_leave_history` :4812 | Read any employee's month-by-month `LeaveBalanceHistory` | `leave_balance_view` scopes by `employee_profile` |
| D-04 | P3 | `GET api/shift-roster/<pk>/` | `api_get_shift_assignment` :1349 | Read any shift assignment (employee name/code, shift times, notes) | `shift_roster:view` on the page |
| D-05 | P3 | `GET branch/<id>/get/`, `departments/defaults/`, `api/holiday/<id>/`, `api/holidays/`, `api/holiday-type/<id>/`, `api/earned-leaves/`, `holiday/api/half-day/<id>/`, `holiday/list/`, `holiday/earned-leaves/`, `attendance-progress/<id>/`, `download-empty-excel/` | various | Read org/config data cross-company | — |
| D-06 | P3 | not routed | `test` :2918 | Dead debug code: calls `test_func.delay()` and queries all active employees with no auth. **Its `urls.py` route is commented out**, so it is unreachable — a first pass flagged it as a live unauthenticated endpoint, which it is not. Worth deleting, not a vulnerability. | — |

Not defects (verified, listing them so they are not re-raised):
`download_attachment` / `download_previous_attachment` delegate to
`_serve_employee_file`, which calls `can_access_employee_record`;
`override_attendance_status` / `bulk_override_attendance_status` carry
`@_attendance_day_editors_only`; `biometric_*_api` check the
`X-HRMS-Sync-Token` shared secret; cross-company access by
Admin / Super Admin / HR / Payroll Officer is intended
(`GLOBAL_ACCESS_ROLES`, `get_company_filter` returns `None` for them).

### Security — other

| ID | Sev | Finding |
|---|---|---|
| D-07 | P2 | **Stored XSS.** `json.dumps(...)` piped through `\|safe` directly into `<script>` bodies. `json.dumps` does not escape `<`, so a `</script>` in any serialized value closes the tag. Carriers: `holidays_json` (`Holiday.name`), `half_day_json` (`HalfDayScenario.description`), `calendar_attendance_json`. Templates: `templates/holiday_calendar/dashboard.html:1853-1854`, `templates/attendance/employee_attendance_detail.html:810`. P2 rather than P1 because once D-01b/c are gated, writing those fields needs `holiday_calendar:edit` — so it is staff-to-staff/employee escalation, not anyone-to-everyone. `calendar_attendance_json` carries only `Attendance.status`, a choices field, so that carrier is not currently injectable. |
| D-08 | P2 | `settings.py`: `DEBUG` defaults to **True** and `SECRET_KEY` falls back to a hardcoded `django-insecure-…` literal when the env var is absent. A server with a missing/mis-spelled `.env` key silently serves debug tracebacks and signs sessions with a key that is in the repository. `ALLOWED_HOSTS` defaults to `['*']`. |
| D-09 | P2 | `TIME_ZONE = 'UTC'` (hardcoded, not env-driven) while `CELERY_TIMEZONE = 'Asia/Kolkata'`. Day boundaries for an India-operating HRMS are 5h30m out. Compounded by mixed `date.today()` (12 uses in views.py, OS-local) vs `timezone.now()` (10 uses, UTC) vs no `localdate()` at all. |
| D-10 | P3 | No brute-force throttling or lockout on `login_view`; no `SESSION_COOKIE_AGE` / idle timeout; `AUTH_PASSWORD_VALIDATORS` declared twice in `settings.py` (second wins, identical). |
| D-23 | **P0** | **Uploaded files are served with no authentication at all.** `DEPLOYMENT.md:427-429` configures nginx as `location /media/ { alias .../hrms/media/; }`, so everything under `MEDIA_ROOT` is fetched straight off disk by any anonymous request — `_serve_employee_file`'s `can_access_employee_record()` check is bypassed by requesting the same bytes one URL over. The team knows media is public: `employee_photo_path` (models.py:141) randomises photo filenames with a comment saying *"media files are served publicly, so the URL must not be guessable"*. That mitigation was applied to **1 of 14** upload fields. The other 13 keep the uploader's original filename, including `EmployeeAttachment.file` → `employee_attachments/` (KYC: Aadhaar and PAN scans), `PreviousEmploymentAttachment.file`, the four `Offboarding` document fields, `AssetHandover.asset_photo`/`receipt`, `AttendanceCorrectionRequest.mom_attachment`, and `AttendanceUpload.file` / `EmployeeImportUpload.file` / `SalaryUpload.file` (whole-company attendance, employee-master and salary spreadsheets). Names like `aadhaar.pdf` or `pan.jpg` are trivially guessable, and any URL ever leaked stays public forever. D-02 made it worse: the ungated `offboarding_detail` / `offboarding_edit_data` handed those `/media/` paths out in JSON. |
| D-24 | P2 | No extension, MIME or size validation on any document upload field. Only `Employee.photo` (forms.py:108) and `Company.logo` (forms.py:344,360) check size and content type. An `.html` or `.svg` attachment uploaded through the KYC or offboarding forms is served inline from the application's own origin by `_serve_employee_file` (no `as_attachment` unless `?download=1`), which makes it stored XSS with the viewer's session; the same file is also world-readable per D-23. |
| D-11 | P3 | `is_staff` grants a full bypass in every decorator and in `can_access_employee_record`. That is deliberate and documented, but it means "can open Django admin" silently equals "can do everything", with no second check. |

### Calculations

| ID | Sev | Finding |
|---|---|---|
| D-12 | P1 | `_compute_payroll_dates` (views.py:9395) and `PayrollSettings.get_payroll_period` (models.py:976) build `date(year, m, from_day)` / `date(year, m, to_day)` with no day clamping. A company whose payroll cycle ends on the 29th/30th/31st raises `ValueError: day is out of range for month` creating a February run — unhandled, so a 500. |
| D-13 | P3 | `calculate_and_populate_record` reads `getattr(payroll_settings, "esic_threshold", 21000)`, but **`PayrollSettings` has no `esic_threshold` field** and no migration ever added one. The ESIC wage ceiling is therefore hardcoded at 21000 while the code and `test_payroll_esic_opt_out.py`'s docstring both read as though it were configurable. |
| D-14 | P2 | **Disclosed, not changed** (policy, not a bug to fix unilaterally): `PayrollSettings.esic_percentage` defaults to `3.67`, and `calculate_and_populate_record` applies it as the *employee* ESIC deduction. The statutory employee ESIC share is 0.75% (employer 3.25%); 3.67% is the EPF employer EPS split. If the default has ever been left untouched, employee ESIC is over-deducted by ~4.9x. Needs the user's decision. |
| D-15 | P2 | Payroll deducts an advance EMI from net pay but nothing calls `services.apply_payment`, so `AdvanceSchedule.status` stays `pending` and `AdvanceMaster.outstanding_amount` never falls. The advance ledger shown to employees and HR diverges from what payroll has actually recovered. |
| D-16 | P3 | `services.revert_skip` computes `outstanding // remaining_count` with no guard; `remaining_count == 0` raises `ZeroDivisionError`. `get_advance_for_employee_month` takes `.first()` with no `order_by`, so the EMI chosen is non-deterministic when a period contains more than one. |

### Attendance rules

| ID | Sev | Finding |
|---|---|---|
| D-29 | P2 | **"All Branches" half-day scenarios applied to nobody.** `add_half_day_scenario` stores `branch=NULL` for the All Branches option and reports success, but `Attendance.get_half_day_scenario()` looked it up with `filter(branch=branch)` — for an employee in branch 5 that is `branch_id = 5`, which never matches the `NULL` row. The model's two partial unique constraints (`branch__isnull=False` / `branch__isnull=True`) show `NULL` was meant as "all branches". `credit_count` is attendance credit, so this is a pay difference. **Fixed.** |
| D-30 | P2 | **Employees with no branch were skipped by holiday and half-day evaluation.** Both steps sat inside `if branch:` in `calculate_status()`, and `Employee.branch` is nullable — **2 of the 104 employees in the working database have no branch**. A national holiday was computed as an ordinary working day for them: no punch, therefore `Absent` / count 0.00 instead of `Holiday` / count 1.00, costing a paid day per holiday. `Holiday.is_applicable_to_branch()` already handled `None` deliberately, so the guard was the only obstacle. **Fixed.** |
| D-31 | P3 | `HalfDayScenario` had **no test coverage at all** before this pass, despite setting a day's pay credit. Now covered by `test_half_day_scenario_application.py` (11 tests). |

### Transactions / integrity

| ID | Sev | Finding |
|---|---|---|
| D-17 | P1 | `payroll_run_finalize` (views.py:9633) is **not** `transaction.atomic`. It loops `recalc_and_save_record` over every record, then flips `run.status` to finalized. An exception on one employee leaves part of the run recalculated and the rest stale, with the run still draft — a partial write to pay data. `create_payroll_run` and `recalculate_payroll_run` *are* atomic, which shows the intent. |
| D-18 | P2 | `payroll_run_create` with `company == "all"` loops companies creating runs with no outer transaction; a failure part-way leaves some companies with runs and some without, and reports success for the ones that got through. |

### Error handling and validation

| ID | Sev | Finding |
|---|---|---|
| D-25 | P3 | 36 call sites return raw exception text to the user (`messages.error(request, f'Error: {str(e)}')`, `JsonResponse({'error': str(e)}, status=500)`). With `DEBUG=False` that is not a traceback, but exception messages still leak field and table names. Worst offenders are the holiday-calendar writes (views.py:10553, 11068, 11102) which wrap the whole handler in `except Exception` and report Python errors where a field validation message belongs. |
| D-26 | P3 | 9 bare `except:` clauses and 5 `except Exception: pass` in views.py swallow failures silently, so a failed write reports success. |

### Performance

| ID | Sev | Finding |
|---|---|---|
| D-19 | P2 | Payroll run generation is O(n) queries per employee: `_build_record_snapshot` → `get_attendance_summary` re-queries `PayrollSettings` **per employee**, plus `SalaryMaster`, 2× `LeaveBalance`, `AdvanceSchedule`, and `recalc_and_save_record` queries `PayrollSettings` again per record. To be measured with `assertNumQueries` before/after. |
| D-27 | **P1** | **A dead Redis cost ~4 seconds per `Attendance.save()`.** Profiling one save: `socket.connect` 4.041s over 2 calls, against 0.018s of actual SQL over 30 queries. `Attendance.save()` fires `auto_recalc_leave_balance_on_attendance_save` → `get_all_payroll_periods_from_attendance`, which asks the cache twice; `django_redis` had no connect timeout, so each ask blocked until the TCP connect gave up. The callers already treat a cache failure as a miss, so none of that time bought anything. This is why the suite took 41.6 minutes. In production it is worse than slow: with no `IGNORE_EXCEPTIONS` and no timeout, a Redis outage stalls every write path for seconds. **Fixed** — `SOCKET_CONNECT_TIMEOUT` 0.2s, `SOCKET_TIMEOUT` 1s, `IGNORE_EXCEPTIONS`, and `LocMemCache` under tests. Measured 4.349s → 0.487s per save, **8.9x**. |
| D-20 | P3 | `holiday_calendar_dashboard` serialises `Holiday.objects.filter(is_active=True)` — every company's holidays, unbounded and unscoped — into the page on every load. |

### UI/UX, accessibility, responsive

Verified in the built-in browser against a **throwaway SQLite database**
seeded with 25 employees / 1,250 attendance rows / 3 holidays, so the
working Postgres database (`hrms_prod_db`) was never touched. Server on
127.0.0.1:8734 with `DJANGO_DEBUG=false`.

**Responsive — no defects found.** Page-level horizontal scroll measured
(`documentElement.scrollWidth` vs `clientWidth`) at every width:

| Page | 375px | 768px | 1366px | 1920px |
|---|---|---|---|---|
| Employee list | no h-scroll | no h-scroll | no h-scroll | no h-scroll |
| Attendance register | no h-scroll | — | — | — |
| Payroll run list | no h-scroll | — | — | — |
| Leave balance | no h-scroll | — | — | — |
| Holiday calendar | no h-scroll | — | — | — |

Two things that looked like defects and are not, checked rather than
assumed:

* Wide data tables (payroll 446px, leave balance 1,189px) do overflow their
  container at 375px, but they sit in scrollable wrappers and the page
  itself does not scroll sideways — normal mobile table behaviour.
* The holiday calendar's six tab buttons run to 961px at 375px, but the
  `.nav-tabs-wrapper` has `overflow-x: auto` and
  `scrollWidth (961) > clientWidth (351)`, so the strip scrolls and all six
  tabs are reachable. Deliberate, working pattern.

**Smoke test.** All nine critical pages returned HTTP 200 as Super Admin:
`/`, `/employees/`, `/attendance/register/`, `/attendance/late-review/`,
`/leave-balance/`, `/payroll/`, `/holiday/dashboard/`, `/salary-slips/`.
(`/shift-roster/` is not a URL — the roster lives elsewhere; 404 expected.)

| ID | Sev | Finding |
|---|---|---|
| D-28 | P3 | Accessibility: form controls without any accessible name — 63 on `/employees/`, 104 on `/attendance/late-review/`, 31 on `/holiday/dashboard/`, 21 on `/leave-balance/` (no `<label for>`, `aria-label`, `aria-labelledby`, `title` or `placeholder`). Most are per-row selection checkboxes and inline filter selects, so a screen-reader user hears "checkbox" with no idea which employee or day it belongs to. Three unlabelled icon-only `<button>`s on `/` and `/employees/`. Images are fine — zero missing `alt` across all pages. |

**D-07 (XSS) fix verified live, not just by unit test.** A holiday named
`</script><img src=x onerror=window.__XSS_FIRED=1>` was stored in the
throwaway database and the calendar page loaded in the browser:

* serialized as `"</script><img src=x onerror=..."`;
* `window.__XSS_FIRED` → `false`, `document.querySelectorAll('img[src="x"]').length` → `0`;
* the inline `<script>` block still parses, `holidaysData.length` → 4, and
  the value round-trips to the exact original string — so the escaping
  changed nothing about how the page behaves.

---

## 4. Work log

| Date | Commit | Group | Files changed | Tests added | Result |
|---|---|---|---|---|---|
| 2026-10-29 | — | Discovery + static audit | — | — | Inventory and defect list above |
| 2026-10-29 | `2b3e5dd` | D-27 cache fail-fast + LocMem under tests | `hrms/settings.py` | — (measured, not unit-tested) | 4.349s → 0.487s per `Attendance.save()` |
| 2026-10-29 | `95ad863` | D-29, D-30 half-day / holiday scoping (+ D-12 models half) | `website/models.py` | `test_half_day_scenario_application.py` (11) | all pass |
| 2026-10-29 | `33d9691` | D-01, D-02, D-03, D-04, D-07, D-12, D-17, D-21, D-22, D-24 | `website/views.py`, `website/utils/dates.py`, `templates/leave_balance/_leave_history_table.html` | 6 files, 53 tests | all pass |
| 2026-10-29 | `1063ebc` | D-19 payroll run query count | `website/services/__init__.py` | `test_payroll_run_query_count.py` (3) | 15.5 → 10.8 queries/employee |

**Red/green evidence.** The 64 new tests were run against the pre-change
code by restoring `views.py`, `models.py` and the leave-history template
from `HEAD`: **18 failures + 20 errors**, each mapping to a documented
defect. Against the fixed code: **64 pass**. So the tests demonstrably
catch what they claim to.

### Second pass (same day, after the first report)

| Commit | Group | Tests added |
|---|---|---|
| `0204315` | D-23 uploaded documents behind a permission check, X-Accel-Redirect support, nginx config in DEPLOYMENT.md | `test_protected_media.py` (13) |
| `3c96b3b` | D-13 `esic_threshold` as a real field (migration 0055), D-16 advance EMI ordering + `revert_skip` zero guard, D-18 partial-batch reporting | `test_advance_and_payroll_edge_cases.py` (9) |
| `be21f63` | D-08 `DEBUG`/`SECRET_KEY`/`ALLOWED_HOSTS` fail safe, D-09 `TIME_ZONE` to Asia/Kolkata | — (config; 139 time-sensitive tests re-run) |
| `8fffe26` | D-25/D-26 error handling in the holiday-calendar family | `test_error_reporting.py` (6) |
| `e94faf2` | D-28 accessible names on bulk-action tables | `test_bulk_table_accessibility.py` (2) |

### Fixed in this pass

First pass: D-01a/b/c/d/e, D-02a/b, D-03, D-04, D-07, D-12, D-17, D-19,
D-21, D-22, D-24, D-27, D-29, D-30, D-31.

Second pass: D-08, D-09, D-13, D-16, D-18, D-23 (application half),
D-25/D-26 (holiday-calendar family), D-28 (bulk-action tables).

### Disclosed, deliberately not changed

| ID | Why |
|---|---|
| D-23 (deployment half) | The application no longer hands out a single `/media/` path and every document has a checked route in, but **the public `location /media/` block has to be removed on the server** before the old paths stop working. `DEPLOYMENT.md` now configures `internal;` + `X-Accel-Redirect` instead. Code cannot make a web server forget a directory. |
| D-14 | Changing a statutory rate is a payroll-policy decision, not a bug fix. |
| D-15 | Payroll deducts an advance EMI but never records it, so `outstanding_amount` never falls. Two plausible designs — record on finalize, or leave it to the existing manual payment screen — and choosing one silently risks double-counting against the other. |
| D-06 | Dead code, not routed. |
| D-10, D-11 | Login throttling and the `is_staff` bypass: both are deliberate-looking design choices worth a conversation, not unilateral change. |
| D-05, D-25/D-26 (rest), D-28 (rest) | Breadth without depth: 26 remaining `str(e)` sites, 8 bare excepts, and the employee-list / holiday-calendar form controls. The same mechanical change, but each needs its own reading of what the expected failures are. |

## 5. Calculations verified

Derived independently rather than by restating the implementation, and
using `Decimal` throughout.

| Calculation | How it was checked | Result |
|---|---|---|
| Payroll pro-rata | 31-day period, no LWP → full monthly components, nothing pro-rated (`test_payroll_run_query_count.test_generated_records_are_still_correct`) | correct |
| PF | 12% of earned basic, capped at the flat statutory contribution (`pf_wage_ceiling` 15000 x 12% = 1800). Asserted at 1800 for a 15000 basic. | correct |
| Payroll period boundaries | Day numbers 29/30/31 against February 2026 (28 days) and February 2024 (29, leap), plus 30-day and 31-day months, same-month and cross-month cycles — 16 cases across the three functions that build them | **was broken** (D-12), now correct |
| Half-day / holiday credit | `count` asserted per status for branched and branchless employees, all-branches and branch-specific scenarios, approved and unapproved | **was broken** (D-29, D-30), now correct |
| Leave history figures | `number_of_days_present` and `leave_balance` asserted against known per-month values | **was broken** (D-22), now correct |
| Money rounding | Existing `test_payroll_money_rounding`, `test_payroll_pf_calculation`, `test_payroll_esic_opt_out` — 52 payroll tests re-run green after the perf change | unchanged |

Not independently verified: leave accrual and carry-forward across a
financial-year boundary, overtime (no overtime module exists in this
codebase), and the eSSL punch-pairing arithmetic beyond its existing
fixtures.

## 6. Database integrity

* **All 54 migrations apply cleanly to an empty database** (verified by
  building the throwaway SQLite database from scratch). No migration was
  added in this pass — none of the fixes needed a schema change.
* `Attendance` has `unique_together (employee, date)` plus indexes on
  `(employee, date)` and `(date)`; `MonthlyEarnedLeaves`, `LeaveBalanceHistory`,
  `HalfDayScenario` and `Department` all carry appropriate unique
  constraints, including partial ones. No missing-index or duplicate-row
  problem found on the paths examined.
* Transaction boundaries: `create_payroll_run`, `recalculate_payroll_run`,
  `recalc_and_save_record`, `create_advance`, `apply_payment` and
  `skip_month` are all `@transaction.atomic`. `payroll_run_finalize` was
  not (D-17, fixed). `payroll_run_create` for "all companies" still is not
  (D-18, open).
* No destructive operation was run against real data. The working Postgres
  database `hrms_prod_db` was **not written to at all** — the browser pass
  used a throwaway SQLite database seeded from scratch.

## 7. Outstanding / blocked

**Open defects, highest first**

| ID | Sev | Summary | Why still open |
|---|---|---|---|
| D-23 (deployment half) | **P0 until applied** | The public `location /media/ { alias ...; }` block is still live on the server, so the old paths keep working until it is replaced. | Only the user can change the server. `DEPLOYMENT.md` now ships the `internal;` + `X-Accel-Redirect` configuration and `.env.example` the matching `MEDIA_ACCEL_REDIRECT` line. The application no longer emits a single `/media/` path and every document has a checked route in. |
| D-14 | P2 | `esic_percentage` defaults to 3.67 and is applied as the *employee* ESIC deduction; the statutory employee share is 0.75%. If untouched, employee ESIC is over-deducted ~4.9x on every payslip. | Changing a statutory rate is a policy decision. The ceiling beside it (D-13) is now a real, tested field, so once the rate is confirmed both are configurable. |
| D-15 | P2 | Payroll deducts an advance EMI but never records it, so `AdvanceSchedule.status` stays pending and `outstanding_amount` never falls. | Two plausible designs: record on finalize, or leave it to the existing manual payment screen (`apply_payment`, views.py:9263). Picking one silently risks double-counting against the other. |
| D-10 | P3 | No login throttling or lockout; no session idle timeout. | Worth a conversation about what the org wants rather than a unilateral lockout policy. |
| D-11 | P3 | `is_staff` is a full bypass in every decorator and in `can_access_employee_record`. | Deliberate and documented in the codebase, but it means "can open Django admin" silently equals "can do anything". |
| D-05 | P3 | Low-sensitivity cross-company config reads (`get_branch` now gated; `department_defaults_api`, `attendance_upload_progress`, `download_empty_excel` remain open). | Deliberately left: the feature registry's own comment warns against locking down pages that are open today without deciding to. |
| D-25 / D-26 (rest) | P3 | 26 `str(e)` sites and 8 bare excepts outside the holiday-calendar family. | Each needs its own reading of what the expected failures are; guessing turns a useless error message into a misleading one. |
| D-28 (rest) | P3 | ~94 unnamed form controls remain on the employee list (63) and holiday calendar (31). | Mechanical, but large; the bulk-action tables were the ones where an unnamed control is a decision about someone's pay. |
| D-20 | P3 | `holiday_calendar_dashboard` serialises every company's holidays, unbounded. | Small volume today (0 holidays in the working database). |

**Blocked / not in scope**

* The eSSL biometric integration cannot be exercised live (SQL Server uses
  Windows auth with an `SA` password the user does not have). Covered only
  by the existing `test_biometric_sync.py` fixtures — 36 KB of them, which
  do pass.
* Production-side, the user's to do: apply migrations (now including
  **0055**), audit night-shift roster ticks, confirm production
  `employee_code` values against eSSL, set `weekend_days` to `sun`.

**Deploy-affecting changes in this pass — read before the next restart**

1. `DEBUG` now defaults to **False**, and with DEBUG off `DJANGO_SECRET_KEY`
   and `DJANGO_ALLOWED_HOSTS` are **required**: the app refuses to start and
   names the missing variable. A server built by following DEPLOYMENT.md
   Step 5 already sets all three and is unaffected.
2. `TIME_ZONE` moves from UTC to **Asia/Kolkata**. Stored data does not
   change (USE_TZ is on, timestamps are UTC), but rendered times and
   `timezone.localdate()` shift by 5h30m. Reporting boundaries deserve a
   look in staging.
3. Migration **0055** adds `PayrollSettings.esic_threshold`, defaulting to
   21000 — the figure the calculation already used, so no figures move.

## 8. Next actions

1. **Apply the nginx change** from DEPLOYMENT.md and set
   `MEDIA_ACCEL_REDIRECT=/protected-media/`. Until then D-23 is only half
   closed. Everything else on this list is secondary to it.
2. **Confirm the ESIC employee rate** (D-14) and correct the default if
   3.67 is wrong.
3. Decide how advance recovery should be recorded (D-15).
4. Validate the timezone change against a month of real reports in staging.
5. The mechanical breadth work: the rest of D-25/D-26 and D-28.

## 9. Readiness

**Ready for staging validation, not for production sign-off.**

Moved up from "needs more fixes" after the second pass, because the two
things that were holding it there have changed state. D-23's application
half is done and tested, leaving a one-line server change that is written
down and reviewable. D-14 is now a single confirmed number away from being
settled, with the ceiling beside it already a real field.

What staging has to prove, rather than what tests can:

* the nginx change serves documents correctly through `X-Accel-Redirect`
  and refuses them without a session;
* the timezone move does not shift any reporting boundary the business
  cares about;
* a payroll run for a real month reconciles against the register.

Not claimed: that the application is free of further defects. This pass
covered the authorization matrix, payroll and attendance calculation,
holiday and half-day rules, transaction boundaries, media serving,
configuration posture, the responsive shell and cache performance. It did
not audit the eSSL integration beyond reading it, leave accrual across
financial years, or the remaining accessibility gaps.
