# Capacity scheduling, actual yield and cutting alternatives

This extension adds real planning documents and measured read models. It does not create another stock, revenue or payroll engine. Reservations use `capacity_schedule` for an existing work order or `capacity_work_order` to create and schedule new multi-day work through `core.execute`; posted sources, request hashes, idempotency, business lock and period controls remain authoritative.

## Production schedule

Open Operations & planning → Capacity and yield → Capacity calendar. Choose **New multi-day work**, or choose **Schedule stages** on an existing unstarted planned work order. New work requires a finished product, a physical production warehouse, actual planned output in that product's unit and total estimated work minutes. Creating the work order and its first reservation is atomic. For example, 300 minutes at a center with 120 available minutes a day reserves 120, 120 and 60 minutes on three days. It creates no production output merely because its dates are planned.

1. Enter the earliest date, optional customer requested delivery date and explicit delivery lead days.
2. Select the actual working weekdays. All seven are initially checked; no Afghan company working-week policy is silently assumed.
3. Split the work order's total estimated minutes into sequential named stages. Existing work preserves its recorded total; new work takes the explicitly entered total. Choose an active work center at the production location for each stage.
4. Enter any calendar-day waiting time **before** a stage, for example curing before trimming. Waiting consumes no work-center capacity.
5. Preview the daily allocations and estimated delivery date. Review material and worker availability separately.
6. Post the capacity reservation. Posting recalculates the schedule under the business lock, so an intervening reservation can move the available dates.

The scheduler respects ordinary work orders and the latest posted multi-stage reservations for each work order. An ordinary new work order cannot consume time already reserved by a multi-stage plan. Reducing a work center's capacity below reserved demand is rejected. Cancelled work orders release their reservations. Completed work retains its historical capacity usage; no actual machine-day is silently made available again. Published historical schedules are never edited; a new supported reschedule supersedes the previous plan for capacity calculations and preserves both source documents.

This is conservative **daily** finite capacity. A subsequent stage begins no earlier than the day after the previous stage, even when it uses another center. Wait and delivery lead days are calendar days. This is not an hourly shift optimizer, automatic staffing/material-readiness checker, machine-breakdown predictor or guaranteed customer commitment. Work-center capacity remains an explicit configured estimate. The default search horizon is 180 days and the API accepts at most 366 days.

Work that already has a job card, linked output or even an uncompleted start/WIP batch cannot be rescheduled by this operation. Complete or review that existing work instead. Starting actual production is still a separate explicit factory operation; scheduling creates no batch, finished inventory, wages or sales.

## Actual batch analysis

Open the Actual production analysis tab. Filter batch **start dates**, then inspect a batch's original measured output, net actual consumption and linked trimming events.

- Sponge outputs retain their original block height, measured footprint and analytical volume. Later cutting/stock changes do not rewrite these original output measurements. Sales continue to use centimetres of thickness, never product-label kilograms or density.
- Adhesive and other outputs retain their own configured units. No sum of unlike units or footprints is presented as one physical yield.
- Actual material returns reduce the reported consumed quantity and input cost. Remaining WIP and abnormal monetary loss are shown only with cost access.
- Original trim heights show main output, top, bottom and documented loss. Main-height yield is main height divided by those comparable source heights. Saleable top/bottom are by-products, not automatically classified as waste.
- Optionally enter a **loss review threshold**, from 0 to 100 percent. There is no invented default. Measured trim loss is documented loss height divided by the total original comparable height; only a percentage strictly above your entered threshold receives a **Requires review** flag. The batch shows how many trim events require review. Clearing the threshold removes the review classification. This is an operational review cue, not an automatic abnormal-loss determination, expense, stock adjustment or formula-derived theoretical yield.
- Input quantities/names require `consumption.view`; costs require `cost.view`. A production-only operator can inspect safe finished-output measurements without confidential actual inputs. Business, location, product-line and source-document scope remain enforced.

No BOM or saved formula is required. The view does not infer a theoretical kg-to-cm conversion, chemical recipe, actual density or statistical anomaly threshold. It displays recorded facts for comparing like batches; it is not a full OEE or theoretical material-yield model. Up to 200 newest batches may be requested; default 100.

## Cutting strategy comparison

The existing customer-order cutting form now compares three deterministic decreasing-size heuristics using the same live physical and commercial validation:

| Strategy | Selection preference |
|---|---|
| Best fit | Smallest suitable residual height |
| Preserve reusable remnants | Exact exhaustion or a residual at least the reviewed threshold, then best fit |
| Oldest block first | Earliest created suitable block identifier |

The comparison shows blocks used, small residual height and reusable residual height. The reusable threshold defaults to **100 mm as an editable planning preference**, not a manufacturing rule. A small remainder stays inventory; this option never posts a write-off. Cutting loss is still a separately entered measured/configured allowance, not the remnant score.

Choose a feasible alternative and post the plan. The server recalculates current availability, then reserves physical block height and customer-order demand using the existing atomic cut engine. Execution creates identified held sheets once. Invoicing those sheets does not cut the parent again. No strategy may join unrelated remnants or footprints. No global optimum is claimed; an alternative can fail while another succeeds because these are bounded heuristics.

## Files and verification

- `backend/erp/advanced_planning.py`: source-backed capacity documents, shared daily reservation calculation, permission-scoped analysis and preview API.
- `backend/erp/growth.py`: ordinary work-center/work-order checks include advanced reservations.
- `backend/erp/order_cutting.py`: additional deterministic choices and reviewed remnant metrics.
- `frontend/src/advanced-planning.tsx` and `.css`: localized scheduling and actual-batch workspace.
- `frontend/src/order-cutting.tsx`: strategy comparison and selected strategy posting.
- `backend/erp/tests/test_advanced_planning.py`: focused PostgreSQL workflow tests. See the current verification handoff for actual execution results; this document alone is not a passing-test claim.

No additional schema migration is needed: immutable core documents store each schedule and its bounded allocation snapshot, while existing work orders determine lifecycle. Private inputs do not appear in schedule snapshots.
