# Production display and master names — 23 November 2026

## What changed

1. Confirmation dialogs now share the active calendar provider with forms and format canonical dates through the shared date formatter. Solar Hijri remains the default; Gregorian selection also works. Stored dates and posted payloads are unchanged. The shared date input skips unchanged-date conversion and uses the latest parent callback for delayed conversion results, preventing previously entered quantity/reason fields from being overwritten. SimpleForm updates also merge current state.
2. The common API boundary selects the translated validation message rather than flattening the whole diagnostic envelope. Unknown/untranslated responses, HTML error pages and connection failures get safe Dari/English/Pashto guidance. ApiError.detail retains diagnostics for investigation; error_code/error_original/translation metadata are not appended to staff-facing errors. Field errors with complete translations remain readable. This is not a claim that every backend diagnostic has an exact translation.
3. Block cards show saleable height separately from physical remaining height. Printed labels show reserved height and a reason when saleable height is zero. A 100 cm block in curing, inspection or transit does not become saleable because a label is printed. Existing stock rules are unchanged. Print navigation uses the user's saved language for warehouse/location names, since a new browser navigation does not send the app's custom language header.
4. Locations and warehouses have separate name_fa, name_en and optional name_ps columns and Settings fields. Dari is primary; a missing translation falls back to the canonical name. API language-only legacy calls remain supported without discarding other translations. New mixed-language concatenations and known placeholder suffixes are rejected with localized messages. Language switching refreshes catalog names while retaining the selected settings tab; previous catalog placeholders are permitted only within the same business and location.

## Ordinary use

- For an unused-material return: Production → Return unused materials → select floor, destination store, material, quantity and reason → Post → check the review date in the selected calendar → confirm. Changing the display calendar does not change the document date.
- For a height mismatch: the trim error now explains that main + top + bottom + loss must equal the measured source height. Correct those measurements; do not change stock to suppress the error.
- For a curing block: complete the actual physical curing/quality checks, then use Inventory → More operations → Quality release with an authorized account. Complete the required trimming as appropriate before sale. In the current application, trimming itself can mark a block ready; physical inspection must therefore be completed before trimming/selling. This update does not redesign that workflow or silently release held stock.
- For translated master names: Settings → Setup & master data → Warehouses or Locations → add/edit → enter the Dari name and optional English/Pashto names in separate fields. Codes belong in code fields. Never enter “فابریکه / Factory” into one name field.

## Migration and preservation

Migration0036 adds six columns. It recognizes the shipped factory/floor/transit/Herat/Kabul/furniture aliases, records before/after values in business-scoped AuditEvent rows and retains IDs. Unknown mixed custom names are retained and explicitly flagged for authorized review, not automatically translated or deleted. Future demo seed names use separate fields; transit lookup uses the stable English field to avoid recreating renamed transit warehouses. No stock quantity, carrying cost, journal, posted document or attachment is rewritten.

Applied to main sponge_erp and owner-training verify_pilot_20261122 after encrypted local snapshots. Also restored the pre-migration main snapshot into NEW restore_ui_names_20261123 and applied the migration there. Seven financial/stock/attachment tables have identical counts and content hashes before/after on main, training and the restored copy. Main migration reviewed13 location/warehouse records, with13 audit events, zero remaining mixed names and zero unrecognized-name review flags. Same-machine snapshots do not establish off-device backup/recovery acceptance.

## Evidence

- Existing focused PostgreSQL baseline:15 passed.
- Full PostgreSQL suite:567 passed, zero failures/errors/skips,1118.28s. Subsequent final label/name amendments additionally pass9 label and4 master-name tests. These focused checks cover the final saved print-language and legacy translation-preservation paths.
- Final sealed-build Playwright:3 passed,29.6s. Real isolated UI checks cover SH/Gregorian review dates, deliberately delayed date conversion without lost quantity/reason, rejected trim with clean Dari validation, curing stock/label explanation, separate warehouse fields and English/Pashto switching with direction preserved. The fixture is NEW verify_ui_fixes_20261123; rejected/cancelled operations did not post to main or training.
- TypeScript/build, static localization, reserved-shortcut guard, migration consistency and diff checks pass. Dari review/error/name-form and block-label screenshots were inspected. Main/training schema and all five core ledger controls pass.
- Current seal: aa2101478636e7f2a9af2b55b4334dee69326d2f3ca42ea404ea0b2090a794b3;343 inputs/56 assets. Private evidence: .local/ui_fixes_20261123/. Credentials, snapshots and screenshots remain private.

Refresh the browser after updating. Native staff/editorial/accountant and physical-device acceptance remain separate. This increment does not complete the tax engine, calendar-preset mandate or whole-application string audit.
