# Staff acceptance record

Status: **not yet performed by the business's staff**. Automated QA is recorded separately in VERIFICATION.md. Copy the blank record for each participant; use a test workspace and synthetic data. An accountant should approve real opening balances and policies independently.

2026-11-22 pilot: the owner is the confirmed participant, with both Android and iPhone planned. The isolated training workspace and owner-specific Dari guide/blank observation record are in OWNER_PILOT_GUIDE.md and OWNER_PILOT_RECORD.md. Automated checks do not fill the human acceptance cells below.

Participant/name: __________  Role: __________  Date: __________

Business/test workspace: __________  Device/browser: __________

Language/calendar: __________  Connection conditions: __________

Localization review: check actual Dari/Pashto wording, English LTR and Dari/Pashto RTL on sign-in, setup, advanced help and all seven learning topics. Record the actual reviewer and findings; automated catalog/browser checks do not approve native terminology. See LOCALIZATION.md for the implemented scope and runtime-error fallback and native-language review limits.

Record observed completion time, errors and assistance actually needed. Do not tick a pass because an automated test exists. Keep confidential customer/payroll/formula data out of shared feedback files.

| Task | Expected result | Observed time/notes | Pass / blocked |
|---|---|---|---|
| Sort/filter sales, hide a column, save and reopen a view | Loaded-page column totals and authorized full-result summaries are distinguished; saved view belongs to own user/business/location; no transaction rows stored in browser preferences | | |
| Inline-edit a product price and cancel/confirm bulk deactivation | Actual authorized master update; old invoices unchanged; cancel makes no change | | |
| Edit an ordinary draft, undo and try a stale edit | Structured fields; undo only own unchanged unposted edit; no stock/journal before posting | | |
| Cancel a destructive review with Escape | Original form and entered reason remain; no posting | | |
| Check bell and document timeline | Only assigned work and accessible original records; print request is not paper-delivery proof | | |
| Transfer between two same-location bank accounts | Separate exact balances reconcile to BANK; statements cannot match the other bank | | |
| Count two independent drawers at one location | Only selected instrument custody is frozen/reviewed; no invented employee debt | | |
| Choose backup folder in host Settings and run a reviewed backup | Write test and archive check succeed; separately verify restore and off-device copy with operator | | |
| Read Dari/Pashto accounting manual and a validation failure | Actual native wording approved or corrected; unknown diagnostics retain original plus translated summary | | |
| Choose own task profile and reload | Preference persists; unavailable permissions are not granted | | |
| Read sales lesson; mark a step and reload | Correct Dari terms; progress persists without posting | | |
| Sell one22mm sheet at500AFN/cm | 2.2cm billed;1,100AFN total; zero-loss1,000mm block becomes978mm | | |
| Collect500AFN on that1,100 invoice |600AFN remains; revenue still1,100 | | |
| Repeat the sale | Old block/payment cleared; current stock and price reviewed | | |
| Scan/search an existing block label | Correct business, product and warehouse; unknown/foreign labels fail clearly | | |
| Open invoice, payment and return | Full page/deep link; Back and related original records work | | |
| Start a batch and record actual materials | No compulsory formula; source warehouse and quantities explicit | | |
| Drag a process card, then cancel | Form opens; no stock, WIP or accounting change | | |
| Complete measured output and review quality | Original events preserved; block dimensions and actual status correct | | |
| Trim top/bottom and record waste | Actual geometry and cost reconcile; no duplicate stock | | |
| Create opportunity and follow-up | Only assigned users access it; expected value is not revenue | | |
| Turn opportunity into quotation | Correct customer/items; no stock or debt posting | | |
| Upload clear real-layout synthetic receipt image/PDF | Private original preview; extraction visibly reviewable; no automatic posting | | |
| Correct source fields and approve draft | Draft only; duplicate hash/reference blocked | | |
| Post reviewed expense or receipt-linked bill | Correct ordinary accounts; no duplicate receipt/payment | | |
| Test representative Afghan fonts/numerals/rotated photos | Record errors/unsupported layouts; do not assume handwriting support | | |
| Use tablet/phone and slower connection | Readable layout, useful loading/errors, no duplicate retry | | |
| Attempt another location/business or confidential source | Server denies unauthorized access including direct URL/download | | |
| Compare trial balance and inventory reconciliation | Correct balances, zero unexplained differences | | |

Issues requiring change (task, exact action, expected/actual, safe screenshot/reference):

____________________________________________________________________

Staff reviewer: __________  Accountant review where needed: __________

Owner decision/date: __________  Follow-up owner/date: __________

This record does not certify legal/tax compliance, off-device recovery, production capacity or independent audit acceptance.
