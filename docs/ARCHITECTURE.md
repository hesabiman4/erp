# Architecture

## Application boundaries

Modular Django/DRF backend, PostgreSQL 18, React/TypeScript frontend. Session authentication with CSRF is served same-origin through the Vite API proxy in development. Operational quantities and financial decimal values are serialized as strings.

Core domain entities: Business, Location, Warehouse, Membership, Product, Party, Employee, Account, immutable Document, Entry, Allocation, StockPool, StockMovement, physical Block, versioned BOM, Asset, TaxRule, private Attachment, AuditEvent.

Every business reference is validated at the service boundary. PostgreSQL triggers additionally reject cross-business foreign-key references. Membership has explicit business/location/product-line/permission scope. Company-wide reports require complete scope; mixed documents are denied rather than partially leaking totals.

## Posting

All operations enter core.execute: resolve action permission; lock business; recheck membership; compare idempotency payload digest; validate period/date; assign a collision-safe document number; run domain handler; reconcile journals and inventory; post/freeze document; record audit. A single transaction commits or rolls back all changes. Business serialization is deliberately conservative for this first implementation.

Posted documents, entries, movements, and allocations are protected against mutation in PostgreSQL. Corrections use linked events. Generic private drafts do not affect ledgers and convert into an idempotently posted event.

## Stock and measurement

StockPool key is business/warehouse/product/profile. Quantity uses six decimal places; carrying value movements round to currency cents, with the final issue taking the pool residual. Blocks retain measured geometry in mm with three decimal places, remaining and reserved heights, status and lineage. Profile is the canonical measured length/width; incompatible faces never pool together.

Financial costing uses warehouse moving average independently of physical block selection. Actual batch costs remain analytical source data. Transfers freeze source carrying value through transit and blend once at the destination.

## Accounting

Entry rows balance per event and business. Stock movement values equal the corresponding gross inventory-control movement. Tax/price snapshots are immutable. Customer/supplier allocations preserve invoice-level debt. Internal branch charges remain outside statutory revenue, COGS and customer AR.

NRV adjustments are separate from physical quantities and gross historical cost; sales release allowance proportionally. Transformations/transfers of impaired pools are blocked until allowance is reviewed/reversed; general historical replay is unavailable.

## Runtime

Native development: isolated .local/pgdata on 127.0.0.1:55432, backend 8000, frontend 5173. No public deployment or system database service modifications. compose.yaml provides a separate development alternative, to be marked verified only after Docker execution.

Backup exports a consistent PostgreSQL snapshot and attachment manifest, encrypts the archive, and restores only into a new local restore_* database and separate media directory. Backup keys and application secrets are excluded from Git and must be retained securely outside the server.
