# Competitive expansion: operating guide and scope

This increment extends the existing ERP, rather than replacing its stock and accounting engine. All financial/stock events still use `core.execute`, balanced `core.journal` entries, the business posting lock, immutable source records, period control, and exact decimal quantities. An estimate, logistics acknowledgement, quality case or offline proposal never silently posts a sale.

## Where to find the ten areas

Open **Operations & planning / عملیات و برنامه‌ریزی**. Only sections allowed by the current membership appear. Existing staff are not automatically granted new permissions.

| Area | Screen / workflow | Current scope |
|---|---|---|
| 1. Order-linked cutting | `?view=order_cutting` | Select customer-order demand, review actual thickness/count and compatible footprint, preview best-fit cuts, reserve block height and order quantity, execute identified sheets, hold them for their order, and invoice whole held sheets once. Other sales cannot consume reserved demand. Cancelling/releasing a plan preserves physical history. |
| 2. Factory tablet | `?view=factory` | Large work cards show scheduled versus posted output and actual time. Start a linked batch, record actual material consumption, complete measured output and close work. Inputs/costs require their existing separate permissions. No formula is compulsory for actual-consumption manufacturing. |
| 3. Foreign workflows | `?view=foreign_advanced` | Foreign-priced sale and purchase entry, exact AFN conversion, refundable monetary credits, matched-party/currency allocation, refund, deposit revaluation, supported physical returns, sales price-only credit and latest-settlement compensation. USD/PKR quantities remain separate from AFN values. |
| 4. Connection interruptions | Notebook button in the header/login/offline boot | Opt-in encrypted quotation/order proposals survive connection loss. A passphrase unlocks each user/business notebook. Reconnect, authenticate as the same user/business and review real catalog selections before creating an idempotent **server draft**. No automatic stock, cash, invoice posting or background financial synchronization. |
| 5. Transport | `?view=dispatch`, Transport & delivery | Register vehicles/drivers, plan trips, load already posted sale/dispatch quantities, depart, record partial accepted/disputed quantities and private proof, resolve discrepancies against original documents and close the trip. Loading/acknowledgement does not repeat stock/revenue. |
| 6. Late landed costs | `?view=accounting_extensions`, Late landed costs | Record a real supplier service bill linked to goods receipts. Review explicit amounts for current on-hand inventory, already-sold cost or an open batch before its first completion. Value-only inventory movements conserve quantities. Backed source amounts cannot be absorbed twice. Later ordinary physical returns restore proportional allocated sold cost. |
| 7. Commissions | Same screen, Sales commissions | Dated, non-overlapping employee percentage policies. Preview/accrue commission on collected AFN net sales after returns, excluding tax. Dr COMMISSION / Cr PAYROLL; payment uses the existing payroll settlement and employee statement. Fixed wage accrual remains separate. Wholly unpaid earnings can be reversed; paid clawbacks are blocked. |
| 8. Quality cases/recall | `?view=dispatch`, Quality claims / recalls | Track customer complaints against actual invoice lines, block/batch lineage when known, decisions and linked original returns/replacement invoices. A scoped recall holds recorded descendants and conservatively holds pooled products. Closing the campaign does not silently release ordinary quality holds or material lots. |
| 9. Furniture/custom jobs | `?view=jobs` | Separate business project records, immutable estimates, unique whole-document actual-cost associations, recognized profit with WIP/clearing shown separately, approved nested BOM requirement snapshots, and subcontract records linked to actual company-owned vendor stock transfers, processing bills and production/finished return receipts. |
| 10. Onboarding/recovery | `?view=onboarding`; recovery command | Guided use of existing setup, CSV preview/import and opening operations. A guarded restore drill creates only a fresh local `restore_*` database, verifies snapshot/attachments and reconciles each ledger. The configured backup destination remains deliberately absent. |

## Important workflow examples

**Cutting:** a sales order for 6.6 cm may be reviewed as three 22 mm sheets. The planner never invents the sheet dimensions from the grade name. Cutting changes the parent once and produces held child sheets. Invoicing them consumes the children and fulfills the original order, without another parent cut. A plan can combine customer demands, but each invoice belongs to one customer order.

**Factory:** plan an output quantity, start its WIP batch, enter the materials actually consumed, then complete measured blocks/adhesive. Record additional materials before the first completion. The card derives posted output and cost availability from real events; recording time is not a wage posting. A cancelled customer order prevents new work, while completion of already-costed WIP remains possible under existing controls.

**Foreign money:** the integrated foreign invoice freezes original foreign line amounts, transaction rate and AFN amounts. A later receipt settles the foreign quantity at its actual approved rate; exchange differences are separate. Only explicitly refundable **monetary** credits are supported. Nonmonetary goods advances need historical-rate consideration and are rejected by this workflow.

**Late freight:** a real 100 AFN supplier bill first debits COST_CLEARING and credits AP. An accountant may allocate 60 to remaining stock and 40 to sold COGS using documented evidence. Remaining stock quantity is unchanged, value rises 60, COGS rises 40, clearing falls 100. Paying the linked supplier bill clears AP. This does not automatically replay historical weighted-average costing or calculate the accountant's allocation evidence.

**Commission:** collected eligible net sales of 10,000 AFN at 2% accrue 200 AFN commission. Wages owed rise 200; cash changes only when paid. A return reduces the calculated entitlement and produces a review exception. The app never silently takes previously paid wages from the employee.

**Furniture job:** link dedicated purchasing, production, expenses and sales to a project. Its ledger profit counts recognized income minus expenses/COGS. Raw material consumed into WIP and then finished stock is not also expensed a second time. Documents serving several jobs must be split before posting; arbitrary retrospective percentage tagging is not provided.

## Scope and rollout limits

- Cutting is best-fit decreasing, not a guaranteed global optimum. Full-face sheets and compatible footprints remain required. Physical measured requirements still need operator review.
- The factory board is a task interface over daily work-center planning; it is not an automatic finite-capacity scheduler, machine telemetry system or time-clock payroll engine.
- Cross-currency settlement, nonmonetary foreign goods advances, foreign supplier price-only cost credits, and unrestricted monetary history corrections are not supplied. A settlement can be reversed only with exact inverse journal/subledger movements and supported latest-event chronology.
- Late costs are explicit current-period allocations backed by a real bill, not historical replay. WIP targets with completed output, active inventory allowances and unsuitable sources are rejected. Product provenance is a conservative candidate check; exact attribution percentages need accountant evidence. Foreign sold-cost return integration is restricted.
- Commission policy currently supports AFN sales and wholly unpaid reversals. Percentage plans are explicit dated versions; contractual payroll/tax policies still require approval. Paid commission clawbacks need a separately reviewed workflow/agreement.
- Subcontract steps validate and associate original posted documents; they do not manufacture stock through checklist completion. Nested BOMs create approved requirement snapshots; they do not automatically schedule/post every subassembly batch. BOM remains hidden/disabled for the sponge company's actual-consumption mode.
- Offline proposals are optional local encrypted notes, not an offline ledger. Passphrases are never stored; lost passphrases cannot be recovered. Keep encrypted exports securely. Browser storage can be erased by the user/device. Static app-shell caching is opt-in on the built app only and never caches API/admin/private-document responses.
- Restore evidence is local/same-machine only. Scheduled backup destination configuration and off-device recovery remain pending by the owner's explicit choice. No startup task, public deployment, paid service or external messaging was activated.
- Native Dari/Pashto editorial/accountant review, physical printer/device acceptance and production-scale performance/security review remain rollout work. No ACCA, IFRS or QuickBooks product certification is claimed.

## Source and operator commands

Domain modules: `order_cutting.py`, `factory.py`, `foreign_extensions.py`, `dispatch.py`, `jobs.py`, `commissions.py`, `late_cost.py`. Read endpoints use the same business/location/product/document scopes as the source operations. New models have PostgreSQL tenant/history guards; foreign compensation has exact multiset journal and subledger validation.

Recovery drill (new target only):

```powershell
.venv/Scripts/python.exe scripts/recovery_check.py --input .local/backups/pre-expansion-finalization-20261102.fernet --database restore_expansion_20261102 --migrate
```

That exact target already exists after verification. Choose a new `restore_*` name for a future drill; existing/active databases are never overwritten. Private evidence is written under `.local/recovery-checks`.

Both account manuals are updated to 65 accounts and 133 registered operations. English and Afghan Dari editable sources and PDFs remain separate; rebuild and verify both after future accounting changes.
