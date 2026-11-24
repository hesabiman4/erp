# Employee profiles and manufacturing reports — 2026-10-29

## Employee structure

The supplied `deepseek_html_20261007_1680ed.html` was a design/feature reference, not an implementation authority. The new profile adopts its employee code, name, phone, department, position, location, joining date and address. It adds optional father name, identity/tazkira reference, email, end date, emergency contact, payment preference, bank details and contract/recovery notes. Unknown legacy details remain blank.

Departments and positions are real business-owned PostgreSQL records. Departments may be business-wide or location-specific; positions may belong to a department. Employee location/department/position must agree. PostgreSQL triggers reject cross-business references. The API blocks moving used organization records before staff are reassigned. Deactivation preserves history.

Employees now offers registration, code/name/phone search, full profile viewing/editing, department/position management, attendance, advances, accrual and settlement. Settings shares the same editor. Personal and payroll data require payroll permission; employee audit details are redacted without payroll access. Bank details record payment instructions; actual cash/bank settlement remains explicit.

Supported schedules: monthly, weekly, daily, hourly, part time and project. The draft's automatic commission/mixed-pay calculation was not copied: sales attribution, returns and an approved commission policy need a separate implemented payroll component. Project earnings retain the supported approved-gross/milestone workflow.

## Weekly payroll

- Default week is Saturday–Friday, configurable per employee.
- Enter the start of a seven-day week and accrue on/after its end, including weeks crossing months or years.
- Weekly rate covers seven calendar days. Partial joining/leaving weeks use employed calendar days / 7. Monthly proration uses employed calendar days / actual days in the month. These are explicit contract defaults, not claims about mandatory Afghan labor law.
- Overlapping/duplicate payroll for one employee is rejected. Core business locks, idempotency and append-only journals remain in effect.
- Daily/hourly contracts use approved attendance within employment dates, excluding accrued windows. Explicit hourly coexists with legacy part-time/hourly terms.
- Effective rate changes cannot rewrite accrued periods. Mid-window rate changes require approved gross pay; weekly overrides require a reason. Automatic payroll rejects a window with no effective starting rate.
- Accrued pay basis, week anchor, location and joining date cannot be rewritten through normal profile editing. Contact details can be updated. Contract changes/corrections require a reviewed process.
- Advances above wages carry forward. The independent fixture earns 7,000 AFN against an 8,000 advance, recovers 7,000 and carries 1,000 without negative salary payment.
- Payslips show employee/organization snapshots, code, gross/deductions/net, earning dates and rate basis. Renaming an employee does not rename an accrued payslip. Settlement prints can use the source payroll snapshot.

## Chart of accounts

Display numbers are separate from stable internal posting codes and report groups. They are editable template conventions; IFRS and ACCA do not mandate one numbering scheme. Migration0007 adds missing master accounts and metadata without generating financial postings, replacing user names or resetting balances.

The template covers cash/bank; trade/other receivables; raw materials, WIP, finished goods, trims, transit and valuation allowance; employee/supplier advances; conversion clearing; prepayments; PPE/depreciation; trade/GRNI/payroll/tax/deduction liabilities; customer deposits; short/long borrowings and leases; capital, retained earnings and drawings; external sales; COGS, abnormal loss and impairment; administrative, selling and factory expenses; investment income, finance costs and income tax.

An account's presence does not implement loan administration, lease measurement or statutory tax calculation. Numbers/groups require accounting management permission and are audited. Used posting code/category/control status stays immutable. Category/group mismatches fail validation. The chart report reads real scoped balances; Settings manages the master chart. Numbers never route postings.

## Financial statements

- Balance sheet: current/non-current assets/liabilities, equity, accumulated unclosed earnings, numbered accounts and section totals. Complete-company scope is required. Inventory stages stay separate and contra balances retain their signs. The screen reconciles assets with liabilities plus equity.
- P&L: external sales, cost of sales, gross profit, operating income/expenses, operating profit, investing/interest income, profit before financing and income taxes, finance costs, profit before tax and net profit. Empty optional sections are omitted; required subtotals remain.
- Equity statement: opening equity including prior unclosed earnings, direct posted equity movements, period profit, closing equity and a reconciliation difference.
- Optional comparative periods use their own ledger/date scope and include accounts active only in the prior period. Comparative CSV includes both amounts.
- Trial balance, ledger, cash flow, aging and inventory/cost reports remain available. Posted INTEREST_EXPENSE cash is financing activity under the chosen policy. Mixed asset/ordinary supplier payments retain the existing classification-review exception.
- Statements retain Dari RTL/AFN and English LTR, explicit business/report scope and print/export controls. Representative balance sheet, comparative P&L and weekly payslip each rendered to one A4 page. Larger ledgers may span pages with repeated table headers.

## International alignment and limits

This is an IFRS-based ledger/presentation implementation, not an audited financial-statement/disclosure package or ACCA certification. ACCA is a professional body/qualification; the reporting basis requires accountant selection. IFRS18 is effective for annual periods beginning on/after 1 January 2027, with early application permitted. These management subtotals alone do not establish full early adoption.

OCI, statutory disclosure notes, policy elections, IFRS18 transition reconciliations, lease/financial-instrument measurement, local tax rules and statutory sign-off remain outside the verified package. Inventory absorption still requires approved eligible-cost and normal-capacity policies; the application does not invent them from raw material totals. Advanced Pashto prose and native language/user/printer review remain release work.

Primary references reviewed:

- [IFRS Foundation — IAS 2](https://www.ifrs.org/issued-standards/list-of-standards/ias-2-inventories/): inventory cost, conversion, NRV and expense recognition.
- [IFRS Foundation — IAS 1](https://www.ifrs.org/content/dam/ifrs/publications/pdf-standards/english/2022/issued/part-a/ias-1-presentation-of-financial-statements.pdf?bypass=onSecurities): current/non-current presentation.
- [IFRS Foundation — IFRS 18](https://www.ifrs.org/issued-standards/list-of-standards/ifrs-18-presentation-and-disclosure-in-financial-statements/): effective date and presentation changes.
- [ACCA — IFRS 18](https://www.accaglobal.com/gb/en/student/exam-support-resources/dipifr-study-resources/technical-articles/ifrs-18.html): operating/profit-before-financing/net-profit subtotals.
- [Intuit — Inventory assets and COGS](https://quickbooks.intuit.com/learn-support/en-us/help-article/inventory-management/understand-inventory-assets-cost-goods-sold/L2WiXgAAE_US_en_US): inventory/COGS relationship.
- [Intuit — Chart of accounts](https://quickbooks.intuit.com/learn-support/en-us/help-article/chart-accounts/learn-chart-accounts-quickbooks-online/L2yc6KBob_US_en_US): types/detail classification for reports.

See VERIFICATION.md for executed evidence and HANDOFF.md for continuation.
