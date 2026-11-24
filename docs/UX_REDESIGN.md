# Interface redesign — 2026-10-29

The owner reported that the working ERP felt unprofessional and difficult to use. The selected direction is **navy navigation, a white workspace, and teal primary actions**. This work changes presentation and task discovery while preserving the PostgreSQL posting services and business boundaries.

## Daily use

- Navigation is grouped into daily work, finance/people, and management. The current section has a strong active state.
- The overview begins with permitted tasks: sell, receive payment, record actual production, and transfer stock. A follow-up panel opens outstanding invoices and physical stock.
- Invoices, orders and quotes have separate views. Purchases, cash and transfers also show one selected ledger instead of stacking unrelated empty tables.
- Less frequent actions are under More actions. Choosing one closes the menu. They still use the existing permission-controlled operations.
- The task guide explains where to sell, produce, inspect stock, collect a remaining balance and send to Kabul. It links directly to those workspaces.
- Invoice search says what it searches. Table rows can open with Enter/Space and restore focus when the document closes.

## Sales

The form has three numbered sections on one page: customer/warehouse, product/quantity, and payment/summary. Sections remain visible so the user can review and correct them without a multi-page wizard.

Walk-in and account customers have explicit selection buttons. Sheet thickness, sheet count and price drive the existing decimal preview. The preview shows billable cm, remaining block height and cutting loss. Optional order, tax and notes are expandable. Cutting loss remains available separately from billable height.

The summary shows subtotal, any chosen tax, total, received amount and outstanding balance. Paid in full and Pay later set the received amount without posting. Posting/draft/approval continue through the existing endpoints and idempotency mechanism. Starting Cut & sell from inventory selects that physical block and its warehouse.

## Responsive and accessible presentation

Text uses a stronger neutral palette; teal identifies primary actions. Location scope remains visible on phones. Interactive invoice tables become labeled cards on narrow screens, exposing amounts and balances without horizontal scrolling. Other report tables retain horizontal scrolling where needed.

Dialogs scroll within the viewport with a persistent title/close control and submit footer. Focus trapping, Escape, keyboard row activation and visible focus states are retained. Reduced-motion preference is respected. These changes are not a claim of a complete WCAG audit or native-user acceptance.

Dari remains primary. New main-workflow copy has English translations and common Pashto translations. Advanced secondary-language coverage still needs native review as recorded in implementation status.

## Verification approach

The additional usability tests read server-backed records and preview operations. Transactional browser journeys use a separate `verify_ui_20261029` PostgreSQL database, API on port 8001 and frontend on port 5174. The user's active database is not used for these transaction tests. Test base URL, credentials path and evidence directory can be configured through `ERP_E2E_BASE_URL`, `ERP_E2E_CREDENTIALS` and `ERP_E2E_OUTPUT`.

See VERIFICATION.md for completed results. Current evidence is stored in `.local/design/e2e`; selected screenshots are saved in `docs/screenshots/redesign-*` after review.

## Accounting workspace refinement — later on 2026-10-29

The owner requested a more professional manufacturing/accounting feel and provided `deepseek_html_20261007_1680ed.html`. The file was inspected as a reference, including its generated pages and browser rendering; its embedded scripts/comments were not instructions for this repository. It remains unchanged in Downloads.

Adopted the useful workflow patterns: dedicated customer/supplier centers, a visible balance overview, account contact details, statements close to open invoices, and a shared transaction menu. Improved them with the real authorization/posting model, cumulative as-of balances, separate deposits, date-bounded AR/AP activity with opening/running/closing balances, payment links and print/export controls. New/edit customer records do not pretend that a free-text opening-balance field posts accounting.

The overview is now a compact accounting workspace. Period buttons change sales, collections, output and profit activity while cash, debt and stock values stay cumulative through today. The seven-day sales chart reads the full scoped journal date range rather than only the latest invoice page. Sales, collections and profit remain separate. Internal branch charges do not enter SALES. No BOM, stock geometry or accounting policy was imported from the draft.

The draft's localStorage database, synthetic stock alerts, kg-based sponge examples, broad roles and simplified ledger calculations were not transplanted. Loans, departments and other draft menu entries were not added as empty features. The sponge business continues to use actual consumption and full-face cm sales. Optional approved BOM mode stays available only where enabled.

The navy sidebar, white workspace and teal actions remain the owner's selected direction. Typography, ledger headers, summary bars and spacing were tightened; phone directories and invoice cards remain usable. A shared New menu uses the existing real forms and permission discovery.

Workflow reference: Intuit describes an actionable sales transaction list and status summary in [View sales transactions](https://quickbooks.intuit.com/learn-support/en-us/help-article/journal-posting/view-sales-transactions/L2Do6c0jS_US_en_US). The design borrows that familiar accounting pattern, not Intuit branding or a claim of QuickBooks compatibility.

Reviewed screenshots: [overview](screenshots/accounting-overview.png), [customer statement](screenshots/accounting-customers.png), [phone center](screenshots/accounting-mobile-center.png), [English supplier center](screenshots/accounting-english-center.png), [Dari statement print](screenshots/accounting-statement-print.png). See VERIFICATION.md for completed checks and limits.
