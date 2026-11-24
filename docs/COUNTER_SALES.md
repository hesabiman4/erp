# Faster counter sales

Open **Sales → Counter sales** (`/sales/counter`). This is a faster entry workspace for the existing sale operation. It does not introduce a second stock or accounting engine. Sale posting, cash-custody controls, periods, permissions, customer credit and price approval remain authoritative on the server.

## Daily use

1. Choose the selling warehouse and date. Dates use the selected Jalali/Gregorian calendar. Choose an existing customer or enter walk-in contact information.
2. Choose an active saleable product. For sponge, enter exact thickness in mm, whole sheet count and total cutting loss. Suggested configurable shortcuts start at 10/20/22/30/50 mm; an authorized settings manager can change or remove them. These are entry shortcuts, not production formulas.
3. Search a block code and choose the actual full-face piece. Each card shows length, width and **unreserved** height. Held, exhausted, recalled and insufficient pieces are excluded. Unlike footprints are never combined into an interchangeable height balance. Listings are bounded to 50 blocks per page and can be filtered by block code. Existing QR/scanner labels can supply that code. If the business requires inspections, a visible notice states that this physical-stock preview has not certified inspection history. The ordinary sale checks the latest applicable block/ancestor inspection again and rejects an unapproved piece. A card is not an inspection approval or a reservation.
4. Add the reviewed item to the invoice. Several lines from one block include their combined consumption in the local availability check. Inventory is rechecked under the ordinary atomic sale at posting; the screen does not reserve a piece while you type.
5. Review current prices, any customer agreement, tax and the actual money received. A 22 mm sheet is 2.2 cm billable. At 500 AFN per cm, total is 1,100 AFN; receiving 500 leaves 600 receivable. Extra received money follows the existing customer-deposit accounting. Payment does not create another sale.
6. Post once. The normal professional document/print view opens. The next invoice starts with an empty basket; selected customer and warehouse remain convenient for repeat work.

Keyboard shortcuts: **Alt+P** product, **Alt+B** block-code search, **Alt+A** add reviewed item. Tab navigation and visible focus styles remain available on all controls. Posting always requires its explicit button.

## Repeat a previous sale

Search an original authorized posted invoice. The system copies the customer and requested quantities, uses current product prices, clears payments/order links/tax and clears physical block IDs. Each copied item must be reviewed and added again with current stock. The original sale, cash and stock remain unchanged until a separate ordinary new sale successfully posts. Product/location/document restrictions are rechecked. Foreign-priced invoices must use the full foreign-invoice workflow; they are not converted silently to AFN repeats.

The counter supports ordinary AFN products, net kg/count products, services and full-face sponge cuts. Zero-price/free issues, sales-order conversions, foreign invoices and advanced discounts continue through the existing full sales forms. No density/grade-to-mass conversion, automatic virtual joining of remnants or camera hardware connection is introduced. Scanner text lookup accepts a block code, existing block-label URL or the application's original QR JSON. QR business, version, ID and code are checked against the selected business/product/warehouse; a scanned identifier is not authorization. Physical scanner/printer acceptance requires the actual device.

Thickness configuration is a business-scoped locked merge of one settings key with an AuditEvent, requiring `settings.manage`. Other settings, confidential formulas and existing posted documents are preserved. Availability/repeat APIs require sale authority, and repeating also requires original document read authority. Read models return physical quantities and commercial prices, never carrying costs.
