# NAWA — Afghanistan tax research and confirmation register

Research date: **2026-11-22 (Asia/Kabul)**. Phase 1 research is retained below; the owner subsequently approved Phase 2.

No tax code, rules, seeds, return, account balance or payroll was changed during Phase 1. Legacy `TaxRule` remains a separate generic invoice-percentage rule; its fields and prior posting behavior are preserved. The approved implementation adds separate `TaxSchedule` revisions and `TaxScheduleChange` review history rather than changing the meaning of old invoice tax IDs.

## Implementation checkpoint — rule administration

Migration `0035_versioned_tax_schedules` adds the versioned schedule/history tables, confirmation flags, source/retrieval metadata, exact percentage/bracket data, currency/rounding policy, revision linkage and database guards. New schedules are unconfirmed; existing revision content cannot be edited or deleted, and confirmation changes require matching retained review events. Settings provides a structured Dari-first form, source/date display, exact calculation preview, confirmation/revocation with reason, amendment creation and history. English/Pashto copy and RTL are retained.

`backend/erp/data/afghan_tax_research_20261122.json` contains five **unconfirmed research candidates** (old/new monthly salary, ordinary/mining CIT, import advance income tax). `seed_tax_schedules` requires an explicitly named business and assigned actor; its default is dry run. No BRT/VAT/import-BRT rate is guessed, no rule is imported into the main business automatically, and no rule is activated by migration. The old salary candidate deliberately covers only the research window 2026-01-01 through 2026-07-10; the first date is **not** a claim about legal commencement. Earlier assessment periods need their own evidenced revision.

This is rule administration and nonposting calculation support. Automatic invoice/payment/payroll tax, BRT returns/import-credit application and withholding certificates remain incomplete. Confirming a schedule does not enable those features. The admin guide is [docs/TAX_SCHEDULE_ADMIN_GUIDE.md](docs/TAX_SCHEDULE_ADMIN_GUIDE.md). Current verification and application status are in [AUDIT.md](AUDIT.md); this research register does not claim the entire tax engine is complete.

## Findings that change the proposed baseline

- July 2026 reform is supported by a current government announcement and implementation guidance; an old guide displaying 20% corporate tax or the old salary schedule cannot be treated as current for every assessment.
- Government announcement supports ordinary corporate income tax of **10%**, with **mining at 20%**, subject to the reform's transition/application rules. Historical assessments must not be automatically recalculated. [Government Media and Information Center, 12 July 2026](https://www.gmic.gov.af/en/news_details/243).
- The scanned implementation guidance identifies an import collection of **2% as advance income tax credit**. That is distinct from an advance **BRT** credit. The requested blanket “4% of imports as advance BRT” was **not verified**. Separate levies may coexist on a customs document; identify the actual legal credit type before posting. [Ministry/ARD implementation guidance, PDF page 12 / printed page 8, practitioner-hosted copy](https://questfinancial.af/wp-content/uploads/2026/07/Guidelines-on-the-Application-of-Tax-Reliefs-and-Adjustments_July_2026.pdf).
- BRT is not profit tax, but the phrase “gross receipts” alone does not establish that every taxpayer uses cash collections rather than taxable gross income under the relevant accounting rules. Historical law distinguishes corporate accrual accounting from other cash accounting cases. The tenant's assessed basis and treatment of deposits, credit sales and refunds need confirmation. [Historical Income Tax Law, articles 37–38 and 64](https://momp.gov.af/sites/default/files/2019-03/Income_Tax_Law.pdf).
- A statutory 10% VAT rate is documented. That is **not evidence of current commencement or this tenant's VAT obligation**. Current implementation/deferment could not be conclusively verified from an authoritative commencement notice in this research. Proposed default remains disabled pending confirmation. [MoF amended VAT law](https://www.mof.gov.af/sites/default/files/2021-03/VAT%20%28Value%20Added%20Tax%29%20LAW%20-%20Amended%20with%20OG_1244.pdf).

## Source register

Every retrieval/check date below is **2026-11-22**. Publication date and retrieval date are different. An old document that is still downloadable or recently crawled is not a current rate update.

| ID | Source / URL | Authority and access | Supported scope / limitations |
|---|---|---|---|
| S1 | [MoF tax-reduction announcement, GMIC, 2026-07-12](https://www.gmic.gov.af/en/news_details/243) | Government-hosted current announcement; read | Confirms 2026 reductions, corporate/mining distinction and annual personal-income changes. Announcement is not a full implementation/transition manual. |
| S2 | [Guidelines on application of tax reliefs/adjustments, July 2026](https://questfinancial.af/wp-content/uploads/2026/07/Guidelines-on-the-Application-of-Tax-Reliefs-and-Adjustments_July_2026.pdf) | Scanned Ministry/ARD government content **hosted by Quest**, not an official-host retrieval. Downloaded; **all 12 PDF pages visually inspected**, including final-page enlarged view. | Salary tables, corporate changes, implementation timing/examples, advance income-tax treatment. Government-content attribution does not certify the chain of publication; retain copy and obtain ARD/accountant confirmation before activating rules. |
| S3 | [Income Tax Law, English PDF](https://momp.gov.af/sites/default/files/2019-03/Income_Tax_Law.pdf); [alternate archived copy](https://questfinancial.af/wp-content/uploads/2024/08/Income-Tax-Law_English_2009.pdf) | Historical English translation hosted by government / practitioner | Historical accounting basis, tax year, BRT and withholding framework. Does not incorporate all 2026 changes; English translation is not controlling Dari/Pashto law. |
| S4 | [MoF guide directory](https://mof.gov.af/index.php/en/guides); [Guide 03 BRT archive link](https://mof.gov.af/sites/default/files/2019-03/Guide%2003%20-%20Business%20Receipts%20Tax-min.pdf) | Official directory/search-indexed historical guidance; old direct links were not consistently retrievable | Historical 2%/5%/10% classifications and import-credit language are discovery evidence, **not proof of today's general BRT rate**. Do not seed from snippets. |
| S5 | [MoF Guide 05 — Wage Withholding Tax](https://mof.gov.af/sites/default/files/2019-03/Guide%2005%20-%20Wage%20Withholding%20Tax-min.pdf) | Historical official guidance | Paid-month remittance framework. Its old salary brackets are superseded where new reform applies. Current deadline applicability still needs filing confirmation. |
| S6 | [MoF Guide 21 — Contractor Services WHT](https://mof.gov.af/sites/default/files/2019-03/Guide%2021%20-%20Withholding%20Tax%20on%20Contractor%20Services-min.pdf) | Historical official guidance | Licensed/unlicensed 2%/7% framework. Thresholds, license validity, exemptions, timing and current applicability require confirmation. |
| S7 | [MoF Guide 04 — Tax Overview](https://mof.gov.af/sites/default/files/2019-03/Guide%2004%20-%20Tax%20Overview%20for%20Businesses%2C%20Investors%20%26%20Individuals-min.pdf) | Historical official guidance | Background on rent/other withholding; cannot alone establish unchanged November 2026 rules. |
| S8 | [MoF amended VAT law, OG 1244](https://www.mof.gov.af/sites/default/files/2021-03/VAT%20%28Value%20Added%20Tax%29%20LAW%20-%20Amended%20with%20OG_1244.pdf) | Official law PDF | Statutory rate/readiness; no verified current commencement notice found. |
| S9 | [Quest — detailed new tax-rate guide, 2026-07-26](https://questfinancial.af/afghanistans-new-tax-rates-a-detailed-guide-for-businesses-and-individuals/) | Current practitioner explanation; read; secondary authority | Corroborates salary/CIT changes, transition nuances, commonly 4% BRT and unchanged rent treatment. Useful interpretation, not a tenant's tax ruling. |
| S10 | [Quest — contractor withholding gross-up, 2026-11-15](https://questfinancial.af/contractor-withholding-tax-gross-up-method/) | Current practitioner search/retrieval evidence; secondary | Supports continued 2%/7% contractor practice; not an official amendment or confirmation of all exemptions. |
| S11 | [Kakar Advocates taxation resources](https://kakaradvocates.com/practices/taxation); [Tax Administration Law translation](https://kakaradvocates.com/uploads/laws/translation-Tax%20Administration%20Law%20-%20En.pdf) | Practitioner resources / historical law | Practice page and historical-law links found; no complete 2026 rate/application bulletin established from these pages. |
| S12 | [PwC Afghanistan tax-summary path](https://taxsummaries.pwc.com/afghanistan) | Checked; current chapter unavailable at this path (404) | Older compiled summaries found in search are not accepted as 2026 verification. No current PwC Afghanistan summary is claimed as consulted evidence. |
| S13 | [Amu Elite](https://amuelite.com/) | Targeted search attempted | No sufficiently authoritative accessible 2026 rule source was established in this research. No rate is attributed to this source. |

Private working copy of S2: `.local/audit_20261122/tax-relief-2026.pdf`, 12 pages, SHA-256 **3b9fbdf5aed59c9377d41811577687a891f5bd4afcdfbf3ab810826bb7350463**. The cover/forwarding letters precede eight printed guidance pages. PDF page numbers below count from 1, including those letters. This digest identifies the reviewed copy; it is not an authenticity signature.

## Monthly salary schedules to model after approval

`x` below means the confirmed monthly taxable AFN amount. Formula intervals use inequalities so fractional AFN values are not left between integer-looking brackets. Calculation precision and final remittance rounding need an explicit approved policy.

| Version | Monthly taxable amount x | Tax formula | Source |
|---|---|---|---|
| OLD | 0 ≤ x ≤ 5,000 | 0 | S2 PDF page 6 / printed 2; historical S3/S5 |
| OLD | 5,000 < x ≤ 12,500 | (x − 5,000) × 2% | Same |
| OLD | 12,500 < x ≤ 100,000 | 150 + (x − 12,500) × 10% | Same |
| OLD | x > 100,000 | 8,900 + (x − 100,000) × 20% | Same |
| NEW | 0 ≤ x ≤ 10,000 | 0 | S2 PDF page 7 / printed 3 |
| NEW | 10,000 < x ≤ 100,000 | (x − 10,000) × 10% | Same |
| NEW | x > 100,000 | 9,000 + (x − 100,000) × 15% | Same |

S2 PDF page 11 / printed 7 identifies **1448/01/25 lunar = 1405/04/20 SH = 2026-07-11 Gregorian** for implementation. Earlier-period filings and finalized assessments are treated differently in the examples. This is **not safely reducible to “earning date before cutoff → OLD; after cutoff → NEW.”** Selection must retain assessment/filing context and an authorized schedule override with evidence and reason. S9 provides further practitioner explanation; taxpayer-specific treatment remains a confirmation item.

The reviewed guidance also contains daily and annual tables. A monthly engine must not invent daily brackets by dividing monthly thresholds by 30 or applying a display-calendar change to prior payroll. The requested first scope is monthly salary calculation plus approved override; additional payroll frequencies need confirmed conversion/application rules.

## Confirmation register for future rule data

These are **applicability/activation decisions**. The research importer now enforces `requires_confirmation = true` for every imported revision; confirmation requires the assigned reviewer, reason and retained history. A numerically supported rate can still be inapplicable to this tenant. The register includes unresolved rule families that are deliberately absent from the research seed file.

| Rule family | Research position | Confirmation / activation decision |
|---|---|---|
| Salary OLD / NEW | Tables above supported by S2; transition is filing/assessment-sensitive | Confirm taxable components, paid/earned/filing dates, applicable schedule and override privilege. Retain OLD for legally required historic assessments. |
| Corporate income tax | Current ordinary 10%; mining 20%, supported S1/S2 | Confirm legal form, sector, assessment status and transition. Do not overwrite historic 20% records or treat a calculation as a filed return. |
| BRT general rate | Commonly 4% in current practitioner explanation S9 | Confirm this factory's assessed rate, tax base and registration. General trade is not automatically the same sector as manufacturing. |
| BRT 2% / 5% / 10% sectors | Historical/sector-specific rates exist; complete current classification/exemption matrix not verified | Inactive until current approval/category evidence is provided. No automatic sector guess from product name. |
| BRT base and quarter deadline | Historical S3 framework addresses gross income and quarterly filing by the 15th of following month; basis differs by taxpayer accounting method | Confirm current ARD return basis, SH quarter, credit sales, prepayments, refunds and deadline/holiday rules. Do not conflate invoice VAT, BRT turnover and cash collections. |
| Import advance income tax | S2 final page identifies 2% advance income-tax collection/credit | Confirm customs document/valuation base and entitlement. Use separate advance income-tax asset and application history. |
| Import advance BRT | Historical S3/S4 contain separate BRT import-credit framework; requested blanket 4% not established | Confirm current customs levy code, rate, creditability, carry-forward/expiry and whether both income-tax and BRT credits apply. Never merge the two credit types. |
| Salary WHT remittance | Historical S3/S5: generally within 10 days after the month in which salary is paid | Confirm current filing instructions and whether special transition/holiday rules apply. Do not derive deadline solely from earning period. |
| Rent WHT | Historical 10%/15% structure supported by S7 and current practitioner statement of unchanged treatment S9 | Confirm exact inclusive thresholds, lessor/lessee status, exemptions, payment basis and current remittance due date. Boundary 10,000 requires authoritative wording before seeding. |
| Contractor WHT | Historical licensed 2% / unlicensed 7%, with current-practice support S10 | Confirm license evidence, contract/retail thresholds, payment timing, exemptions and whether tax is creditable/final. Explicit gross-up only when contract supports it. |
| VAT | S8 law specifies 10%; current commencement/applicability not established | **Disabled by default**. A VAT-ready schema is not permission to charge VAT. Require official commencement and taxpayer-registration evidence. |

## Accounting and implementation constraints for the approved phase

1. Store rates/brackets/source/version/effective dates as versioned business data, never constants inside posting services. Keep draft, confirmed, superseded and disabled states; retain immutable calculation snapshots on posted documents. Confirmation history needs who/when/reason/source, not a mutable boolean alone.
2. Separate **commercial price tax**, **seller turnover liability**, **withholding deducted from a payee**, and **tax credits/prepayments**. Inclusive/exclusive pricing cannot be a universal switch that turns BRT into VAT. A seller-borne tax may debit an appropriate expense and credit liability; payment withholding settles gross AP through net cash plus withholding liability; actual design must reflect the approved legal treatment and chart mappings.
3. All journals must use `core.execute` and `core.journal`, honor period locks, balance in functional currency and reconcile to immutable tax subledger events. Remittance reduces the relevant liability; an import credit is an asset until lawfully applied. Keep invoice/customer advances separate from tax credits.
4. Every tax report needs business/location scope, configured fiscal calendar, period/as-of date, currency, selected rule versions, confirmation state, adjustments and source-document drill-down. Rate changes cannot silently revise a submitted return. Corrections need separate adjustment/reversal events and an amended-return workflow where appropriate.
5. Rule/override/confirm actions require explicit scoped permissions and Dari-first explanatory text. Proposed warning: **«قواعد مالیاتی این تجارت هنوز تأیید نشده است؛ پیش از فعال‌سازی، حسابدار باید نرخ، دوره و سند منبع را بررسی کند.»** This text is a proposal, not an implemented banner. Never silently substitute a plausible tax rate when configuration is absent.

## Required tests once rules and implementation are approved

- Both monthly schedules at, below and above every threshold, including fractional amounts and zero/invalid inputs; snapshot/version integrity.
- The **2026-07-11** effective boundary, pre-cutoff earning periods filed later, finalized assessments, explicit override/reason/authority, disabled/unconfirmed rules.
- Real SH month and quarter ends, leap Esfand/Hut, configured fiscal-year transitions and paid-month deadline calculation; lunar correspondence must not affect tax periods.
- BRT turnover/receipt basis approved for this tenant; invoices, collections, prepayments, refunds, write-offs and reversals without double counting. Quarter totals reconcile to source ledger events and separately classified import credits.
- Contractor/rent gross/net/WHT, certificate numbering, partial payments, remittance and bounce/reversal scenarios; applicable FX/rounding behavior or explicit unsupported-case rejection.
- Payroll gross/bonus/tax/advance/net payment; every resulting journal balanced; close/reopen/isolation/idempotency checks.

Unresolved tax questions are batched in **[AUDIT.md](AUDIT.md)**. The owner has approved implementation, but that does not certify taxpayer applicability or authorize activation of unconfirmed rules. The research completes F1 evidence gathering; F2–F4 must be assessed against the actual delivered functionality and remaining gaps.
