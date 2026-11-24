# Cutting customer orders and invoicing held sheets

This workflow connects sales-order demand to real sponge blocks and separately identified sheets. It uses the existing `cut_plan`, `cut_execute` and `sale` operations; it does not create revenue when a plan is reserved or executed. The product grade name, such as اسفنج 45 کیلو گرام, remains a commercial name. Quantities are centimeters of full-face height for a compatible length/width footprint.

## Daily workflow

1. Post the customer's sales order with the correct product, quantity in cm, price and sheet footprint. A quotation can first be converted into an order using the sales progression actions.
2. Open **برش برای سفارش مشتری** in Operations. Its demand table shows ordered, delivered, reserved and available-to-plan quantities from the database.
3. Choose **ثبت طرح از سفارش‌ها**. Select a customer order and its item; its warehouse, product and footprint are carried into the plan. Enter the thickness of each sheet in millimeters, the whole-number sheet count and actual/configured loss per cut. The remaining order height does not determine the customer's desired thickness; enter the real cutting request.
4. Add more demand lines when useful. One plan can combine several customers/orders only within the same warehouse, product and compatible footprint. Select **محاسبه و بررسی طرح** to inspect the proposed individual source blocks.
5. Save the plan after reviewing it. This reserves both the physical block height, including cutting loss, and the commercial order quantity. It records neither a sale nor cash. Availability is recalculated while posting, so a preview is not a guarantee of later availability.
6. Select **اجرای برش** on a planned record. Execution releases the plan's parent-block reservation exactly once, performs the physical cuts through the existing cutting service, creates the identified child sheets, and holds each linked sheet for its original order/customer.
7. In **ورق‌های برش‌شده مشتریان**, select ready sheets from one order and choose **ثبت بل ورق‌های انتخاب‌شده**. Review the sheet codes, quantity, original agreed price, date and amount actually received. The server checks the real pieces and creates a normal sales invoice. A partial receipt leaves a balance on that invoice; later receipts settle it without creating another sale.

The earlier general cutting workflow remains available through **بدون سفارش، برش عمومی**. General cuts create free stock sheets without a customer-demand commitment.

## Worked physical and accounting example

Order A requests 4.4 cm of a given sponge product and footprint, to be supplied as two 22 mm sheets. Order B requests 2.2 cm as one 22 mm sheet. With a verified 1 mm cutting loss per sheet, their combined commercial quantity is 6.6 cm, while source blocks must provide 69 mm of physical height.

An available 30 mm remnant can supply one 22 mm sheet plus 1 mm loss; an available 50 mm remnant can supply two. The system never joins the remnants into a fictional larger block.

| Event | Physical result | Accounting result |
|---|---|---|
| Save cutting plan | Reserve 69 mm across identified source blocks and 6.6 cm across the two orders | No journal, revenue, payment or COGS |
| Execute cutting | Parent blocks lose the cut height; three separate 22 mm sheets enter stock; each sheet is reserved for its order | Cutting reclassifies the same inventory carrying value; normal cutting loss is absorbed in the retained sheets under the existing cost policy |
| Invoice one held sheet | That identified sheet leaves inventory; parent-block height is not reduced again | Normal sale: debit receivable, credit sales; debit COGS and credit finished goods for the issued sheet value; record cash/receivable allocation only for money actually received |
| Receive an invoice balance later | No additional stock movement | Debit cash/bank and credit receivable; no repeated sales revenue |

The inventory engine retains its established weighted-average pool valuation and explicit stock/control-account reconciliation. A cutting plan does not introduce a separate per-piece FIFO costing policy.

## Cancellation and release

Closing a quotation or sales order stops further commercial conversion, linked cutting execution and delivery against that source. It preserves posted cuts, invoices and receipts. It does not erase already-created sheets or silently reverse financial documents.

For a planned cutting plan, **آزادسازی رزرو / ورق‌ها** cancels the plan and releases the parent-block height and order-demand reservation. For an already-executed plan, the same action, with a reason, releases unsold held sheets into free inventory. It does not glue them back to the parent block, reverse cutting loss, or change prior invoices. Already-invoiced sheets remain linked to their invoice.

The API can release one customer's remaining held sheets from a multi-order executed plan using `release_order`. The initial workspace release action releases all unsold held sheets in the selected plan. A cancelled customer order can still release its holds; it cannot execute or invoice further demand. Released stock can subsequently be sold through a new authorized sale/order.

## Controls and implementation

- Manufacturing services still enter through `core.execute`; financial posting still uses `core.journal`. The business lock serializes reservation, cutting, release and invoicing.
- `OrderCutDemand` records the order/line, thickness, count and quantity committed by a plan. `OrderCutSheet` records the actual child block and its one-way invoice or release disposition.
- PostgreSQL guards reject cross-business references, changed provenance/dimensions, reopening of completed dispositions, deletion of the cutting history and incompatible sheet/order/product/footprint references.
- A direct order invoice cannot consume quantity already committed to a cutting plan or held sheet. It must invoice the identified sheet or first release the commitment.
- Held sheets must be sold whole, once, with no second cutting loss. One invoice can include several held sheets from one sales order. Different customers/orders require separate invoices.
- Source-order document permissions and warehouse/product scope apply to preview, commands, workspace tables and linked-plan document access. An inventory-only permission does not grant access to private customer order details.
- Creating a plan requires the existing cutting-plan and nested reservation permissions; execution/release requires its existing operation permissions. Invoice and credit/price/payment authority remain enforced by the sales engine.

Main code: `backend/erp/order_cutting.py`, `cut_models.py`, migration `0014_order_cutting.py`, the existing growth cutting handlers and sales fulfillment handler, and `frontend/src/order-cutting.tsx`.

## Explicit limits

The allocation algorithm is best-fit decreasing, verified against individual compatible physical blocks. It is a heuristic, not a proof of globally optimal waste or production scheduling. A plan uses one warehouse/product/footprint, up to 1,000 physical sheets. It does not perform partial-width/partial-length nesting, mix incompatible cm, or infer formulas from production inputs. The first workspace has not been benchmarked against a large historical order/sheet ledger. Native-language and real-device acceptance remain separate review work.

Focused PostgreSQL tests cover multi-customer plans, no duplicate demand/fulfillment, cancellation/release, wrong customer/partial piece rejection, scope/isolation, database history guards, parent-versus-child height behavior and concurrent planners. Consult the latest verification document for actual executed results; the existence of a test file is not a pass claim.
