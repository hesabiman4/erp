# Nawa Chart of Accounts: a beginner's operating manual
# راهنمای مبتدی حساب‌ها و اثر هر عملیات

Version: 2026-11-22. This manual describes the implemented Nawa application, not a hypothetical ERP. Amounts are illustrative AFN. Chemical quantities and tax examples are teaching examples, not production recipes or Afghan tax instructions. Read it alongside the application's actual document journals and your accountant's approved policies.

Latest extension: reviewed commissions, job costing/subcontract source tracking, nested BOM requirements and order-linked cutting are supplied. Offline proposals are encrypted drafts only. Refundable foreign monetary credits are supported; nonmonetary goods advances and cross-currency settlement remain unsupported. Late costs use explicit reviewed current-period allocation, not historical replay.

## 1. Start here: what a chart of accounts does

A chart of accounts is the organized list of financial buckets used by the business. A customer invoice, warehouse receipt or salary event creates journal lines in these accounts. You normally choose the business operation, not its debit/credit lines. The system posts the corresponding accounts automatically.

Four different things must not be confused:

| Thing | Meaning | Example |
|---|---|---|
| Account | A financial bucket | AR = all customer receivables in this business |
| Subledger | The individual records behind a control account | Which customer/invoice owes each part of AR |
| Dimension | A reporting label on the entry | Herat or Kabul; sponge, adhesive or shared |
| Quantity | Physical inventory measurement, not money | 100 cm compatible sponge block; 50 kg adhesive |

There is no need to create a separate chart account for every customer, employee, sponge grade or warehouse. Customer/employee/inventory subledgers and dimensions provide that detail. Another separate business has its own chart and ledgers. The Kabul branch is a location of the same business, not automatically a separate external customer.

### Debit and credit in plain language

Debit (Dr / بدهکار) and credit (Cr / بستانکار) are bookkeeping sides, not automatically bad/good, paid/unpaid, or cash in/out.

| Type | What it represents | Usually increases with | Usually decreases with |
|---|---|---|---|
| Asset / دارایی | What the business controls or is owed | Debit | Credit |
| Liability / بدهی | What the business owes | Credit | Debit |
| Equity / حقوق مالک | Owner's residual interest | Credit | Debit |
| Income / درآمد | Earned revenue/gains | Credit | Debit |
| Expense / مصرف | Costs recognized in profit/loss | Debit | Credit |

Every financial posting has equal total debits and credits. For example, receiving 500 AFN from an existing debtor is Dr CASH 500 / Cr AR 500. Cash increases; the customer's debt decreases; no new sales income is earned by collecting the same invoice again.

Assets = Liabilities + Equity. Profit increases unclosed earnings in the balance sheet; cash is not the same as profit. A profitable credit sale can leave cash unchanged until collection. Buying raw materials normally creates inventory, not an immediate manufacturing expense. An advance to an employee creates a recoverable asset, not salary expense.

Two asset accounts deliberately have a usual **credit** balance: ACCUM_DEPR and INVENTORY_ALLOWANCE. They reduce the related gross assets. DRAWINGS is a reduction of equity and usually carries a debit balance. A report column labeled **debit minus credit** can therefore be negative for a normal liability, income or contra-asset balance. Negative does not automatically mean an error or a loss.

## 2. How to use the accounts screen

Open **Accounting & reports → Chart of accounts**. Search by number, name or internal code, or filter by account type. Select a row to see its usual balance side and posting guidance. Download this manual from that screen.

| Screen field / option | What it does | Example and caution |
|---|---|---|
| Number | Human-readable sorting/display number |10000 for cash. The displayed numbering convention is not an IFRS/ACCA mandated chart. |
| Internal code | The stable key used by posting services | CASH, AR, FG. Do not repurpose it to mean something different. |
| Name | Human-readable account description | Office rent can have a translated/localized name. |
| Type/category | Asset, liability, equity, income or expense | RENT is expense; AP is liability. A wrong type changes report interpretation. |
| Report group | Where it appears in classified statements | Administrative expenses versus selling expenses; current versus non-current assets. |
| Control | Whether an authoritative subledger must create entries | AR, RAW, CASH and PAYROLL require linked workflows. Generic manual posting is blocked. |
| Debit minus credit | Signed financial balance | AR debit 5000 shows+5000; AP credit 3000 can show-3000. |
| Posting method badge | Operational guidance | Use Sales for AR/SALES; use Payroll for PAYROLL. Non-control does not remove other workflow restrictions. |
| Business selector | Selects a wholly separate set of books | Furniture and sponge/adhesive balances do not merge automatically. |
| Location/product filters | Narrow eligible reports | Not a license to call an incomplete branch view the whole-company balance sheet. |

Settings → Accounts is restricted to accounting-manage authority. Historical posting keys/control classifications are protected where used; do not try to bypass these protections. A display-number change is different from changing the economic meaning of an account. A custom account does not automatically acquire a new purchasing/payroll/cash workflow. For example, expense entry accepts a non-control expense account; it does not accept an arbitrary asset account.

The system supports reasoned, balanced **Adjustment journal** entries to eligible **non-control** accounts. It blocks direct manual posting to control accounts, including CASH/BANK and inventory. Do not use an invented journal to force customer, supplier, stock, bank or payroll balances to agree. Use the actual linked workflow, or request a designed extension when none exists.

## 3. Every default account: meaning, location and example

Default display numbers are listed below. A local business may have authorized naming/number changes. “Template/noncash journal” means the account exists and can participate in an eligible reviewed journal; it does **not** imply that a dedicated cash settlement or full specialist module exists. Dr/Cr examples below are accounting examples; only the stated workflow is an implemented entry route.


| Number / code | Account and type | Meaning / where used | Example / actual posting route |
|---|---|---|---|
| 10000 · `CASH` | **Cash** · asset; control; `current_assets` | Physical AFN cash, separated by location. Cash reports/collections/payments. | Receipt 1000: Dr CASH 1000 / Cr AR 1000. Use customer receipt, not adjustment journal. |
| 10010 · `FX_CASH` | **Foreign currency cash** · asset; control; `current_assets` | Foreign physical-cash wallets, reported at AFN carrying value with separate USD/PKR quantities. | Verified USD 100 opening at 70: Dr FX_CASH 7000 / Cr EQUITY 7000. Register the wallet/currency first. |
| 10100 · `BANK` | **Bank** · asset; control; `current_assets` | AFN bank control, separated by location; bank reconciliation. | Transfer cash to bank 2000: Dr BANK 2000 / Cr CASH 2000. Multiple named AFN bank instruments need extension. |
| 10110 · `FX_BANK` | **Foreign currency bank** · asset; control; `current_assets` | Foreign bank wallets, with AFN carrying value and original currency quantity. | Receive USD 10 into a foreign bank wallet at 70: Dr FX_BANK 700; foreign invoice settlement credits AR carrying value and posts any exchange difference. |
| 10200 · `FX_TRANSIT` | **Remittances in transit** · asset; control; `current_assets` | Foreign remittance dispatched but not received; unavailable-cash current asset. | Send USD 20 carrying 1400: Dr FX_TRANSIT 1400 / Cr FX_CASH 1400; destination receipt Dr FX_BANK / Cr FX_TRANSIT. |
| 11000 · `AR` | **Customer receivables** · asset; control; `current_assets` | Customer invoice debt. Customer center, open invoices and aging. | Credit sale 5000: Dr AR 5000 / Cr SALES 5000; later receipt credits AR. A walk-in debtor is still invoice-linked. |
| 11100 · `OTHER_RECEIVABLES` | **Other receivables** · asset; non-control; `current_assets` | Template for non-customer trade balances; no dedicated cash collection module for these claims. | Reviewed opening noncash receivable 1000: journal Dr OTHER_RECEIVABLES 1000 / Cr EQUITY 1000. Normal customer receipt targets AR, not this account. |
| 12100 · `RAW` | **Raw materials** · asset; control; `current_assets` | Raw-material stock at carrying value by warehouse/product. | Receive materials 50000: Dr RAW 50000 / Cr GRNI 50000. Consumption moves value to WIP. |
| 12200 · `WIP` | **Work in progress** · asset; control; `current_assets` | Production costs not yet completed into finished inventory. | Actual inputs 20000: Dr WIP 20000 / Cr RAW 20000; completed output Dr FG / Cr WIP. |
| 12300 · `FG` | **Finished goods** · asset; control; `current_assets` | Finished stock; sponge physical dimensions and adhesive kilograms remain separate quantity measures. | Completed block 25000: Dr FG 25000 / Cr WIP 25000. Sale releases its carrying cost to COGS. |
| 12400 · `TRIM` | **Saleable trims** · asset; control; `current_assets` | Saleable top/bottom trims and recoverable by-products. | Trim output carrying value 1000: Dr TRIM 1000, with the main block and any WASTE conserving the original cost. |
| 12500 · `TRANSIT` | **Inventory in transit** · asset; control; `current_assets` | Goods dispatched but not yet received at another location. | Dispatch 10000: Dr TRANSIT 10000 / Cr FG 10000; receiving Dr FG / Cr TRANSIT. No external sales. |
| 12900 · `INVENTORY_ALLOWANCE` | **Inventory valuation allowance** · asset; control; `current_assets` | Credit-balance reduction for approved inventory NRV write-downs. Physical historical cost pools are not rewritten. | Write-down 500: Dr IMPAIRMENT 500 / Cr INVENTORY_ALLOWANCE 500. Controlled reversals/issues restore or release it. |
| 13100 · `ADVANCES` | **Employee advances** · asset; control; `current_assets` | Recoverable employee advances. Employee advance statement. | Pay advance 8000: Dr ADVANCES 8000 / Cr CASH 8000; recover 5000 in payroll: Cr ADVANCES 5000. |
| 13200 · `SUPPLIER_DEPOSITS` | **Supplier deposits** · asset; control; `current_assets` | Advances paid to suppliers or supplier credits exceeding unpaid bills. | Pay supplier deposit 2000: Dr SUPPLIER_DEPOSITS 2000 / Cr CASH 2000; allocate later Dr AP / Cr deposit. |
| 13300 · `PREPAID` | **Prepaid expenses** · asset; non-control; `current_assets` | Template for costs belonging to future periods. No automatic prepaid schedule exists. | Opening prepayment 6000: Dr PREPAID 6000 / Cr EQUITY 6000; recognize 1000 rent with Dr RENT 1000 / Cr PREPAID 1000 through reviewed journals. |
| 13910 · `LABOR_CLEARING` | **Production labor clearing** · asset; control; `current_assets` | Eligible factory labor awaiting linked production absorption, not automatic additional salary. | Factory payroll 3000: Dr LABOR_CLEARING 3000 / Cr PAYROLL 3000; authorized batch absorption Dr WIP / Cr LABOR_CLEARING. |
| 13920 · `COST_CLEARING` | **Production conversion clearing** · asset; control; `current_assets` | Eligible conversion overhead awaiting linked production absorption. | Record eligible overhead 2000: Dr COST_CLEARING 2000 / Cr CASH 2000 using production-cost expense; absorb Dr WIP / Cr COST_CLEARING. |
| 15000 · `ASSETS` | **Fixed assets** · asset; control; `noncurrent_assets` | Fixed assets managed by acquisition/depreciation workflows. | Buy machine 60000: Dr ASSETS 60000 / Cr CASH or AP 60000. A machine purchase is not all current-month expense. |
| 15900 · `ACCUM_DEPR` | **Accumulated depreciation** · asset; control; `noncurrent_assets` | Credit-balance contra-asset reducing gross fixed assets. | Monthly depreciation 1000: Dr DEPRECIATION 1000 / Cr ACCUM_DEPR 1000. Net asset value decreases. |
| 16000 · `LONG_TERM_DEPOSITS` | **Long-term security deposits** · asset; non-control; `noncurrent_assets` | Template for non-current security deposits, not rent expense. | Reviewed opening deposit 25000: Dr LONG_TERM_DEPOSITS 25000 / Cr EQUITY 25000. Dedicated cash-deposit settlement needs an extension. |
| 20000 · `AP` | **Supplier payables** · liability; control; `current_liabilities` | Supplier debt supported by supplier invoices. Supplier center/aging. | Supplier bill 50000: Dr GRNI 50000 / Cr AP 50000; payment 30000 Dr AP 30000 / Cr CASH 30000. |
| 20100 · `GRNI` | **Goods received not invoiced** · liability; control; `current_liabilities` | Goods received, not yet supplier-invoiced; prevents receipt and bill from adding stock twice. | Receipt 50000 credits GRNI; matched supplier bill 50000 debits GRNI and credits AP. |
| 20200 · `PAYROLL` | **Salary payable** · liability; control; `current_liabilities` | Net approved earnings still owed to employees, not their contract rate. | Gross 25000 less deductions 1000 credits PAYROLL 24000. Cash 15000 plus advance recovery 5000 debits PAYROLL 20000, leaving 4000. |
| 20300 · `TAX` | **Tax payable** · liability; control; `current_liabilities` | Configured sales-tax and permitted deduction liability control. No automatic Afghan tax rate is assumed. | Illustrative configured tax 50: sale credits TAX 50; a linked return debits the original tax. Use only an accountant-approved rule. |
| 20400 · `DEPOSITS` | **Customer deposits** · liability; control; `current_liabilities` | Customer advances/unallocated receipts/credits; a liability rather than new sales. | Receive 7000 against 5000 debt: Dr CASH 7000 / Cr AR 5000 / Cr DEPOSITS 2000. |
| 20500 · `ACCRUED_EXPENSES` | **Accrued expenses** · liability; non-control; `current_liabilities` | Template for non-AP accrued liabilities. Supplier expense invoices use AP instead. | Accrue unpaid office rent 5000: journal Dr RENT 5000 / Cr ACCRUED_EXPENSES 5000. A dedicated settlement route for this account is not supplied. |
| 20600 · `INCOME_TAX_PAYABLE` | **Income tax payable** · liability; non-control; `current_liabilities` | Template for approved income-tax liability, distinct from sales TAX. | Accountant-approved tax charge 10000: journal Dr INCOME_TAX_EXPENSE 10000 / Cr INCOME_TAX_PAYABLE 10000. No statutory rate or generic liability-payment workflow is invented. |
| 20700 · `PAYROLL_DEDUCTIONS` | **Payroll deductions payable** · liability; non-control; `current_liabilities` | Permitted payroll deduction liability, separate from net wages. | Gross 10000 with deduction 500: Dr SALARY 10000 / Cr PAYROLL 9500 / Cr PAYROLL_DEDUCTIONS 500. Remitting deductions needs an approved payment design. |
| 21000 · `SHORT_TERM_LOANS` | **Short-term borrowings** · liability; non-control; `current_liabilities` | Template for current borrowings. No automated cash borrowing/repayment workflow. | Current-portion reclassification 10000: journal Dr LONG_TERM_LOANS 10000 / Cr SHORT_TERM_LOANS 10000. |
| 21100 · `CURRENT_LEASE` | **Current lease liabilities** · liability; non-control; `current_liabilities` | Template for the current part of an approved lease liability. No automatic lease measurement. | Reclassify due lease principal 10000: journal Dr LONG_TERM_LEASE 10000 / Cr CURRENT_LEASE 10000. |
| 25000 · `LONG_TERM_LOANS` | **Long-term borrowings** · liability; non-control; `noncurrent_liabilities` | Template for non-current borrowing. No automatic amortization schedule. | Reviewed opening loan 50000: journal Dr EQUITY 50000 / Cr LONG_TERM_LOANS 50000; separately classify current portions. |
| 25100 · `LONG_TERM_LEASE` | **Non-current lease liabilities** · liability; non-control; `noncurrent_liabilities` | Template for non-current lease liability. Full IFRS 16 lease automation is not implemented. | Reviewed opening lease liability 20000: Dr EQUITY 20000 / Cr LONG_TERM_LEASE 20000; accountant must establish matching opening assets independently. |
| 30000 · `EQUITY` | **Opening capital** · equity; non-control; `equity` | Opening/owner capital classification; balance-sheet residual interest. | Reviewed opening cash 200000: Dr CASH 200000 / Cr EQUITY 200000. Opening supplier debt reduces opening equity. |
| 31000 · `RETAINED_EARNINGS` | **Retained earnings** · equity; non-control; `equity` | Template for prior retained profit; period_close only locks dates and does not generate an earnings-transfer journal. | Reviewed equity reclassification 2000: Dr EQUITY 2000 / Cr RETAINED_EARNINGS 2000. Current unclosed profit is calculated in reports. |
| 32000 · `DRAWINGS` | **Owner drawings** · equity; non-control; `equity` | Owner withdrawals classification, not an operating expense. Dedicated owner cash-withdrawal posting is not implemented. | Eligible noncash close of existing drawings 1000: Dr EQUITY 1000 / Cr DRAWINGS 1000; this does not withdraw cash. |
| 40000 · `SALES` | **External sales** · income; control; `revenue` | External delivered sales; separate from collections and internal transfers. | Delivered sale 5000 credits SALES 5000; inspected return 1000 debits SALES 1000. Customer receipt creates no second SALES entry. |
| 41000 · `OTHER_INCOME` | **Other operating income** · income; non-control; `other_operating_income` | Template for other operating income, not automatic collection or product sales routing. | Accrue another earned claim 500: journal Dr OTHER_RECEIVABLES 500 / Cr OTHER_INCOME 500. Cash settlement of that claim needs a designed route. |
| 42000 · `INVESTMENT_INCOME` | **Investment income** · income; non-control; `investing_income` | Template for investment income accrual; no investment instrument module. | Earned dividend receivable 1000: journal Dr OTHER_RECEIVABLES 1000 / Cr INVESTMENT_INCOME 1000. |
| 42100 · `INTEREST_INCOME` | **Interest income** · income; non-control; `finance_income` | Template for finance income accrual, not an automatic bank-interest feed. | Earned interest claim 200: journal Dr OTHER_RECEIVABLES 200 / Cr INTEREST_INCOME 200. |
| 43000 · `FX_GAIN` | **Foreign exchange gains** · income; non-control; `other_operating_income` | Profit from monetary exchange gains or closing-rate retranslation. | USD 100 receivable carrying 7000 revalued to 7200: Dr AR 200 / Cr FX_GAIN 200. No foreign quantity or sales revenue is added. |
| 50000 · `COGS` | **Cost of goods sold** · expense; control; `cost_of_sales` | Carrying value of delivered goods, not their selling price. | Selling inventory costing 2500: Dr COGS 2500 / Cr FG 2500. A supported return reverses the original carrying cost. |
| 50100 · `WASTE` | **Abnormal waste and stock losses** · expense; control; `cost_of_sales` | Approved abnormal losses, cutting loss, damage or shortages. | Confirmed damaged goods carrying 200: Dr WASTE 200 / Cr the affected inventory control 200. |
| 50200 · `IMPAIRMENT` | **Inventory write-down expense** · expense; non-control; `cost_of_sales` | Expense from reviewed stock net-realisable-value reduction. | Inventory write-down 500: Dr IMPAIRMENT 500 / Cr INVENTORY_ALLOWANCE 500. Generic expense entry is not a substitute for that stock allowance. |
| 61000 · `SALARY` | **Administrative wages** · expense; non-control; `administrative_expenses` | Administrative payroll expense. Employee subledger comes from payroll accrual, not a free-form cash expense. | Accrue administrative salary 10000: Dr SALARY 10000 / Cr PAYROLL 10000; settlement does not debit SALARY again. |
| 61100 · `DEPRECIATION` | **Depreciation** · expense; non-control; `administrative_expenses` | System-calculated straight-line fixed-asset depreciation expense. | Machine 60000, residual 0, life 60 months: Dr DEPRECIATION 1000 / Cr ACCUM_DEPR 1000 per eligible month. |
| 61200 · `RENT` | **Office rent** · expense; non-control; `administrative_expenses` | Office/admin rent expense; expense entry or reviewed accrual. | Pay office rent 5000: expense Dr RENT 5000 / Cr CASH 5000, or Cr AP for a supplier bill. |
| 61300 · `UTILITIES` | **Office utilities** · expense; non-control; `administrative_expenses` | Office electricity/water/utility expenses. | Pay office utility 700: Dr UTILITIES 700 / Cr CASH 700 through Expense. |
| 61400 · `PROFESSIONAL_FEES` | **Professional fees** · expense; non-control; `administrative_expenses` | Accountant, legal or other professional-service expenses. | Supplier service 1000: Expense Dr PROFESSIONAL_FEES 1000 / Cr AP 1000. |
| 61500 · `OFFICE_SUPPLIES` | **Office supplies** · expense; non-control; `administrative_expenses` | Office consumables recognized as expense. | Buy stationery 300: Dr OFFICE_SUPPLIES 300 / Cr CASH 300 through Expense. |
| 61900 · `EXPENSE` | **Operating expenses** · expense; non-control; `other_operating_expenses` | Generic operating expense and certain approved purchase-return carrying-value differences. | General expense 300: Dr EXPENSE 300 / Cr CASH 300. Prefer a specific expense account where appropriate. |
| 62000 · `OVERHEAD` | **Production overhead** · expense; non-control; `other_operating_expenses` | General production-overhead expense classification; not an automatic WIP absorber. | Expense entry 600: Dr OVERHEAD 600 / Cr CASH 600. Eligible absorbed overhead instead uses the controlled COST_CLEARING route. |
| 62100 · `FACTORY_RENT` | **Factory rent / unabsorbed overhead** · expense; non-control; `other_operating_expenses` | Factory rent/unabsorbed-overhead expense; capitalization is not automatic. | Unabsorbed factory rent 1000: Dr FACTORY_RENT 1000 / Cr CASH 1000. Eligible conversion absorption uses reviewed COST_CLEARING sources. |
| 62200 · `FACTORY_UTILITIES` | **Factory utilities / unabsorbed overhead** · expense; non-control; `other_operating_expenses` | Factory utility/unabsorbed-overhead expense; not automatically included in every block. | Factory utility 500 expensed: Dr FACTORY_UTILITIES 500 / Cr CASH 500. Do not enter it again as unsupported batch overhead. |
| 62300 · `REPAIRS` | **Repairs and maintenance** · expense; non-control; `other_operating_expenses` | Equipment repair and maintenance expense. | Maintenance spare consumption 200: Dr REPAIRS 200 / Cr RAW 200 at carrying cost. Supplier repair invoices can use Expense. |
| 63000 · `DELIVERY` | **Outbound delivery** · expense; non-control; `selling_expenses` | Outbound delivery/selling cost, not automatically added to finished inventory. | Delivery charge 400: Dr DELIVERY 400 / Cr CASH 400 through Expense. |
| 63100 · `MARKETING` | **Marketing and selling** · expense; non-control; `selling_expenses` | Advertising and selling expense. | Advertisement 800: Dr MARKETING 800 / Cr CASH 800 through Expense. |
| 64000 · `BANK_FEES` | **Bank service charges** · expense; non-control; `other_operating_expenses` | Bank/saraf service charges recognized separately from the currency principal. | Currency exchange fee 10: Dr BANK_FEES 10 / Cr CASH 10, in addition to the actual exchange entries. |
| 64100 · `BAD_DEBTS` | **Receivable impairment** · expense; non-control; `other_operating_expenses` | Receivable impairment/write-off expense. | Approved customer write-off 500: Dr BAD_DEBTS 500 / Cr AR 500; linked invoice allocation closes that portion of debt. |
| 64200 · `FX_LOSS` | **Foreign exchange losses** · expense; non-control; `other_operating_expenses` | Expense from monetary exchange losses. | USD 100 supplier debt carrying 7000 settled for 7200 AFN: Dr AP 7000 / Dr FX_LOSS 200 / Cr CASH 7200. |
| 71000 · `INTEREST_EXPENSE` | **Finance costs** · expense; non-control; `finance_costs` | Finance cost, not principal repayment. Selected cash-flow policy treats its direct cash expense as financing. | Interest paid 200: Expense Dr INTEREST_EXPENSE 200 / Cr BANK 200. Automatic loan interest calculation is absent. |
| 80000 · `INCOME_TAX_EXPENSE` | **Income tax expense** · expense; non-control; `income_tax` | Income-tax charge approved by an accountant. No default Afghan tax calculation. | Tax accrual 10000: journal Dr INCOME_TAX_EXPENSE 10000 / Cr INCOME_TAX_PAYABLE 10000. |

| 21310 · `FX_CUSTOMER_DEPOSITS` | liability · current_liabilities | Refundable foreign monetary customer credits, reconciled to the foreign deposit ledger. | Receive USD100 at70: Dr CASH7000 / Cr FX_CUSTOMER_DEPOSITS7000; allocation/refund/revaluation uses its own workflow. |
| 11310 · `FX_SUPPLIER_DEPOSITS` | asset · current_assets | Refundable foreign monetary supplier credits, separate from goods advances. | Pay refundable USD100 at70: Dr FX_SUPPLIER_DEPOSITS7000 / Cr CASH7000. |
| 63200 · `COMMISSION` | expense · selling_expenses | Approved commission expense, separate from fixed wages. | Collected eligible net sales10000 at2%: Dr COMMISSION200 / Cr PAYROLL200; paying the earning debits PAYROLL and credits cash. |

### Report groups explained

| Group | Meaning and example |
|---|---|
| Current assets | Cash, receivables, inventory and eligible short-term balances. RAW/FG are money values, not cm/kg totals. |
| Non-current assets | Fixed assets net of accumulated depreciation; long-term deposits. Current/non-current classification needs approved facts. |
| Current liabilities | Supplier bills, payroll, tax and current loan/lease portions. |
| Non-current liabilities | Approved long-term borrowing/lease balances; no automated measurement is implied. |
| Equity | Capital, retained earnings/drawings and calculated unappropriated profit. |
| Revenue | External SALES. Internal Herat/Kabul charges are not external revenue. |
| Cost of sales | COGS, abnormal WASTE and approved inventory impairment in the current template. |
| Administrative expenses | Office SALARY, RENT, UTILITIES, professional fees and office supplies. |
| Selling expenses | DELIVERY and MARKETING. |
| Other operating expenses | EXPENSE, unabsorbed factory expenses, repairs, fees, bad debts and FX losses under this template. |
| Other operating income | OTHER_INCOME and FX_GAIN under this template. |
| Investing income | INVESTMENT_INCOME. This P&L category does not automatically decide every related cash flow. |
| Finance income | INTEREST_INCOME. |
| Finance costs | INTEREST_EXPENSE. |
| Income tax | INCOME_TAX_EXPENSE, based on approved applicable policy. |

Account group selection affects presentation. It does not change a cash collection into income or a supplier bill into inventory. Complete statements also need approved classification/disclosures; the app is not “ACCA certified” or a full IFRS disclosure package.

## 4. One complete manufacturing example

Use a separate synthetic training business, not live books. No chemical formula is provided: the production inputs below represent actual approved total consumption costs.

| Step | Application action | Debit | Credit | Result |
|---|---|---|---|---|
|1 | Reviewed opening cash | CASH 200000 | EQUITY 200000 | Cash 200000; capital 200000. |
|2 | Receive 100 kg generic material at 500 | RAW 50000 | GRNI 50000 | Raw stock 100 kg costing 50000; no salary or sales expense. |
|3 | Matched supplier bill for receipt | GRNI 50000 | AP 50000 | Receipt clearing is zero; supplier owed 50000. No second receipt. |
|4 | Pay supplier 30000 | AP 30000 | CASH 30000 | Supplier still owed 20000; cash 170000. |
|5 | Factory salary earned 3000, eligible for this batch | LABOR_CLEARING 3000 | PAYROLL 3000 | Employee owed 3000; cash unchanged. |
|6 | Record backed eligible production overhead 2000 | COST_CLEARING 2000 | CASH 2000 | Cash 168000; source available for approved absorption. |
|7 | Actual material consumption costing 20000 and linked conversion sources 5000 | WIP 25000 | RAW 20000; LABOR_CLEARING 3000; COST_CLEARING 2000 | Raw value 30000; clearing sources zero; WIP 25000. Source documents cannot be reused beyond available amounts. |
|8 | Complete one compatible 100 cm-high measured block | FG 25000 | WIP 25000 | WIP zero, block cost 25000 =250 AFN/cm for this example. Grade “45 kg” is a name, not a conversion factor. |
|9 | Deliver 10 cm at 500/cm, kerf 0 | AR 5000; COGS 2500 | SALES 5000; FG 2500 | Customer owes 5000; block 90 cm, remaining FG 22500. |
|10 | Receive 3500 on same invoice | CASH 3500 | AR 3500 | Remaining invoice 1500. Profit remains 2500, not 3500. |
|11 | Receive the final 1500 | CASH 1500 | AR 1500 | Customer debt zero. Cash 173000. Total sales remains 5000. |
|12 | Give the employee 1000 advance | ADVANCES 1000 | CASH 1000 | Cash 172000; advance asset 1000; salary liability still 3000. |
|13 | Settle that salary: cash 2000 plus advance recovery 1000 | PAYROLL 3000 | CASH 2000; ADVANCES 1000 | Salary liability 0; advance 0; cash 170000. Salary/production cost is not expensed a second time. |

Final balance sheet for this isolated example: cash 170000 + RAW 30000 + FG 22500 = **assets 222500**. Supplier liability 20000 + equity 200000 + profit 2500 = **222500**. P&L: SALES 5000 − COGS 2500 = profit 2500. Factory salary/eligible overhead still inside unsold stock are not immediately charged again to P&L.

With real cutting loss, trim by-products, tax or several materials the lines differ. Physical height, cost and actual sales must still reconcile. Sales of sponge aggregate height only within compatible footprints; do not add 1 m-wide and 2 m-wide sheets into an unexplained single interchangeable stock unit. Adhesive remains kg-based.

## 5. Every registered operation: where it is and what it changes

The identifiers below are stable implementation names; menus display translated business labels. Visibility depends on permission, business mode, location, product-line scope and approval limit. Some advanced operations open through “More actions” or the operations workspace. An implemented API action is not permission for every employee to post it.

The numerical examples describe the relevant part of each transaction. Optional tax, deposits, valuations, abnormal loss or source allocations can create additional linked lines. Look at the posted document journal to inspect the exact result.

| Operation | Workspace / purpose | Accounts affected | Example and limits |
|---|---|---|---|

| `allocate_deposit` | Money/credit allocation | Customer: Dr DEPOSITS/Cr AR. Supplier: Dr AP/Cr SUPPLIER_DEPOSITS | Apply existing 2000 customer credit against an invoice: AR down 2000 without another cash movement. |
| `asset_acquire` | Accounting/fixed assets | Dr ASSETS; Cr CASH/BANK or AP | Buy 60000 machine: asset 60000; cash decrease or supplier liability. Expense is recognized over useful life. |
| `asset_depreciate` | Accounting/fixed assets | Dr DEPRECIATION; Cr ACCUM_DEPR for additional due charge | 60000/60 months with zero residual gives 1000 per eligible month. Repeating the same covered depreciation adds nothing and is rejected. |
| `attendance_record` | Employees/time | No journal; approved attendance feeds eligible payroll | Approve 8 hours; do not pay or expense a salary until payroll accrual/settlement. |
| `bank_reconcile` | Money/bank reconciliation | No new cash journal; records matching selected bank entries to statement | Bank statement 20000 matched to cleared entries 20000; uncleared transactions remain identifiable. |
| `bin_create` | Operations/warehouse | No financial journal from this action | Create rackA 1; no physical stock is created. |
| `block_place` | Operations/warehouse | No financial journal from this action | Place the identified local block inA 1; warehouse quantities/value do not change. |
| `budget_set` | Operations/budget | No financial journal from this action | Budget rent 1000 for an accounting month/site/line; no expense is recognized by a budget. |
| `cash_count` | Money/cash control | No journal; evidence of counted versus recorded cash | Count 9800 against recorded 10000: report variance-200. No silent write-off or automatic balance overwrite. |
| `cash_transfer` | Money/cash and bank | Dr receiving CASH/BANK/location; Cr sending CASH/BANK/location | Deposit cash 2000 into bank: cash-2000, bank+2000, no expense/income. |
| `catalog_import` | Settings/import | No financial journal from this action | Import reviewed products/parties; zero opening stock/cash unless separate actual opening operations are posted. |
| `collection_create` | Operations/collections | No financial journal from this action | Create promise 1500 against a real unpaid invoice; no AR or cash movement. |
| `collection_note` | Operations/collections | No financial journal from this action | Record call/reschedule/outcome; marking kept requires settled debt but does not itself receive money. |
| `customer_price` | Operations/customer rates | No financial journal from this action | Approve 400 AFN/cm for a customer/compatible footprint/effective date; no sales entry until delivery. |
| `customer_refund` | Money/customer credit | Dr DEPOSITS; Cr CASH/BANK | Refund available customer credit 1000: cash-1000, customer liability-1000; not new sales return by itself. |
| `cut` | Inventory/cutting | Dr new piece inventory; Cr source block inventory; Dr WASTE for valued kerf | Cut 2.2 cm from 100 cm:97.8 cm remains when kerf 0. Carrying value moves to the piece; no SALES/AR entry. |
| `cut_execute` | Operations/cutting plans | Executes linked cuts; customer-demand plans hold identified sheets for their order. Cancellation releases uncut reservations or unsold held sheets without reversing past cuts or invoices. | The 120 mm plan becomes pieces plus 4 mm kerf and an 880 mm remnant from 1000 mm. No automatic sale. Invoicing held sheets later issues those child pieces once, without reducing the parent again. |
| `cut_plan` | Operations/cutting plans | No revenue or value journal; reserves individual block height and, when linked, outstanding sales-order quantities across compatible customer demands. | Plan 3×22 mm and 1×50 mm with 1 mm kerf each:120 mm consumed when executed; reserve now. A second plan or direct order invoice cannot consume the same committed demand. |
| `delivery_confirm` | Operations/delivery | No financial journal from this action | Confirm recipient on an already posted sale once; no second stock issue, revenue or AR. An opening debt is not a delivery. |
| `employee_advance` | Employees/money | Dr ADVANCES; Cr CASH/BANK | Give 8000 before earnings: employee advance asset 8000, cash-8000, salary expense 0. |
| `equipment_create` | Operations/equipment | No financial journal from this action | Register machine/service interval and optional existing fixed asset; no asset purchase is invented. |
| `expense_post` | Money/expense | Dr selected allowed expense; Cr CASH/BANK or AP; special reviewed COST_CLEARING requires production authority | Pay office rent 5000: Dr RENT 5000 / Cr CASH 5000. A supplier expense bill credits AP instead; do not duplicate it at payment. |
| `forecast_add` | Operations/cash forecast | No financial journal from this action | Plan expected collection 1500; it remains an estimate until a real receipt is posted. |
| `fx_exchange` | Operations/saraf exchange | Move AFN cash against FX wallet; release carrying value on sale; separate FX_GAIN/LOSS and BANK_FEES | Sell USD 50 carrying 3500 for 3600: Dr CASH 3600 / Cr FX_CASH 3500 / Cr FX_GAIN 100; fee 10 Dr BANK_FEES/Cr CASH 10. |
| `fx_opening` | Operations/currency opening | Dr FX_CASH/FX_BANK; Cr EQUITY | Verified USD 100 at 70 =7000 AFN opening carrying value. |
| `fx_rate` | Operations/currency | No journal; stores approved immutable AFN-per-unit rate/reference | Record USD 70 AFN per 1 USD. Never infer a market rate from the business label or customer currency. |
| `fx_register` | Operations/foreign invoice terms | No second revenue or stock entry; registers unpaid AFN invoice contractual currency at original date | AFN 7000 invoice may register USD 100 at 70 only if its exact total matches and it is unpaid/unadjusted. |
| `fx_remit_dispatch` | Operations/internal remittance | Dr FX_TRANSIT; Cr source FX wallet; fee separately Dr BANK_FEES/Cr CASH | Send USD 20 carrying 1400 internally. It is in transit, unavailable at destination and not external revenue. |
| `fx_remit_receive` | Operations/internal remittance | Dr destination FX wallet; Cr FX_TRANSIT once | Receive that USD 20 at its current transit carrying amount 1400; do not create a second 7000-style opening deposit. |
| `fx_revalue` | Accounting/currency closing value | Assets rise: Dr monetary control/Cr FX_GAIN; liabilities rise: Dr FX_LOSS/Cr AP; reverse when rates fall | USD 100 AR 7000 at closing 72 becomes 7200: gain 200; quantity 100 USD stays fixed. Historical aging respects the as-of date. |
| `fx_settle` | Operations/foreign settlement | Customer: Dr actual cash/wallet, Cr AR carrying released, balance FX_GAIN/LOSS. Supplier reverses liability/cash sides | USD 40 receivable carrying 2880 settled at 73 gives cash 2920 and FX_GAIN 40. Foreign quantity falls 40; normal AFN receipt cannot bypass it. |
| `fx_wallet` | Operations/currency | No financial entry; creates a currency/location wallet | Create Herat USD cash wallet with balance 0; a name alone adds no money. |
| `inspection_template` | Operations/quality | No financial journal from this action | Define measured thickness/finish criteria; no accounting entry. |
| `internal_charge_adjust` | Transfers/management price | No external journal; changes supported managerial internal charge | Adjust internal branch price by 500 with a reason; company external sales/profit are unchanged. |
| `internal_settlement` | Money/internal transfer settlement | Dr destination CASH/BANK; Cr source CASH/BANK; management charge balance is reduced | Kabul remits 2000 to Herat: location cash changes; company cash total and external revenue do not. |
| `inventory_write_down` | Accounting/inventory NRV | Dr IMPAIRMENT; Cr INVENTORY_ALLOWANCE; no physical count change | Cost 10000, approved carrying-value reduction 1000: net stock 9000, quantity unchanged. |
| `inventory_write_down_reverse` | Accounting/NRV reversal | Dr INVENTORY_ALLOWANCE; Cr original impairment expense within remaining supported amount | Recover 400 of the 1000 write-down: net stock rises 400; original unreleased reduction remains 600. |
| `job_card` | Operations/job cards | No financial journal from this action | Record 120 actual minutes; it does not create salary accrual/payment automatically. |
| `journal_adjust` | Accounting/adjustment journal | User-specified balanced eligible non-control entries; reason required | Accrue office rent 5000: Dr RENT 5000 / Cr ACCRUED_EXPENSES 5000. RAW/AR/CASH control bypass is blocked. |
| `lot_create` | Operations/material lots | No financial journal from this action | Record supplier lot code/expiry for a raw material; it has no quantity until tagged/received. |
| `lot_opening` | Operations/material lots | No financial journal from this action | Assign existing 5 kg to a lot, without receiving that stock or value again. |
| `lot_status` | Operations/material quality | No financial journal from this action | Hold/release a lot with reason and full-location authority; consumption observes released/unexpired eligibility. |
| `lot_tracking_enable` | Operations/material lots | No financial journal from this action | Enable strict tracking only when every existing raw pool reconciles to its recorded lot quantities. |
| `maintenance_complete` | Operations/equipment | If parts consumed: Dr REPAIRS; Cr actual inventory carrying cost. Otherwise no value journal | Use spare material cost 200: stock-200 and repairs+200;45 minutes downtime does not invent payroll. |
| `maintenance_open` | Operations/maintenance | No financial journal from this action | Open repair request with due date/reason; expense occurs only when actual parts/expenses are posted. |
| `material_issue` | Inventory/factory floor | Dr inventory at floor; Cr same inventory control at store | Move raw stock 1000 to floor: warehouse quantities move; company RAW total and expense do not change. This is not consumption. |
| `material_return` | Inventory/factory floor | Reverse physical floor-to-store move within same location | Unused floor material 500 returns to store with no production expense or revenue. |
| `opening_cash` | Accounting/opening | Dr CASH/BANK; Cr EQUITY | Reviewed opening cash 200000 creates cash and opening capital, not revenue. |
| `opening_employee_advance` | Accounting/opening | Dr ADVANCES; Cr EQUITY | Old employee advance 2000 opens employee debt; no cash is paid again. |
| `opening_payable` | Accounting/opening | Dr EQUITY; Cr AP | Old supplier debt 3000 becomes a supplier-linked payable. |
| `opening_receivable` | Accounting/opening | Dr AR; Cr EQUITY | Old customer debt 5000 becomes an invoice-linked opening receivable; collecting it later is not a new sale. |
| `order_cancel` | Sales/purchasing orders and quotation closure | Closes a quotation at any stage, stops new conversions and remaining linked sales-order fulfillment; no reversal of posted delivery | Cancel unfulfilled quantity 10 or close an already converted quotation with a reason. Posted invoices, delivered inventory and payments remain; use their own linked corrections. Quotation closure is not receivable write-off; that uses receivable_writeoff. |
| `payment_reverse` | Money/linked correction | Exact opposite of supported original receipt/supplier payment; compensating invoice allocations | Wrong receipt 1000: Cr CASH 1000 / Dr AR 1000, reopening the old debt. It does not undo stock delivery or sales. |
| `payroll_accrue` | Employees/payroll | Dr SALARY or eligible LABOR_CLEARING gross; Cr PAYROLL net; Cr deduction liabilities | Gross 25000, deductions 1000: expense/clearing 25000; PAYROLL 24000; tax/deduction liability 1000. Cash unchanged. |
| `payroll_settle` | Employees/payroll payment | Dr PAYROLL; Cr CASH/BANK for cash and ADVANCES for recovery | Net payable 24000; pay 15000 and recover 5000 advance: PAYROLL remains 4000, advance falls 5000, cash falls 15000. |
| `period_close` | Accounting/period control | No closing-income journal; locks postings through the approved date | Close through a selected date. Earlier new postings are blocked. Existing profit is not magically moved to retained earnings. |
| `period_reopen` | Accounting/period control | No account movement; changes closed-through date with authority/reason | Reopen an earlier date for a reviewed correction. It does not erase immutable documents. |
| `print_profile` | Operations/system | No financial journal from this action | Set official name/address/footer; it does not rewrite financial history or create a journal. |
| `production` | Production/actual consumption | Consumption into WIP plus completion out of WIP in one transaction | Actual backed cost 25000 produces a measured 100 cm block valued 25000. No formula is required. |
| `production_bom` | Production/optional approved BOM | Same cost routing as actual production; approved BOM assists requirements | In a BOM-enabled business, expected inputs guide entry; actual consumed cost still determines inventory value. Disabled for this sponge business. |
| `production_complete` | Production/staged WIP | Dr FG/TRIM; Cr WIP; Dr WASTE for approved abnormal loss | Complete WIP 25000 with 1000 abnormal loss: FG 24000, WASTE 1000, WIP-25000. |
| `production_consume` | Production/staged WIP | Dr WIP; Cr actual RAW and eligible LABOR_CLEARING/COST_CLEARING | Consume actual cost 20000 plus backed conversion 5000: WIP 25000; corresponding sources reduced once. |
| `production_material_return` | Production/WIP material return | Dr inventory; Cr WIP at original unreturned input cost | Return 1000 of genuinely unused consumed inputs before completion: RAW+1000, WIP-1000. |
| `production_start` | Production/staged WIP | No financial entry; creates a batch identity | Start batch B 1; no invented input use or finished output. |
| `purchase_bill` | Purchases/bill | Dr GRNI; Cr AP for matched unbilled received quantities | Invoice 6000 of a 10000 receipt: GRNI decreases 6000; AP increases 6000; stock is not received twice. |
| `purchase_order` | Purchases | No journal or stock receipt | Order 100 kg at 500 =50000 planned; inventory/AP remain unchanged. |
| `purchase_receive` | Purchases/receive | Dr item inventory; Cr GRNI for purchase plus supported landed cost | Receive 100 kg at 500 =50000: RAW+50000, GRNI+50000. A later bill must link this receipt. |
| `purchase_request` | Operations/replenishment | No financial journal from this action | Request suggested 40 units; no inventory receipt, AP or cash commitment is posted. |
| `purchase_return` | Purchases/return | Cr inventory at carrying cost; Dr GRNI if unbilled, otherwise Dr AP/ SUPPLIER_DEPOSITS; EXPENSE handles carrying/credit difference | Return goods carrying 1000 with supplier credit 900: credit inventory 1000, debit AP 900 and EXPENSE 100. Link receipt/bill; original quantity limits apply. |
| `quality_inspect` | Operations/quality | No financial journal from this action | Record actual pass/fail. A physical block enters inspection hold; no fake stock write-off occurs. |
| `quality_release` | Production/quality | No financial journal from this action | Release eligible held stock with required passing inspection/reason; stock value and sales do not change. |
| `quotation` | Sales/quote | No financial entry or inventory deduction | Quote 5000 is a proposal, not earned SALES or AR. |
| `receipt` | Money/customer center | Dr CASH/BANK; Cr AR; Cr DEPOSITS for unallocated excess | Collect remaining 1500 on the same 5000 invoice: AR 0; SALES remains 5000. |
| `receivable_writeoff` | Accounting/collections | Dr BAD_DEBTS; Cr AR; linked allocation | Approve unrecoverable invoice portion 500: debt decreases 500 and expense increases 500; cash is unchanged. |
| `reminder_prepare` | Operations/reminders | No financial journal from this action | Prepare or queue reviewed text; provider not configured means blocked, acceptance is not confirmed delivery. No accounting entry. |
| `reorder_policy` | Operations/replenishment | No financial journal from this action | Set minimum 20 and target 50 for a real warehouse/product/compatible footprint; stock remains unchanged. |
| `request_order` | Operations/purchase requests | No financial journal from this action | Convert an open request to a real purchase order once; that order still has no inventory/AP journal. |
| `reservation_release` | Inventory/reservation | No journal; releases the active reservation once | Cancel unused 44 mm reservation; available height rises, physical height does not. |
| `reserve` | Inventory/reservation | No journal; commits available physical height | Reserve two 22 mm sheets plus measured kerf; stock value and sales stay unchanged. |
| `sale` | Sales/delivery | Dr AR; Cr SALES and configured TAX; Dr COGS/Cr inventory; immediate cash receipt/deposit if supplied | Sell 5000 costing 2500, collect 3500: AR net 1500; SALES 5000, COGS 2500, inventory-2500, CASH+3500. |
| `sales_order` | Sales/order | No delivered sales journal yet | Confirm order 5000; actual delivery/sale creates revenue and cost later. |
| `order_promise` | Sales order / readiness and delivery review | No financial journal, stock movement or reservation. | For an open order, record a reviewed delivery date, reason and availability/production basis. This records a promise, not a guarantee: it does not reserve a block, cut a sheet, deliver goods, create an invoice or collect money. Recheck availability before fulfillment. |
| `sales_return` | Sales/linked return | Dr SALES and original TAX; Cr AR or DEPOSITS; Dr inventory/Cr original COGS; supported allowance restoration | Return sales 1000 costing 500. Unpaid debt falls 1000, stock value rises 500, COGS falls 500. Paid-invoice credit becomes customer deposit until refunded/applied. |
| `shared_cost_allocate` | Accounting/shared expenses | Reclassifies backed shared expense across authorized product lines; no new cash/total expense | Split 1000 shared office expense 600 sponge/400 adhesive; company total expense remains 1000. |
| `stock_adjust` | Inventory/controlled adjustment | Surplus Dr inventory/Cr EQUITY; shortage Dr WASTE/Cr inventory | Approved missing stock cost 200: WASTE 200 and inventory-200. Use a measured count/reason instead of editing quantity. |
| `stock_count` | Inventory/count observation | No stock or journal mutation | Observe 90 kg against 100 kg expected; preserve snapshot evidence and variance-10 kg. |
| `stock_count_adjust` | Inventory/approved count reconciliation | Shortage Dr WASTE/Cr inventory; supported valued surplus Dr inventory/Cr EQUITY | Apply observed 10 kg shortage costing 500: inventory-500, WASTE+500. Stale counts after intervening moves are rejected. |
| `stock_opening` | Inventory/opening | Dr RAW/FG/TRIM; Cr EQUITY | Reviewed stock value 10000 with real kg/blocks creates opening inventory; it is not a purchase expense. |
| `supplier_payment` | Money/supplier center | Dr AP for allocations, Dr SUPPLIER_DEPOSITS for excess; Cr CASH/BANK | Pay 7000 against 5000 debt: AP down 5000, supplier deposit up 2000, cash down 7000. |
| `supplier_refund` | Money/supplier credit | Dr CASH/BANK; Cr SUPPLIER_DEPOSITS | Recover 2000 of actual available supplier credit: cash up 2000, supplier deposit down 2000. |
| `transfer_dispatch` | Transfers/Herat to Kabul | Dr TRANSIT; Cr source inventory; freeze carrying value | Dispatch stock 10000: source warehouse decreases and transit increases. Internal price 12000 is management data, not SALES/AR. |
| `transfer_receive` | Transfers/branch receipt | Dr destination inventory; Cr TRANSIT for actual received quantities | Receive 60% of 10000 shipment: destination stock 6000; transit 4000. No new purchase cost or sales income. |
| `transfer_resolve` | Transfers/discrepancy | Return: Dr source inventory/Cr TRANSIT. Damage/shortage: Dr WASTE/Cr TRANSIT | Resolve lost transit goods carrying 500: WASTE 500, TRANSIT-500; state and quantities cannot be silently marked received. |
| `trim` | Production/block finishing | Cr source inventory; Dr main/trim outputs; Dr WASTE only for approved abnormal loss | Source cost 10000 becomes main 8500 + saleable top/bottom 1000 + abnormal WASTE 500. Costs and measured heights must reconcile. |
| `work_center` | Operations/capacity | No financial journal from this action | Configure 480 minutes per day at the assigned location; no labor expense is posted. |
| `work_close` | Operations/work orders | No financial journal from this action | Close 100 cm target only after real linked production reaches 100 cm, or cancel remaining plan with reason. |
| `work_order` | Operations/production plan | No financial journal from this action | Plan 100 cm output/300 minutes; the work center must have enough actual configured capacity. |

| `fx_sale` | Foreign monetary workflow | Posts a normal delivered `sale` with foreign-priced lines converted at an approved transaction rate: Dr AR / Cr Sales; Dr COGS / Cr inventory for delivered stock. Creates the linked foreign contractual exposure in the same transaction. It does not create a second sale or a separate registration journal. | Review the actual source invoice, party, currency and rate; refundable monetary credit only. Nonmonetary goods advances remain unsupported. |
| `fx_purchase` | Foreign monetary workflow | Receives stock and bills the supplier atomically: receipt Dr inventory / Cr GRNI; bill Dr GRNI / Cr AP. Foreign line costs and contractual quantity are preserved. Stock is received once. | Review the actual source invoice, party, currency and rate; refundable monetary credit only. Nonmonetary goods advances remain unsupported. |
| `fx_deposit` | Foreign monetary workflow | Records explicitly **refundable monetary** customer/supplier money. Customer: Dr AFN cash or foreign wallet / Cr `FX_CUSTOMER_DEPOSITS`. Supplier: Dr `FX_SUPPLIER_DEPOSITS` / Cr AFN cash or foreign wallet. Differences between wallet carrying cost and the transaction value use FX gain/loss. | Review the actual source invoice, party, currency and rate; refundable monetary credit only. Nonmonetary goods advances remain unsupported. |
| `fx_deposit_allocate` | Foreign monetary workflow | Settles a matching-currency, matching-party invoice with refundable credit; no cash moves. Customer: Dr foreign deposit liability / Cr AR. Supplier: Dr AP / Cr foreign deposit asset. Each side releases its actual proportional AFN carrying amount; the difference is FX gain/loss. Both foreign balances decrease by the same foreign quantity. | Review the actual source invoice, party, currency and rate; refundable monetary credit only. Nonmonetary goods advances remain unsupported. |
| `fx_refund` | Foreign monetary workflow | Returns unused monetary credit. Customer: Dr deposit liability / Cr cash/wallet; supplier: Dr cash/wallet / Cr deposit asset. Carrying versus cash differences use FX gain/loss. Refunds cannot exceed remaining foreign credit. | Review the actual source invoice, party, currency and rate; refundable monetary credit only. Nonmonetary goods advances remain unsupported. |
| `fx_settlement_reverse` | Foreign monetary workflow | Compensates the latest supported `fx_settle`: opposite original journal, opposite foreign-exposure/wallet movements, and negative historical invoice allocation. Original records stay immutable. It reopens the original foreign quantity and AFN carrying value. | Review the actual source invoice, party, currency and rate; refundable monetary credit only. Nonmonetary goods advances remain unsupported. |
| `fx_return` | Foreign monetary workflow | Processes inspected physical returns using the established inventory/lineage/COGS workflow, then replaces the draft AFN debt rows with linked foreign credit movements. Reverses historical revenue/purchase credit at its original carrying basis; releases current AR/AP carrying value, posting the difference to FX gain/loss. A paid/excess return creates a refundable foreign monetary deposit. | Review the actual source invoice, party, currency and rate; refundable monetary credit only. Nonmonetary goods advances remain unsupported. |
| `fx_credit` | Foreign monetary workflow | Approved **sales price-only** credit with no physical stock movement. Dr Sales at the original invoice rate / Cr current AR or refundable foreign deposit, plus FX gain/loss for the difference. Retains reason and original invoice. | Review the actual source invoice, party, currency and rate; refundable monetary credit only. Nonmonetary goods advances remain unsupported. |
| `fx_deposit_revalue` | Foreign monetary workflow | Remeasures an open refundable monetary deposit to the approved closing rate without changing foreign quantity. Supplier asset increase: Dr deposit / Cr FX gain; customer liability increase: Dr FX loss / Cr deposit. Reductions reverse those directions. | Review the actual source invoice, party, currency and rate; refundable monetary credit only. Nonmonetary goods advances remain unsupported. |
| `transport_vehicle` | Operational evidence / job costing | None. | Register the real vehicle plate, its loading location, and a descriptive capacity note. This is not a fixed-asset acquisition. |
| `transport_driver` | Operational evidence / job costing | None. | Register the driver's name, telephone, and location. This does not create an employment contract or payroll. |
| `delivery_trip` | Operational evidence / job costing | None; planning only. | Select an active local driver and vehicle, planned departure date, warehouse, and destination. |
| `delivery_load` | Operational evidence / job costing | None; stock was fulfilled/dispatched by the original source. | Select an already posted customer sale or stock dispatch and its exact line quantity. Loading cannot exceed the original source quantity across uncancelled trips. |
| `delivery_depart` | Operational evidence / job costing | None. | Confirm that the loaded trip has departed. A vehicle/driver cannot be active on two trips simultaneously. |
| `delivery_acknowledge` | Operational evidence / job costing | None; this does not receive a warehouse transfer or repeat a sale. | Record the recipient, accepted quantity, disputed quantity, and explanation. Partial acknowledgements are cumulative; each remaining quantity can be acknowledged once. Attach private proof to the trip/acknowledgement document. |
| `delivery_dispute_resolve` | Operational evidence / job costing | None; link/evidence only. | Record reviewed acceptance, or link an actual original-invoice return / original-dispatch discrepancy document. Post any required stock or financial correction through its original workflow first. |
| `delivery_close` | Operational evidence / job costing | None. | Complete a departed trip only after every loaded quantity is acknowledged and every discrepancy resolved. |
| `delivery_cancel` | Operational evidence / job costing | None; cancellation never reverses the source sale/transfer. | Cancel an un-departed planned trip with a reason. Its loading references remain in history and can be reassigned to another trip. |
| `quality_claim` | Operational evidence / job costing | None; opening a claim is not a credit note. | Select the real original invoice and affected product line, measured claimed quantity, issue category, and description. Known sponge block/batch lineage is copied from the sale; pooled adhesive batch identity is not invented. |
| `quality_claim_review` | Operational evidence / job costing | None. | Record inspection findings and choose return, replacement, repair, no financial action, or rejection. An existing inspection can be linked when it matches the actual product/block. |
| `quality_claim_close` | Operational evidence / job costing | None; original-cost stock restoration and customer credit are handled by `sales_return`; replacement stock/GL by its separate sale. | For a return/replacement disposition, first post the normal sales return. For replacement, also post the separately authorized replacement delivery/invoice. Link those same-customer documents and record the closure result. |
| `quality_recall` | Operational evidence / job costing | No write-off or financial posting. Existing physical quantities and carrying values are preserved. | A fully authorized quality supervisor selects one recorded raw-material lot or production batch. The campaign traces recorded descendant blocks and customer invoices. Available blocks are held for inspection; pooled kg/count outputs are conservatively held at whole-product scope. The material lot remains held. |
| `quality_recall_close` | Operational evidence / job costing | None. | Record the reviewed reason for ending the campaign. This releases only campaign restrictions. It does not automatically restore any block's ready status or release a material lot. Perform separate quality/lot release after the appropriate inspection. |
| `job_project` | Operational evidence / job costing | None. | Create the real customer project, job code, administrative location, scope, and promised date. |
| `job_estimate` | Operational evidence / job costing | None; an estimate is not an expense or revenue. | Save a new immutable estimate version with material, labor, overhead, subcontract and other expected costs and expected customer revenue. Old estimates remain unchanged. |
| `job_document` | Operational evidence / job costing | No new journal or stock movement; actual entries remain in the original document. | Associate an actual posted whole document with this project. One document can belong to only one project. Split mixed-project invoices or cost documents in the original workflow before posting. |
| `job_bom_plan` | Operational evidence / job costing | No automatic consumption or output; expected planning only. Disabled for the actual-consumption sponge company. | In a BOM-enabled business, select an approved root BOM and planned output quantity. Approved nested component BOM references are expanded, cycles are rejected, and a versioned expected-requirement snapshot is frozen. |
| `job_subcontract` | Operational evidence / job costing | None; materials sent remain company inventory. | Create a supplier-processing job and explicitly select a company-owned warehouse representing goods physically held by that supplier. |
| `job_subcontract_link` | Operational evidence / job costing | No new stock/value/revenue; the real source workflow already posted them. | Link actual sent transfer, vendor material receipt, costed production with its absorbed supplier processing bill, or finished return receipt. These events verify existing documents instead of posting them again. |
| `job_subcontract_close` | Operational evidence / job costing | None. Leftover company-owned material at the supplier is retained and must be returned/adjusted separately with authorization. | Close only when planned output has actually been produced and all that finished quantity has been received back through real stock transfers. |
| `job_close` | Operational evidence / job costing | None. | Complete the reviewed customer project after open subcontract jobs are completed. Closing is administrative and does not write off unpaid invoices, inventory or WIP. |
| `commission_policy` | Reviewed accounting extension | Approved, dated employee commission percentage; no journal. | Retain source evidence and reason; use assigned permissions and an open accounting period. |
| `commission_accrue` | Reviewed accounting extension | Dr COMMISSION / Cr PAYROLL for earned commission on collected AFN net sales after returns, excluding tax. Existing salary accrual remains separate. Requires payroll approval; settle using payroll_settle. | Retain source evidence and reason; use assigned permissions and an open accounting period. |
| `commission_reverse` | Reviewed accounting extension | Reverse wholly unpaid commission: Dr PAYROLL / Cr COMMISSION. Original earning remains immutable. Paid clawbacks are blocked and need a separately reviewed agreement. | Retain source evidence and reason; use assigned permissions and an open accounting period. |
| `late_cost_bill` | Reviewed accounting extension | Linked supplier expense bill: Dr COST_CLEARING / Cr AP once. Records actual freight/customs/service amount and original receipt references; wrapper creates no duplicate payable. | Retain source evidence and reason; use assigned permissions and an open accounting period. |
| `late_cost_allocate` | Reviewed accounting extension | Review explicit backed cost shares: Dr on-hand inventory / COGS / open WIP; Cr COST_CLEARING. Inventory quantity stays unchanged. Late sold cost is proportionally restored on later physical returns. This is current-period allocation, not historical valuation replay. | Retain source evidence and reason; use assigned permissions and an open accounting period. |
| `late_cost_wip` | Reviewed accounting extension | Internal child of a reviewed allocation: Dr WIP / Cr COST_CLEARING, linked to an unfinished production batch. Consumed by ordinary completion; cannot target an already completed batch or be invoked as an independent unsupported adjustment. | Retain source evidence and reason; use assigned permissions and an open accounting period. |

### Cash custody, statement evidence and supplier sourcing

| Operation | Screen | Accounting effect | Example and control |
|---|---|---|---|
| `money_instrument` | Money / bank and cash instruments | No journal or opening funds | Register an immutable real AFN CASH/BANK instrument. A new instrument starts at zero; fund it through cash_transfer with distinct source/destination instruments. Same-location transfers between different instruments are supported. Legacy location balances remain linked by a controlled bridge; old posted amounts are not rewritten. |
| `cash_drawer` | Operations / Cashier | No journal | Register a drawer linked to one real AFN CASH instrument at this location. Separate tills have separate instruments; activation waits for an exact opening count of its own funds. |
| `cash_shift_open` | Cashier / Open shift | No journal | Count 1,000 AFN against the selected drawer instrument CASH book balance; accept a pending handover if assigned. Opening custody does not create cash. |
| `cash_shift_count` | Cashier / Count | No journal | Expected cash 900; physical count 890; freeze outgoing and incoming cash posting pending review. |
| `cash_shift_recount` | Cashier / Recount | No journal | Preserve the first count and record corrected denomination evidence with a reason. |
| `cash_shift_review` | Cashier / Supervisor review | Shortage: Dr EXPENSE / Cr CASH; overage: Dr CASH / Cr OTHER_INCOME | A reviewed 10 AFN shortage reduces CASH by 10 only when explicitly approved. Zero variance closes without a journal. No employee debt is invented. |
| `cash_handover` | Cashier / Handover | No journal | Offer the reviewed 890 AFN to a named authorized cashier; the next exact opening count accepts custody. |
| `cash_handover_redirect` | Cashier / Reassign handover | No journal | A manager records why a departed receiver is replaced. Original handover evidence remains; an accepted handover cannot be reassigned. |
| `statement_import` | Operations / Statement imports | No journal | Preview and save an AFN CSV/XLSX with explicit column/date mapping. Bank withdrawals are negative; deposits positive. Saraf files are evidence only. |
| `statement_review` | Statement imports / Match | No journal | Match a -200 bank fee to an existing -200 BANK expense entry; reject duplicate matches. Missing fees must first be posted through the ordinary expense workflow. |
| `statement_reconcile` | Statement imports / Finalize | No journal; creates linked bank reconciliation evidence | Opening 1,000, withdrawal 200 and deposit 300 close at 1,100. Every statement row and period BANK entry must match exactly. Select the actual BANK instrument and its institution/account reference. Other instruments at the same location are excluded from this reconciliation. |
| `rfq_create` | Operations / Supplier quotations | No journal or stock | Request exact material quantities and required sponge footprint, without estimating a chemical recipe. |
| `rfq_offer` | Supplier quotations / Add offer | No journal or stock | Record an AFN supplier price, freight estimate, expiry, lead time and payment terms. Freight is comparison evidence, not capitalized inventory. |
| `rfq_award` | Supplier quotations / Award | Creates one real purchase order; no journal or stock | Compare two whole-request offers and record a reason for choosing one. Actual receipt, supplier bill and payment retain their normal accounting steps. |
| `rfq_close` | Supplier quotations / Close | No journal or stock | Close an unawarded request with a reason; preserve offers. An awarded request cannot be closed here; cancel its order remainder through the normal purchase-order workflow. |

The installation/recovery screen only reads verified release, schema, worker and database-bound backup evidence. It cannot apply updates or post financial entries. Local operator scripts require a sealed build, an explicit database target, stopped runtime ports and a completed encrypted snapshot before forward migration. Same-machine recovery is not evidence of off-device recovery.

### Daily work, CRM and reviewed document capture

| Operation | Screen | Accounting effect | Example and control |
|---|---|---|---|
| `crm_create` | CRM / Opportunity | No journal or stock | Record a prospect/customer, scoped salesperson and expected AFN value; no revenue or stock. |
| `crm_transition` | CRM / Stage | No journal or stock | Record a reasoned stage decision; won/lost is commercial evidence, not a sale or cancellation. |
| `crm_assign` | CRM / Assignment | No journal or stock | Record an eligible new salesperson without changing source history. |
| `crm_activity` | CRM / Follow-up | No journal or stock | Assign a dated next action; no message is sent automatically. |
| `crm_activity_done` | CRM / Outcome | No journal or stock | Retain the completed task and its actual outcome. |
| `crm_note` | CRM / Note | No journal or stock | Append a scoped note without editing original evidence. |
| `crm_quote` | CRM / Quotation | No journal or stock | Create one real linked quotation using ordinary quotation rules; no stock, receivable or revenue. |
| `capture_import` | Document capture / Upload | No journal or stock | Locally extract a photo/PDF; retain private original and hash. No financial entries. |
| `capture_review` | Document capture / Human review | No journal or stock | Correct and confirm original fields, then create one ordinary expense or receipt-linked bill draft. Draft alone posts nothing. |
| `capture_reject` | Document capture / Reject | No journal or stock | Keep unreadable/rejected evidence with a reason; no financial posting. |

Reviewed capture posting retains the ordinary expense/bill accounts and permissions. A cash expense120 AFN posts Dr EXPENSE120 / Cr CASH120; an unpaid supplier expense posts Dr EXPENSE120 / Cr AP120. A bill against an existing GRNI receipt posts Dr GRNI / Cr AP, without receiving stock again. Original evidence and duplicate/source checks remain linked.

### Automatic linked valuation entries

An inventory issue can create an `inventory_allowance_release` linked to an earlier write-down: Dr INVENTORY_ALLOWANCE / Cr COGS for the released portion. A supported returned sale can restore its original allowance using a linked valuation record: Dr COGS / Cr INVENTORY_ALLOWANCE. These are internal linked effects, not standalone buttons to use arbitrarily. The original cost pool is retained; gross stock cost less its remaining allowance gives net carrying value. Other transformations with active allowances can be blocked until an approved review/reversal.

### Other screens and options that do not post money by themselves

| Option | What it really does |
|---|---|
| New/edit product, warehouse, location, employee, department, position or contact | Master data. A contract rate is not automatically salary expense; a product price is not revenue; a warehouse is not opening stock. Historical protected fields cannot simply be rewritten. |
| Business creation/switch | Separate customer, inventory, chart and membership boundaries. No automatic consolidation or opening balances. |
| User roles/location/product permissions and posting limits | Decide what can be seen/posted/approved. Hiding a menu is not the server's only security check. |
| Draft | Unposted proposal; no stock or journal until supported final posting succeeds. |
| Approval request/rejection | Review workflow; no fake success. The authorized approval can execute the real action and then create stock/journals. |
| BOM versions | Optional expected components in an enabled business. Actual-consumption mode for this sponge company does not require a secret formula. |
| Dashboard, statements, aging, stock/cash reports and exports | Read already posted records with as-of/scope rules. A report is not a new posting. |
| Employee statement | Separate PAYROLL wages owed and ADVANCES employee debt. Gross earned, actual cash paid, advance recovery and opening/closing balances are not interchangeable. |
| Budgets and cash forecasts | Plans and explicit expectations; not actual expenses or cash. |
| QR label/bin placement/quality inspection/trace lookup | Identity, location, holds and history. No additional valuation/revenue unless a separate actual movement/loss action is posted. |
| Customer portal | Read-only access to that granted business/customer's invoices/payments/balances. No staff membership or direct posting authority. |
| Attachments, print/copy, manual download, calendar and language preference | Supporting evidence/presentation. Calendar conversion does not alter stored transaction dates or financial amounts. |
| Backup/restore/maintenance health | Recovery/operational controls. A backup does not post income and a same-machine restore drill does not prove off-device recovery. The owner deferred the scheduled backup destination. |

### Reviewed operating improvements (November 2026)

| Operation | Purpose | Accounts affected | Example and limits |
|---|---|---|---|
| `closing_open` | Open an exact dated closing checklist | No journal or stock movement. | Review 1-31 October; overlapping or already-closed windows fail. |
| `closing_review` | Assign and attest one closing review | No journal. Evidence links and a financial fingerprint are preserved. | Only the eligible assigned accountant can accept; later financial/stock or current FX changes require another review. |
| `closing_finish` | Finalize eight current reviews and lock the period | Invokes the existing period_close date lock; no closing income journal is invented. | Resolve ledger/stock/FX differences first. An open checklist also blocks direct partial-period locking. |
| `portal_listing` | Publish agreed items for one customer portal account | No journal, stock reservation or price promise. | Publish grade 45 with a 2000 x 1000 mm full face; deactivate access without changing history. |
| `portal_review` | Review a customer request | Accepted requests create the real quotation/sales_order; delivery evidence invokes delivery_confirm. Neither repeats revenue or stock. | Three 22 mm sheets request 6.6 cm; staff checks warehouse and price. Only later delivered sale creates AR/SALES and COGS/inventory. |
| `notice_prepare` | Prepare a consented customer update | No journal or stock movement. | Dari/Pashto/English order, invoice or recorded-delivery template; missing provider blocks external delivery honestly. |
| `notice_status` | Record provider evidence or cancel a queued notice | No journal. Preserve source and operator evidence. | Provider acceptance is not delivery. Staff-confirmed delivery must match the accepted provider reference. |
| `notice_retry` | Authorize a reviewed retry | No journal; reuse the same provider idempotency key. | Requires checked provider status/current consent; cannot retry a notice already accepted or superseded by a queued replacement. |
| `calendar_policy` | Schedule a prospective business earning calendar | No journal; existing ledger dates and payroll snapshots remain intact. | Use an approved future Jalali month boundary; monthly pay uses exact contract days and transition proration. |
| `capacity_schedule` | Reserve an unstarted work order across daily stage capacity | Planning only; no material consumption, wages, finished stock or revenue. | Mixing, curing wait and cutting reserve actual center minutes; delivery estimate still requires material/staff review. |
| `capacity_work_order` | Create and reserve multi-day work | Planning only; actual production retains existing posting flows. | 300 minutes on a 120-minute daily center uses at least three days, excluding additional stage waits. |
| `supplier_claim` | Open a documented supplier discrepancy | No supplier credit, expense or stock is invented. | Record missing or damaged material against a real order/receipt/bill and original product line. |
| `supplier_claim_resolve` | Resolve a claim against evidence | A linked posted purchase_return retains its original inventory/AP or GRNI accounting; resolution does not post it again. | A supplier acknowledgement alone is evidence, not a financial credit. |
| `cycle_count_assign` | Assign a blind physical stock count | No journal or quantity change. | Choose warehouse/items and an authorized counter; quantities are not displayed to the restricted counter. |
| `cycle_count_record` | Record physical observations and freeze evidence | No journal; actual count and protected book snapshot are retained. | Five counted pieces do not automatically change stock. Stale observations must be recounted before adjustment. |
| `cycle_count_review` | Independently review differences | Accept/recount is nonfinancial; approved adjustment invokes existing stock_count_adjust once with its exact inventory/loss journal. | Explain shortages; cannot bypass reviewer, stale-stock, quantity or strict lot controls. |
| `weighing_device` | Register a weighing device | No inventory or accounting posting. | Device identity/warehouse are retained; this is not a verified live hardware integration. |
| `scale_calibrate` | Record dated calibration evidence | No journal; approved calibration dates and evidence are retained. | Later measurements require effective valid calibration and cannot precede device registration. |
| `weight_measure` | Confirm gross, tare and net kilograms | Evidence only: net=gross-tare, no stock receipt. | Gross 12 kg less tare 2 kg is 10 kg inventory quantity only after an actual measured receipt. |
| `measured_receive` | Receive goods once using a confirmed net reading | Invokes existing purchase_receive: Dr inventory / Cr GRNI. The later supplier bill clears GRNI into AP. | A 10 kg net reading receives 10 kg once; tare is excluded, lot controls remain, supplier billing must not receive goods again. |

## 6. Sales, purchases and cash: the common confusions

1. **Sales versus receipt:** selling 5000 and later collecting 5000 produces SALES 5000 once, not 10000. Use the same invoice number for partial payments, including walk-ins.
2. **Receipt versus supplier bill:** physical receipt increases stock/GRNI. Its matched supplier bill moves GRNI to AP. A supplier payment reduces AP. Recording all three as separate “expenses” duplicates cost.
3. **Deposit versus income:** advance customer money is a liability until applied to a delivered sale. Supplier advance money is an asset until allocated to a real payable/credit.
4. **Inventory versus expense:** manufacture converts inventory cost through WIP. Profit recognizes the cost of goods delivered; unsold finished stock remains an asset, subject to approved valuation.
5. **Herat to Kabul:** an internal transfer changes warehouse/transit and possibly management-price balances. A genuine external customer sale is separate. Do not create fake company profit by selling to itself.
6. **Salary versus advance:** salary accrual creates the wage expense/eligible clearing and liability. An advance before earnings is an asset. Recovery reduces that asset against an already accrued liability, without paying the same money twice.
7. **Normal versus abnormal waste:** ordinary conversion losses affect actual output cost; approved abnormal loss is separately expensed. Do not silently destroy saleable سربلوک/کف بلوک identity.
8. **Balance versus period activity:** an employee may have no new salary in July but still be owed June salary. Opening balances carry into the statement; changing the from-date does not erase old debt.

## 7. Using the financial reports

| Report | Answers | Example |
|---|---|---|
| Chart of accounts | Which financial buckets exist and what is their signed balance? | AR debit 5000, AP credit 3000. |
| General ledger | Which posted journal lines produced a balance? | Trace an expense to its document/reference and dimensions. |
| Trial balance | Do total posted debits equal credits? | A zero difference is necessary; it does not prove that every classification is correct. |
| Balance sheet | What is owned/owed at an as-of date? | Unsold FG 22500 is an asset, not remaining profit or cash. |
| P&L | What revenue and recognized cost occurred in the selected period? |5000 sales less 2500 cost =2500 gross profit before other costs. |
| Equity movements | How capital/earnings changed across a period? | Unclosed profit is calculated; date-lock closure is not an automatic profit-transfer journal. |
| Cash flow | How recorded cash/bank changed, with operating/investing/financing/internal/rate-effect classification? | Fixed-asset purchase is investing; currency revaluation is not an ordinary cash receipt. Review unclassified items. |
| Customer/supplier aging | Which invoices remain unpaid at the date? | Customer 5000 less receipts 3500 leaves 1500; later payments do not change an earlier as-of report. |
| Employee statement | Gross earnings, real cash settlement, advance recovery and separate balances? | Gross 25000, deductions 1000, settlement 20000 leaves 4000 wages owed. |
| Inventory reconciliation | Do physical stock carrying values agree to stock-control journals? | RAW+FG+TRIM+TRANSIT costs match the corresponding controls; WIP and valuation allowances are separately explained. |
| Foreign reconciliation | Do wallet/remittance AFN carrying values match FX controls? | Original USD quantity can stay 100 while carrying value changes 7000→7200. |

Shared date inputs now use the selected calendar. Jalali is the default; dates are validated/conveyed to posting/report APIs as canonical Gregorian ISO dates. Accounting month identifiers remain the system's Gregorian month periods; the picker presents their **actual start/end in your selected calendar**, rather than falsely renaming October as a Jalali month. Date selection/display is not a change to payroll proration, fiscal year policy or existing financial records. CSV keeps stable date/amount identifiers for reconciliation.

## 8. Foreign currency: one understandable example

The general ledger is AFN. Suppose an unpaid original invoice is 7000 AFN, contractually USD 100 at 70 AFN perUSD. Register those exact original terms; it does not create another sale. Revalue at closing 72: Dr AR 200 / Cr FX_GAIN 200; receivable carrying value becomes 7200 while debt remainsUSD 100.

ReceiveUSD 40 at 73: cash 2920 AFN, carrying debt released 2880, gain 40. Remaining debtUSD 60 carrying 4320. Receive finalUSD 60 at 71: cash 4260; carrying debt released 4320; loss 60. AR ends 0. Historical aging before those settlements retains the appropriate earlier balance.

Foreign cash/bank wallets also have original currency quantity and AFN carrying value; exchanging or internally remitting funds is different from collecting an external invoice. Current limitations include foreign credits/write-offs/settlement reversals/deposits and integrated foreign-unit-price invoicing. Unsupported corrections are blocked rather than silently falling back to AFN receipts. Obtain approved rates and a designed linked correction when needed.

## 9. Safe correction and daily working sequence

For an error, first identify the posted source document, location, product line, quantities and original amounts. Posted history is immutable. Use a supported return, refund, payment reversal, count adjustment or valuation reversal. A balanced generic journal cannot fix the missing physical/invoice subledger, and controls intentionally reject it. If a whole downstream production/payroll/foreign correction is unsupported, ask for the designed workflow rather than editing database balances.

Daily sequence: verify the selected business/site and calendar; record real receipts; match supplier bills; record actual production use/output; deliver and invoice sales; allocate collections/payments to the correct invoices; record attendance/approved payroll/advance recovery; reconcile cash, bank and stock; review overdue debt, quality holds and transit; review statements before closing dates.

Before closing a period: inspect supplier GRNI/bills, AR/AP aging, wages and advances, WIP/clearing sources, inventory controls/count variances, active allowances, fixed assets/depreciation, applicable tax approvals, foreign rates/open monetary balances and cash-flow classifications. Explain unexpected negative balances. Verify backups and restoration ownership. Period close locks dates; it does not certify your accounts.

## 10. Boundaries: what is not supplied by a chart template

Presence of loan/lease/prepaid/investment/tax/drawings accounts is not an automated loan, lease, owner-cash, tax-remittance, prepaid or investment module. Direct control-account cash journals remain prohibited. Statutory rates, legal entity policy, normal-capacity absorption, final disclosures, OCI/IFRS 18 transition reporting, unrestricted commission clawbacks, automatic multi-level production scheduling and full consolidation are not implied by the template. Selected international accounting concepts inform the implementation; ACCA/IFRS or QuickBooks product certification is not claimed.

## 11. References and implementation source map

- [ACCA: principles and concepts of accounting](https://www.accaglobal.com/middle-east/en/student/exam-support-resources/foundation-level-study-resources/fa2/fa2-technical-articles/a-matter-of-principle.html): introductory duality and debit/credit principles.
- [IFRS Foundation: IAS 2 Inventories](https://www.ifrs.org/issued-standards/list-of-standards/ias-2-inventories/): inventory cost/expense framework. Actual local costing and normal-capacity assumptions require approved business policy.
- [IFRS Foundation: IAS 21](https://www.ifrs.org/issued-standards/list-of-standards/ias-21-the-effects-of-changes-in-foreign-exchange-rates/): foreign monetary translation framework.
- `backend/erp/chart.py`, `seed.py`: default numbers, types and groups; a template, not a mandatory international numbering standard.
- `core.py`: exact decimals, scope, atomic/idempotent execution, balanced journals and stock-control reconciliation.
- `operations.py`, `finance.py`, `corrections.py`: actual stock, purchasing, sales, payroll, corrections and accounting postings.
- `growth.py`, `growth_hooks.py`, `foreign.py`: planning/quality/maintenance/rates/monetary integration.
- `reports.py`, `employee_reports.py`: report/as-of/opening balance calculations.
- `docs/OPERATIONS_AND_CURRENCY.md`, `IMPLEMENTATION_STATUS.md`, `HANDOFF.md`: current delivery limits and operational evidence.

All examples were authored for this application's workflows. These references support underlying concepts; the app's code and verified limitations determine which specific actions you can actually perform.
