# Supplier quotations and reviewed sourcing

Open **Operations & planning → Supplier quotations / مقایسه پیشنهادهای خرید**. This module records competing offers and a reviewed purchase decision. It does not email suppliers or receive goods automatically.

## Workflow

1. Create a request with receiving warehouse, desired receipt date and exact product quantities. A sponge quantity is centimetres of full-face height for an explicitly stated length/width; a grade name such as 45 is never a mass conversion. Raw materials keep their configured units.
2. Record each supplier's original reference, validity, delivery lead days, payment terms and AFN price for every requested line. Freight is a separate supplier estimate. Original offers remain immutable; a revised quote is another dated reference.
3. Compare original merchandise totals, separate freight estimates, validity, supplier-stated lead time and payment terms. The comparison total is merchandise plus estimated freight. The table sorts by that total but does not force the cheapest supplier to win. Record the operational reason when delivery timing or quality history justifies another offer.
4. An authorized reviewer selects one current whole-request offer and records a reason. The operation creates exactly one ordinary purchase order through `core.execute`, with original quantities/prices, request/offer references and explicit source-line mapping. A repeated idempotency key returns the same award; another award key cannot order the demand again.
5. Use the existing purchase receiving, bill, payment and supplier-claim workflows. The award posts no stock movement, supplier payable, freight capitalization or cash payment. Purchase-order base prices exclude the separate comparison freight estimate.
6. Close an unawarded request with a reason when it is no longer required. Offers remain available as historical evidence. An already awarded request cannot be reopened or cancelled through sourcing; use the normal purchase-order remainder-cancellation workflow for its commercial order.

## Example

Request 10 kg by 3 June:

| Offer | Merchandise | Freight estimate | Comparison total | Lead time | Decision |
|---|---:|---:|---:|---|---|
| Supplier A | 100 AFN | 20 AFN | 120 AFN | 2 calendar days | Arrives 3 June when reviewed 1 June |
| Supplier B | 110 AFN | 0 AFN | 110 AFN | 5 calendar days | Estimated arrival 6 June |

An accountant/purchasing approver can select A with the documented delivery reason. The resulting PO has merchandise 100 AFN; the protected offer and award preserve the separate estimated freight 20 AFN snapshot. No account or inventory changes until the existing actual receipt/bill/cost workflows post their events.

For 6.6 cm of a 2000 × 1000 mm sponge footprint at 500 AFN/cm, merchandise is 3300 AFN. The number in the product grade is not used in this calculation.

## Permissions and records

- `purchases.post`: create a request, record supplier offers, close an unawarded request. Recording offers additionally requires `cost.view` because it enters purchase price information.
- `purchases.view`, `purchases.post` or `purchases.approve`: read request quantities within assigned location/product scope.
- `cost.view`: read competing prices, comparisons and original offer/award documents, including direct document/print endpoints. Generated purchase orders retain ordinary commercial pricing presentation; the separate private freight estimate stays in the protected offer/award.
- `purchases.approve`, `purchases.post` and `cost.view`: award and create the purchase order. The normal posting/value approval limits remain authoritative. Purchasing module access does not bypass location, product, raw-material or business isolation.
- `inventory.raw` or `consumption.view`: required for raw-material request details. A mixed request is denied as a whole when one of its product lines is restricted. Generated purchase-order document/print reads recheck the originating raw-item/request scope.

Requests, supplier offers and awards have PostgreSQL tenant guards. Offer and award evidence cannot be edited/deleted after their source posts. Request dimensions/lines are immutable; only a documented one-way closure is supported. The source Document ledger remains the audit/posting boundary. New tables contain operational evidence rather than another financial ledger.

## Current limits

- Only whole-request AFN offers are supported. Partial supplier offers, split awards, automatic foreign-rate translation, tax evaluation, minimum-order constraints and automatic negotiation are not implemented. The server rejects unsupported foreign currencies explicitly.
- Freight is a comparison estimate, not a supplier bill or automatically capitalized cost. Actual freight must use the already supported receipt/landed-cost workflow with accountant review.
- Lead days are supplier statements. No factory capacity, transport booking or material availability is promised by the comparison.
- Supplier performance remains available in the existing supplier-performance screen. It is not converted into an invented quality score or hidden automatic award.
- No external request or notification is sent by this module. Original papers can use the existing private document attachments workflow.

## Technical handoff

- Models: `SourcingRequest`, `SupplierOffer`, `SourcingAward` in `sourcing_models.py`.
- Operations: `rfq_create`, `rfq_offer`, `rfq_award`, `rfq_close` in `sourcing.py`.
- Read API: `/api/sourcing/requests/` (bounded pagination) and `/api/sourcing/comparison/?request=<id>&as_of=YYYY-MM-DD`.
- `sourcing.document_guard` must remain in generic `api.doc_permission`; hiding prices only in the frontend is insufficient.
- Schema migration: `0027_supplier_quotes`, dependent on `0026_statement_imports`.
- Frontend: `SourcingWorkspace` in `sourcing.tsx`, with Dari/English labels and exact server-authoritative totals.
- PostgreSQL tests: `backend/erp/tests/test_sourcing.py`. Browser acceptance: `frontend/tests/sourcing.spec.ts`, explicitly isolated QA only. Verification results are recorded by the integrating agent; this guide alone does not claim tests were executed.
