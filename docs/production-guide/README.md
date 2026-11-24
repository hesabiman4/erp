# Illustrated production guide — 23 November 2026

Delivered PDF: `output/pdf/Nawa_Production_Step_By_Step_Dari.pdf`.
Language: Afghan Dari, RTL, Solar Hijri dates. Landscape A4, **73 pages, 40 steps, 61 actual UI screenshots**, clickable contents, embedded fonts, searchable text and document outline. Long filled forms have consecutive views rather than omitted lower fields. Final inventory is split into two overlapping views for readability. Zoom the digital PDF to inspect small fields.

## Coverage

Business and no-forced-BOM setup; factory/floor/Herat warehouses; raw materials, sponge grade, trim and adhesive products; supplier; physical material receipt; supplier bill against that receipt; stock review; floor issues; WIP start; actual consumption; unused returns; measured block completion and abnormal loss; curing/quality release; main/top/bottom/waste height and cost allocation; ready block; actual QR label; dispatch/in-transit/destination confirmation; sales-ready stock; filled 22 mm sale preview; documented production overhead; alternative one-step sponge form; actual adhesive production; final stock and accounting checks.

The main scenario has **16 actual UI-posted documents**, all in a NEW synthetic PostgreSQL database `verify_production_guide_20261123`, separate from main `sponge_erp` and existing owner-training `verify_pilot_20261122`. No live business was cloned. Screenshots are from the sealed application recorded in `capture-manifest.json`; sample names/materials are fictitious and are not a manufacturing recipe.

The sale preview and alternative one-step sponge form were filled then closed, **not posted**. Draft/approval mode examples were selected but not submitted. The final sponge block remains ready, unreserved, 1000 mm / 100 cm high in Herat; adhesive stock is 20 kg. Do not describe those previews as completed sales/production. Physical QC is a fictional teaching confirmation, not a real factory acceptance test.

## Verification

`verification.json`: 18 read-only PostgreSQL checks pass: exact materials/returns/output values, final block location/status/height, inventory total 34,500 AFN, AP 35,500, abnormal loss 1,000, WIP/GRNI/conversion-clearing zero, every posted journal balanced, trial balance balanced, inventory/GL agreement, nonnegative stock and no sale/BOM.

`pdf-checks.json`: actual page/image/link counts, A4 landscape, text on every page, tagged structure, outline and final SHA-256. All pages were rendered with Poppler and inspected in contact sheets; individual cover, filled forms, cost/trim/adhesive, ready block and final stock pages were also inspected. Structural automation does not substitute for native staff/editorial or accountant acceptance.

## Maintain or rebuild

For document-only rebuild (no database needed), use installed frontend Playwright/Edge and Vazirmatn assets:

```powershell
node docs/production-guide/build.mjs
.venv/Scripts/python.exe docs/production-guide/check_pdf.py
```

Render with the existing Poppler `pdftoppm`, inspect the PDF visually, and repeat after any layout change. The HTML/build report and rendered pages are private scratch files under `.local/production_guide_20261123/`.

For scenario verification or recapture, the private fresh fixture, generated credentials and dedicated 8083 server must already exist. Credentials/setup/server state are deliberately excluded from Git. Never point the capture scripts at the owner's main or training database. Capture checks `/guide-info/` and exact database identity before use:

```powershell
node docs/production-guide/capture.mjs
node docs/production-guide/refresh-final-views.mjs
.venv/Scripts/python.exe docs/production-guide/verify.py
node docs/production-guide/build.mjs
.venv/Scripts/python.exe docs/production-guide/check_pdf.py
```

Capture resumes completed steps; it is not a general-purpose seed or recovery tool. `refresh-final-views.mjs` is read-only and refreshes only final-state images, never historical curing/WIP states. The manifest retains the original capture release; a later PDF-only seal does not change the captured application behavior. No runtime feature, financial rule, schema or audit-program completion status is changed by this manual.

Current UI limits are explained honestly: usual staged consumption is one material per document; that form has no labor/overhead field; eligible documented conversion sources are demonstrated using actual one-step adhesive production. The current trim operation marks a block ready, so the guide explicitly requires physical curing/QC before trim and sale. No field/feature was invented for the screenshots.
