# Master prompt: Build an Afghanistan-focused manufacturing ERP

Copy this entire document into an AI coding agent with access to the intended project repository. It is a self-contained implementation brief. The text below authorizes local implementation, not public deployment or use of real production data.

---

You are my senior software engineer, ERP architect, manufacturing accountant, security engineer, QA engineer, and professional UI/UX designer. Build the application specified in this document as working software in the current repository.

Make sensible implementation decisions and document them. Implement, run, verify, and correct the application. Deliver real database-backed workflows rather than a proposal, static prototype, or dashboard populated with hardcoded arrays. Follow your platform instructions, tool permissions, and applicable repository instructions.

## 1. Outcome, authority, and execution contract

Build a maintainable manufacturing ERP for an Afghan sponge and adhesive company, with isolated additional businesses and configurable manufacturing for future customers.

The intended result includes persistent PostgreSQL data, authentication, granular permissions, purchasing, manufacturing, block cutting, inventory, sales and collections, branch transfers, payroll and advances, integrated accounting, reports, localized UI, printing, tests, and operating documentation.

Scope boundary: every core workflow explicitly required below, including both actual-consumption and optional-per-business BOM-assisted manufacturing, is mandatory to implement. BOM-assisted manufacturing is disabled for this sponge company, not omitted from the product. Extensions that may remain unavailable with clear validation and documented limitations are partial-footprint cutting, Jalali input/display, multi-currency settlement/revaluation, historical cost replay/late-cost adjustment, unrestricted offline finalization, and full intercompany consolidation. These exceptions do not permit omitting core accounting, payroll, reports, business isolation, or the main local-language workflows.

Local source changes, dependency installation, migrations against an explicitly local development database, synthetic demo data, and local verification are authorized. Do not buy services, publish publicly, send messages to others, overwrite real business data, or deploy to production without separate authorization. Never run destructive resets against an unidentified database.

First inspect the repository, applicable AGENTS.md files, existing work, and available runtimes. Preserve useful existing architecture and uncommitted work. If the repository is empty, use the default architecture below. Do not spend the whole task comparing frameworks.

Make routine choices without requesting approval after every step. Record nonblocking unknowns in docs/DECISIONS.md and continue with explicit conservative defaults. Ask a concise question only when missing information prevents safe progress. Missing real tax rates, actual formulas, production credentials, and real customer records must not prevent a functional local build with clearly marked demo/configurable values.

Work in complete, verifiable increments across database, domain logic, API, UI, and tests. Continue through the specified core scope; finishing one milestone is not completion of the whole project. If execution limits prevent finishing, preserve a runnable state, update the handoff files, and state exactly what remains. Never claim a module or test is complete without evidence.

Use independent subagents for suitable review or implementation work when available, with clear file ownership and integration review. Delegate accounting and security review as useful, while keeping one coherent design.

## 2. Business context and non-negotiable interpretation

The main company manufactures and sells sponge and adhesive. It has three locations:

- Factory: receives materials and manufactures sponge; manufacturing capability can be enabled at any authorized location.
- Herat main office: دفتر مرکزی هرات; warehouse, sales, collections, and administration.
- Kabul branch: نماینده گی کابل; its own warehouse, sales, collections, and assigned staff, inside the same business.

Sponge and Adhesive are product lines within this company. They are not separate legal companies merely because their profit is reported separately.

The owner also has a furniture business named مبلمان شهر. Give it a completely isolated business workspace: its own customers, suppliers, products, stock, accounts, expenses, employees/payroll records, documents, numbering, settings, and user memberships. Shared login identities are permitted; business access must always be explicitly granted.

Software workspaces do not determine legal entity status. Support mapping businesses to a legal reporting entity. Default demo workspaces may be separately mapped and clearly labeled. If multiple workspaces belong to one registered entity, legal reporting requires accountant-approved aggregation. Do not silently mix the operational books. Full multi-entity statutory consolidation is an extension, not something to claim without implementing.

Sponge product names include:

- اسفنج 45 کیلو گرام
- اسفنج 40 کیلو گرام
- اسفنج 35 کیلو گرام
- اسفنج 30 کیلو گرام
- اسفنج 25 کیلو گرام
- اسفنج 21 کیلو گرام
- اسفنج 13 کیلو گرام

CRITICAL: 45, 40, 35, etc. are business product labels/grades in this specification. Never interpret the label as actual block mass, a density measurement, or a weight-based sales quantity. Optional measured weight is a different field.

Sponge is sold by centimeters of thickness taken from the full face of a block, for a stated sheet footprint. Adhesive is sold by net kilogram. Support full and partial payments for permanent and walk-in customers.

Raw material names to seed, without guessing formulas or treating aliases as verified chemical equivalents:

مواد چسپ، رنگ / پودر، مواد پولیو %45، تی دی آی، پولیو، گاز، میتو کلو راید / پودر، دابکو، کاسموس، سلیکون.

Store clear internal item codes and editable original names/aliases. Confirm units through configuration; demo units are examples, not claims about real material packaging.

## 3. Default technical architecture

For a greenfield build, use a modular monolith:

- Backend: Python, a currently supported Django LTS release, Django REST Framework, Psycopg 3.
- Database: a supported PostgreSQL release compatible with the chosen Django version.
- Frontend: React, TypeScript, Vite, React Router, TanStack Query, i18next, and accessible reusable UI components.
- Styling: a consistent token-based design system with logical CSS properties and real RTL support. Tailwind is acceptable.
- Authentication: same-origin server sessions, HttpOnly cookies, CSRF protection, secure production cookie settings. Do not store bearer credentials in browser localStorage.
- Calculations: Python Decimal and PostgreSQL NUMERIC; decimal strings in APIs; a decimal library for necessary frontend previews. The server is authoritative.
- Tests: pytest/pytest-django and PostgreSQL integration tests; Playwright for essential browser journeys.
- Local development: Docker Compose for database, API, and frontend/reverse proxy as appropriate; provide Windows-friendly instructions. Document native development steps if supported and distinguish verified from unverified steps.
- Printing: reliable HTML print views and/or a maintained PDF renderer with verified Dari shaping and RTL. Include an embedded/open-license font where needed.

Verify current official compatibility and pin exact compatible dependency versions and lockfiles. Do not blindly install mutually incompatible latest releases. Preserve a suitable existing stack instead of rewriting merely to match this default; document any adaptation that preserves the required invariants.

Avoid unnecessary microservices, Redis, queues, external SaaS, paid APIs, or AI features. Add infrastructure only for an implemented requirement. Use PostgreSQL, not SQLite, for transactional, locking, authorization integration, and accounting acceptance tests.

Use explicit domain services for posting. Keep accounting, cost calculations, and stock mutations out of React components and scattered model signals. Generate API documentation and consistent validation/error responses.

## 4. Business isolation and access control

Model organization/owner identity, legal entity mapping, business workspace, location, warehouse, and product line separately.

All business-owned records require an explicit business identifier. Validate every referenced customer, supplier, product, employee, warehouse, account, document, and attachment against that business. Cross-business references must fail even if the same user happens to have memberships in both businesses.

Use database constraints and business-safe composite references where practical, scoped query services, and server authorization. PostgreSQL row-level security may provide additional defense if implemented correctly; account for owner/superuser bypass and connection pooling. Do not claim isolation based only on hiding menu items.

Effective permission is the intersection of:

- Active business membership.
- Assigned location/warehouse scope.
- Product-line scope, where enabled.
- Module and action permission.
- Sensitive-field permission.
- Approval/value limits.

Provide configurable role templates: owner, business administrator, accountant, sales clerk, cashier, purchasing officer, storekeeper, production recorder/supervisor, branch manager, payroll officer, and read-only auditor. Small teams may combine roles.

Separate actions: view, create draft, edit draft, submit, approve, post, reverse, print, export, refund, discount, credit sale, adjust stock, backdate, manage users, close/reopen periods, and change settings.

Protect cost, margin, payroll, bank/cash details, production consumption, formulas, and sensitive customer information independently. An administrator does not automatically receive every financial permission. Do not serialize forbidden fields and hope the frontend hides them.

Apply access restrictions to list/detail endpoints, search, dashboards, reports, autocomplete, attachments, direct download links, imports, exports, background work, and cached results. Avoid leaking unauthorized business names or totals. Only show stock from another location when the user has a separate permitted availability view.

For invoices and other documents containing several product lines, default to denying the whole document unless the user is authorized for every line or has an explicit broader financial-document permission. Never hide some lines but expose the full totals, payments, or print view in a way that leaks forbidden data or produces a misleading financial document.

The active business and location must remain visible. Log membership and permission changes. Users cannot approve their own restricted transaction where separation of duties is configured; provide owner-review reports for small teams.

## 5. Product, unit, and precision model

Support raw materials, finished goods, semi-finished goods, saleable by-products, recoverable scrap, services, and noninventory expenses.

Implement measurement profiles for count, net weight, and dimensioned block/sheet thickness. Structure units so length, area, volume, and other manufacturer profiles can be added without changing the accounting engine. Only advertise profiles whose workflows are actually implemented.

Initial exact precision defaults:

- Canonical geometry: millimeters, NUMERIC(18,3).
- Kilogram quantities: NUMERIC(18,6).
- Costs, rates, exchange rates, and intermediate allocation calculations: sufficient exact decimal precision, generally at least 6 to 8 decimal places.
- Posted currency amounts: currency-specific precision; AFN demo totals use two decimals.

Use an explicit rounding policy, documented and tested. Retain precision through calculations and round at defined line/document/posting boundaries. Balance any unavoidable allocation residual explicitly. No floating-point accumulation for money or authoritative stock.

Store conversions with dimensions. Fixed mm/cm conversion is universal; liters/kg and drums/kg require verified item-specific configuration or actual measurement. Never convert material input kg directly into sponge output cm without a defined physical model; output count/geometry are independently measured.

Prices are per business, product/grade, compatible size profile, unit, and optionally customer price list. Freeze price, discount, tax, currency, and exchange-rate snapshots on posted documents.

## 6. Physical sponge block and cutting model

Track every physical block or independently saleable piece with:

- Unique ID and printable barcode/QR or scanner-friendly label.
- Business, product grade, batch, current location/warehouse, and parent/child lineage.
- Actual length, width, original measured height, saleable starting height, remaining height, and reserved quantity.
- Compatible footprint/size profile with documented tolerances; retain actual dimensions.
- Status: in production, curing, inspection/hold, ready, reserved/partially allocated, in transit, exhausted, or damaged as applicable.
- Stock-movement references and costing references.

Never assume every new block is exactly 2 m long, 1 m wide, and 1 m high. Those are common final dimensions, not guaranteed production output.

For full-face sheet cutting:

billable_cm = sheet_count × thickness_mm / 10

physical_height_consumed_mm = sheet_count × thickness_mm + actual/configured cutting_loss_mm

The cutting-loss policy must specify per cut or per operation and be visible. Use zero by default in the demo until a real allowance is configured. Bill delivered thickness; record additional loss separately unless an explicit commercial rule says otherwise.

Example: one 22 mm sheet from a 1,000 mm saleable block, zero loss, leaves 978 mm = 97.8 cm. Three 22 mm sheets consume 66 mm = 6.6 sale cm. A 50 mm order is 5 cm, never 50 cm.

Calculate suitable availability from individual pieces, not only aggregate height. Ten 10 cm remnants cannot fulfill one 22 cm thick sheet. Whole-sheet quantities need a feasible allocation across identified blocks. Never join remnants virtually.

Aggregate height only within the same grade and compatible footprint. A 2 m × 1 m block and a 1 m × 1 m block must not appear as interchangeable cm. Any area-equivalent analytical view must be separately named and defined.

Initial required cutting operation: full-face thickness cuts. If partial-width/partial-length cutting is implemented, create dimensioned child pieces with validated physical conservation. Otherwise explicitly reject that unsupported operation; never silently handle it as a height-only cut.

Reserve and cut under row locks or an equivalently proven concurrency design. Revalidate business, location, status, reservations, stock, and geometry at posting time. Prohibit negative available height.

A cut may be delivered immediately or become a separately identifiable sheet held for collection. Reservation, cutting, delivery, invoice, and payment are linked but distinct events. Prevent double deduction when a cut sheet is later delivered/invoiced.

A returned sheet becomes a separate inspected piece with its actual dimensions. Never add its thickness back to the original parent block. Preserve traceability through transfers, returns, rework, and write-offs.

## 7. Actual-consumption production and optional BOM

Manufacturing mode is a business setting. Seed the main sponge company with ACTUAL_CONSUMPTION and no required BOM.

An actual production batch contains date, location, product/grade or output lines, actual material consumption lines, production staff/cost references, eligible overhead, finished quantities, measured blocks or adhesive kg, by-products, recoverable material, documented losses, approvals, and status history.

The owner must be able to enter: Today we produced 10 grade-45 blocks and actually consumed 100 kg TDI, 100 kg Kasmos, and the other materials used. These numbers are user examples, not a recipe to hardcode. No percentages, expected ingredients, saved formula, or hidden compulsory BOM may be required.

Separate material issue to a production-floor warehouse from actual consumption into a batch. Support returns of unused material and stock still present on the production floor. Cost only consumed quantities. Return previously consumed material through a linked WIP return when appropriate; do not confuse that with returning unconsumed issued stock.

Support work in progress, staged completion, quality holds, and multiple outputs. Prefer grade-specific batches. Mixed-grade batches require attributable input costs or an explicit approved allocation method and an estimated-cost label where appropriate. Never invent exact grade costs from undivided daily totals.

The underlying model must also include BOMs, approved versions, component quantities/units, effective dates, and work-order references. Implement an optional BOM-assisted flow for a separate demo manufacturing business or an isolated test business: selecting a version creates expected requirements; actual consumption remains separately recorded; changes do not rewrite older batches. Keep it disabled and hidden for the real sponge company configuration. A company can enable BOM mode without changing other businesses.

No-BOM is not a promise of formula secrecy. Anyone who sees detailed inputs and outputs can infer approximate ratios. Enforce separate permissions on material quantities, cost reports, exports, and BOMs. Sales-only roles see finished quantities, not confidential input detail.

## 8. Trimming, by-products, waste, and adhesive

Represent formation/curing, inspection, trimming, and saleability as explicit linked stages. A trim operation can produce a main saleable block, سربلوک, کف بلوک, reusable offcuts, and irreversible waste.

Create grade-specific top-trim items and grade-specific bottom trim where configured. Let the business select their commercial stock units: piece, kg, bag, etc. Never assume all trim sells in cm. Retain dimension data where measured.

Trim creation must deduct/convert the parent once. Selling the trim later reduces trim stock only. Separate normal process loss, cutting loss, abnormal damage, recoverable scraps, and rework. Require reasons and approval based on configured thresholds.

When geometry is comparable, reconcile it. For example, a 1,060 mm block may become a 1,000 mm main block, 30 mm top, 20 mm bottom, and 10 mm documented loss. Side trimming requires its own geometry or appropriately measured loss, not a fictitious height subtraction.

Adhesive uses the same actual-input batch engine but produces net kg. Track container count, gross weight, tare, and net quantity separately when relevant. A container's tare never becomes adhesive inventory. Support fractional kg sales and unused/recovered material.

## 9. Purchasing and stock operations

Implement purchase orders, goods receipts, supplier bills, purchase returns/credits, supplier payments, supplier deposits, and payable aging. Simple immediate purchases can combine steps through one clear UI action while preserving separate event records.

Capture supplier, invoice/reference number, dates, material/item, quantity/unit, price, currency, receiving warehouse, payment terms, attachments, and landed-cost components such as eligible transport/import costs. Prevent duplicate supplier bills using sensible scoped checks with an approved override process.

Separate physical receipt from financial billing. If received before billed, use a controlled received-not-invoiced clearing workflow. Receipt plus later bill must not double-count stock or liability. Landed-cost allocation must use a stated basis and reconcile.

Support warehouse receipts/issues, production-floor movements, reservations, stock counts, approved adjustments, damaged/quarantine stock, dispatches, returns, and audit history.

Stock balances derive from posted movement records. Mutable cached balances, if used, must reconcile to the ledger. Drafts never affect official balances. Availability excludes reservations, held goods, and stock in transit.

Opening stock must carry quantity, measured block/piece dimensions, cost, location, and source references through an audited opening process. Opening inventory accounting and stock initialization must not duplicate one another.

## 10. Herat/Factory/Kabul transfers and internal branch sales

Implement these clearly separated types:

1. STOCK_TRANSFER: physical stock moves at carrying cost; no company sales, customer receivable, COGS, or internal inventory profit.
2. INTERNAL_BRANCH_CHARGE: the same carrying-cost stock movement plus an explicitly managerial transfer price and branch settlement record.

The second option meets the owner's need to treat Kabul as buying from Herat internally. Implement internal charges in a separate management subledger, not as ordinary customer invoices with an optional report filter. They must never inflate company external revenue, statutory profit, customer debt, or inventory value.

Provide internal charge statements, outstanding internal amounts, adjustments, and settlement links. When branches physically move cash, use a same-company cash transfer at actual amount and link it to management settlement as appropriate; do not create income or expense simply because cash moved.

For example, transfer stock with carrying cost 10,000 AFN and internal price 12,000 AFN. Company inventory remains 10,000; company sales/profit remain unchanged. Management reports can show the 12,000 charge and its settlement separately.

Transfer lifecycle: draft, submitted/approved as configured, dispatched, in transit, partially received, received, discrepancy resolution, or returned/cancelled where valid. Source stock leaves at dispatch; destination becomes available only on confirmed receipt. Never make stock simultaneously available in both places.

Support partial receipt, shortages, damage, and sender/receiver acknowledgment. Preserve block identity or explicit child-piece lineage, grade, dimensions, remaining height, and carrying-cost references. A partially consumed block must not become a fresh full block when transferred.

A transfer does affect stock and movement reports even though it does not affect external sales. Use source/transit/destination inventory dimensions or accounts that reconcile.

A genuinely separate customer/legal entity requires an external/intercompany sale-purchase workflow, not the internal-transfer endpoint. Cross-business transfer must be rejected unless a separately implemented explicit intercompany workflow handles it. If full intercompany consolidation is deferred, document that accurately and prevent misuse.

## 11. Sales, customers, invoice debt, and collections

Implement quotations/orders where useful, stock reservation, cut/fulfillment, delivery, invoicing, immediate payments, later receipts, customer statements, deposits, credit notes, returns, refunds, write-offs, and overdue aging.

Both permanent and walk-in customers may buy on credit. Permanent customers have a consolidated account. A walk-in credit invoice has a lightweight invoice-linked debtor/reference with name/phone/address/notes as available. Do not pool unidentified unpaid walk-in bills into an inseparable balance.

The walk-in sale screen must allow contact notes without forcing a full customer-registration process. Configure a warning or approval when a credit sale lacks useful contact information.

Invoice totals, paid amount, allocated credits, and outstanding balance must be visible. Search by invoice number, customer name, phone, and notes within authorized scope.

One invoice can receive many payments. One payment can be allocated to many invoices of the same authorized debtor/business. Prevent over-allocation, cross-business allocation, unauthorized cross-customer allocation, and currency mismatches without a supported conversion rule. Preserve allocations and reversals.

Customer overpayments and pre-delivery deposits are liabilities/customer credit, not additional sales. An overpayment is not a negative invoice balance silently discarded. Collection on a prior invoice never creates another sale.

The owner's exact example must work: 5,000 AFN invoice, 3,500 received, 1,500 outstanding; later collect 1,500 on the original invoice and print a new payment receipt. The invoice number and original sale remain intact.

Recognize revenue with the configured delivery/control-transfer event for the supported sale terms, not blindly on cash receipt or creation of a pro forma invoice. Keep delivery and financial recognition mapping explicit and tested.

Initial recognition policy: an ordinary immediate counter sale posts fulfillment, the sales invoice, stock/COGS, and any immediate receipt as one atomic business operation. Before delivery, use an order/pro forma and treat collected money as a customer deposit. A later invoice printout or receipt must not repeat revenue or inventory postings. If separate fulfillment and invoicing are supported, define one authoritative recognition event and the necessary unbilled/deferred clearing entries, with tests; do not leave the timing ambiguous.

Reservation or cutting alone does not recognize sales revenue. Support partial fulfillment by finally invoicing only confirmed delivered quantities, keeping the undelivered order balance open. Reject unsupported recognition arrangements explicitly.

For mixed Sponge/Adhesive invoices, classify sales and COGS per line. Keep one customer account. Management allocation of partial collections by product line must use a documented rule, not guessed totals.

Returns require inspection and stock disposition, a linked credit note where appropriate, and a separately authorized refund or customer credit. Prevent refunding or reversing the same amount twice. A reprinted document retains its original number and displays copy status.

Restore a returned identifiable item at its original issued cost with the corresponding COGS reversal and applicable valuation adjustment. Selling price or refund amount is not the returned item's inventory cost; impairment is assessed separately.

## 12. Employees, attendance, wages, advances, and projects

Support monthly full-time salary, part-time terms, daily wages based on approved attendance, and project/milestone-based earnings based on accepted work. Employment/contractor classification is configurable and subject to local professional validation.

Maintain separate earnings, liabilities, advances, expense reimbursements, loans where enabled, deductions, and cash payments. A worker receiving cash is not automatically an expense transaction.

An employee statement shows opening advance/debt, advances taken, salary/wages earned, approved deductions, advance recovery, net payable, actual payment, and closing balances.

Apply authorized recovery terms to available net payable after applicable deductions. Do not force recovery above the permitted amount. Excess advances remain an employee receivable; never pay a negative salary or silently erase the balance.

Example excluding taxes: earn 20,000 AFN, withdraw 25,000 AFN, settle an approved 20,000 against salary, and carry forward a 5,000 employee advance asset.

Provide attendance, daily rate changes with effective dates, project approval, salary changes with history, advance limits, approvals above limits, payroll runs, payslips, settlement, and reversals.

Distinguish a personal advance from money entrusted for company purchases. The latter needs expense clearing and return of unused cash.

Assign labor to product lines/batches where supported. Payroll and production absorption must use a clearing or directly attributable posting design so one salary is not counted twice. Administrative wages are operating costs; eligible production labor may be capitalized through WIP.

## 13. Accounting and costing contract

Implement a real double-entry general ledger. Every posted journal balances by business in base currency. Enforce this in a central posting service and with appropriate database protections; application screens alone are insufficient.

Provide configurable chart of accounts with asset, liability, equity, income, cost, and expense categories. Seed a sensible demo chart covering cash/bank, receivables, deposits, supplier payables, received-not-invoiced, raw materials, WIP, main finished goods, adhesive, trims, inventory in transit, employee advances, salary payable, cost clearing, production overhead, COGS, abnormal waste, sales, operating expenses, fixed assets, accumulated depreciation, tax accounts, equity, and drawings.

Every journal and stock/value movement needs source-event/document references, business, effective/posting timestamps, applicable dimensions, actor, and reversal links. Restrict direct manual entries into controlled subledger accounts except audited opening/adjustment mechanisms that preserve reconciliation.

Core event mappings, excluding tax:

- Purchase received and billed on credit: Dr raw inventory; Cr supplier payable. If receipt precedes bill, use the explicit clearing workflow.
- Actual material consumption: Dr WIP; Cr raw inventory.
- Eligible labor/overhead: Dr WIP; Cr relevant payable or cost clearing. Never double-count payroll or overhead already posted elsewhere.
- Production completion: Dr main finished inventory and by-product inventory; Cr WIP, with approved loss expense and allocation as applicable.
- Delivered credit sale: Dr receivable; Cr sales, and Dr COGS; Cr finished inventory.
- Customer collection: Dr cash/bank; Cr receivable, or customer deposit until allocated/earned as appropriate.
- Employee advance: Dr employee advance asset; Cr cash/bank.
- Administrative payroll accrual: Dr salary expense; Cr salary payable.
- Approved advance recovery: Dr salary payable; Cr employee advances.
- Cash payout of net salary: Dr salary payable; Cr cash/bank.
- Same-company stock dispatch: Dr inventory in transit; Cr source inventory, or equivalent location-dimension movement.
- Transfer receipt: Dr destination inventory; Cr inventory in transit.
- Owner withdrawal: equity/drawings treatment, not an ordinary operating expense.

Initial cost policy: moving weighted average for ordinarily interchangeable raw-material and standardized finished-product pools, consistent within similar categories. Use an explicit pool key of business, product, compatible valuation/footprint profile, and warehouse; apply the same cost formula everywhere. Each receipt combines opening quantity/value with its actual incoming quantity/value; each issue removes quantity at that pool's current average with controlled rounding. Transfer dispatch freezes the source carrying value, transit preserves that value, and destination receipt incorporates it into the destination pool without a markup. Lock affected pools safely and reconcile the sum of warehouse/transit values to the company ledger. Different resulting warehouse averages are not permission to select different cost formulas arbitrarily. Retain actual batch production analysis independently of financial cost flow. Do not use block selection to manipulate profit. Specific project costs may be appropriate for genuinely noninterchangeable custom jobs when implemented.

Choose a deterministic, documented inventory-value posting order. Prevent unsupported historical re-costing: reject stock-value backdating before later affected cost events unless a controlled replay/revaluation process is implemented and tested. Separate recorded event time from effective document date. Never silently recalculate closed history after changing a supplier price, recipe, wage rate, or overhead setting.

Production cost includes actual consumed input carrying cost, eligible direct labor, and systematic production overhead. Allocate fixed overhead based on normal capacity. Exclude abnormal loss and unrelated selling/administrative costs from stock. Normal process loss affects good-output cost under the approved policy.

Joint products require rational consistent cost allocation. Immaterial by-products may use estimated net realizable value deducted from main-product cost; material trim must use an approved allocation basis. Record the selected method, assumptions, and approval. Sum of output carrying values plus relevant expense/loss equals batch cost. Do not assign full batch cost to main output and then create extra trim value.

Cost per sponge cm is calculated for a specified grade and footprint. Volume/area may be an allocation driver when rational, but selling remains by cm of thickness. Mixed grades need separate costs or transparent allocation, not a universal density-based conversion.

Implement controlled cost finalization and close. Distinguish approved estimates from final costs. If allowing late costs after output has been sold, implement an auditable policy-consistent adjustment to remaining inventory/COGS with reconciliation; otherwise block that unsupported workflow clearly and document the supported pre-finalization process. Never quietly push all late cost into unsold stock or rewrite prior journals.

Support accounting periods, locks, controlled reopening, cash/bank reconciliation, customer/supplier aging, inventory-to-GL reconciliation, opening balances, expense transactions, fixed-asset register, basic depreciation schedules, and adjustment journals with approvals.

Implement reviewed inventory write-downs when carrying value exceeds net realizable value, with reason, evidence, approval, and linked GL/subledger valuation adjustments. A later reversal is limited to the remaining original write-down so inventory is not raised above its otherwise applicable cost. Preserve physical quantities and historical cost; release applicable valuation adjustments on sale/disposal and reconcile net inventory and any contra-inventory allowance to the GL. Test write-down, disposal release, and capped reversal.

Base currency defaults to AFN. If multi-currency is enabled, preserve original currency, amount, transaction rate, base amount, settlement allocation, and realized FX differences. Do not silently translate historical transactions using today's rate. Either implement tested revaluation/period-end FX or explicitly leave that feature unavailable rather than claim it exists.

Provide effective-dated configurable tax/withholding rules, TIN/registration fields, document snapshots, tax accounts, and reports. Do not invent current Afghan rates, thresholds, or legal applicability. Demo scenarios use no tax unless a test explicitly configures a synthetic rate. Label those values clearly. Have local professional validation as a production-readiness requirement; it must not block building the configurable engine.

Use internationally recognized accounting principles as design references, including IAS 2 inventory costing and customer-revenue recognition principles. Do not market the application as certified IFRS compliant or Afghanistan tax compliant merely because these features exist. QuickBooks integration is not required and must not be falsely claimed.

## 14. Product lines, shared costs, and management reporting

Classify operational revenue and costs as Sponge, Adhesive, or Shared/Unallocated at the appropriate transaction-line level. A shared item or resource does not require duplicate customer records or fabricated inventory.

Direct costs follow their actual use. Shared expenses use a documented allocation driver, for example approved labor hours, machine usage, or another appropriate basis. Display pre-allocation and post-allocation results. Do not allocate everything by revenue automatically and claim exact product profit.

Branch reports preserve original sales location and stock movement history even when another authorized branch collects the customer payment. Cash belongs to the receiving cash account; collection does not relocate the original sale.

Company-level trial balance, balance sheet, and cash flow are the primary complete financial statements. Branch profit reports are required. Branch-filtered trial balances or balance sheets must not be labeled balanced standalone statements unless interbranch clearing/balancing is implemented and tested. Provide branch cash/stock reports without making that unsupported claim.

External company sales reports exclude internal branch charges by construction. Internal branch management reports are separately labeled and cannot alter statutory totals.

## 15. Required UI/UX and localization

Create a professional operational application for Afghan staff with modest accounting/computer experience. Use familiar terminology, clear labels, concise forms, and useful defaults. Avoid decorative marketing layouts, oversized empty dashboards, fabricated charts, and unnecessary technical language in ordinary workflows.

Dari is the default language. Provide complete initial navigation/common workflow translations in Dari and English, and a usable Pashto translation catalog with remaining language-review needs identified. Do not present English strings as completed Pashto translations. Allow per-user language preference.

Use proper HTML direction attributes, logical CSS properties, and bidi isolation for invoice codes, phone numbers, numeric inputs, and mixed-script units. Support Persian/Arabic and Latin numerals, normalize inputs, validate decimals consistently, and show units next to all quantities.

Use AFN by default, Asia/Kabul timezone, and an optional Jalali display/input mode with reliable conversion to canonical stored dates. Display unambiguous dates in documents. Never change the underlying accounting date when toggling display calendar.

Design accessible desktop/tablet workflows with useful mobile layouts. Support keyboard navigation, visible focus, readable type, non-color-only statuses, searchable selects, pagination/filtering, loading/empty/error states, confirmation summaries for consequential posting, and safe retry behavior.

Persistent header: active business, location, user, language, and connection state. Primary navigation: Sales, Purchases, Production, Inventory/Transfers, Money, Employees, Reports, Settings. Show only permitted modules.

Role-focused start pages:

- Cashier: new sale, find invoice, receive payment, own cash closing.
- Warehouse: receive goods, available stock, transfer dispatch/receipt, stock count.
- Factory: new actual batch, material consumption, output measurements, trim, completion.
- Accountant: receivables/payables, reconciliation, posting exceptions, period close.
- Owner: external sales, collections, debt, stock, production, losses, profit; internal branch activity clearly separate.

Required screens:

- Login, password change/reset with a locally usable administrative recovery path, user/session management, business/location switcher.
- Business settings, legal entity mapping, warehouses, product lines, chart of accounts, units, item catalog, prices, taxes, numbering, roles, approvals.
- Customer/supplier records, lightweight walk-in references, statements, invoices/bills, allocations, deposits, credits, refunds.
- Purchase order, receipt, bill, supplier payment, landed costs, returns.
- Production batches, actual inputs, floor stock, work in progress, output measurement, trimming, waste, optional BOM/version/work-order flow.
- Block/piece list, remaining height, suitable availability, reservation, cut preview, cut history, labels, stock counts/adjustments.
- Transfers, transit, receipt, discrepancies, internal charges, internal settlement.
- Sales entry, fulfillment, invoice lookup, collection, returned-sheet disposition.
- Cash/bank accounts, expenses, money transfers, cash closing, bank reconciliation.
- Employee terms, attendance/project acceptance, advances, payroll, payslips, settlements.
- Journals, ledgers, period management, assets/depreciation, financial reports, audit log.

The sponge sale form must show grade, actual/compatible footprint, thickness with mm/cm selector, sheet count, billable cm, suitable block allocation, before/after remaining height, cutting loss, rate, total, amount paid, and debt.

Print functional A4 invoices, compact payment receipts, transfer slips, payslips, and block labels. Verify Dari shaping, numbers, page breaks, totals, and copy/reprint labels in the rendered output.

## 16. Reports that must reconcile to real transactions

Implement date/business/location/product-line filters with permission enforcement, printable output, and authorized CSV exports. Report time boundaries must respect the business timezone and accounting periods.

Required reports:

- Raw material opening, receipts, issues, actual consumption, unused returns, losses, closing stock.
- Production by batch/date/grade, block count, saleable cm, adhesive kg, WIP, inputs, outputs, cost and loss.
- Block/remnant stock by grade and footprint, suitable availability, reserved/held quantities.
- Top/bottom trim and recoverable scrap produced/sold/on hand.
- Inventory movement, valuation, physical-count variance, inventory-to-GL reconciliation.
- Sales by product/grade, line, branch, customer, and salesperson; external and internal reports separated.
- Invoice-level outstanding debt, customer statements, aging; supplier equivalents.
- Payments/collections, cash closing, bank reconciliation, cash in transit.
- Transfers dispatched/in transit/received and discrepancies; managerial charges and settlements.
- Attendance, wages, advances, payroll, employee debt.
- General ledger, trial balance, profit and loss, balance sheet, cash-flow statement with documented classification/method and reconciliation.
- Product-line and branch profit, shared-cost allocations, batch cost and cost per sale cm for the appropriate profile.
- Audit and approval exception reports.

Dashboards must use these real data sources. Cash collected, sales revenue, profit, and customer debt are different measures. Label estimated/provisional costs where applicable. Never return invented zeros or demo arrays when a calculation fails.

## 17. Security, integrity, and operations

Use established password hashing, safe session settings, CSRF protection, login throttling, session revocation, and owner/accountant MFA capability through a maintained implementation. Never implement a custom cryptographic scheme or embed universal production passwords.

All posting operations are atomic across document state, stock/value movements, accounting entries, and relevant allocations. Use unique source-event keys. Implement idempotency keys on payment, posting, cutting, consumption, dispatch, and receipt endpoints; same key with conflicting payload must fail. Number documents safely under concurrency, scoped by business/type and configured location/period. Voided numbers remain traceable; gaps are not silently reused.

Posted records and ledger movements are append-only through ordinary application access. Corrections preserve originals and create linked reversal/adjustment documents. Reject duplicate reversal. A reversal requiring unavailable physical stock must use a valid return/adjustment workflow rather than creating negative stock. Master-data deactivation preserves historical references.

Audit actor, business, time, action, reason, approval, source document, and before/after for relevant editable data. Protect sensitive input details in logs and errors. Never log passwords, session secrets, or unnecessary payroll/formula information. Document the limits of application audit controls versus database administrator access.

Attachments require business-scoped authorization, private storage, safe file validation, nonexecutable serving, and permission checks on downloads. Protect CSV exports from spreadsheet formula injection. Exclude secrets and backups from source control.

Use online authoritative posting initially. Show connection failures and keep drafts distinguishable from posted transactions. Do not claim unrestricted offline accounting; any offline-finalization extension needs stock allocation, durable queues, duplicate protection, and conflict resolution.

Implement encrypted backup guidance/configuration, copies outside the application server, health checks, migration procedures, log/error monitoring, and a tested local restore into a separate database. Backups must cover PostgreSQL and private attachments with a consistent snapshot procedure and the required configuration/encryption-key references; handle secrets securely outside public source control. Document recovery assumptions. Dev reset commands require explicit demo targeting.

Use indexed, paginated queries and explainable report performance. Add indexes for business/date/document/stock lookup patterns. Verify representative reporting and lookup on a documented synthetic dataset; record measurements instead of claiming arbitrary scalability guarantees.

## 18. Mandatory acceptance scenarios

Convert these into automated domain/API integration tests, using PostgreSQL. Use independent expected balances, not assertions that merely repeat the implementation formula. Add browser tests for representative complete journeys and negative permissions. Fixtures are synthetic and exclude tax unless stated.

A01 — Product label is not mass.
Create one grade-45 block, 2,000 × 1,000 × 1,000 mm. Expect one block and 100 saleable cm for that footprint. Do not create 45 kg automatically.

A02 — Exact cut.
Cut/sell one 22 mm full-face sheet from that block with zero loss. Expect 2.2 billable cm and 978 mm / 97.8 cm remaining. At 500 AFN/cm, the pre-tax line value is 1,100 AFN.

A03 — Units and sheet count.
Three 22 mm sheets consume 66 mm / 6.6 cm. Entering 22 mm and 2.2 cm gives identical results. 50 mm equals 5 cm.

A04 — Cutting loss.
Set 1 mm loss per cut. One 22 mm sheet bills 2.2 cm and physically consumes 23 mm. Expect 977 mm remaining and a separately recorded 1 mm loss, with appropriate cost treatment.

A05 — Aggregate stock.
Start with 9,000 cm of one grade and compatible footprint. Fulfill 50 cm with zero loss. Expect 8,950 cm remaining and no change to other grades.

A06 — Fragmentation.
Ten remnants each 10 cm high cannot fulfill one 22 cm sheet despite 100 aggregate cm. An order for appropriate smaller pieces can succeed.

A07 — Footprints.
100 cm height of 2 m × 1 m stock and 100 cm of 1 m × 1 m stock appear as separate groups, never as 200 interchangeable standard-sheet cm.

A08 — Concurrency and idempotency.
Two users simultaneously request 22 mm from a block with 30 mm available. Exactly one succeeds. Retry the successful key without another stock or journal change. Test conflicting payload with the same key.

A09 — Production without BOM.
Post actual material quantities and 10 measured grade-45 blocks. Stock and WIP/output costs update. No BOM is created or required. A sales-only user cannot retrieve the input quantities through API/export/report.

A10 — Issued versus consumed.
Issue 120 kg to the production floor, consume 100 kg, return 15 kg unused. Expect 5 kg remaining on the floor and only 100 kg consumed/costed into the batch.

A11 — Trim conservation.
Convert a 1,060 mm block into 1,000 mm main height, 30 mm top, 20 mm bottom, and 10 mm loss. Reconcile the geometry. Create trim inventory in the configured units; selling trim does not reduce main-block height again.

A12 — Manufacturing cost conservation.
In a clean test pool, total batch cost is 130,000 AFN. Approved abnormal loss is 5,000; by-product carrying value is 5,000; main output is 120,000 across ten equal 100 cm standard blocks, totaling 1,000 sale cm. Main unit cost is 120 AFN/cm. Sell 50 cm: COGS is 6,000 and remaining main stock is 114,000. Assert 114,000 remaining main + 6,000 COGS + 5,000 by-product stock + 5,000 abnormal loss = 130,000.

A13 — Walk-in and permanent partial payments.
For each customer type, invoice/deliver goods for 5,000 AFN, receive 3,500, and expect 1,500 remaining. Later receive 1,500 on the same invoice. Debt becomes zero and revenue remains 5,000. Receipt retries do not duplicate cash. Overpayments become customer credit; over-allocation fails.

A14 — Sales/cost journal fixture.
In a separate clean fixture, actual production has raw-material cost 160,000 AFN, eligible labor 30,000, and eligible overhead 10,000. Approved outputs are main stock 180,000 and trims 20,000, leaving zero completed-batch WIP. Main stock totals 9,000 compatible sale cm, so unit cost is 20 AFN/cm. Deliver 50 cm at 100 AFN/cm: Dr receivable 5,000 / Cr sales 5,000; Dr COGS 1,000 / Cr main inventory 1,000. After first receipt of 3,500, outstanding is 1,500 and main quantity is 8,950 cm. Collecting later does not change sales or COGS.

A15 — Internal transfer.
Transfer 100 cm carrying 2,000 AFN from Herat to Kabul. At dispatch: source decreases, transit increases. At receipt: Kabul increases, transit clears. Company quantity/value remain constant. Sales, customer receivables, COGS, and company profit remain unchanged. Include partial receipt, damage, shortage, return, and duplicate-request tests.

A16 — Internal branch charge.
Repeat A15 with a 3,000 AFN managerial charge. Stock/company GL is identical to A15. The 3,000 appears only in internal management records and its settlement history. External sales/receivables/inventory must not depend on the user remembering to exclude a filter.

A17 — Advances below salary.
An office worker earns 20,000 AFN and has a 12,000 advance. Accrue salary, recover an authorized 12,000, pay 8,000. Expect salary expense 20,000, advance zero, payable zero, total cash paid over both events 20,000.

A18 — Advances above salary.
An office worker earns 20,000 and takes a 25,000 advance. Recover an authorized 20,000. Expect no negative salary payment, a 5,000 advance asset carried forward, salary expense 20,000, and payable zero. These fixtures omit other deductions; test recovery limits separately.

A19 — Returned sheet.
Return an intact 22 mm sheet. Expect a separate inspected piece of its original footprint/thickness; the original parent block does not gain height. Restore its original issued cost rather than selling/refund price. Refund/credit, COGS reversal, and applicable valuation postings reconcile.

A20 — Adhesive decimals.
Produce 250.750 kg net, sell 12.500 kg, expect 238.250 kg remaining. Tare does not increase stock. A valid linked reversal reconciles quantities and cost.

A21 — Business/access isolation.
A furniture-only user cannot read or mutate sponge records by UI, URL, API ID, export parameters, attachment link, report, or autocomplete. A Kabul cashier cannot access unauthorized Herat payroll or cost fields. Test cross-business foreign-key submissions even for a user with both memberships.
For a mixed Sponge/Adhesive document, a user lacking one line's permissions cannot leak its total, receipts, or print view through partial filtering.

A22 — Transaction rollback.
Force failure after one intermediate posting step. No invoice-only, stock-only, payment-only, or journal-only result remains. Retry is safe. Every successful journal balances.

A23 — Immutability and periods.
Reject silent editing/deletion of posted documents, duplicate reversal, unsupported historical costing changes, and closed-period posting. Changing current prices, tax settings, or BOM versions does not alter posted documents.

A24 — Purchase lifecycle.
Receive goods before billing, later enter a matching bill, and pay partially. Stock is received once, clearing reconciles, supplier debt is correct, and purchase return/credit works.

A25 — Optional BOM isolation.
Another demo business uses an approved BOM version to create expected material requirements and records actual variance. Main sponge company still completes actual production without a BOM and cannot see the other business's recipe.

A26 — Reconciliation and opening balances.
After the linked operating fixtures, reconcile stock quantities/value, inventory controls, WIP, receivables, payables, employee advances, cash, and trial balance. Opening imports do not double-count GL/stock.

A27 — Localized real UI.
Complete a Dari RTL sponge sale, invoice lookup, later collection, actual batch, and transfer receipt in a real browser. Verify Persian/Arabic numeral entry, mm/cm display, Jalali toggle if implemented, error handling, and printed invoice/receipt output.

A28 — Fresh install and recovery.
From a fresh local PostgreSQL database, run documented migrations and demo seed, start the app, authenticate, and execute core tests. Back up and restore into a different local database/storage target; compare reconciled balances and confirm a restored private attachment still downloads only under the correct business permissions. Never restore over the active source database.

A29 — Credentials and sessions.
Verify CSRF/session rules, logout/revocation, throttling, and permission changes taking effect. Demo credential creation is explicit; production has no shared hardcoded password or demo fallback.

A30 — Cost adjustment and currency settings.
For enabled late-cost/multi-currency workflows, verify policy-consistent valuation/COGS adjustments, original exchange-rate snapshots, settlement differences, and balanced rounding. Unsupported variants must fail explicitly and appear in the limitations list, not silently corrupt balances.

A31 — Nonmonthly worker earnings.
Post approved daily attendance, part-time hours/terms, and accepted project milestones with effective-dated rates. Calculate independently expected earnings, reject duplicate attendance/milestone accrual, distinguish approved work from unaccepted work, and verify the resulting payroll/payable/cash postings. A later rate change must not rewrite already posted earnings.

A32 — Warehouse costs and impairment.
Receive the same item into two warehouses at different costs using the same moving-average formula. Transfer a quantity between them: preserve source carrying value through transit, recompute the destination average, and reconcile total inventory value. Post an approved net-realizable-value write-down and a capped reversal without changing physical quantities or raising value above the applicable cost.

## 19. Synthetic demo data and onboarding

Create an explicit demo-seed command that is repeatable and does not duplicate transactions. Require an explicit demo environment/target and never seed real production automatically.

Seed main sponge/adhesive business with Factory, Herat, and Kabul; isolated مبلمان شهر; seven sponge grades and compatible sample footprints; top/bottom trim; adhesive; raw materials; warehouses; sensible accounts; customers/suppliers; sample employees; approved opening balances; and representative posted/draft workflows.

Provide role account creation or a generated local credential mechanism with instructions. Clearly mark all sample prices, costs, quantities, names, and rules as demo data. Never include real formulas, real personal data, secrets, or public default production credentials.

Offer a practical setup wizard/checklist: business details, language/calendar, warehouses, units, items, prices, permissions, accounting mappings, configurable taxes, opening balances, backup configuration, and owner/accountant review. Configuration review must not be falsely presented as legal certification.

Support validated template-based CSV imports for master data and reviewed opening balances. Preview errors, prevent cross-business references, and make imports auditable and retry-safe.

## 20. Implementation sequence and continuation

Create/maintain these documents without treating documentation as a substitute for code:

- README.md: exact prerequisites, setup/run/test commands, local URL, credential setup, migration, demo seed/reset safeguards, backup/restore, troubleshooting.
- .env.example: all required settings with safe examples and no secrets.
- docs/REQUIREMENTS.md: numbered requirements and acceptance mapping.
- docs/ARCHITECTURE.md: modules, schema/ERD, posting boundaries, precision, auth, isolation, locking, and cost ordering.
- docs/ACCOUNTING_RULES.md: event-to-journal mappings, cost policies, clearing, allocations, close, and reconciliation.
- docs/DECISIONS.md: dated choices, assumptions, supported defaults, unresolved business matters, and compliance review needs.
- docs/IMPLEMENTATION_STATUS.md: requirement → implementation files → test/evidence → complete/partial/blocked status.
- docs/HANDOFF.md: current runnable state, last verified commands, failures, limitations, next concrete work.
- docs/USER_GUIDE.md: ordinary workflows with Dari labels and concise illustrations/screenshots where useful.
- docs/DEPLOYMENT_AND_RECOVERY.md: configuration, hardening, migration, backup/restore, monitoring, and production-readiness checklist.

Adapt useful existing documentation rather than duplicating facts. Keep permanent agent instructions short and refer to the authoritative documents.

Implement in this order, adjusting dependencies sensibly:

1. Repository orientation, concise architecture/schema decisions, requirement IDs, and runnable shell with actual authentication and business isolation.
2. Accounts, units/items/warehouses, opening balances, stock/value ledgers, transactional posting, numbering, audit, and permissions.
3. Purchasing and actual-consumption production through WIP, trimming, measured blocks, and adhesive output.
4. Cutting/reservation/fulfillment, invoicing, permanent/walk-in debt, collections, returns, and print documents.
5. Transfers/transit/receiving, internal charges/settlements, expenses, cash/bank reconciliation, and product-line reporting.
6. Attendance/project earnings, advances/payroll, financial close, assets/depreciation, reports, and optional BOM-assisted demo workflow.
7. End-to-end verification, access/concurrency/rollback tests, localization/print inspection, import/onboarding, backup restore, and documentation repair.

Keep the application runnable between increments and continue toward the full authorized scope. Do not stop after the shell or rename a partial implementation as the finished ERP. Update status with real evidence. If context or time limits interrupt work, persist decisions and the exact next tasks; on continuation, read those files and inspect existing code before editing.

## 21. Definition of done and final delivery

Completion requires functional database-backed core modules, real workflows, migrations, server-enforced permissions, exact stock/accounting calculations, meaningful passing tests, usable localized screens, printed documents, and reproducible local operation.

Disallowed substitutes include localStorage-only business data, fake APIs, hardcoded dashboard arrays, buttons without actions, TODO journal posting, client-only permissions, success responses that swallow errors, untested concurrency claims, and claims that a planned extension is already implemented.

Before reporting completion, run the relevant lint/type/build checks, PostgreSQL domain/API integration tests, browser journeys, and reconciliation checks. Fix failures within scope. Inspect actual browser/printed output. Record which commands passed, which failed, and which could not run. Avoid broad repetitive testing once meaningful checks pass unless a change or unresolved concern justifies it.

Report:

- What is implemented and any remaining requirements.
- Exact local start commands and URL.
- How to create/access demo role accounts safely.
- Migration/seed/test commands and actual verification results.
- Key UI screenshots or usable local previews where supported.
- Accounting and stock reconciliation evidence.
- Backup/restore instructions and tested outcome.
- Known limitations, unresolved business choices, and production review items.

Do not call the application production-ready merely because it builds or the demo loads. Local accountant configuration, real opening-balance validation, operational training, deployment hardening, and recovery review are separate go-live requirements. Do not perform public deployment automatically.

Begin now: inspect the repository, record concise implementation decisions, and start building the first working increment. Continue implementing and verifying the remaining increments under this contract.

---

## Reference links for the coding agent

Verify relevant current official documentation when selecting dependencies or interpreting standards. These links support the design; they do not supply the owner's real tax configuration or production formulas.

- [OpenAI prompting guidance](https://developers.openai.com/api/docs/guides/prompt-engineering)
- [Django support/downloads](https://www.djangoproject.com/download/)
- [Django database support](https://docs.djangoproject.com/en/stable/ref/databases/)
- [Django REST Framework](https://www.django-rest-framework.org/)
- [React application setup](https://react.dev/learn/build-a-react-app-from-scratch)
- [PostgreSQL numeric types](https://www.postgresql.org/docs/current/datatype-numeric.html)
- [PostgreSQL locking](https://www.postgresql.org/docs/current/explicit-locking.html)
- [PostgreSQL row security](https://www.postgresql.org/docs/current/ddl-rowsecurity.html)
- [W3C RTL guidance](https://www.w3.org/International/questions/qa-html-dir)
- [IAS 2 overview](https://www.ifrs.org/issued-standards/list-of-standards/ias-2-inventories/)
- [Public standard-setter inventory text](https://standards.xrb.govt.nz/standards-navigator/nz-ias-2/)
- [IFRS 15 overview](https://www.ifrs.org/issued-standards/list-of-standards/ifrs-15-revenue-from-contracts-with-customers/)
- [Intuit assembly/BOM reference](https://quickbooks.intuit.com/learn-support/en-us/help-article/set-inventory-lists/set-products-bill-materials/L3Kao5E9m_US_en_US)
