# Purchasing assurance, assigned counts and measured receiving

Open **Operations & planning → Purchasing & stock counts** (`?view=procurement`). The four tabs use database records and existing posting services. Their visibility depends on the current business membership. Existing memberships are not silently granted new permissions.

## Purchase matching

The matching tab compares a posted goods receipt against its linked purchase order, billed quantities and physical returns. It highlights an unlinked order, partial order receipt, unbilled goods and (for cost-authorized users) a difference between the purchase-order unit price and the receipt's original base unit cost. Landed costs are shown separately through the receipt carrying cost; they are not mistaken for a supplier price change.

Example: an order requests 20 kg at 10 AFN/kg. A receipt records 10 kg at 12 AFN/kg and a supplier bill covers 4 kg. Matching shows 10 kg outstanding on the order, 4 kg billed on this receipt and a 2 AFN/kg purchase-price difference. Opening the review posts nothing. Existing billing controls still prevent billing more than actually received and require controlled cost treatment for later price changes. This is an exception review, not an automatic invoice-price revaluation or blanket payment hold.

Supplier invoice references now normalize letter case, Persian/Arabic digits, spaces and punctuation across posted purchase bills, supplier expense bills and asset bills. `INV-۰۰۱` and `inv 001` for the same supplier are rejected as duplicates. The original reference remains saved. Different suppliers can use the same reference. A new reference is optional for legacy workflows, so duplicate detection cannot replace accountant review of missing-reference bills.

## Supplier claims

Create an evidence-based shortage, damage, quality, price or other claim against an actual receipt item. Undelivered-shortage claims can instead reference an order item, limited to that order's remaining quantity. Claimed quantities cannot exceed the source quantity across non-cancelled claims. Describe the physical or commercial evidence; attach supporting files through the normal protected source document if needed.

A claim has no journal or stock effect. An authorized purchasing approver can resolve it as:

- An actual returned credit: link a posted `purchase_return` for exactly the original receipt item and claimed quantity. The existing return already moved stock and posted the supplier credit; resolution does not repeat it.
- An actual replacement: link a different posted goods receipt for the same supplier, product and exact quantity. The receipt's actual financial treatment remains authoritative; this association does not manufacture free stock or automatically clear an old payable.
- Accepted without financial credit, rejected, or cancelled, with a documented outcome.

Each supporting return/replacement document can resolve only one claim; split actual documents appropriately if separate claims need distinct resolutions. Foreign price-only supplier credits remain outside this increment. Source document, location, raw-material and product-line restrictions apply to every view and action.

## Assigned blind counts

1. A count manager chooses the warehouse, specific product pools or identified blocks, assigned counter, due date and instructions. A scanner acting as a keyboard can search the exact item/block code. The assignment stores identities, without expected quantities.
2. Only the assigned active counter records all assigned items once. Kilogram/count items use observed quantities; physical sponge blocks use measured remaining height in millimetres. The canonical existing `stock_count` service freezes the pool/block/movement snapshot at observation time. Counting posts no inventory or journal.
3. The dedicated counter response omits book quantities, variance and pool values. Generic document/print/download routes sanitize the counter's own observation snapshot as well. Assigned observers use the separate `inventory.count_record` permission, so they cannot probe book quantities by posting arbitrary standalone `stock_count` observations. A user separately granted ordinary inventory viewing or standalone counting can still see those ordinary screens; a truly blind counter role should not receive those rights.
4. A different authorized reviewer compares book and observed quantities. They can request a new recount, accept an actual zero-variance observation, or apply the reviewed variance through the existing `stock_count_adjust` operation. Direct adjustment of an assigned count is blocked so it cannot bypass session review. The owner wildcard includes the separate `inventory.count_self_review` exception; ordinary reviewers need it explicitly to review their own counts.
5. A stock movement, reservation or block-condition change after observation invalidates adjustment/zero-difference acceptance. Recount instead. No original document or observation is rewritten. A positive surplus uses existing average carrying cost or an approved explicit total value; an empty pool requires a reviewed value. Shortage uses the existing moving-average cost. Count adjustments never release quality holds.

Permissions are separated: `inventory.count_manage` assigns; `inventory.count_record` records only assigned work; `inventory.count_review` reviews; `inventory.adjust` remains necessary for the actual financial/stock adjustment. The existing standalone `inventory.count` permission is independent. Raw-material counting separately needs `inventory.raw` or consumption authority. The underlying strict material-lot rules remain enforced; raw-lot adjustments needing explicit lot allocations must supply them through the API or use a separately reviewed lot-supported workflow. The simple screen does not invent lot assignments.

## Weighing evidence and goods receipts

Register a warehouse scale and its maximum kg capacity using `inventory.scale_manage`. Record external calibration evidence, responsible-person notes and a future due date. The software records that evidence; it does not certify physical calibration. Confirm manual readings under `inventory.measure` only while a recorded calibration is current.

Enter gross kg, the **total tare of all containers**, container count, product and explicit operator confirmation. Exact `net = gross − total tare` is checked by the service and a PostgreSQL constraint. Gross cannot exceed the recorded device capacity. Only actual kilogram stock items are supported; sponge grade names do not become kilograms. For example, gross 105.5 kg less total tare 5.5 kg creates 100 kg net evidence. Container count is descriptive and does not multiply tare a second time.

The measurement posts nothing. **Receive this measured quantity** then chooses the supplier and purchase cost per net kg and invokes one real `purchase_receive`: Dr inventory / Cr GRNI. Product, warehouse, original measurement date and exact net quantity are validated; one physical reading cannot be used for two receipts. The wrapper itself does not post a duplicate journal or movement. Create the ordinary supplier bill from the resulting actual receipt to clear GRNI to AP, then pay through existing purchasing workflows.

Direct serial/USB/network scale integration and automatic measurement capture are not implemented. This is an operator-confirmed manual workflow. Camera scanning continues to depend on the existing scanner/browser capability; the new assignment search supports manual or keyboard-scanner codes without claiming a new camera driver.

## Technical integration

Domain logic: `backend/erp/procurement.py`; models: `procurement_models.py`; scoped reads: `procurement_api.py`; UI: `frontend/src/procurement.tsx`; migration: `0024_procurement_counts.py` after `0023_business_excellence`. Nine new actions are registered through `core.registry`. All stock and monetary changes run through `core.execute` and the original `core.journal` posting routines, under the same business lock and idempotency boundary.

Database guards validate cross-business foreign keys and prevent rewriting posted evidence/assignment identities. A source session's state, observation, adjustment and review references remain controlled workflow fields. The application protects assigned actions and source scopes; database administrator access remains outside application-role isolation.

Focused verification lives in `backend/erp/tests/test_procurement_counts.py`, covering source matching, duplicate normalization, actual-credit resolution, shortage conservation, blind API/print access, reviewer separation, stale snapshots, measured receiving and immutable/tenant controls. Root verification records the executed PostgreSQL/browser runs and final counts; do not infer completion merely from this test file existing.
