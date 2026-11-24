# Performance evidence and acceptance limits

The v5 benchmark runs only against the project loopback PostgreSQL cluster and a named `verify_*` database. It creates a separately labelled synthetic workspace using actual ordinary opening-stock, sale and draft workflows. It never fabricates posted records or resets the active database. Retain the same dataset parameters when rerunning an existing benchmark workspace; use a fresh isolated database for a different dataset.

```powershell
.venv/Scripts/python.exe scripts/benchmark_workflows.py --database verify_ui_20261029 --products 400 --sales 200 --drafts 1000 --blocks 100 --runs 5
```

Measured dataset: **401 products, 200 posted sales, 1,000 ordinary drafts, 100 blocks and 1,203 journal lines**. Every financial report in the benchmark reconciles. The before/after evidence has identical dataset counts and financial results.

| Read workflow | Median seconds after change | Maximum SQL queries |
|---|---:|---:|
| Personal workspace | 0.3106 | 56 |
| 20-invoice page | 0.3798 | 146 |
| Physical counter availability | 0.0250 | 9 |
| CRM page | 0.0270 | 9 |
| Trial balance | 0.0249 | 6 |
| Inventory reconciliation | 0.1623 | 9 |

Inventory reconciliation previously used409 queries with median0.8594s on the same dataset. It now groups historical movement by pool once, preserving the as-of date, permissions, moving-average values and complete control totals. The response remains85,062 bytes in this fixture. This specifically fixes query growth with pool count; other report and invoice-list optimizations remain possible.

Measurements ran on one local machine alongside other verification work. They are descriptive evidence, not statistical service-level commitments, hardware specifications, production concurrency claims or a guarantee that every screen became faster. SQL capture is cleared before each sample; an earlier saturated debug query log was rejected and rerun rather than reported as zero-query performance.

Operational modules that can be separated load on demand. Shared form dependencies still belong to the main bundle; Vite's large-chunk/static-and-dynamic import warnings remain visible. The app does not claim complete bundle optimization.

`workflow-performance.spec.ts` supplies an explicitly enabled read-only built-runtime journey with browser network emulation:200ms latency,384,000B/s download and192,000B/s upload. The final sealed-build check passed:6,952ms for open/refresh/Back, with zero financial mutations (usability-slow-network.json). The journey opens, refreshes and returns from a full document page; it does not simulate branch-level concurrency or offline posting.

Use [STAFF_ACCEPTANCE.md](STAFF_ACCEPTANCE.md) for actual staff, device, Dari/Pashto and representative document-layout acceptance. Human acceptance remains unperformed; automated QA does not prefill it.
