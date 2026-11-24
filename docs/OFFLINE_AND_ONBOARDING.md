# Connection interruptions, private proposals and guided onboarding

## What works during an interruption

The opt-in offline notebook holds **quotation and sales-order proposals only**. It does not issue invoice numbers, post sales or receipts, deduct stock, reserve blocks, accrue payroll, or finalize any financial document offline. A saved local proposal is not a server draft and is never silently submitted when connectivity returns.

Create a notebook while signed in to its assigned business. Choose a separate passphrase of at least 12 characters. The app derives a non-extractable AES-GCM 256-bit key using PBKDF2/SHA-256 with a random salt and 310,000 iterations. Each save uses a new random 96-bit IV. Authenticated encryption binds the data to the user and business identifiers, so moving an envelope to another workspace does not make it readable there.

Only the encrypted envelope and user/business IDs are stored in IndexedDB. The passphrase, derived key, login cookies, catalog, API responses and session credentials are not persisted by the notebook. The key and decrypted proposals remain in memory while unlocked; locking or closing the notebook removes that component's decrypted state. The notebook locks after five minutes without keyboard/pointer activity, or when returning after more than one minute hidden. Browser encryption does not protect an already-unlocked browser from someone using that session or a compromised device.

Record the proposal date, customer reference, product descriptions, requested quantities/prices and any requested sheet footprint. These are typed notes, not cached customer/product master records. The notebook proposal date is explicitly labeled Gregorian `YYYY-MM-DD` so an offline note does not pretend to perform server calendar conversion. Online ERP dates continue to use the selected calendar.

The initial limits are 100 proposals per notebook, 100 item lines per proposal and 1 MB of decrypted notebook JSON. Browser storage can be removed by private-browsing cleanup, user action or device loss. Export the encrypted notebook and retain its passphrase separately; the company cannot recover a forgotten notebook passphrase. Encrypted import verifies both the passphrase and user/business binding and refuses to overwrite an existing notebook.

## Online handoff

1. Reconnect and sign in to the same account with access to the notebook's business.
2. Unlock the notebook and select **بررسی و انتقال به پیش‌نویس سیستم**.
3. The app verifies the live session and business membership, fetches the current permitted catalog without browser response caching, and asks for the real customer, warehouse and product selections. Review the date, unit quantities, prices and sheet footprint.
4. Select **ثبت پیش‌نویس در سیستم**. This calls only the server document-draft endpoint. A stable offline proposal identifier is used as its idempotency key, so retrying the same handoff after a lost response does not create another draft.
5. The encrypted local proposal records the returned server draft reference. Open the normal ERP draft to review and post it with normal permissions, current availability, accounting-period rules, prices and approvals. There is no automatic posting or reconciliation of stock from an offline assumption.

If the server creates a draft but the response or local save fails, retry the exact reviewed proposal. Changing a proposal after an uncertain submission uses the same key and is rejected rather than silently creating conflicting duplicates. Review the server draft register before resolving such a conflict.

## Optional app shell

The user must explicitly enable the offline app shell on the **built** local application. The development server intentionally does not install it. The service worker caches the public HTML shell, built `/assets/` files, manifest and icon. It bypasses `/api/`, `/admin/`, attachments, print views, non-GET and external requests. It never caches authenticated API responses or replays a failed transaction.

Reload the built application once after enabling it. If required JavaScript assets were not yet cached, the static fallback explains that a connected visit is needed. A cached app shell alone does not create an authenticated session or make server workflows available offline. The boot-error notebook entry permits passphrase-based access to existing encrypted notes while the ERP API is unreachable. Disabling the shell removes its service worker/cache; it does not delete encrypted notebook contents.

## Guided onboarding

The settings-authorized onboarding guide reads real workspace/catalog/readiness data. Its seven steps cover business separation and manufacturing mode, locations/warehouses, CSV imports, user permissions, real opening balances, reconciliation, and recovery responsibility.

It reuses the existing CSV preview-and-confirm import, opening-balance operations and server setup-review acknowledgments. It does not manufacture opening balances, declare demo values real, auto-grant permissions, require a confidential BOM, or certify tax/accounting compliance. Review acknowledgments remain attributed server audit events. The owner-selected backup destination remains unconfigured until the owner supplies it.

## Operator recovery drill

Use the project Python environment and an existing encrypted backup with its separate key:

```powershell
.venv/Scripts/python.exe scripts/recovery_check.py --input C:/private/backups/example.fernet --database restore_operator_drill_20261102
```

An optional `--key-file` selects a separate key file; optional `--migrate` applies current migrations only to the new verification copy before the checks. The wrapper invokes the existing guarded restore operation, which requires a **new** `restore_*` local database and a new private restored-media directory. It refuses live targets, existing databases/directories and remote database hosts. It never overwrites or deletes the active database and does not configure or enable the backup scheduler.

The drill compares restored document count, inventory carrying value and total journal difference to the captured manifest; verifies every captured attachment checksum/database reference; checks posted journals individually; reconciles each business's inventory control accounts with stock pools; and checks nonnegative pool/block reservations. It does not assume demonstration usernames. These checks do not replace application authorization tests, a full statutory review, or a comprehensive foreign-subledger review.

Private logs and a JSON result are saved under `.local/recovery-checks`. The restored copy and diagnostics are retained on failure for review; no automatic destructive cleanup occurs. A successful local drill is evidence of same-machine recovery only. Off-device copies and disaster recovery require a separately configured destination and a drill on that recovery environment. Run results are recorded in the implementation verification/handoff documents; source code existing on disk is not a successful recovery claim.

## Source and verification

Frontend: `offline-store.ts`, `offline-notebook.tsx`, `onboarding.tsx`, public service worker/manifest/static fallback. Operator scripts: `recovery_check.py` and `recovery_verify.py`. Focused browser tests exercise encrypted persistence, wrong passphrases, cross-business binding, export/import/tampering and service-worker API bypass. Pure command-boundary tests reject unsafe recovery target names. Consult the latest verification document for actually executed results and outstanding acceptance work.
