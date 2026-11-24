# NAWA upgrade changelog

## Production display corrections — 2026-11-23

- Confirmation dates follow the active calendar; delayed Solar Hijri conversion preserves later form entries. API errors show clean localized messages without diagnostic envelopes.
- Inventory cards and labels distinguish physical/reserved/saleable height and explain curing/quality holds without changing availability rules.
- Added separate Dari/English/Pashto location/warehouse fields, validation and localized Settings/catalog display. Additive migration0036 cleans known seed aliases with audit history; unknown custom mixtures are preserved for review. IDs and all seven checked financial/stock/attachment tables remain unchanged.
- Verified567 full PostgreSQL tests, final9 label/4 name checks and3 sealed-build browser checks, including delayed conversion. Main/training schema/ledger controls pass; restored-copy migration verified.

## Illustrated production manual — 2026-11-23

- Added a 73-page Afghan Dari production PDF with 40 steps and61 real filled-form/result screenshots, from setup and material receipt through staged no-BOM sponge production, quality/trim, two-step transfer and sales-ready stock; includes actual adhesive production and clearly unposted preview alternatives.
- Verified16 UI postings in a separate fresh synthetic PostgreSQL database with18 read-only stock/accounting assertions; rendered and visually checked pages, searchable text, fonts, contents links and PDF structure. No production feature, financial rule or audit-item completion changed.

## Audit-first program — 2026-11-22

The owner approved Phase 2 with `proceed`. Existing accounting/stock/isolation protections and historical posted identifiers remain mandatory. Tax rules stay inactive until applicability is confirmed; negative stock and offline financial finalization remain prohibited.

### Baseline repair — accounting manual coverage

- Documented `order_promise` in the English, Dari and Pashto accounting manuals: reviewed date/reason/basis only, without journal, stock movement, reservation, delivery or receipt.
- Verified focused registry-coverage test; all three manuals now cover 65 accounts and 179 actions. Rebuilt PDFs (English 61 pages, Dari 70, Pashto 63); extracted `order_promise` and visually checked its page in each language.
- Existing audit baseline was 508 passing tests and one manual-registry coverage failure. Full post-repair PostgreSQL suite passed: 509 tests, zero failures/errors/skips (1378.350s). No accounting or stock posting logic changed.

### P0-1 — safe search shortcuts and contextual help

- Added Ctrl+K search and retained Alt+F, prioritizing current document-table search before global sales search. Physical keys support Dari/Pashto layouts.
- Replaced permanent purchasing/transfer key hints with accessible expandable help; Escape/outside-click dismiss it. Action keys retain permission checks and all shortcuts pause inside dialogs.
- Added the reserved-window-shortcut source guard and three passing Playwright checks, including actual RTL screens on isolated training. TypeScript/static localization pass; sealed build `0aee986654f77e0c961ac12152dcdd38cec7e556cd2e8dacc8a7a8d560676d1c`.

### P0-2 / F4a — versioned tax-rule administration

- Added additive migration0035 with separate tax schedules/review events; legacy invoice percentage tax IDs and calculations remain unchanged. Database guards retain revision content/history and tenant references. Confirmation requires a fresh review revision and reason, with permission recheck under the business lock.
- Added Settings tax administration, structured bracket/source/date forms, read-only preview, confirmation/revocation, amended revisions and paginated retained history. New tax role permissions are available in the access editor. Dari/English/Pashto copy, SH display and precise decimal presentation are supported.
- Added five unconfirmed research candidates and an explicit dry-run-by-default importer. No research rate was imported or activated in main/training. Automatic invoice/payment/payroll tax, BRT returns/credits and withholding certificates are still pending.
- Verified full PostgreSQL suite: 561 passed (1155.739s); final Playwright: 2 passed (39.895s), covering the actual multilingual workflow/validation/isolation and precise displays. TypeScript/static localization/shortcut guard pass. Pre-upgrade encrypted snapshot restored and migrated in a new private database; seven main financial tables retain identical content fingerprints. Main/training schema0035 and runtime seal87eb0e5d72d1a3e1c28abe3bdb5b60d03bfd74ed7775f89b8ce216dbe82f8431 verified.
- Added docs/TAX_SCHEDULE_ADMIN_GUIDE.md and updated TAX_RULES.md/AUDIT.md/status/handoff with delivered scope and remaining tax work.
