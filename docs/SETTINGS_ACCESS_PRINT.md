# Settings, access and print experience — v7 (2026-11-03)

This increment changes actual application controls, not financial posting rules. Dari remains primary; new controls have English/Pashto resources and preserve RTL/LTR behavior.

## Use the new Settings sections

Open **Settings / تنظیمات کسب‌وکار**. Five task cards replace the previous continuous stack:

- **راه‌اندازی و اطلاعات پایه** — products, parties, employees, warehouses, accounts/taxes, setup checklist and business details. The Add button sits directly above the master list.
- **کاربران و صلاحیت‌ها** — saved roles and business user assignments.
- **چاپ، PDF و رسیدها** — company letterhead, receipt paper, accent color, footer, payment instructions, signatures and authorized preview.
- **حساب‌ها و مانده آغازین** — AFN bank accounts/drawers, reviewed openings and approvals.
- **مصونیت و پشتیبان** — personal security and existing host-operator encrypted backup controls.

Each section has a persistent URL, for example `/settings?section=access` or `/settings?section=print`. Visibility follows existing permissions; user management does not automatically grant finance or print-setting management.

## Saved roles and user checkboxes

1. Choose **کاربران و صلاحیت‌ها → نقش‌های قابل تنظیم → نقش جدید**.
2. Enter a name. Optionally start from a conservative sales, storekeeper, production, accountant or read-only reviewer template. Templates outside your own grant authority are unavailable.
3. Search or expand the module groups. Select actual server capabilities: view, post, approve, print/export, refunds, corrections, sensitive cost/consumption/payroll data and administration. The current catalog contains107 concrete capability codes, covering all178 registered services. A checkbox may govern several related services; their operation captions/codes are listed. The editor does not pretend an unsupported per-field/per-operation permission exists.
4. Save and review the confirmation. This creates a real business-owned `AccessRole`.
5. In **کاربران**, select an existing user or **کاربر جدید**. Choose the saved role or custom permissions, permitted locations/product lines, approval limit and active status. New identities require a strong initial password.
6. Save and confirm. Saved-role changes immediately materialize into every assigned membership's existing permissions. Choosing custom permissions detaches that user's role; it does not change other users. Existing memberships are not automatically assigned to new roles.

Only `users.manage` can administer assignments. A manager cannot grant permissions, locations, product lines or monetary limits beyond their own assignment unless explicitly granted `users.grant_all`. Stale role/member edits are rejected. The last active full-access owner cannot be demoted/deactivated through either the new editor or legacy catalog endpoint. The business lock serializes role/assignment writes with ordinary posting; existing server checks remain authoritative. Audit events contain before/after values and affected membership IDs, never passwords. The PostgreSQL business-reference trigger also guards the new membership role FK.

There is no universal Delete checkbox for posted accounting/stock history. Use existing draft cancellation, authorized reversals/returns and master deactivation. Current capabilities intentionally retain their existing service groupings. These controls are not a new arbitrary CRUD authorization system.

## Print and PDF settings

1. Choose **چاپ، PDF و رسیدها**.
2. Set the official company name, contact/address, footer and payment instructions.
3. Choose A4 or80mm as the default for payment receipts, plus a validated six-digit accent color. Ordinary invoices/orders remain A4. Existing compact-receipt links still explicitly select thermal output; `compact=0` explicitly selects A4.
4. Choose whether to show signature spaces and the print timestamp; edit the two signature labels.
5. Save. The preview shows **saved** settings and is clearly marked as a sample, with no document, stock or journal creation. Open its separate print preview to print or choose Save as PDF in the browser.

The same validated profile drives ordinary staff document printing and the portal's existing authorized document projection. It changes presentation on future prints; stored amounts, source snapshots, customer debt, tax and journal history are not rewritten. The older print-profile operation preserves newer appearance fields. Text is escaped and CSS colors are allowlisted. Preview requires `settings.manage`; actual documents still require their existing scope and print permissions. Only the synthetic preview allows SAMEORIGIN framing with `frame-ancestors 'self'`; global frame denial remains in place. This is not a new PDF server renderer, logo uploader, legal invoice template certification or verified physical-printer configuration.

## Shared screen/form corrections

Dialogs now have a fixed header and a single scrollable content body, with reachable form footers. A shared token-based page lock handles nested confirmation dialogs and cleanup in either order, preserving the original page overflow. Focus restoration avoids moving the underlying page. Mobile grids and measured-block fields collapse without widening the document. Input/help spacing, row editors and section hierarchy are refined. Production columns allow page scrolling to continue at their boundary. Shared changes apply across forms; they do not mean every individual advanced page was separately redesigned or every device/printer tested.

## Verification and rollout

- PostgreSQL:27 API/security cases passed in `settings-security.xml`; final14 access/print cases passed in `settings-final-controls.xml`, with overlap of8 new cases. **33 distinct passing backend cases**; no33-case single-run claim. The final denied-post check supplies the required idempotency key. Early harness-only missing keys were corrected; no authorization assertion was weakened.
- Browser: three new QA journeys pass in `settings-final-browser.xml` (371.431471s), including actual saved role→user→revocation, persistent print settings/preview, long mobile sale scrolling, nested correction confirmation and17 core/settings phone layouts. An overlapping dedicated layout run also passes. English/Pashto employee and production form regression passes in `settings-forms-regression.xml` (113.797647s). Real synthetic changes stayed in `verify_ui_20261029`.
- Built runtime: the read-only active8080 Settings/permission-catalog/print-preview check passes in `settings-built-browser.xml` (23.5s), with zero financial/access/print-setting writes. Total current passing browser scope is five distinct journeys: three new QA journeys, one localized form regression and one built-runtime check. An early smoke assertion guessed31 groups; the final assertion matches the exact107-capability catalog across30 populated groups.
- Static localization:2,750 phrases/44 source files, no missing audited English/Pashto resources or raw visible native JSX captions. Native editorial acceptance is still pending.
- TypeScript/Vite, Django checks/migration consistency and current dependency/schema/core-ledger checks pass. Existing shared-import/large-chunk warnings remain.
- Migration0032 adds roles and a nullable membership role FK; existing grants/scopes and financial history are preserved. Applied to QA, then main through the guarded updater after an encrypted snapshot. No reset/seed on main.
- Current seal: `4edd0e9833b12dfe6eb71b45b418dd3b763a6528d2b7d36e0c0a359f42c461a3`,256 inputs/55 assets. Built8080 and API8000/dev5173 restarted and healthy.
- Main financial snapshot exactly matches the pre-update capture:110 documents/max153,279 entries, equal journal debit/credit4217843.34,32 stock pools/value2166450.000000,two attachments. Evidence: `settings-main-before.json`, `settings-main-after.json`, `settings-main-reconciliation.json`, `settings-release-final.json` in private `.local/design`.

Earlier browser harness failures involved working-directory paths, a stale QA server, missing QA CSRF trusted origin and a real embedded-preview frame block. The frame issue was fixed with the narrow preview policy and verified in the browser. Do not erase failing evidence or label staff/native/printer acceptance complete. Backup destination remains the user's Settings choice; no external messaging, public deployment or startup service was activated.

The108-page complete handbook remains its2026-11-03 earlier edition. Use this supplement for the new Settings navigation; the handbook's accounting/production examples were not regenerated or changed in this UI release.
