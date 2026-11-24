# English and Pashto interface coverage — 2026-11-03

Dari remains the primary language and the fallback. English uses LTR; Dari and Pashto use RTL. Language selection is available before sign-in, in the staff header and in the customer portal. The document language/direction now updates at the application boundary, including sign-in and portal-only sessions. Changing the display language does not change accounting dates, contractual calendars or stored business values.

## Implemented coverage

- Setup/onboarding, master-data editors, permissions, BOM guidance, MFA accessibility, imports, opening-balance guidance and offline notebook instructions.
- Sales/counter sales, quotations, collections, customer/supplier centres, employee profiles/statements, accounting screens, status captions, production/cutting and inventory instructions.
- CRM, reviewed capture, cashier custody, statement evidence, supplier comparisons, runtime diagnostics, projects/subcontracts, commissions/late costs, transport/quality, planning, procurement, closing, profitability and customer requests/communications.
- All seven learning topics now have full Pashto titles and explanations for their21 steps, alongside existing Dari/English content. Step identifiers, versions and progress semantics remain unchanged. Workspace queues now include Pashto captions.
- Shared modal titles, empty states, placeholders, line headings, form help notes, setup tabs, toasts, dynamic quantity labels and controlled catalog captions now use the existing localization boundary.
-35 fixed server explanations have explicit Dari/Pashto text and original English: inventory/replenishment assumptions, forecasts, reconciliation scope, production/planning limits, customer requests, custody, sourcing, statement matching and recovery. Their API values and source records are unchanged.

The v6 static audit checks2,660 unique source phrases across42 files. It finds no missing English/Pashto entries and no raw Dari text in native JSX captions/accessibility attributes. This is a bounded source audit, not a claim that every possible server response is localized. The audit resolves2,812 English and2,775 Pashto keys across resource bundles; counts include earlier copy and aliases and must not be described as entirely new translations.

## Source and maintenance

`localize.ts` keeps the existing `l()`/i18next pattern. New explicit catalogs are `expanded-copy.ts`, `setup-localization-copy.ts`, `commercial-localization-copy.ts`, `planning-help-copy.ts` and `server-help-copy.ts`, `table-copy.ts` and `daily-v6-copy.ts`. Screens retain established inline English resources where appropriate. Shared navigation keys in i18n.ts now require complete English/Pashto shapes at compile time. Language-specific calendar abbreviations, digit parser alphabets and native calendar placeholders are intentional audit exclusions.

Run from the repository root:

```powershell
node scripts/check_localization.cjs --report .local/design/localization-static.json
```

The audit reads actual source and resource bundles; it does not load demo arrays, make requests or write financial records. It catches missing static phrase resources and raw native JSX copy. Browser checks remain necessary for computed labels, shared components and server metadata. A catalog entry alone does not prove that a screen calls the localization function.

Translate captions, never API values: options keep values such as `weekly`, `raw`, `CASH`, warehouse IDs and document references. Product names/grades, business names, employee/customer details, original OCR evidence, imported statement text and free-text notes remain original data. Use bidi isolation and existing numeric/date components; do not change stock units or infer mass from product labels. Avoid naming a callback variable `l`, which can shadow the localization helper.

## Verification and limits

Focused tests in test_daily_workspace.py and test_api.py:28 passed (PostgreSQL for database cases), including complete Pashto lesson coverage, permissions, business-safe preferences/progress, draft neutrality and API isolation controls. All12 QA browser journeys and3 built-runtime/offline/network journeys pass. TypeScript/Vite, Django/migration and final release/dependency/schema/ledger checks pass; no schema migration is required. English/Pashto onboarding, Pashto login/lessons/phone layouts were visually inspected. Active financial/stock reports exactly match the pre-change baseline. See VERIFICATION.md for exact runs and corrected failures.

Native Dari/Pashto editorial and actual staff acceptance remain unperformed. Some backend/Django validation errors and unstructured external-provider diagnostics may still appear in English; exhaustive runtime-error localization is not claimed. The v6 update supplies illustrated Dari, English and Pashto PDF manuals; text/bounds and rendered layout checks pass. Native editorial review remains separate. User-entered business data is deliberately not translated. Existing large-bundle warnings remain a deployment/performance consideration.

## Daily controls v6 additions

Tables, structured drafts, attention/review/timeline, trends, bank instruments and backup Settings use existing Dari-first l()/i18next hooks. Updated cashier instructions refer to the selected physical instrument. API errors negotiate Accept-Language, then saved preference, then Dari:214 exact diagnostics and two closed identifier templates have authored Dari/Pashto translations. Structure/status/codes remain; unknown messages keep original text, a localized summary and translation_complete=false. This is partial runtime coverage, not exhaustive certification. All three illustrated accounting PDF editions now exist and cover65 accounts/178 registered operations; native editorial/accountant approval remains unperformed. See DAILY_CONTROLS_V6.md and VERIFICATION.md.
