# Foreign workflow extension — implementation and manual rows

The functional ledger remains AFN. USD/PKR contracts, refundable deposits and wallets retain separate foreign quantities and AFN carrying values. Every action uses `core.execute` and `core.journal`; records and movements are protected by tenant and posted-history database guards. A quoted rate means AFN per one unit of the stated foreign currency.

## English manual rows

| Action | Actual posting and purpose |
|---|---|
| `fx_sale` | Posts a normal delivered `sale` with foreign-priced lines converted at an approved transaction rate: Dr AR / Cr Sales; Dr COGS / Cr inventory for delivered stock. Creates the linked foreign contractual exposure in the same transaction. It does not create a second sale or a separate registration journal. |
| `fx_purchase` | Receives stock and bills the supplier atomically: receipt Dr inventory / Cr GRNI; bill Dr GRNI / Cr AP. Foreign line costs and contractual quantity are preserved. Stock is received once. |
| `fx_deposit` | Records explicitly **refundable monetary** customer/supplier money. Customer: Dr AFN cash or foreign wallet / Cr `FX_CUSTOMER_DEPOSITS`. Supplier: Dr `FX_SUPPLIER_DEPOSITS` / Cr AFN cash or foreign wallet. Differences between wallet carrying cost and the transaction value use FX gain/loss. |
| `fx_deposit_allocate` | Settles a matching-currency, matching-party invoice with refundable credit; no cash moves. Customer: Dr foreign deposit liability / Cr AR. Supplier: Dr AP / Cr foreign deposit asset. Each side releases its actual proportional AFN carrying amount; the difference is FX gain/loss. Both foreign balances decrease by the same foreign quantity. |
| `fx_refund` | Returns unused monetary credit. Customer: Dr deposit liability / Cr cash/wallet; supplier: Dr cash/wallet / Cr deposit asset. Carrying versus cash differences use FX gain/loss. Refunds cannot exceed remaining foreign credit. |
| `fx_settlement_reverse` | Compensates the latest supported `fx_settle`: opposite original journal, opposite foreign-exposure/wallet movements, and negative historical invoice allocation. Original records stay immutable. It reopens the original foreign quantity and AFN carrying value. |
| `fx_return` | Processes inspected physical returns using the established inventory/lineage/COGS workflow, then replaces the draft AFN debt rows with linked foreign credit movements. Reverses historical revenue/purchase credit at its original carrying basis; releases current AR/AP carrying value, posting the difference to FX gain/loss. A paid/excess return creates a refundable foreign monetary deposit. |
| `fx_credit` | Approved **sales price-only** credit with no physical stock movement. Dr Sales at the original invoice rate / Cr current AR or refundable foreign deposit, plus FX gain/loss for the difference. Retains reason and original invoice. |
| `fx_deposit_revalue` | Remeasures an open refundable monetary deposit to the approved closing rate without changing foreign quantity. Supplier asset increase: Dr deposit / Cr FX gain; customer liability increase: Dr FX loss / Cr deposit. Reductions reverse those directions. |

### Accounts

| Account | Meaning |
|---|---|
| `FX_CUSTOMER_DEPOSITS` | Current liability for refundable foreign monetary customer credits, maintained by foreign-deposit subledger. It is separate from ordinary AFN customer deposits. |
| `FX_SUPPLIER_DEPOSITS` | Current asset for refundable foreign monetary supplier credits, maintained by foreign-deposit subledger. It is separate from ordinary AFN supplier deposits. |

## متن پیشنهادی راهنمای دری

| عملیات | ثبت واقعی و هدف |
|---|---|
| `fx_sale` | بل نهایی فروش و تحویل با قیمت ارزی: بدهکار طلب مشتری / بستانکار فروش؛ برای کالای تحویلی، بدهکار بهای تمام‌شده فروش / بستانکار موجودی. مقدار قراردادی ارز و نرخ اصلی در همان معامله نگهداری می‌شود؛ فروش دوباره ایجاد نمی‌شود. |
| `fx_purchase` | ورود خرید و بل تأمین‌کننده یک‌جا: ورود کالا، بدهکار موجودی / بستانکار کالای دریافت‌شده بدون بل؛ ثبت بل، بدهکار همان حساب واسط / بستانکار بدهی تأمین‌کننده. موجودی فقط یک بار افزایش می‌یابد. |
| `fx_deposit` | ثبت وجه ارزی **قابل استرداد**. مشتری: بدهکار صندوق/بانک یا صندوق ارزی / بستانکار اعتبار ارزی مشتری. تأمین‌کننده: بدهکار اعتبار ارزی تأمین‌کننده / بستانکار صندوق/بانک. تفاوت بهای دفتری صندوق ارزی با نرخ معامله در سود/زیان ارز ثبت می‌شود. |
| `fx_deposit_allocate` | تخصیص اعتبار به بل همان طرف حساب و همان ارز؛ وجه دوباره جابه‌جا نمی‌شود. مشتری: بدهکار اعتبار ارزی مشتری / بستانکار طلب بل. تأمین‌کننده: بدهکار بدهی بل / بستانکار اعتبار ارزی تأمین‌کننده. تفاوت ارزش‌های دفتری در سود/زیان ارز ثبت می‌شود. |
| `fx_refund` | استرداد اعتبار استفاده‌نشده. مشتری: بدهکار اعتبار مشتری / بستانکار صندوق؛ تأمین‌کننده: بدهکار صندوق / بستانکار اعتبار تأمین‌کننده. مقدار استرداد نمی‌تواند از باقی اعتبار ارزی بیشتر باشد. |
| `fx_settlement_reverse` | برگشت آخرین تسویه ارزی اشتباه با سند جبرانی، حرکت معکوس دفتر ارزی و تخصیص منفی به بل. سند اصلی حذف یا تغییر نمی‌کند. مقدار ارز و ارزش دفتری اصلی دوباره باز می‌شود. |
| `fx_return` | برگشت کالای بازرسی‌شده با حفظ ابعاد و رهگیری موجودی و بهای تمام‌شده؛ اعتبار بل به دفتر ارزی وصل می‌شود. تفاوت نرخ اصلی با ارزش دفتری فعلی طلب/بدهی در سود/زیان ارز ثبت می‌شود. برگشت کالای پرداخت‌شده، اعتبار ارزی قابل استرداد ایجاد می‌کند. |
| `fx_credit` | تخفیف اصلاحی فروش بدون برگشت کالا: بدهکار فروش به نرخ اصلی / بستانکار طلب فعلی یا اعتبار قابل استرداد؛ تفاوت در سود/زیان ارز ثبت می‌شود. دلیل تأییدشده و بل اصلی نگهداری می‌شود. |
| `fx_deposit_revalue` | تجدید ارزش اعتبار نقدی قابل استرداد به نرخ پایانی تأییدشده؛ مقدار ارز تغییر نمی‌کند. افزایش طلب از تأمین‌کننده: بدهکار اعتبار / بستانکار سود ارز. افزایش بدهی به مشتری: بدهکار زیان ارز / بستانکار اعتبار. |

`FX_CUSTOMER_DEPOSITS`: بدهی جاری شرکت بابت اعتبار نقدی ارزی قابل استرداد مشتری. `FX_SUPPLIER_DEPOSITS`: دارایی جاری شرکت بابت اعتبار نقدی ارزی قابل استرداد از تأمین‌کننده. هر دو حساب با دفتر فرعی ارزی تطبیق می‌شوند.

## Exact supported boundaries

- Integrated invoices support delivered sales and simultaneous goods receipt/supplier billing. They retain ordinary invoice kinds, source links, physical controls and private printing. Pre-existing orders/receipts, invoice tax and separate landed-cost amounts are rejected by these initial integrated entry forms.
- These are refundable **monetary** deposits and return credits. Nonrefundable advances for goods/services are not treated as monetary deposits. IFRIC 22 generally requires a nonmonetary advance's historical rate to carry into the associated revenue/asset; that different fulfillment workflow is explicitly unsupported. See the [IFRS Foundation explanation of IFRIC 22](https://www.ifrs.org/issued-standards/list-of-standards/ifric-22-foreign-currency-transactions-and-advance-consideration/).
- A foreign settlement cannot overpay an invoice; record any additional refundable credit through its explicit deposit workflow. A deposit cannot cross business, party, currency or customer/supplier side.
- Exact settlement reversal requires the source to remain the latest invoice movement and, when a foreign wallet was used, the latest wallet movement. Later revaluations, allocations, credits or wallet activity block reversal. A customer receipt reversal also checks recorded funds. General unrestricted foreign-event reversal is not advertised.
- Physical foreign returns require integrated foreign line snapshots. Legacy invoice registration still supports settlement and valuation, but it cannot reconstruct missing foreign item prices. Customer price credits support actual sales; supplier price-only corrections require controlled inventory-cost treatment and are rejected here. A price-credited invoice is not eligible for automatic later physical return without reviewed combined price/quantity treatment.
- Foreign monetary quantities use two decimal places; rates use up to eight. AFN line targets sum exactly to the translated foreign document total, and final portions take rounding residuals. Current carrying amounts are released proportionally; full final settlement/refund removes the exact remainder.
- Foreign exposure outstanding balances and historical reporting use the foreign movement ledger, while historical invoice allocations are conserved separately for source traceability. The deposit controls reconcile to current foreign-deposit carrying balances.
- Product-line, location and business scope are enforced on source invoices, wallet/deposit movement history and private option endpoints. The interface does not authorize hidden cross-business references.

## Verification to retain

Regression scenarios cover integrated sales rounding and retry safety, receipt/bill conservation, deposit classification/revaluation/allocation/refund, original settlement reversal and later-movement rejection, physical customer/supplier returns, price credits, immutable monetary records, and scope denial. Record actual PostgreSQL test results in the central implementation-status document; compilation alone is not a passing financial workflow test.
