# Business calendars and exact earning periods

The display calendar in the header remains a personal preference. It does not change employment contracts, posted salaries, journal dates or accounting locks. A separate effective-dated business calendar now controls actual monthly earning windows. Existing businesses retain Gregorian boundaries until an authorized operator schedules a change.

Open **Operations & planning → System management → Business calendar and actual periods** (`/operations?view=business_periods`). The workspace shows the active policy, its immutable history, a month-boundary preview and the prospective transition form. Recording a change requires both `settings.manage` and `accounting.manage`, all locations and all business product lines. Readers need payroll, accounting or settings access.

## Enabling a شمسی calendar

1. Review employment terms and choose the first day of a future Jalali month. The app does not infer contract consent from a display preference.
2. Select **Jalali / هجری شمسی**, enter that first day and document the transition review.
3. Save the policy. The action uses `core.execute`, is idempotent and creates an audited immutable source document. It does not create a journal or move stock.
4. In payroll, select the earning calendar and month. The form displays the actual canonical-date window before posting. A mismatch with the business policy is rejected by the server.

Policies append chronologically. They cannot be overwritten through business-settings PATCH. A new policy cannot precede today, its posting date, its earlier policy, or already accrued payroll. The new calendar must start on its own first day. Reverting to Gregorian uses a new prospective policy; it never deletes the Jalali history.

## Transition and salary example

If the new calendar begins on **1 حمل 1405 / 21 March 2026**, the old Gregorian March window ends on 20 March. A 31,000 AFN monthly contract earns `31,000 × 20 / 31 = 20,000 AFN` for that transition segment. The first new Jalali month is 21 March–20 April: 31 calendar days and a full 31,000 AFN, assuming full employment throughout. The short old-calendar segment can accrue on its actual last day. No day is paid twice.

Joining/leaving dates further prorate the number of employed days. The denominator is the full contractual calendar month, including when the transition clips its ending. A rate change within the window still requires the existing authorized gross-amount override. Daily/hourly attendance is selected by the actual exact earning dates; sequential accruals advance beyond already paid attendance, including when calendars differ. Weekly contracts retain their explicitly configured seven-day week; changing the monthly calendar does not shift weeks.

Monthly overlap protection uses actual earning windows across all previous accruals, rather than comparing only a month string. This preserves cross-calendar protection. Existing payroll snapshots are never rewritten.

## Stored dates and identifiers

The canonical document and ledger dates remain Gregorian ISO dates. New payroll documents additionally freeze:

| Field | Meaning | Example |
|---|---|---|
| `period` | Backward-compatible Gregorian month of the earning-period start | `2026-03` |
| `period_calendar` | Explicit contract calendar | `jalali` |
| `calendar_period` | Month selected in that calendar | `1405-01` |
| `period_key` | Unambiguous display/reference key | `jalali:1405-01` |
| `period_first`, `period_last` | Policy-clipped monthly boundaries | `2026-03-21`, `2026-04-20` |
| `earning_from`, `earning_through` | Actual employed/accrued window | Same dates when fully employed |
| `denominator_days` | Full original contract period length | `31` |

Historical documents that lack those additional snapshots continue to use their original saved earning dates or legacy Gregorian month fallback. Accounting period locks still use exact closed-through dates and work independently of the presentation calendar.

## Budgets and reports

Budget creation and the budget-versus-actual screen now have an explicit calendar selection and month selector. Jalali `1405-01` and Gregorian `2026-03` budgets are separate plans. Their actuals use posted ledger dates within the selected exact month. Budget storage retains the existing `YYYY-MM` column; supported Gregorian years 1900–2199 and corresponding Jalali years have disjoint year ranges, avoiding key collisions. No budget event posts a journal.

Financial reports can request `?calendar_period=1405-01&period_calendar=jalali`. For example, the P&L includes journal dates 21 March–20 April 2026 inclusive. If an explicit `from`/`to` is supplied as well, it must agree with those boundaries. Print/export remain based on the authorized report's exact dates. This adds month selection, not a second set of books or an automatic change of the legal fiscal year.

API endpoints:

- `GET /api/calendar/?view=period&calendar=jalali&value=1405-01`: authenticated pure date conversion; no business facts.
- `GET /api/business-periods/?calendar=jalali&period=1405-01`: scoped policy and earning preview.
- `POST /api/operations/calendar_policy/`: `date`, `calendar`, `effective_from`, `reason`, plus Idempotency-Key.
- `POST /api/operations/payroll_accrue/`: existing fields plus explicit `period_calendar`; `period` is in that input calendar. Weekly calls use `week_start_date` as before.
- `POST /api/operations/budget_set/`: existing fields plus `period_calendar`.
- `GET /api/growth/budgets_actual/?period=1405-01&period_calendar=jalali`.

## Limits and acceptance

This feature does not infer local statutory payroll/tax rules, reinterpret historical month keys, change legal fiscal-year registration, schedule payroll automatically or migrate approved budgets between calendars. Existing employee attendance/rate, deduction, advance-recovery, approval and financial posting controls remain authoritative. Native terminology and accountant approval of employment transition policies remain operator acceptance tasks.

PostgreSQL coverage is in `backend/erp/tests/test_calendar_periods.py`: real/leap month boundaries, append-only policy permissions, nonfinancial/idempotent events, legacy-preserving transition proration, exact monthly and hourly windows, overlap prevention, joining proration, weekly continuity, report/budget boundaries and tenant-denied reads. See the current verification report for executed results; a test file alone is not a passing claim.
