# Business operations improvements - 2026-11-02

This is a working extension of the existing ERP, not a replacement ledger. The main business retains its existing contract calendar and settings until an authorized operator schedules a prospective change. No synthetic financial transactions are posted to the active business. See VERIFICATION.md for the final evidence and HANDOFF.md for runtime details.

## Where to work

Open **Operations & planning / عملیات و برنامه‌ریزی**. Membership permissions still intersect with business, location, product line and sensitive-data authority. New action permissions are not silently granted to existing staff.

| Area | Screen | Implemented workflow and boundary |
|---|---|---|
| 1. Actual calendar periods | `?view=business_periods`; payroll; budgets | Audited prospective Jalali/Gregorian business policies, exact monthly payroll/attendance windows, transition/employment proration, historical overlap protection, calendar-aware budgets/actuals and report date parameters. Display preference remains separate from contractual periods. Ledger dates and existing snapshots remain canonical and unchanged. |
| 2. Finite daily production capacity | `?view=advanced_planning` | Preview and reserve multiday work across sequential work-center stages, explicit working weekdays, curing/wait days and delivery lead time. Concurrent reservations cannot overbook the same available daily minutes. Started production cannot be casually rescheduled. Material and staffing availability are separate reviews, not promised by the calendar. |
| 3. Actual yield and loss review | Same screen, Actual production analysis | Actual net inputs, original measured output by grade/footprint/unit, original trim geometry, main-height yield and measured loss percentages. An optional operator-chosen loss threshold flags events for review; it never creates an expense or requires a formula. No kg-to-cm or grade-name/density conversion. |
| 4. Cutting alternatives/remnants | Existing order-linked cutting screen | Compare best-fit, remnant-preservation and oldest-first heuristics before selecting and reserving. Explicit reusable-remnant threshold and remaining-height comparisons. Execution revalidates live availability; no guaranteed global optimum or partial-face cutting is claimed. |
| 5. Purchasing assurance | `?view=procurement`, Purchase matching / Supplier claims | Real PO/receipt/bill quantity and base-price comparison, partial/unbilled flags, normalized duplicate supplier-reference prevention including integrated foreign purchases. Shortage/damage claims link original documents and separately posted returns/credit evidence; resolving a case does not post another credit. No automatic repricing, retrospective valuation or blanket payment hold. |
| 6. Guided period close | `?view=closing` | Exact dated checklist with eight assigned reviews: cash, bank, customers, suppliers, inventory, WIP, payroll and foreign balances. Eligible assigned reviewers attest evidence or an explained review. Changed financial/stock evidence or current FX control balances invalidate prior approvals. Complete current reviews and zero reconciliation differences precede the existing date lock. Direct partial locking cannot bypass an open checklist. |
| 7. Actual profitability | `?view=profitability` | Posted recognized sales/returns, COGS and other net expenses grouped by customer, branch, product plus footprint, source order or dedicated project. Original return footprints are retained. Unattributed adjustments/shared costs remain separate; figures reconcile rather than assigning invented customer/product overhead. Project names require job authority; payroll details require payroll authority. |
| 8. Customer requests | `?view=customer_requests`; customer portal | Staff publishes agreed items/footprints per customer grant. Customers submit quotations/order requests, repeat previous requests and acknowledge their own delivered invoice. Submissions are idempotent, immutable and nonfinancial. Staff reviews prices/warehouse and creates a real quotation/order or confirms delivery evidence. Customers never acquire staff membership/posting rights. |
| 9. Customer communications | `?view=customer_notices`; existing collections reminders | Dari/Pashto/English order-recorded, invoice-issued and recorded-delivery templates, explicit recipient/consent, duplicate checks, provider idempotency, honest blocked/failed/accepted states and staff-recorded delivery evidence/cancellation. A disabled/revoked authorizer or cancelled source cannot send. No live gateway or callback has been verified/configured by this release. |
| 10. Stock counts and confirmed weights | `?view=procurement`, Assigned counts / Weighing | Assigned blind observations with protected snapshots, independent review, stale-count checks, recount/no-difference closure and authorized original stock adjustment once. Separate device registration, effective calibration evidence and manually confirmed gross/tare/net kg. A confirmed reading can receive goods once through actual purchase receiving; lot controls remain. Direct scale hardware capture remains unimplemented. |

## Examples

**Calendar transition:** a reviewed change to a Jalali month boundary clips the preceding Gregorian contract month. The new monthly window uses its exact day count, with no duplicated employment day. A weekly employee keeps the configured seven-day week. See CALENDAR_PERIODS.md for the calculation and configuration steps.

**Delivery promise:** 300 minutes on a 120-minute daily work center requires at least three capacity days. Curing waits and subsequent stages may extend the estimated finish. The displayed delivery date is a capacity-based estimate, not a guarantee that chemicals, workers or transport are available.

**Loss review:** an original 1,060 mm block divided into 1,000 mm main height, 30 mm top, 20 mm bottom and 10 mm loss has measured height loss of approximately 0.943396%. A selected 0.9% review threshold flags it; a 1% threshold does not. Top/bottom saleable outputs are distinguished from irreversible loss.

**Stock count:** a restricted counter records 99 kg without being shown the book balance. A reviewer checks the protected snapshot, changes since observation and evidence. A recount changes no stock. An approved shortage uses the original stock-adjustment journal and material-lot controls; checklist completion cannot manufacture stock.

**Weighing:** gross 12 kg less 2 kg tare produces a confirmed 10 kg reading. Recording it creates no stock. Measured receiving enters 10 kg once, Dr inventory / Cr GRNI. The later supplier bill clears GRNI into AP without a second goods receipt. The reading cannot be reused for another receipt.

**Customer request:** three 22 mm sheets equal 6.6 cm for the agreed full-face footprint. The customer cannot submit a selling price or choose another customer's items. Staff approval creates the appropriate commercial document; revenue/COGS still wait for the existing delivered-sale event.

## Authority and operational behavior

- Closing requires complete business accounting/cost/cash/payroll/raw-inventory scope plus `accounting.close`. Only eligible reviewers appear in assignment choices. Open WIP can remain an asset after explicit review. Current foreign-control reconciliation is labelled current; other closing checks use the period-end date. Closing is not statutory certification.
- Blind counters use **`inventory.count_record`**. Do not grant standalone `inventory.count` or `inventory.view` to someone who must not see book quantities. Managers use `inventory.count_manage`; reviewers use `inventory.count_review` plus the original adjustment authority where posting is required. `inventory.count_self_review` is an explicit small-team exception.
- Scale management uses `inventory.scale_manage`; confirmed readings use `inventory.measure`; receiving still requires `purchases.post`. Raw-material fields remain separately protected, including generic document/print routes.
- Customer catalogue publishing requires sales and portal-user management authority. Unassigned customer requests require complete location scope. Revoked grants cannot submit new requests; staff can reject preserved historical submissions. No public endpoint grants accounting access.
- New customer notices retain the original authorizing user and immutable content. Missing provider configuration blocks external delivery. Provider acceptance is not proof of delivery; the status screen records staff review of provider evidence, not a verified callback. An ambiguous retry keeps the original provider key and cannot race an already queued replacement. Order-ready automation and a production gateway/callback require a further integration.
- Selected business/location identifiers persist per signed-in user in tab session storage. Financial data, API responses and credentials are not stored there. Live memberships/location scope are revalidated; changing businesses closes old transaction dialogs and clears their search context.
- Recent lists are bounded pilot views. Production-volume pagination/performance, native terminology review and physical device/printer acceptance remain rollout work; no scale or compliance certification is claimed.

## Recovery and rollout

Before applying 0023/0024, an encrypted snapshot was captured at `.local/backups/pre-business-excellence-20261102.fernet`. It contains 93 documents and two private attachments. A fresh `restore_excellence_20261102` copy restored, migrated and reconciled successfully; this is same-machine recovery. Never overwrite/reuse that target for another drill.

The owner still chose **configure backup destination later**. No backup destination, automatic logon task, public deployment, provider credentials, external message recipients or physical-device integration was configured by this increment. Both beginner PDF editions cover 65 accounts and 153 registered operations, with the existing six teaching figures.

Detailed companion guides: CALENDAR_PERIODS.md, ADVANCED_PLANNING.md, PROCUREMENT_AND_COUNTS.md. No ACCA, IFRS, QuickBooks or Afghanistan statutory certification is claimed.

Verified delivery evidence: **281 distinct PostgreSQL cases** and **34 distinct browser journeys** pass across the recorded full/focused runs. The main ledger/stock totals remain identical to the pre-upgrade baseline; both main and isolated QA controls reconcile. TypeScript/Vite and Django/migration checks pass. See VERIFICATION.md for exact run scope rather than interpreting those totals as a single-run count.
