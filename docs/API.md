# HTTP API contract

Employee/financial extensions (2026-10-29): `/api/catalog/departments/` and `/api/catalog/positions/` support scoped GET/POST/PATCH. Reads share employee payroll authorization; edits use payroll.manage/settings.manage. Employee fields include code, contact/identity/emergency/organization/employment/payment details. Nullable organization/end dates can be cleared. Both API and PostgreSQL validate tenant references.

Weekly payroll_accrue accepts employee, week_start_date, posting date, account/line and optional approved gross/reason. It derives a seven-day window and rejects early, misaligned or overlapping weeks. Earning dates are authoritative; the month identifier remains a compatibility field. Explicit hourly coexists with legacy part-time/hourly terms. Contract/rate history restrictions remain server-side.

`chart_of_accounts` and `changes_equity` require accounting.view. Balance sheet/P&L retain flat rows/totals and add statement/sections/subtotals. compare_from/compare_to add a separately scoped comparative result to profit_loss/balance_sheet/changes_equity. CSV adds comparison_amount. Company balance/equity requires full company scope and ignores the operational header location; explicit unsupported branch parameters fail.

All state-changing calls use same-origin session cookies plus `X-CSRFToken` from `/api/session/`/the `csrftoken` cookie. All business calls require `X-Business-ID`. `X-Location-ID` narrows operational lists/reports; a complete company trial balance/balance sheet intentionally uses full-business scope. Download/print links accept `?business=<id>` and still revalidate membership. Query parameters never substitute for authentication.

Exact decimals are JSON strings; dates are `YYYY-MM-DD`. Nonfinite/binary-float stock or money inputs are rejected. Unsupported foreign currencies and cutting geometries fail explicitly.

## Discovery and records

| Endpoint | Behavior |
|---|---|
| GET/POST `/api/session/` | Session/CSRF discovery or password/TOTP login |
| POST `/api/logout/` | Revoke current session |
| GET `/api/context/` | Assigned businesses and effective membership settings |
| GET `/api/schema/` | Live action names and permission identifiers available to the current member |
| GET `/api/catalog/` | Scoped locations, warehouses, products, customers/suppliers, employees, accounts, BOMs, assets, tax rules |
| POST/PATCH `/api/catalog/<resource>/[id/]` | Authorized master-data creation/update; stocked units and used account classification are protected |
| POST `/api/businesses/` | Create a separate business with its own chart/owner membership |
| GET `/api/stock/` | Scoped cost-redacted pools and dimensioned blocks; total on-hand and available quantities differ |
| GET `/api/documents/?kind=&q=&limit=&offset=` | Scoped document search/pagination with count/next_offset |
| GET `/api/documents/<id>/` | Authorized immutable document, result, current balance, attachment references |
| POST `/api/documents/` | Save `{kind,data}` as a nonfinancial draft |
| PATCH `/api/documents/<id>/` | Edit draft data only |
| POST `/api/documents/<id>/post/` | Idempotently convert draft into a posted event |
| POST `/api/operations/<action>/` | Atomic domain posting; required unique `Idempotency-Key` |
| GET/POST `/api/approvals/` | Review queue or submit `{kind,data}` |
| POST `/api/approvals/<id>/` | Approve, or `{reject:true,reason}`; distinct approver by default |
| POST/GET `/api/attachments/[id/]` | Private validated upload/download |
| GET `/api/documents/<id>/print/` | A4 or `compact=1` document; `copy=1` labels a reprint |
| GET `/api/blocks/<id>/label/` | Authorized printable physical block label with SVG QR |
| GET `/api/reports/<name>/` | Real-ledger reports; date/location/line filters validated per report |
| GET `/api/export/<name>/` | Authorized CSV with formula-injection protection |
| GET/POST `/api/import/products/` or `/parties/` | Columns/preview/validated commit, no balance effects |
| POST `/api/security/<action>/` | Password, session revocation, TOTP setup/confirmation |

## Representative posting payloads

Retrieve IDs from authorized catalog/stock endpoints. These are synthetic examples, not production formulas.

```json
{
  "warehouse": 1,
  "inputs": [{"product": 4, "quantity": "100"}],
  "outputs": [{"product": 11, "blocks": [
    {"length_mm":"2000", "width_mm":"1000", "height_mm":"1000"}
  ]}],
  "labor_cost":"0", "overhead_cost":"0"
}
```

`production` consumes actual inputs. Nonzero conversion costs require eligible posted `conversion_sources`. `production_start`, `production_consume`, `production_material_return`, and `production_complete` support staged WIP. `bom` is optional only when the business enables BOM mode, and selects an approved immutable version.

```json
{
  "warehouse": 2, "customer_name":"Walk-in", "phone":"0700000000",
  "lines":[{"product":11, "block":1, "thickness_mm":"50", "sheet_count":1,
    "unit_price":"1000"}],
  "paid":"3500"
}
```

`sale` combines confirmed delivery, final invoice, inventory/COGS and immediate payment atomically. `thickness_cm` or `{thickness,thickness_unit}` are alternative validated inputs. Price overrides, discounts and credit require their own permissions. Exact block availability is rechecked on posting.

```json
{"location":2,"invoice":15,"amount":"1500","cash_account":"CASH"}
```

`receipt` collects against existing debt; it does not post revenue again. `allocations:[{invoice,amount}]` can settle several same-party invoices. Excess becomes customer credit. `payment_reverse:{payment,reason}` supports reviewed full receipt/supplier-payment correction with compensating allocations; used deposits/unsupported downstream credit effects prevent reversal.

```json
{"warehouse":2,"destination":3,"lines":[{"product":11,"block":1,"quantity":"100"}],"internal_charge":"3000"}
```

`transfer_dispatch` preserves carrying cost and physical identity through transit. `transfer_receive:{transfer}` receives all outstanding stock; optional `lines:[{index,quantity}]` acknowledges partial quantities. A physical block is received in full. Internal charge is management-only.

`payroll_accrue:{employee,period}` uses approved terms/attendance. Hourly part-time workers use `terms.rate_basis="hour"`. Overrides and deductions need approval. `payroll_settle:{payroll,advance_recovery,amount,cash_account,location?}` never pays negative wages.

`stock_count` records immutable observed quantity/height; `stock_count_adjust` requires the count ID/reason, rejects stale observations, and posts separately approved variance. `shared_cost_allocate` links an ordinary shared expense to documented product-line driver weights without new company expense/cash.

## Failure and retry semantics

- 400: invalid quantity/date/reference, insufficient stock, closed period, unsupported workflow, or failed reconciliation.
- 403: missing business/location/product-line/action/sensitive-data/approval permission.
- 409: uniqueness/protected-record conflict.
- 429: login throttling.

Domain failures roll back document, stock, allocations, journals, and audit creation together. Retrying the identical action/payload/key returns the original document. Reusing a key with different data fails. Posted documents cannot be silently edited/deleted.

Live action discovery is authoritative for current supported endpoints. Source-level payload validation resides in `operations.py`, `finance.py`, `corrections.py`, and `administration.py`; automated fixtures provide independently expected balances.


Setup readiness is available at GET /api/setup/; POST records an authorized internal review reference, not certification. Initial opening cash/receivables/payables/employee advances use accounting.opening; stock uses the approved stock_opening workflow. Bank reconciliation choices come from GET /api/bank-entries/ with location/date scope, payroll detail restrictions and whole-document product permissions. New employee rate configuration requires effective_date; daily/hourly workers can accrue and settle new, nonoverlapping attendance windows before month end, while monthly salary remains month-end based. Internal managerial charge changes use internal_charge_adjust with an approved signed amount; reductions cannot exceed unpaid internal debt.

## Account-center read reports

- `GET /api/reports/customer_balances/?to=YYYY-MM-DD&q=...` requires sales.view; supplier_balances requires purchases.view. Returns business address-book rows with scoped AR/AP balance, separate deposits and overdue debt. Start date does not discard old debts.
- `GET /api/reports/customer_statement/?party=<id>&from=YYYY-MM-DD&to=YYYY-MM-DD` requires sales.view; supplier_statement requires purchases.view. Returns the selected party, control-account activity, opening/closing/deposit totals and linked open invoices. Wrong-business/wrong-kind parties fail. Product-line filtering of complete party debt is rejected.
- Existing report export additionally requires reports.export; the UI includes business, location, party and dates in the URL. UI print is offered with documents.print. The existing API enforces financial/tenant scope independently of navigation.
- The dashboard now includes permission-controlled profit and a seven-entry `sales_series` from the posted SALES ledger for seven days through the report end date. Zero-day values derive from the absence of scoped postings; query errors remain HTTP errors. These reports do not mutate stock or journals.
