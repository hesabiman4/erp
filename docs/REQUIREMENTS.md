# Acceptance traceability

Authoritative source: ERP_AI_CODER_MASTER_PROMPT.md. This maps A01–A32 to implemented independent checks; release limits remain in IMPLEMENTATION_STATUS.md.

| ID | Behavior | Evidence |
|---|---|---|
| A01 | Grade label is not weight | Exact-cut and label-geometry tests |
| A02 | 22mm=2.2cm; 1000mm→978mm | Domain/API tests and browser cut |
| A03 | Multiple sheets/mm/cm/local numerals | Unit, precision, sheet-count tests |
| A04 | Separate cutting loss | Configured loss and rollback tests |
| A05 | 9000−50=8950cm | test_exact_9000_cm_manufacturing_accounting_cycle |
| A06 | Remnants cannot virtually join | Fragmented-stock rejection test |
| A07 | Different footprints separate | Unlike-footprint pool tests |
| A08 | Atomic concurrent cuts/retries | Threaded PostgreSQL and idempotency/conflicting retry tests |
| A09 | Actual production, no required BOM | Actual-cost/batch and consumption privacy tests |
| A10 | Issue vs consume vs unused floor return | Material/WIP tests |
| A11 | Trimming conservation | Main/top/bottom/loss geometry and cost tests |
| A12 | 130000 cost conserved | Actual production/loss/by-product/COGS fixture |
| A13 | Partial payments/deposits | Finance/API and 5000/3500/1500 browser flow |
| A14 | Full manufacturing accounting example | Independent 200000 cost→9000cm→sale/transfer/BS/stock fixture |
| A15 | Carrying-cost transfer and receipt | Partial/discrepancy/identity/warehouse-average/recipient tests |
| A16 | Internal charges exclude external revenue | Charge/adjustment tests and browser before/after sales |
| A17 | Advance below salary | 12000 advance+8000 net salary settlement fixture |
| A18 | Advance above salary | 25000 less20000 earnings leaves5000 asset fixture |
| A19 | Returned sheet separate at issued cost | Returned-sheet and impaired-return tests |
| A20 | Net-kg adhesive | Exact decimal production/sale/return tests |
| A21 | Business/location/line/field isolation | API, reports, labels and database reference tests |
| A22 | Atomic rollback/balanced journals | Late failure, immutability, inventory/GL and concurrency tests |
| A23 | Frozen postings/periods/snapshots | PG triggers and historical price/tax/BOM tests |
| A24 | Receipt before bill/payment/return | GRNI, partial bills, supplier deposit and returns tests |
| A25 | Optional approved BOM in other business | BOM isolation/version snapshot tests |
| A26 | Reviewed openings/reconciliation | Opening, financial fixture, fresh install/double seed |
| A27 | Dari RTL real UI/print/mobile | Playwright screenshots/PDFs; secondary-language limits explicit |
| A28 | Install/restore/private attachment | verify_fresh_install.py, backup.py, verify_restore.py |
| A29 | Sessions/CSRF/MFA/throttle/revocation | Dedicated API security tests |
| A30 | Optional FX/replay boundaries | Unsupported FX/backdating rejected; general replay disabled |
| A31 | Monthly/daily/hourly/project earnings | Attendance/rates/approval/advances and earning-window tests |
| A32 | Warehouse average/NRV | Warehouse transfer and capped impairment/reversal/return tests |

Additional checks cover mixed-document privacy, supported payment reversals, private CSV/import retries, separate approvers, stale stock counts, backed shared-cost allocation and source-backed labor/overhead absorption.

Native Docker execution, full secondary-language review, production printers/hardware, legal/tax setup and real opening balances are not established by these local passing tests.
