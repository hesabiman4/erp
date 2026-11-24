# Operations release v4

This increment implements the four recommended next-release areas. All use real PostgreSQL records and existing business isolation. Financial posting remains in `core.execute` / `core.journal`.

| Workspace | Open | Operating guide |
|---|---|---|
| Cashier shifts | `/operations?view=cashier` | [Cash custody](CASHIER_SHIFTS.md) |
| Statement imports | `/operations?view=statements` | [Statement evidence and matching](STATEMENT_IMPORTS.md) |
| Supplier quotation comparison | `/operations?view=sourcing` | [Supplier quotations](SUPPLIER_QUOTES.md) |
| Release and recovery management | `/operations?view=runtime_management` | [Local release management](RUNTIME_MANAGEMENT.md) |

Cash custody uses one full AFN location pool, frozen counts, explicit reviewed variances and accepted handovers. Statement imports retain original evidence, require explicit mappings, flag duplicates and match existing AFN BANK entries without creating artificial payments. Saraf statements are evidence only. Supplier awards create one real purchase order; receipts, bills and payments continue through their normal posting flows. Runtime diagnostics are read only; local operator tools handle reviewed builds, snapshots and forward migrations.

New dedicated permissions must be assigned deliberately. Existing restricted memberships receive no automatic access. All cost, raw-material, payroll, location and product scopes continue to apply.

Other suggested competitive features, including OCR, broader forecasts, CRM, hardware integrations and expanded training, remain outside this four-area release. See implementation status and verification for tested scope and remaining acceptance limits. Backup destination configuration remains deferred by the owner.
