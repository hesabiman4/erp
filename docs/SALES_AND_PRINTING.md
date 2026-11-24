# Linked sales, quotation closure and printed documents

## Using the sales process

The sales document window contains a **Sales progression / جریان فروش** panel immediately below its summary. It shows the current stage, remaining quantities and permitted linked documents. Every next-step action opens a reviewable form; it does not silently post the next transaction.

1. Create a quotation with the customer, warehouse, items, quantities, prices and sponge sheet footprint. A quotation does not recognize revenue, deduct inventory or collect money.
2. Open the quotation and choose **Create order from quotation**. Customer, warehouse, agreed prices and remaining source lines fill automatically. Reduce quantities for a partial order. The server prevents conversion beyond the quotation quantity.
3. Open the sales order and choose **Invoice remaining order**. Remaining quantities and prices fill automatically. For sponge, select the actual physical block and review thickness and sheet count; the application does not invent a physical block allocation from aggregate centimeters. This sale records delivery, revenue, receivables, cost of sales and any immediate payment once.
4. If full payment was received at issue, print the **Cash sales receipt** from that same sale. Do not create a second sale for the receipt. A credit invoice paid later keeps its original invoice identity.
5. Open an unpaid invoice and choose **Receive payment**. Customer, location and outstanding amount fill automatically. Change the amount for a partial receipt. It credits receivables and debits cash/bank; it does not recognize the revenue again. An explicitly recorded excess becomes customer credit. Foreign invoices use the foreign-settlement workflow rather than a second AFN collection.

The source line index and footprint are validated on the server. Two users cannot exceed a commercial source through concurrent posting: posting runs through the existing business lock, `core.execute` and journal/stock services. Copying an authorized source price does not grant permission to enter arbitrary new prices. A source document outside the first page of the list is fetched directly when opened through its next-step action.

## Closing a quotation or order

Use **Close / cancel remainder** and enter a meaningful reason. This is a commercial closure, not a receivable write-off.

- A posted quotation can close before conversion, after partial conversion, after invoicing, or after payment. Further conversions and the outstanding deliveries of its linked orders stop.
- A draft quotation can also be closed. Its proposal data is retained, its status becomes cancelled, and a separate cancellation/audit record is created. It cannot later be posted, edited or converted. Posting and editing share the cancellation lock.
- Already posted invoices, receipts, deliveries, costs and customer balances remain valid. Use the appropriate return, refund or reviewed financial correction if those also need to change.
- New linked work, job cards and additional production consumption are blocked after closure. Already started, costed WIP can complete into inventory, even when its work order has been closed. Completion does not recognize a sale and does not reopen the work order.
- Cancellation is dated and linked to its source. It cannot be backdated before already recorded child fulfillment. Duplicate closure is rejected.
- Existing reservations and independent operational records are not silently reversed. Review any related work, stock reservations and physical commitments using their own controlled workflows.

Progress and links obey business, location, product and document permissions. For legacy cross-location conversions, a reader who cannot see all affected children receives restricted progress instead of hidden quantities. Cancellation details require access to the cancellation document; a permitted reader can still see that the source has been closed.

## Printing and PDF

Use **Print document / Save PDF** for the A4 document or **Small receipt** for the 80 mm layout. The browser print dialog can save either layout as PDF. The shared design includes Dari/English headings, business and contact details, references, document dates in the selected calendar, item quantities, settlement allocations, current balances, notes and signature areas. Multi-page tables repeat their headers and include page numbering. Exact physical printer margins still depend on the device.

Payment receipts show the amount of that receipt and its invoice allocation. Invoice prints show settlement history, including cash collected at sale, and the current balance as of printing. The posted issue snapshot remains immutable. Payroll prints distinguish cash paid from advance recovery. Manufacturing documents use permission-filtered amounts and inputs; printing does not restore hidden costs.

Financial, customer, supplier and employee reports use a common navy/teal paper style. A paginated employee ledger explicitly identifies the displayed portion; use its all-row CSV export when the entire ledger is required. A print preview is not a replacement for reconciliation or accountant review.

## Accounting guide

The Chart of Accounts download is now a PDF. Dari and Pashto interface users receive the Afghan Dari edition; English interface users receive the English edition. The protected endpoint also accepts the fixed language choices `fa-AF` and `en`.

- Dari source: `docs/CHART_OF_ACCOUNTS_BEGINNER_MANUAL_DARI.md`; PDF: `output/pdf/Nawa_Beginner_Accounting_Manual_Dari.pdf`.
- English source: `docs/CHART_OF_ACCOUNTS_BEGINNER_MANUAL.md`; PDF: `output/pdf/Nawa_Beginner_Accounting_Manual.pdf`.
- Both editions describe all 62 default accounts and 96 registered operations, including quotation closure. The sources are maintained separately; rebuild and verify both when accounting behavior changes.
- Rebuild Dari using `node scripts/build_dari_accounting_manual_pdf.mjs` with the repository's Playwright/Edge installation. Rebuild English using the bundled Python runtime and `scripts/build_accounting_manual_pdf.py` as described in the handoff.

The Dari edition uses Afghan terminology, native RTL shaping and an embedded Vazirmatn font. Native Dari editorial and local accountant review remain pending. It is a beginner operating guide, not an assertion of statutory or ACCA certification.
