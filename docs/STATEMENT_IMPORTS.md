# Statement imports and reviewed matching

Open **Operations & planning → Statement import and matching** (`?view=statements`). This workflow imports external evidence into PostgreSQL. Uploading, matching or verifying evidence never creates cash, supplier debt, revenue, expenses or stock. A missing fee/payment must be recorded through its existing authorized transaction workflow.

## Supported source files

- CSV in UTF-8 (including BOM) or BOM-marked UTF-16; comma, semicolon and tab delimiters.
- XLSX with exactly one values-only worksheet. The bounded standard-library parser reads text and numeric values without executing formulas. Formula cells, macros, external workbook links, XML entities, encrypted archives, unsafe expansion and invalid paths are rejected. No third-party spreadsheet engine or external service is required.
- At most 2 MB source size, 1,000 transactions and 60 columns. The source bytes, filename, hash, period metadata and normalized original rows are preserved in PostgreSQL and covered by the database backup. Source content is not echoed in generic document JSON/print; a separately authorized attachment download returns the original file.
- Supported statement currency is **AFN**. A selected location and specific institution/account reference are mandatory. Foreign statement matching, bank feeds and live bank/saraf connections are not implemented.

Example CSV:

```csv
date,reference,description,amount
2026-06-01,FEE-1,Bank fee,-200.00
2026-06-02,DEP-1,Customer deposit,300.00
```

For this example, opening balance 1,000 plus net movements 100 equals closing balance 1,100 AFN. An `amount` column is signed from the account owner's perspective: deposits positive, withdrawals negative. With separate columns, **credit = deposit** and **debit = withdrawal**; this describes an external bank statement, not the company's debit/credit journal sides. Choose one amount method and map the columns explicitly if the supplier's export uses different headings.

Date formats are explicit: YYYY-MM-DD, DD/MM/YYYY or MM/DD/YYYY, with Gregorian or Jalali numeric dates. Canonical ledger dates remain Gregorian. Excel serial dates use the workbook's 1900/1904 calendar; fictitious Excel day 60 is rejected. Ambiguous timestamps, missing dates and impossible calendar dates are rejected. Money uses exact Decimal values with two places and is never silently rounded.

## Import and duplication

1. Select institution, source type, location, account reference and exact period/opening/closing balances.
2. Choose the original CSV/XLSX file and preview it. Map nonstandard columns, then preview again.
3. Verify that every signed transaction is included. Opening balance plus all transactions must equal closing balance. A missing fee cannot disappear into an unexplained adjustment.
4. Commit the source evidence. The server reparses and revalidates the original file. Safe retry uses the same idempotency key; a changed payload cannot reuse it.

Exact repeated transactions are rejected within a file and across overlapping files for the same normalized institution/account/location/source type. Matching ignores superficial reference/description letter case and repeated spacing. Legitimately identical transactions need their real distinct bank reference; the system does not invent transaction identifiers or silently discard one row. Statement and transaction snapshots cannot be rewritten/deleted through ordinary database or application access.

## BANK matching and reconciliation

Bank imports use the existing **BANK** control account and a selected AFN bank instrument at the chosen location. Multiple registered physical bank accounts at one location have independent balances and matching. Select the actual bank instrument at import/reconciliation; its immutable institution/account reference must match the external statement. Ambiguous selection is rejected. Legacy unbound statements retain their original legacy pool and identity rather than rewriting historical entries. New instrument registration creates no opening money; use a real transfer to allocate existing funds. Saraf evidence-only files remain separate from BANK and do not create a saraf ledger. See DAILY_CONTROLS_V6.md.

The detail screen suggests already posted BANK entries with the exact signed amount, a ledger date inside the statement period and no more than seven days from the bank date. Reference agreement and date distance help order suggestions. A human must select the actual entry and record evidence; no candidate is posted or automatically matched. Ambiguous or missing candidates remain explicitly unresolved.

One ledger entry can have only one active statement match. A correction releases the old match through a separate immutable review event and preserves its reason before another match is allowed. Other evidence reviews remain in history. Cross-business, wrong-location, wrong-account, wrong-amount and ineligible-date matches fail.

Finalization requires:

- Every statement transaction has a match.
- Every actual BANK ledger entry for the selected instrument in the period is matched exactly once, including offsetting transactions that would otherwise disappear in a net total.
- The selected instrument ledger before the period agrees exactly with the statement opening balance.
- The existing `bank_reconcile` operation receives **all** historical BANK entries through the statement end, including original opening entries, and agrees exactly with the closing balance.

Finalization records an evidence link to that real reconciliation; it creates no journal. The statement is then sealed against rematching. Unresolved timing differences must remain open in this strict workflow; automatic suspense/fee postings, many-to-one matching, splitting one ledger entry across transactions, multiple bank-control accounts and negative-closing/overdraft reconciliation are not implemented. Negative statements can still be imported and reviewed as evidence; finalization rejects the unsupported negative document amount clearly.

## Saraf boundary

**Saraf imports are AFN evidence only.** Staff can preserve source rows, record explanations and mark a row's evidence verified. This does not create a BANK entry, saraf payable/receivable, exchange, remittance, or reconciliation. The separate tested foreign-wallet/hawala workflows remain authoritative for supported foreign monetary events. A saraf paper statement must not be relabeled a bank statement merely to force it into BANK.

## Permissions and isolation

Reading requires `finance.view`, `payroll.view`, the selected location, and complete product-line visibility or `documents.all_lines`, because external statements can contain payroll and every product line. Uploading/reviewing/finalizing additionally requires **`finance.statements`**; finalization also requires the existing **`finance.post`** reconciliation authority. Actual ledger candidates retain their source-document permissions. The service refuses an incomplete candidate ledger rather than silently omitting inaccessible rows and calling the remainder a complete reconciliation.

Permissions apply to list, detail, source download, generic document JSON/print, and every operation. Raw source bytes are private database evidence. The staff membership of the current business is checked for every request; customer portal accounts gain no access. New permissions are not silently assigned to existing staff.

## Source map and API

- `statement_models.py`, migration `0026_statement_imports.py`: source evidence, exact original transactions, review events, active matches and reconciliation links; tenant, history, unique-match and exact-match database guards.
- `statement_imports.py`: bounded parsing, preview, normalized duplication, review and exact reconciliation domain services.
- `statement_api.py`: `/api/statements/imports/`, `/detail/?id=…`, `/source/?id=…`, multipart `/preview/` and `/commit/`.
- Operations: `statement_import`, `statement_review`, `statement_reconcile`. All execute through `core.execute`; only the existing reconciliation is invoked, with no new ledger.
- `frontend/src/statement-imports.tsx`: upload mapping/preview, source list, exact candidate review and preserved history.

Production-scale performance and actual bank/saraf export acceptance still need representative files. No live institution integration or statement/accounting certification is claimed.
