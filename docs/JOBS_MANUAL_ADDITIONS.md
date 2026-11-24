# Dedicated job costing, nested BOM planning, and subcontract work

The project workspace is intended for custom furniture orders and other dedicated manufacturing jobs. A project lives entirely inside one business workspace. It never combines the furniture business with the sponge company's books.

| Operation | English instruction | رهنمای دری | Ledger / inventory effect |
|---|---|---|---|
| `job_project` | Create the real customer project, job code, administrative location, scope, and promised date. | پروژه واقعی مشتری، کد کار، موقعیت، شرح و تاریخ وعده را ثبت کنید. | None. |
| `job_estimate` | Save a new immutable estimate version with material, labor, overhead, subcontract and other expected costs and expected customer revenue. Old estimates remain unchanged. | نسخه برآورد مواد، مزد، سربار، پیمانکار و سایر بهاها و درآمد مورد انتظار را ثبت کنید؛ برآورد قبلی تغییر نمی‌کند. | None; an estimate is not an expense or revenue. |
| `job_document` | Associate an actual posted whole document with this project. One document can belong to only one project. Split mixed-project invoices or cost documents in the original workflow before posting. | یک سند واقعی ثبت‌شده را به همین پروژه وصل کنید. هر سند کامل فقط به یک پروژه تعلق دارد؛ اسناد مشترک چند کار را نخست جدا ثبت کنید. | No new journal or stock movement; actual entries remain in the original document. |
| `job_bom_plan` | In a BOM-enabled business, select an approved root BOM and planned output quantity. Approved nested component BOM references are expanded, cycles are rejected, and a versioned expected-requirement snapshot is frozen. | در کسب‌وکار با فرمول فعال، نسخه تأییدشده و مقدار خروجی را انتخاب کنید. فرمول قطعات فرعی باز می‌شود، حلقه رد شده و نیازمندی برآوردی به‌صورت ثابت محفوظ می‌ماند. | No automatic consumption or output; expected planning only. Disabled for the actual-consumption sponge company. |
| `job_subcontract` | Create a supplier-processing job and explicitly select a company-owned warehouse representing goods physically held by that supplier. | کار پروسس پیمانکار را ایجاد و انبار ملکی شرکت نزد همان پیمانکار را مشخص کنید. | None; materials sent remain company inventory. |
| `job_subcontract_link` | Link actual sent transfer, vendor material receipt, costed production with its absorbed supplier processing bill, or finished return receipt. These events verify existing documents instead of posting them again. | انتقال واقعی مواد، رسید پیمانکار، تولید واقعی با بل جذب‌شده پروسس یا رسید محصول برگشتی را وصل کنید؛ همان اسناد دوباره ثبت نمی‌شود. | No new stock/value/revenue; the real source workflow already posted them. |
| `job_subcontract_close` | Close only when planned output has actually been produced and all that finished quantity has been received back through real stock transfers. | وقتی مقدار برنامه واقعاً تولید و تمام محصول از طریق رسید واقعی به شرکت برگشت، کار پیمانکار را ختم کنید. | None. Leftover company-owned material at the supplier is retained and must be returned/adjusted separately with authorization. |
| `job_close` | Complete the reviewed customer project after open subcontract jobs are completed. Closing is administrative and does not write off unpaid invoices, inventory or WIP. | پس از ختم کارهای باز پیمانکار و بررسی اسناد، پروژه مشتری را ختم کنید؛ طلب، موجودی و کار در جریان پاک نمی‌شود. | None. |

## Actual project profit

Actual revenue is the net credit to income accounts on uniquely associated source documents. Actual recognized cost is the net debit to expense accounts, including COGS. Project ledger profit is revenue minus recognized cost. The report separately shows WIP, unabsorbed production cost clearing, and actual material-consumption analysis. Material issued into WIP or finished stock is not also counted as an immediate expense. A completed batch's material cost is expensed through COGS when the actual output is sold.

Customer receipts do not add project revenue a second time. Supplier processing cost first enters `COST_CLEARING` from an actual supplier `expense_post` with `production_cost: true`; actual production absorbs that source once. Raw materials are consumed at carrying cost at the owned vendor warehouse. Finished outputs return at carrying cost through the existing transfer dispatch/receive workflow. Internal transfers never become sales.

Revenue, costs and cash are always read in the business's functional currency from existing ledger entries. Project association does not perform currency conversion, replay costing, allocate shared expenses, or create payroll. Dedicated whole-document tagging is the supported allocation policy. Untagged documents are excluded, so a project report is not a claim that the books have been exhaustively allocated.

Financial totals require `accounting.view` and `cost.view`, plus access to every linked document and product line. If even one linked document is outside the user's location/product scope, the full financial panel is withheld rather than displaying misleading partial profit. Payroll-associated totals also require separate payroll access. Estimates require `cost.view`; recipe snapshots require `bom.view` and `consumption.view` in a BOM-enabled business.

## Nested BOM definition

The existing versioned BOM component structure accepts an optional `bom` reference to an approved BOM that produces that exact component product:

```json
{"product": 123, "quantity": "5", "bom": 456}
```

Without `bom`, the component is a purchased/leaf requirement. Expansion uses each version's `output_quantity` as its denominator, preserves exact Decimal calculations, rejects cross-business references and mismatched component products, detects cycles, and caps the graph at 16 levels / 1,000 component nodes. Frozen plans are separate from later BOM versions. This is planning expansion only; actual production continues to record actual consumed quantities independently. Do not enable or expose it for the owner's actual-consumption sponge business.

## Subcontract sequence

1. Configure a dedicated company-owned warehouse for the supplier's physical custody. Keep legal ownership with this business; this is not a sale to the supplier.
2. Post `transfer_dispatch` from company stores and `transfer_receive` into that owned vendor warehouse. Link both actual documents to the subcontract job.
3. Post the supplier processing bill with `expense_post`, `production_cost: true`, `expense_account: COST_CLEARING`, and the actual supplier account.
4. Post one-shot actual production at the vendor warehouse. Consume actual materials from that warehouse; specify actual output; absorb the bill with `conversion_sources`. Existing production checks prevent duplicate cost absorption.
5. Link that real production and its processing bill. Output must match the job product; cumulative produced quantity cannot exceed the job's planned quantity.
6. Transfer finished output from the vendor warehouse back to company stores and acknowledge actual receipt. Link that receipt, then complete the subcontract job.

This initial subcontract job linker supports one-shot actual/BOM-assisted production. Staged WIP remains available through the normal production module but is not presented as a supported subcontract completion link. It does not track outsourced service-provider scheduling, customs, cross-company legal ownership transfers, or automatic subcontract invoice creation. Mixed/shared vendor pools retain moving-average valuation; the job records source document associations and do not pretend to identify individual kg batches. Any remaining material stays company-owned until a separately authorized return or adjustment.

## Permissions and corrections

Use `jobs.view`, `jobs.manage`, and `jobs.plan`, with the financial, payroll, BOM, source-document and warehouse permissions described above. Project estimates and association history are immutable after their source document posts. Existing linked returns/credits must belong to the same original project. A document already assigned to another project is rejected. Corrections use the original accounting/stock workflows; no generic project edit rewrites source ledgers.
