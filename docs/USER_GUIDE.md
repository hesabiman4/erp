# Practical user guide

For the latest Settings navigation, saved role checkboxes and receipt/PDF appearance controls, read [Settings/access/print v7](SETTINGS_ACCESS_PRINT.md). These steps are now included in the refreshed handbook.

The complete illustrated Afghan Dari handbook, updated to place the related screen or form preview before each practical explanation, is available as [PDF](../output/pdf/Nawa_Complete_User_Guide_Dari_Screen_First.pdf), with its maintained [step-by-step source](APP_USER_GUIDE_DARI.md). It covers setup through production, sales, corrections, payroll, reports and backups, and identifies current limits explicitly.

## Daily controls and separate bank accounts

Read [Daily controls v6](DAILY_CONTROLS_V6.md). Tables sort/filter loaded rows, show selected columns and save a personal business/location view. Explicit totals cover loaded rows only. Product master rows support authorized inline name/price edits and confirmed bulk deactivation; posted transactions remain immutable. The bell shows a bounded authorized attention list, not a complete unread total. Document pages include original linked event history. Structured draft editing has version checks and one-time undo of your unchanged unposted edit; posted errors require the ordinary return/reversal process. Purchases/transfers use Alt+N, Alt+R and Alt+F.

Settings → Bank accounts and separate cash drawers registers zero-opening AFN instruments. Choose the actual instrument when posting money; use real transfers to allocate legacy balances, including between distinct accounts at the same location. Never repeat opening money for a transfer. Custody and bank statements use the selected instrument.

On the host computer, the designated host-backup operator can choose an existing destination folder in Settings → Encrypted backups, save/test it and review Back up now. The scheduler uses the same saved folder. Until you choose one, scheduled backups remain not_configured. Archive verification is separate from restoring the database and from a copy outside the device. Keep the encryption key separately and securely. Camera scanning on a phone requires trusted HTTPS; manual entry/keyboard scanners work on LAN HTTP.

The accounting guide download provides Dari, English and Pashto PDFs according to the selected language. Native terminology/accountant/staff acceptance still requires actual review.

## Language and direction

Dari is the default. Choose English or Pashto on sign-in or in the header; customer portal users also have a language selector. English uses LTR, Dari/Pashto RTL. Setup instructions, advanced help and all21 learning steps have English/Pashto copy. Business names, product grades, original evidence and stored account/item codes keep their original values. Language changes do not change accounting dates or contractual calendars. Read [LOCALIZATION.md](LOCALIZATION.md) for verified scope and remaining review/error-message/PDF limits.

## Daily work, guided production and document pages

Read [Daily workflows v5](DAILY_WORKFLOW_V5.md). The home task profile uses your existing permissions. `/help` provides practical Dari lessons and personal progress. `/sales/counter` offers reviewed thickness shortcuts and repeat sales. CRM and private receipt/bill capture are in Operations & planning. Document rows open full detail pages with direct links and Back navigation; entry forms remain focused dialogs. Production cards open reviewed next steps by button or drag; moving a card alone changes no stock or account. Use [Staff acceptance](STAFF_ACCEPTANCE.md) with actual staff and devices; automated checks do not complete it for you.

## Cash custody, statements, supplier rates and recovery

The Operations & planning workspace includes four dedicated areas. Read [Operations release v4](OPERATIONS_RELEASE_V4.md) for the screen links, required authority, operating examples and exact limits. Cash counts and handovers record custody; bank matching records evidence; supplier selection creates a purchase order. These events must not be mistaken for sales or repeated cash movements. Release/recovery diagnostics are read only.

This is an operational guide for the initial local application. Use synthetic demo data until opening balances, permissions, accounting configuration, and recovery procedures have been reviewed. The interface is designed around Dari labels; English equivalents below explain the actions.

## Customer and supplier centers

Open **مشتریان** or **تأمین‌کنندگان** in the sidebar. The summary shows receivables/payables, accounts with balances, overdue amounts and separate deposits. Choose a summary filter, search by name/phone/address, and select the account. The address book belongs to the active business; displayed financial activity also follows your allowed location and product scope.

Use **بل‌های باز** to select an unpaid invoice and **دریافت وجه** / **پرداخت** to settle that specific document. This also works for controlled opening debts; supplier expense/asset bills are valid payable sources. Choose the actual receiving/paying location and cash/bank account explicitly. A payment changes the outstanding debt, not sales revenue.

Use **صورت‌حساب** for debit/credit activity, opening balance, running balance and closing balance. **از تاریخ** limits activity, and **تا تاریخ** sets the as-of date for balances and open invoices. Deposits/credit appear separately from AR/AP debt. Print the selected statement or export CSV when permitted. Contact information and notes have their own tab. **مشتری جدید** / **تأمین‌کننده جدید** creates a real business-scoped contact; edits require the corresponding permission.

The shared **ثبت جدید** menu in the header offers permitted sales, collections, purchasing, expense and production actions. On the overview, **امروز** / **این ماه** / **از آغاز** select the activity period. Cash, customer/supplier debts and inventory value remain as-of balances; they are not period revenue. The seven-day chart is explicitly independent of the activity period.

## Before entering transactions

Employee registration is available directly in **کارمندان و معاشات → کارمند جدید**. Complete personal/contact details, job/department/location, employment dates, pay schedule, contractual rate/effective date and advance/payment terms. Identity and bank details are optional. Department and job-position tabs create real organization records. Select an employee row to inspect or edit the complete profile; Settings uses the same editor.

For **هفته‌وار**, the rate covers seven calendar days. Select the first weekday (Saturday by default). In **ثبت معاش / مزد**, choose the worker and **تاریخ آغاز هفته معاش**. Accrue on/after the seventh day ends, including weeks crossing a month. Partial joining/leaving weeks use employed calendar-day proration; duplicate/overlapping weeks are rejected. Effective rate changes and approved overrides follow history checks. Payslips show exact earning dates. Advances above salary carry forward; settlement explicitly selects the actual cash/bank account.

Accounting includes classified **بیلانس**, **سود و زیان**, **صورت تغییرات حقوق مالک** and **چارت حساب‌ها**. Select **مقایسه با دوره دیگر** and enter comparison dates for columns/CSV. Complete-company balance/equity reports remain company statements when an operational location is selected; branch P&L is a management view. Accountants manage display numbers/report groups in Settings → Accounts. See EMPLOYEES_AND_FINANCIAL_REPORTS.md for defaults and policy decisions.

The redesigned home page offers four permitted daily tasks. The navy sidebar groups daily work, finance/people and management. Choose **راهنمای کارهای روزانه** near the bottom of the sidebar if you need help finding a task. The selected business and location stay in the header, including on phones.

In Sales, choose the invoice/order/quote tab. Use **دارای مانده** to find unpaid balances and **دریافت وجه** on the relevant invoice to collect money. Less frequent actions are under **عملیات بیشتر**. In the sale form, follow the numbered customer, product and payment sections; **پرداخت کامل** fills the total received and **پرداخت بعداً** sets it to zero. Neither button posts the invoice. Review the remaining balance before **ثبت نهایی**.

From an inventory block, **برش و فروش** opens a sale with that block and warehouse selected. Review the sheet thickness unit and remaining-height preview. Notes, linked orders and tax settings are under the optional details section. Physical stock and accounting are still validated by the server at posting.

1. Sign in with an assigned account. Check the active business and location in the header every time you switch work.
2. Confirm you are in the sponge/adhesive business or in مبلمان شهر. They have separate books and access.
3. Set up locations, warehouses, items/units, customers/suppliers, employees, accounts, and prices using permitted master-data screens.
4. Enter reviewed opening stock and financial balances through the controlled opening workflow. Do not import stock and then duplicate its accounting entry.
5. Keep the application online when posting. A network error does not mean the operation failed; retry using the same action request and inspect the document before entering another one.

An accountant uses dedicated Opening cash, Opening receivable, Opening payable, and Opening employee advance actions. These preserve the subledger links and offset opening equity. Enter a supplier/customer opening balance as its own outstanding record so later payments can settle it. Do not use a new sale or expense to fabricate an opening balance.

Every posted transaction gets a unique number. Save that number on its paper evidence. A posted transaction is not an editable draft. Use its linked correction workflow when something changes.

## Purchase materials — خرید مواد

Record the actual receipt into its receiving warehouse, with item, unit, quantity, and acquisition cost. A receipt can exist before the supplier bill. Later match the bill to the receipt so stock is not added twice. Record supplier payments against the bill. If you pay more than the bill balance or pay before billing, the difference is a supplier deposit asset.

Always verify material units. A drum is not automatically a fixed number of kilograms, and liters are not automatically kilograms. Use configured measured conversions only.

## Actual production — تولید واقعی

The main sponge company does not need a saved recipe. Record the actual materials consumed and actual output measured for the batch. The owner may enter ten grade-45 blocks and the actual quantities of TDI, Kasmos, and other consumed materials without providing percentages or a formula.

Moving materials onto the factory floor does not consume them. Record actual batch consumption separately and return unused floor stock when appropriate. Keep each grade in its own batch where practical. Shared mixed-grade input totals require an approved allocation.

For production wages, first accrue the eligible wages to Labor clearing. For eligible overhead, first record the actual paid/billed cost with the production-cost option and Cost clearing. Select those posted source documents when absorbing labor/overhead into a batch. Do not enter a second invented wage expense in production.

Measure each block and inspect/trim it. Record the main saleable block, سربلوک, کف بلوک, recoverable material, and loss separately. The grade label 45/40/35/etc. is not the block's measured weight. Adhesive output and sales use net kilograms; container tare is separate.

Complete a batch after its supported costs and outputs are approved. Do not complete it and expect later costs to rewrite past sales automatically.

## Sell sponge — فروش اسفنج

1. Choose the correct grade and footprint.
2. Enter thickness and select mm or cm. For example, 22 mm equals 2.2 cm; 50 mm equals 5 cm.
3. Enter sheet count and select feasible physical blocks. Review thickness consumed, cutting loss, price, and remaining block height.
4. Select/create the customer reference. A walk-in customer does not need a long registration form, but credit sales need a useful invoice-linked identity/contact note.
5. Confirm delivery and post the sale. The initial workflow recognizes a delivered counter sale; held/reserved goods alone are not revenue.
6. Record the amount received. Full payment, partial payment, and no immediate payment are supported.

A 1,000 mm saleable block cut by 22 mm with zero loss remains 978 mm high. Available centimeters are grouped by compatible grade/footprint. Several small remnants cannot make one thicker sheet.

## Collect outstanding money — دریافت باقی‌حساب

Find the original invoice by number or the customer's details. Review its outstanding amount, enter the money received and cash/bank account, then print the new payment receipt. Do not create another sales invoice for later collections.

Example: invoice 5,000 AFN, first payment 3,500, remaining debt 1,500. A later receipt of 1,500 settles the original invoice and leaves its sales amount at 5,000.

One receipt can settle several invoices for the same customer. An excess receipt stays as customer deposit/credit. Use Allocate deposit to settle later invoices, or an authorized Refund to return the unused credit. A refund cannot exceed the available credit. Credit approval is separate from deleting a transaction.

## Returns and bad debts

Inspect returned sponge and record it as a separate physical sheet/piece. Never add returned thickness back onto its old parent block. Use the original invoice's linked return and credit workflow. A paid invoice's credit may become customer credit and be refunded separately.

An accountant may write off an uncollectible outstanding invoice amount with a reason and expense account. A write-off reduces debt through an audit trail; it does not remove the sale from history.

## Send goods to Kabul — انتقال به کابل

Choose Stock transfer for ordinary movement. Source stock leaves at dispatch, remains in transit, and becomes available in Kabul only after confirmed receipt. The receiver checks actual quantity, blocks/dimensions, damage, and shortages. A partly used block stays partly used.

Choose Internal branch charge when the owner wants a managerial price for Kabul's stock. This adds an internal statement and settlement record. It does not become the company's external sales or customer debt. Cash sent between the company's branches remains company cash movement.

The furniture workspace is a separate business. An ordinary warehouse transfer cannot send stock across business workspaces.

## Employees and advances — کارمندان و پیش‌پرداخت

Set the employee type, agreed rate, location, advance limit, and any authorized recovery cap. Monthly employees, daily/part-time workers, and accepted project/milestone earnings are supported.

For a part-time employee paid by the hour, set the terms `rate_basis` to `hour` and record actual approved hours in attendance. For example, 4 hours plus 6 hours at 150 AFN/hour accrues 1,500 AFN. Day-paid terms remain the default. Overriding the hours directly in payroll needs approval and is preserved on the payslip record.

Record personal money withdrawn during the month as Employee advance. Record daily attendance before calculating daily wages, or enter an approved gross amount. Project earnings need a unique accepted project/milestone reference. Post monthly earnings on or after the earning period ends; use advances for earlier withdrawals.

Accrue payroll once for the employee/period. Review gross earnings, configured deductions, and net payable. During settlement, enter authorized advance recovery and the actual cash/bank payment. Do not enter a negative payment if advances exceed salary.

Example: salary 20,000 and advance 25,000. Recover an authorized 20,000, pay zero new cash, and carry a 5,000 employee advance. The advance is not another salary expense. Money entrusted for company purchases should not be mixed with personal salary advances.

When rates change within a month, automatic proration is not guessed. Enter a reviewed gross amount and retain the calculation evidence. Employee statements show earnings, payments, advances, recovery, and the remaining balance.

A rate change needs an effective date and appends history. A date already included in accrued payroll cannot be overwritten. Manual gross, manual working days, deductions, and advance recovery need payroll approval. A production payroll source also needs production permission.

## Expenses and cash — مصارف و پول

Record an immediate expense against its cash/bank account or leave it payable to a supplier. Do not choose both payment sources in one expense. Classify the expense as Sponge, Adhesive, or Shared when appropriate.

For an ordinary cost initially recorded as Shared, an authorized accountant can use Shared cost allocation. Select its original expense, explain the approved driver, and enter positive weights for Sponge/Adhesive. For example, 3 and 1 splits the allocated amount 75%/25%. You may allocate only part of the source amount; the remainder stays Shared. The allocation moves classification in the same expense account and does not pay cash again or add another company expense. Payroll/production/inventory/asset costs use their dedicated workflows. Compare each product-line profit report with the remaining Shared profit view.

Use Cash transfer to move recorded funds between permitted company cash/bank locations. A transfer creates no income or expense. Count cash regularly. Cash count shows expected, counted, and variance; an observed difference does not automatically become an expense.

Review Cash balances by location. A positive company total can hide negative recorded cash in one branch. Negative physical cash or unassigned entries are flagged for investigation; correct missing opening balances, duplicates, timing, or account mistakes through the appropriate supported workflow. A reported negative bank balance is not permission to overdraw it.

For bank reconciliation, choose the account, statement date/balance, and actual cleared entry IDs. Include the bank opening entry where applicable. The selected entries must match the statement balance; uncleared entries remain visible. Do not alter old posted entries to force a match.

## Fixed assets and depreciation

Record the asset's name, acquisition date/cost, residual value, useful life in months, location, and cash/supplier funding. Depreciation starts on the configured first day of a month; the default is the following month.

Post depreciation through a selected completed month. The system computes the additional cumulative charge, prevents repeating the same charge, and stops at residual value. Review the asset register against the fixed-asset and accumulated-depreciation accounts.

## Inventory value review

An authorized accountant can record a documented reduction to net realizable value. It changes the valuation allowance, not physical stock. Sales release the related allowance; valid linked returns restore it. A reversal needs a revised estimate and cannot exceed the remaining original write-down.

The initial release blocks non-sale transformations of stock with active write-downs. Full allowance propagation through manufacturing/transfers is not available. Ask the accountant to resolve/reassess the valuation under the supported policy; do not reverse it merely to bypass validation.

## Reports and period close

Use customer/supplier aging for debt, employee balances for advances/payroll, inventory reconciliation for stock versus financial controls, and the general ledger for source entries. Set an as-of date carefully: a receipt in May must not reduce an April debt report.

If another authorized location collects an invoice, its cash increases while the invoice remains attributed to its original location. Invoice-level debt and cash flow are not automatically split between Sponge and Adhesive. Use the full invoice/party balance; product-line cash/debt filters are intentionally unavailable.

Sales, collections, profit, and outstanding debt measure different things. Internal branch charges have their own reports. Company trial balance and balance sheet require full accounting scope; branch/product profit reports are management views and do not imply standalone balanced branch books.

Before closing a period, review cash/bank, customer/supplier allocations, stock/WIP, payroll, assets, valuation adjustments, and clearing balances. Close the business through the reviewed date. Later posting to that date is blocked. Reopening requires special permission and a recorded reason.

Actual tax rates and legal applicability must be reviewed locally before real use. Demo scenarios do not establish current Afghan tax obligations.

## Corrections and connection errors

If validation fails, read the error and correct the unsupported quantity, reference, date, permission, or balance. Do not repeatedly create new requests to overcome an idempotency warning. A conflicting request key means a different action was already recorded with that key.

For a posted error, preserve its number and use the appropriate linked workflow. Generic direct journal access does not permit bypassing receivables, inventory, payroll, or other control-account subledgers.

For a mistaken customer receipt or supplier payment, an authorized finance user can choose Payment reversal, select the original payment, and record a reason/date. The system creates a compensating document and reopens its invoice debt; it keeps the original evidence. Full reversal is allowed only once, before deposit credit is used/refunded and before conflicting return/write-off effects. Receipt reversal also requires the original cash/bank funds to be available. If the payment has downstream effects, review those with the accountant instead of deleting entries or issuing an unrelated second receipt.

Backups, restore commands, account recovery, and deployment instructions are in the README and deployment/recovery guide. Test restoration into a different local database; never restore over the active source database without a deliberate recovery plan.


## Daily and project payments before month end

Monthly salary is accrued on or after month end. Daily/hourly workers may accrue and settle approved attendance through the posting date during the month; a later accrual starts after the last covered day and cannot pay the same days/hours twice. Record/approve attendance before accruing that window. Attendance in an already accrued window requires a reviewed correction. Project earnings may be accrued/paid on accepted completion before month end, with a unique accepted milestone reference and approved gross amount.

The employee rate screen records an effective date and day/hour basis. Historical wage rate snapshots and posted payables remain unchanged. Mixed-rate earning windows require an approved prorated gross amount.

Initial opening balances are available in Settings. Use the reviewed opening cash/debt/employee/stock actions, not fake purchases/sales or ordinary salary advances. Tax rules require accountant-configured effective dates and liability mappings; no current legal rate is supplied by the demo. Bank reconciliation uses a checkbox picker over actual permitted ledger entries instead of manual entry IDs.
