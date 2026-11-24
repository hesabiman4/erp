# Operational extensions — 2026-10-30

Latest2026-11-02: read `COMPETITIVE_EXPANSION_V2.md` before relying on the historical limits below. Integrated foreign entry, refundable monetary credits/corrections, order-linked cuts, controlled recalls, factory/transport/jobs/commission/late-cost/onboarding and encrypted proposal workflows now have verified implementation. Nonmonetary goods advances, cross-currency settlement, unrestricted offline posting and historical cost replay remain unsupported. The PDF manuals now cover65accounts/133operations.

This is a local pilot implementation, with the existing posting engine and PostgreSQL remaining authoritative. The ten-area roadmap is tracked in COMPETITIVE_ROADMAP.md. A working subset is not a claim that every advanced extension or release review is complete.

## Where to work

The **Operations & planning / عملیات و برنامه‌ریزی** navigation item contains permission-filtered collections, reminders, replenishment, work centers/orders/cards, cutting plans, QR/bin lookup, inspection templates/results, material lots, equipment/maintenance, budgets, cash forecasts, customer prices, supplier performance and runtime status. New granular permissions are discoverable in `/api/schema/` through the existing role editor. Existing employee memberships are not silently granted new authority; the owner can assign the required permissions/location/product scope.

All postings use `core.execute`, and all journals use `core.journal`. The business lock, idempotency keys, period closure, approval limits, stock/control reconciliation and immutable posted records continue to apply. Planning records do not create fictitious sales, inventory or payroll.

## Collections and replenishment

Create a promise against a real unpaid customer invoice, assign an authorized collector, and record outcomes/next dates. Combined open promises cannot exceed current debt. A promise marked kept requires full payment. Promises and manual forecast items are explicitly estimates.

Reminder preparation freezes the recipient, body and authorization. Manual messages are **prepared**; remote messages are queued only after explicit consent/recipient confirmation. `ERP_MESSAGE_PROVIDER_URL` plus `ERP_MESSAGE_PROVIDER_TOKEN` configure an operator-selected HTTPS JSON gateway. The worker checks scope, unpaid/open status and stale body before submitting the same provider idempotency key. Missing configuration blocks delivery; a provider `message_id` means **accepted**, never confirmed delivered. Ambiguous failures need provider review; there is no silent retry or delivery webhook. No real provider was configured or real messages sent during implementation.

Reorder policies are specific to warehouse/product/compatible sponge footprint. They use physical stock less reservations plus unreceived purchase orders and open requests. Safety stock, planned daily usage and lead days are explicit assumptions. Review the suggestion, create a request, then convert it to a real purchase order. The suggestion is not a purchase or a statistical demand forecast.

## Production and cutting

A work center has an assigned location and daily minutes. A work order reserves that day's planned capacity and output target; job cards record actual minutes. Select the work order in the normal production form to link actual posted output. Completion checks real output. This does not require exposing a BOM for the sponge company or create wages from a job card.

The cutting planner accepts measured sheet thickness/count demands for one compatible footprint. It uses best-fit decreasing placement across available physical blocks, including kerf per cut. Review the proposal and reserve it; execution atomically releases its own reservation and cuts the physical sheets through the existing engine. Cancellation releases the reservation. It does not book revenue. It cannot combine remnants into a sheet, promise a mathematical global optimum, or yet allocate its demands back to multiple customer orders.

QR labels carry scoped block identifiers, not authentication tokens. Manual codes and keyboard scanners always work through the same authorized lookup. Camera QR depends on browser BarcodeDetector support, permission and a secure context; unsupported devices receive an explicit fallback. Assign bins, open the actual sale/transfer form from the scanned block, and separately confirm customer delivery without double-posting stock/revenue.

## Quality, lots and maintenance

Versioned inspection criteria support numeric bounds and explicit pass/fail measurements. Link a block or posted production/receipt batch. Inspecting a block places it on hold; release requires its latest inspection to pass when inspections exist or are required. When required inspections are enabled, new produced blocks are held and uninspected blocks cannot be cut/sold; approved parent inspection can follow cut descendants. Receipt/batch inspections record evidence; a failed raw-material inspection does not automatically recall every location's stock. The controlled lot hold/release action requires quality.manage, raw-material visibility, complete location scope and a recorded reason because it affects all warehouses. Automated recall campaigns remain an extension.

Create raw material lots and select incoming lots in purchase receipts. Existing untracked stock must first be assigned, without adding stock or value twice. Strict lot tracking can be enabled only after all existing raw pools reconcile to their lot quantities. Actual production can select a lot or use released, unexpired FIFO lot stock. Transfers preserve recorded lot identities through transit. Expired/held tracked stock cannot be treated as untracked consumption. Use **Lot & product traceability** from the lot row to view movements, direct/staged production outputs, descendant pieces and related authorized customer invoices. API: `/api/growth/traceability/?lot=<id>`; untracked legacy quantities are explicitly outside its claim. Splitting a received quantity across several lots currently requires separate input/receipt lines.

Equipment, planned service dates and maintenance requests track actual downtime. Maintenance completion can issue spare parts from the equipment location, debit repairs and credit inventory at carrying value, then advance the service date. It cannot post the same completion twice. Approved cost capitalization and preventive scheduling optimization are separate policies.

## Budgets, prices and supplier metrics

Budgets are month/account/location/product-line plans. Actual/variance reads the posted ledger. Cash forecasts separately label recorded cash and estimated promises/manual events; they do not assume every payable or salary will be paid on a guessed date. Due collections, expired lots and due equipment appear as exceptions.

Customer prices have non-overlapping effective dates and compatible sponge footprints. A sales user can read and apply an approved customer's effective rates without arbitrary price-override permission. Normal discount/override controls still apply. Supplier performance reads actual receipts, linked order lead times and receipt inspections. On-time statistics require an explicit expected delivery date; an uninspected receipt is not a quality pass.

## AFN-functional foreign monetary workflows

Supported contract currencies are USD and PKR; the general ledger and financial statements remain AFN. Rates always mean **AFN for one unit of foreign currency**. Record an approved immutable rate/reference, or enter a source-referenced rate with `finance.fx_rate` authority. No guessed/live market rates are supplied.

1. Post the real invoice through the normal AFN sale/purchase workflow. Register its foreign contractual total at the original invoice date, while fully unpaid/unadjusted and in an open period. Foreign amount × original rate must exactly match the AFN invoice total. Registration adds no revenue or stock movement. Integrated foreign-unit-price invoicing is not yet supplied; this explicit two-step control is intentional.
2. Use foreign settlement for that invoice. Partial receipts/payments reduce contractual foreign quantity and release proportional AFN carrying value. Realized exchange differences post separately. AFN receipts/deposit allocation and ordinary credits/write-offs cannot bypass a registered foreign subledger.
3. At reporting dates, revalue open invoices, foreign wallets and pending remittances using an approved closing rate. Foreign quantity remains unchanged. Exchange differences post to FX_GAIN/FX_LOSS. Historical aging uses movements only through its as-of date. Events cannot precede an existing monetary movement.
4. Foreign cash/bank wallets record original currency quantity and AFN carrying value. Opening balances require opening authority; exchanges use actual rates, explicit AFN fees, sufficient foreign wallet quantity and weighted carrying-value release. AFN cash/bank controls remain separate from foreign wallet controls.
5. Internal remittances debit FX_TRANSIT at the destination and credit the source wallet; receiving credits that transit control and funds the destination wallet once. Internal transfers create no external revenue. Pending remittances can be revalued. No real saraf network transaction is initiated.

Foreign wallet/control reconciliation is available in Operations and `/api/growth/fx_reconciliation/`; it requires complete business accounting scope. Cash-flow reporting separates exchange effects and fees. Remittances in transit are current assets outside available cash; their recorded exchange adjustment is reflected in the cash-flow bridge upon receipt.

Limits: foreign credits/returns/write-offs and settlement reversals are explicitly blocked pending linked correction design; foreign deposits, cross-currency settlements, hedging, external saraf APIs and automatic closing-rate completeness checks are absent. This is not a full IAS 21 compliance/certification claim. Accountants must approve rates and reporting policies. Basis: [IFRS Foundation IAS 21](https://www.ifrs.org/content/dam/ifrs/publications/pdf-standards/english/2024/issued/part-a/ias-21-the-effects-of-changes-in-foreign-exchange-rates.pdf?bypass=on), particularly monetary retranslation and exchange differences in profit or loss.

## Calendar, printing and customer portal

Jalali is the default, with a per-user Gregorian option. Shared date controls have an Afghan-month popup, Saturday-first day grid, month/year navigation and keyboard access. Choose a day, or enter a Solar Hijri date and leave the field to validate it; no separate confirmation button is required. Server conversion validates leap dates and Persian/Arabic numerals. Staff/portal dates, customer/supplier/report filters, dashboard calendar-month selection, bank rows and print dates follow the selection. Canonical document dates and accounting period keys remain Gregorian; period pickers show actual start/end dates in the selected calendar. This is not a new Jalali payroll/fiscal-boundary policy. CSV retains canonical data dates. Remaining native-language/print-device acceptance is documented.

Runtime status includes print profile configuration: official name/address/phone, payment instructions and document footer. Printing escapes these fields and uses the user's selected calendar for document/earning/print dates. Uploaded logos and a complete native translation/print-device acceptance matrix remain release work.

The customer portal creates a strong-password customer login **without staff membership**. It only lists/prints that granted business/customer's invoices, allocated payments, delivery confirmation and balances. Staff APIs reject it. Revoke a grant in the portal access list. Creating grants requires users.manage, sales.view and full business scope. Credentials are never placed in posting documents or delivered externally by this implementation. The existing staff location permissions continue to govern branch users.

## Stable local runtime and backup deferral

`npm --prefix frontend run build` then `.venv/Scripts/python.exe scripts/serve_local.py --port 8080` serves built frontend and API on one loopback origin through Waitress. The default loopback HTTP mode explicitly disables secure-cookie flags; operator-managed HTTPS/non-loopback deployment requires appropriate host/origin and cookie configuration. It is not public hosting.

`scripts/run_runtime.py` supervises this server and runs a PostgreSQL advisory-lock-protected maintenance tick each minute. It records per-database status, daily reconciliation, authorized outbox processing and configured encrypted backups. The Windows installer `scripts/install_runtime.ps1` previews a current-user logon task; `-Apply` installs it. Installation/automatic startup is not claimed merely from the dry run.

The owner selected **configure backup destination later**. `ERP_BACKUP_DIRECTORY` remains absent, scheduled backup status is **not_configured**, and no off-device recovery is claimed. Private manual encrypted snapshots remain available through `scripts/backup.py`. A backup's success is separate from a restore drill. Keys must remain private and available to the recovery operator. Log rotation, automated recovery drills, monitoring escalation and final deployment ownership remain operational release work.

## Employee statements and chart guidance

Employee register rows open a full statement page, with separate wage-payable and advance balances, historical opening/closing movements, actual cash payments and advance recoveries, date filters, pagination, full CSV export and source-document access. Use the explicit profile-edit action to change authorized personnel data. Chart of accounts provides classification/control guidance and a download of CHART_OF_ACCOUNTS_BEGINNER_MANUAL.md; this manual distinguishes automated operations from template-only accounts and unsupported specialist cash workflows.
