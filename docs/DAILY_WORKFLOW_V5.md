# Daily workflows and evidence release v5

This release covers six authorized areas plus the requested production and document navigation improvements. All amounts and stock still post through the existing domain services.

## Workspaces and guidance

The home page offers task profiles for management, cashiers/sales, warehouse, factory, accounting, sales follow-up and payroll. Choices derive from actual permissions, not the membership's display role. Selecting a profile saves a preference for that user in that business; it grants no authority. Revoked choices fall back. Task queues contain authorized original documents, are bounded/paginated and explicitly are not company totals. Warehouse dispatches and batches are labelled recent records rather than falsely advertised as unfinished work.

Open `/help` for practical lessons in Dari, English and Pashto. Each permitted topic has examples and personal versioned progress saved in PostgreSQL. Contextual help appears beside the corresponding workspace. Lessons distinguish mm/cm, inputs/output, receipts/bills, debt/cash/profit and payroll/advances. Completion is learning progress, not accountant approval or a financial operation. The later localization increment adds all21 Pashto step explanations; native editorial/staff review remains pending. See [LOCALIZATION.md](LOCALIZATION.md).

## Counter sales and commercial follow-up

Open `/sales/counter` from the cashier profile. Select warehouse/product, a measured thickness shortcut and a physical block; review quantities, loss, current price, actual payment and balance. Shortcuts can be configured with settings authority. Repeating a permitted sale copies requested quantities/customer, clears old physical stock and payment and requires reviewing the new selection. Existing ordinary sale posting owns all final concurrency, quality, recall, cash, credit, tax and accounting checks. See [Counter sales](COUNTER_SALES.md).

Open `/operations?view=crm` for opportunities, assigned salesperson, stage history, next actions and outcomes. Expected amounts and won/lost stages do not create revenue, cash or debt. A linked real quotation follows ordinary commercial conversion and cancellation rules. See [CRM](CRM.md).

## Private document capture

Open `/operations?view=capture`. Local OCR reads an image or PDF and preserves the original privately. The reviewer compares the protected preview/original, corrects fields and explicitly confirms before creating one ordinary draft. No supplier, account, tax or uncertain amount is silently guessed into posting. Final posting retains ordinary authority, period and cash checks. Source hashes, normalized supplier references and one-time conversion prevent supported duplicates. Reviewed fields are protected after approval; verify uncertain data before confirming. See [Document capture](DOCUMENT_CAPTURE.md) for actual supported variants, engine setup and limits.

## Production and document navigation

The production screen now starts with an actual process board: material/work entry, measured output, quality review, recorded output. It includes staged batches without requiring a planned work order. States derive from posted consumption/completion and current physical block status. Columns scroll within a bounded height so history does not push entry controls far down the page. Drag to the next column or use the equivalent next-step button; either opens the same reviewed operation. No cosmetic drag changes stock, WIP, quality or journal entries. Some valid operations may move directly to recorded output when goods were already ready; adhesive output is reviewed through its output document. Trimming is an explicit optional operation with actual geometry and by-product costing, not an automatic checkbox on every batch.

Sales, quotations, payments, returns and other original documents open at `/documents/:id?business=:business` in full detail pages. Browser Back, explicit Back, refresh/deep links, related original documents and existing private printing are supported. Action-entry forms remain focused transient dialogs. Switching business prevents rendering a document from a different workspace; source permissions are rechecked on every request. Reviewed capture drafts show their evidence status and retain the ordinary final-post action.

## Performance and acceptance

Operational modules that can be separated load on demand. Some shared form modules remain in the main bundle and Vite still reports the large-chunk warning; no blanket performance claim is made. The document queue has a business/kind/state/id index. Inventory reconciliation groups historical pool movements into one aggregate query, preserving dates, original costs, authorization and complete totals. Measured evidence is in VERIFICATION.md; the synthetic benchmark uses 401 products, 200 real posted sales, 1,000 ordinary drafts, 100 blocks and reconciled books. Local timings are not a concurrent-user or production-scale guarantee.

Use [STAFF_ACCEPTANCE.md](STAFF_ACCEPTANCE.md) with actual staff and devices. Automated journeys and synthetic documents do not substitute for native-language/accountant, representative supplier-file, device or recovery acceptance. No staff approval is prefilled or fabricated.
