# Daily controls and financial instruments — 2026-11-03

This increment addresses the specialist critique with verified local workflows. Consult IMPLEMENTATION_STATUS.md and VERIFICATION.md for exact evidence and operational acceptance limits.

## Tables

The shared table supports accessible sorting, current-page text/status/date filtering, column visibility, scoped saved views and explicitly configured exact decimal totals. It states that operations cover loaded rows, not company-wide results. Sales/document totals explicitly use original decimal values; balances/prices/quantities are not automatically added together. Settings products support real authorized inline name/price edits and confirmed bulk deactivation through audited server validation. Bulk deactivation is atomic: a foreign or forbidden row rejects the whole request. Posted documents have no inline edit callback.

Saved preferences are keyed by user, business, location and table. Only column/sort and allowlisted status/date filters persist in browser storage; no rows, customer query text, document numbers or financial totals are saved. Revoked/removed columns cannot return from old preferences. Table tools do not imply server-wide sorting or bulk selection across unseen pages.

## Attention and trust

The bell and Operations badge show a bounded page of currently authorized pending approvals and recent overdue invoices. They are explicitly not an unread count or full company total. The server reuses document authorization; location/product/payroll/cost restrictions remain in force. No external notification is sent. Approval links lead to the review area; invoice links open original full pages.

Document timelines show creation/posting, authorized linked records, approval events and print-view requests. Audit details and confidential payloads are not copied into the timeline. A print request does not prove a printer produced paper or a customer received it. Inaccessible linked records are excluded through their original authorization.

## Structured drafts, review and undo

The raw JSON editor is replaced by structured dates, references, text, exact decimal fields and nested line/block editors derived from the draft's existing payload. System/evidence references remain protected. Existing optional fields not present in the draft must be entered through the original operation flow; this is not an unrestricted schema builder. Reviewed OCR drafts remain sealed. Draft ownership or explicit drafts.manage permission is required; references and product/location scope are rechecked at save and final posting.

Optimistic version checks reject stale edits. A successful edit returns an undo reference, encrypted before-image and exact after-version binding. Undo applies only to that actor's own still-unposted, unchanged draft and is one-time/audited. Current permissions apply again. Posted financial transactions have no delete/undo illusion: use the ordinary authorized return/reversal/adjustment. Consequential operation forms and final draft posting have explicit review dialogs; bulk product deactivation has its own reviewed confirmation. Undo is available in the draft editor rather than a disappearing toast.

## Cash drawers and bank instruments

Actual AFN instruments are separate from the CASH/BANK control accounts. Migration0031 introduces immutable instrument identities and entry links, with legacy pools for historical location balances. Old posted amounts and original journals are not rewritten. New instruments start at zero; registration itself has no journal. Use an actual cash_transfer from the real source to fund another instrument. Same-location transfers between distinct instruments are valid. Do not repeat opening balances for transferred money.

Normal monetary payloads, including AFN sides of foreign settlements/exchanges/deposits/refunds and remittance fees, select cash_instrument or bank_instrument; transfers select from_instrument/to_instrument matching their account kind and location. When several active instruments exist, ambiguous selection fails. Drawer custody and bank statement matching operate on the selected physical/account pool. Old unbound statements retain a controlled legacy bridge. Ordinary payment and FX settlement reversals retain the original instrument, including legacy sources after later pool splits; a new payload cannot redirect the compensation. Whole-business null-location historical entries remain explicitly unassigned, not guessed into a bank. Instrument totals reconcile to the original control GL; choices endpoints omit balances for ordinary posting users. Multiple foreign-currency wallets retain their separate existing workflows.

## Backups in Settings

The user chose to select the destination later from Settings. No destination is silently chosen. The panel supports an existing host-folder browser, an explicit path (including an operator-accessible network folder), write testing, interval configuration and Back up now. A backup includes PostgreSQL and private attachments, is encrypted, and its archive/attachment hashes are checked. This does not certify a restore or an off-device copy; separate recovery evidence is required. Scheduled ticks consume the same saved destination and report not_configured until a path is chosen. They run while the runtime supervisor is running; no operating-system startup task/service was installed.

Backups contain the whole installation, so business-owner permission alone must not expose arbitrary host folders or other businesses' data. A host operator is provisioned by a local command for that database:

```powershell
.venv/Scripts/python.exe backend/manage.py configure_backup_operator --username owner
```

This grants no business role, Django administrator status or financial posting permission. The selected user must still hold complete required business authority and access Settings on the host loopback connection. Host file browsing/configuration cannot be performed remotely over LAN. The configuration and operator allowlist are private files under .local. Encryption keys must be copied securely and separately from the server; same-disk folders cannot survive disk failure. No retention policy deletes old backup files automatically.

## Trends, keyboard and scanning

Owner trends use actual posted net sales, historical physical-inventory controls (WIP separate), actual invoice aging and positive measured finished-output movements. Output remains separate by grade, footprint and unit; kg input never becomes cm output. SVG charts require no extra chart dependency and expose underlying point tooltips. They do not invent historical aging snapshots or forecast data.

Purchases and transfers expose Alt+N for new receipt/dispatch, Alt+R for payment/transfer receipt, and Alt+F for table search. Existing counter shortcuts remain. A modal prevents global shortcuts from launching another entry form.

Manual code entry and keyboard scanners work over LAN HTTP. Phone camera scanning requires a trusted HTTPS secure context, device support and browser permission; localhost on the host is different from a phone visiting a LAN HTTP address. This increment does not install a certificate authority, trust certificate on staff phones, open firewall ports or advertise LAN HTTP camera scanning as available. The scan screen explains the supported fallback honestly.

## Language and staff acceptance

API errors negotiate Accept-Language (then authenticated preference, then Dari).214 exact messages and two closed identifier templates have authored Dari/Pashto translations. Error codes, HTTP status and field/list structure remain; unknown diagnostics retain original text with a localized summary and translation_complete=false. This is intentionally honest partial runtime-error coverage, not a claim all future validation text is translated.

The Pashto beginner manual source covers65 accounts and178 registry operations; English/Dari sources have factual instrument updates. All194 PDF pages were rendered and inspected, with complete required identifier coverage and no out-of-page text glyphs. Native-editor/accountant/staff acceptance remains unperformed. STAFF_ACCEPTANCE.md records tasks but no invented names, signatures or outcomes.
