# Accounting and valuation rules

Employee/statement extension (2026-10-29): weekly earnings use the existing salary/labor-clearing debit and PAYROLL credit through core.execute/core.journal. Seven-day windows may cross months. Employment-date calendar proration is explicit; weekly gross overrides require approval/reason. Settlement and advance carry-forward remain unchanged. Accrued windows/rates and printed identity snapshots are protected.

Account numbers never route postings. Report groups must agree with account category. Chart migrations create master data only. P&L subtotals reconcile to posted income minus expenses; equity movements reconcile opening equity plus direct equity changes plus period profit to closing equity. Comparisons use independent date bounds. Cash expense postings to INTEREST_EXPENSE are financing activity under the chosen policy. See EMPLOYEES_AND_FINANCIAL_REPORTS.md for scope and statutory limitations.

This document describes the initial implementation. It is not a tax opinion or certification of IFRS compliance. Amounts in the examples are AFN; tax is omitted unless a configured synthetic rule explicitly applies. Source code and passing tests determine the supported behavior.

## Books, dimensions, and posting

Each business workspace has a separate ledger, accounts, documents, customers/suppliers, inventory, employees, and permissions. A workspace does not establish a legal entity. Factory, Herat, and Kabul are locations inside the same sponge/adhesive business. Sponge and adhesive are reporting divisions.

All supported posting actions run through `core.execute` within a PostgreSQL transaction and a business-row lock. This deliberately serializes writes per business in the initial release. The lock, source event key, and request hash prevent duplicate retries and conflicting stock use. A failure rolls back the entire operation.

Documents move from draft to posted after balanced entries and stock movements are recorded. Posted documents and their ledger rows are immutable through application and database guards. Corrections use supported linked return, refund, write-down reversal, or other adjustment actions; a generic unrestricted reversal engine is not implied.

`payment_reverse` provides a full correction of a customer receipt or supplier payment. It creates an opposite journal and compensating negative invoice allocations, keeping the originals unchanged. It requires finance reversal plus the relevant collection/payment permission, a reason, all source locations, and adequate recorded funds when returning receipt cash. A source reverses once. Used/refunded deposit credits and target invoices with posted return/write-off effects prevent this simple reversal; they require review of the downstream credit workflow. Reversed deposits cannot later be allocated/refunded. Aging evaluates the positive and negative allocations by their own posting dates, so earlier reports retain their original balances.

Values are decimal, with AFN journal amounts rounded to two decimals using half-up rounding. Intermediate rates and quantities retain precision. General-ledger entry dimensions include location, warehouse, product division, party, and employee where relevant. Financial stock movements use the same cent precision as their control-account postings.

## Inventory cost flow

Moving weighted average pools are scoped by business, warehouse, product, and compatible footprint/profile. The same cost method applies across warehouses; averages may differ because receipt histories differ. An issue uses the selected pool average and cannot use a chosen block's historic production cost to manipulate margin. A complete final issue takes the pool's remaining cost to avoid rounding residue.

Block geometry and batch production cost analysis remain separately traceable. The number in a sponge grade name is not actual mass or density. Stock in centimeters is interchangeable only inside a compatible grade/footprint group.

Backdated inventory-value events before a later pool event are rejected. Changing a master price, BOM, or wage rate does not rewrite posted documents. Multi-currency settlement and historical cost replay are not supported in the initial posting engine.

## Event-to-journal mappings

| Event | Debit | Credit |
|---|---|---|
| Reviewed opening cash/bank | Cash/bank | Opening equity |
| Reviewed opening customer debt | AR | Opening equity |
| Reviewed opening supplier debt | Opening equity | AP |
| Reviewed opening employee advance | Employee advance asset | Opening equity |
| Goods received before billing | Raw/finished/trim inventory | Goods received not invoiced (GRNI) |
| Matching supplier bill | GRNI | Supplier payable (AP) |
| Supplier payment applied to bill | AP | Cash/bank |
| Supplier payment exceeding bills | Supplier deposit asset | Cash/bank |
| Actual material consumed | Work in progress (WIP) | Raw inventory |
| Production wages accrued to clearing | Labor clearing | Payroll payable and configured deductions |
| Actual eligible overhead paid/billed | Cost clearing | Cash/bank or AP |
| Backed conversion cost absorbed once | WIP | Corresponding labor/cost clearing |
| Completed production | Main finished inventory, by-product inventory, approved abnormal loss | WIP |
| Delivered sale | Customer receivable (AR) | Sales and configured tax liability |
| Inventory delivered | Cost of goods sold (COGS) | Finished inventory |
| Customer collection applied to invoice | Cash/bank | AR |
| Customer prepayment/overpayment | Cash/bank | Customer deposit liability |
| Customer deposit allocated later | Customer deposit liability | AR |
| Supplier deposit allocated later | AP | Supplier deposit asset |
| Customer deposit/credit refunded | Customer deposit liability | Cash/bank |
| Supplier unused deposit refunded | Cash/bank | Supplier deposit asset |
| Approved bad-debt write-off | Approved expense | AR |
| Personal employee advance | Employee advance asset | Cash/bank |
| Office payroll accrual | Salary expense | Payroll payable and configured deductions |
| Authorized advance recovery | Payroll payable | Employee advance asset |
| Net salary payment | Payroll payable | Cash/bank |
| Fixed asset acquired | Fixed assets | Cash/bank or AP |
| Straight-line depreciation | Depreciation expense | Accumulated depreciation |
| Inventory NRV write-down | Impairment expense | Inventory valuation allowance |
| Approved NRV reversal | Inventory valuation allowance | Original impairment/return adjustment expense |

Sales and purchase returns retain their original document references and generate the appropriate credit and stock events. Fully paid returned purchases become supplier credit assets; fully paid customer returns become customer credit liabilities. Physical returned sheets are separate inspected pieces, never restored height on their parent blocks.

## Manufacturing conversion costs and completion

The actual-consumption workflow requires no formula or BOM. Recorded input quantities must be actual consumption, not merely issues to the production floor.

Nonzero labor/overhead absorption requires eligible posted source documents. Payroll accrued with `expense_account=LABOR_CLEARING` and eligible overhead recorded with `production_cost=true, expense_account=COST_CLEARING` provide those sources. Production validates available source amounts and prevents reuse. The source incurs the real payroll/supplier liability or cash cost; absorption reclassifies it into WIP. Do not record the same salary as ordinary salary expense and again as an independent production cost.

Normal loss is absorbed by good output under the selected allocation. Abnormal loss is expensed. Joint outputs must share one conserved cost total. Saleable trim cannot be created with extra value on top of the full main-output cost. Immaterial by-product estimates and other allocation choices require explicit approval and assumptions.

Late additional cost after completion is not silently forced into remaining stock. The supported initial workflow finalizes eligible costs before completing the batch. Unsupported late-cost adjustment is rejected rather than retroactively changing old journals.

## Sales, payments, and credit

The initial sales workflow is a delivered counter sale: fulfillment, final invoice recognition, inventory cost, and an optional immediate payment post atomically. Orders, reservations, and held cut sheets are not independent revenue events. Unsupported bill-and-hold and separately recognized unbilled deliveries are unavailable.

One invoice may have many receipts; a receipt may settle several invoices for the same party. Allocations cannot exceed either invoice debt or payment credit. Walk-in credit uses a lightweight identifiable party/reference, preserving separate invoice debt. Collections never create another sale.

A prepayment or excess receipt is a liability, not revenue. It can later be applied or refunded using the source credit document. Supplier deposits use a separate asset account. Customer and supplier deposits must not share the same liability account.

Bad-debt write-offs reduce invoice debt through a recorded allocation and expense entry. They are not deletions of invoices or receipts. Tax implications of credits and write-offs require local configuration review.

## Shared operating cost allocation

`shared_cost_allocate` reclassifies an actual posted ordinary Shared expense into Sponge/Adhesive using approved positive driver weights. It requires accounting allocation permission and a documented rationale. The source expense remains unchanged. The allocation debits the same expense account in the selected product lines and credits that account in Shared; company expense and cash do not change.

Partial allocations are supported, but their cumulative amount cannot exceed the original eligible Shared expense. Weights, source amount/account, reason, and rounded destination amounts are preserved on each immutable allocation document. The final destination absorbs any rounding residue. Product-line profit reports then show the allocated cost, while a Shared profit view shows the unallocated remainder. Source and allocation reports together explain the before/after classification.

This initial workflow accepts ordinary `expense_post` sources recorded wholly in Shared. It rejects production clearing, inventory, payroll, depreciation, impairment, COGS, and waste sources. It does not create production absorption or justify a driver automatically. The owner/accountant must select a rational driver such as occupied area, approved labor hours, or machine use; revenue is not imposed as a universal rule.

## Transfers and internal branch charges

At stock dispatch, source inventory moves to an in-transit warehouse/control. Receipt moves it from transit to destination at the preserved dispatch cost. Destination moving average recomputes once on receipt. Total company quantity and cost are unchanged unless a separately approved discrepancy/loss is recorded.

An internal branch charge adds only management records and settlement history. It never becomes external sales, customer receivables, COGS, or inventory markup. Actual branch cash settlements transfer company cash between locations; they are not income or expense. True intercompany sales are a separate unsupported extension.

## Payroll, attendance, and advances

Monthly payroll defaults to the employee rate. Daily/part-time payroll uses approved days or an explicit reviewed gross amount. Project earnings require a unique accepted project/milestone reference. Repeated employee-period payroll and repeated project references are rejected.

For hourly part-time/daily terms, set `Employee.terms.rate_basis` to `hour`. Payroll then multiplies the effective rate by approved attendance hours rather than days. An explicit hours override requires payroll approval; the rate basis, applied rate, and approved hours are stored as snapshots. The default remains `day`, preserving day-wage behavior.

Rates can have effective-date history. If a rate changes inside a period, automatic proration is not guessed: enter a reviewed gross amount. Accrual posts on or after the earning period ends. Earlier personal withdrawals are advances.

Rate changes append a dated history entry; they cannot rewrite dates already used by posted payroll or insert an earlier historical version. Manual gross amounts, manually supplied workdays, deductions, and advance recovery require payroll approval. Payroll assigned to production clearing additionally requires production posting permission. Recovery uses the employee advance actually outstanding at the settlement date, so a future advance cannot fund an earlier settlement.

Gross earnings, statutory/configured deductions, net payable, advance recovery, and cash paid are distinct. Recovery cannot exceed employee debt, remaining net salary, or an employee's configured recovery cap. Advance-limit overrides and recovery require approval permission. Excess advances carry forward as employee assets.

Example: earn 20,000; receive an advance of 25,000; recover an authorized 20,000 against salary. Pay zero net cash and carry an employee receivable of 5,000. The salary expense remains 20,000. Expense money entrusted to an employee for company purchases must not be treated as personal salary without a supported clearing process.

## Assets and NRV

Assets use straight-line monthly depreciation with an explicit first-of-month start date. The default start is the month after acquisition. Cumulative calculation gives the final month its rounding residue and never depreciates below residual value. Reposting the same covered period cannot depreciate twice.

NRV write-downs leave physical quantity and original gross inventory cost intact. The allowance is a separate contra-asset. A sale releases the applicable allowance into COGS; a linked sales return restores the relevant allowance to its returned pool so the return does not create artificial profit. Reversals cannot exceed the outstanding write-down and never raise stock above original cost.

Initial safe boundary: non-sale stock transformations with an active allowance are rejected. Before transfer, raw-material consumption, trimming, or other unsupported transformation, an accountant must resolve/reassess the write-down through an authorized supported process. Reversing merely to bypass the rule is not an accounting policy. Full allowance propagation through manufacturing/transfers is an extension.

## Counts, reconciliation, and close

A cash count records expected cash, counted cash, and variance. It does not silently post the discrepancy. Bank reconciliation records selected actual bank entries, statement balance, uncleared difference, and date. Selected entries must match the statement balance; include opening entries when applicable.

The Cash balances report shows each permitted location's CASH/BANK balance independently. Negative physical cash and unassigned cash entries are flagged for review, even when the combined company total is positive. General posting does not claim to enforce a cash-spending limit. Reconcile missing openings, timing, duplicates, or incorrect accounts; a bank overdraft requires separate authorization and is not authorized by its appearance in a report.

Manual journals require a reason, balanced sides, and permitted accounts. Controlled subledger accounts cannot be bypassed with free-form journals. Cash-affecting manual journals require a cash-flow classification.

Closing sets a business-wide closed-through date; transactions on or before it are rejected. Reopening requires dedicated permission and a documented reason. A period lock does not imply that all balances or tax returns have been professionally approved.

Company trial balance and balance sheet require complete business scope and do not accept branch/product filters. Branch/product profit reports are management views. A standalone balanced branch balance sheet requires interbranch balancing, which is not claimed here.

Reports derive from posted data. Aging includes old unpaid invoices and only settlements through the as-of date. Financial inventory reconciliation compares gross inventory movement values with controls, then shows allowance and WIP separately. The direct cash-flow report identifies unclassified/mixed movements for review and reconciles opening cash plus movement to closing cash. CSV exports use the same access controls as the underlying report.

Collections/payments credit/debit each invoice's original AR/AP location; the cash entry uses the location that actually receives/pays. Deposit allocations clear the credit at its original source location and settle the target invoice at its original location. This prevents a cross-branch collection from moving the original sale or leaving a phantom branch receivable.

Individual employee-linked general-ledger rows are excluded without payroll viewing permission; aggregate financial control balances remain part of company statements. Cash-flow reporting summarizes employee movements when detail is restricted. Product-line invoice debt and cash-flow allocation are unsupported: those filters are rejected rather than presenting zero or a guessed split. Product-line profit reporting remains available.

Entry-based reports also enforce whole-document product visibility. Without explicit all-lines document permission, a user assigned only Sponge cannot see a mixed Sponge/Adhesive invoice's Shared receivable or its partial revenue through a dashboard/report. This applies alongside entry-line and branch restrictions.

Opening debt documents remain invoice-like outstanding records and can receive normal later settlements. Opening actions require `accounting.opening`; they must not be simulated with ordinary sales, expense payments, or unrestricted manual control-account journals. Opening cash is explicitly marked as an initial financing movement when included inside a cash-flow period; normally choose the reviewed conversion cutoff before the first operating reporting period.

## Production review

Before real use, validate actual opening balances, account mappings, tax/withholding applicability and effective dates, normal capacity/overhead policy, production allocations, fixed-asset policy, employee recovery terms, approval limits, and backup/restore operation with the owner and local accountant. No historic Afghan rate is hardcoded as a current legal conclusion.


## Daily and project payments before month end

Monthly salary is accrued on or after month end. Daily/hourly workers may accrue and settle approved attendance through the posting date during the month; a later accrual starts after the last covered day and cannot pay the same days/hours twice. Record/approve attendance before accruing that window. Attendance in an already accrued window requires a reviewed correction. Project earnings may be accrued/paid on accepted completion before month end, with a unique accepted milestone reference and approved gross amount.

The employee rate screen records an effective date and day/hour basis. Historical wage rate snapshots and posted payables remain unchanged. Mixed-rate earning windows require an approved prorated gross amount.

Initial opening balances are available in Settings. Use the reviewed opening cash/debt/employee/stock actions, not fake purchases/sales or ordinary salary advances. Tax rules require accountant-configured effective dates and liability mappings; no current legal rate is supplied by the demo. Bank reconciliation uses a checkbox picker over actual permitted ledger entries instead of manual entry IDs.
