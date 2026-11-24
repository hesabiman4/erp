# Cashier shifts and handovers

Open **Operations & planning → Cashier shifts** (`/operations?view=cashier`). Permissions are separate for opening, viewing, managing, reviewing, handing over, delegating and adjusting. Existing memberships are not automatically granted these permissions; the owner retains `*` access.

## Register and activate

A drawer represents **one selected physical AFN cash instrument at a location**. Multiple separately registered instruments/drawers can coexist at one location; each has its own balance and custody. Historical unlinked location cash remains in its legacy instrument. Register instruments in Settings, then allocate real funds through cash_transfer; registration creates no money. The cashier needs authority over the full physical cash pool and its product scope. Registering a drawer is nonfinancial and leaves it dormant. First opening requires denomination evidence exactly equal to the nonnegative CASH book balance. This activates custody controls prospectively; no existing transaction is rewritten. Correct genuine book errors through their ordinary documented workflows before activation.

Only one shift can be open or awaiting review at a drawer. All new CASH entries in that instrument must belong to its active shift, through the existing accounting service and database guards. Ordinary authorized cash transactions still post the same accounts as before. The shift records their custody association. Another operator needs explicit delegation permission and a reason; the screen retains this reason only in memory and clears it on business switch. Restricted payroll/source identities remain hidden from cashiers without document permission.

## Count, review and hand over

1. Open with the actual number of each denomination. For example, ten units of 100 total 1,000 AFN. Opening custody creates no journal.
2. Use ordinary sales, collections and expenses. A 100 AFN cash expense reduces expected cash to 900.
3. Count and freeze. If physical cash is 890, the recorded variance is -10. New cash posting is blocked pending review. A reasoned recount preserves earlier evidence.
4. A separate authorized supervisor reviews. Zero variance closes without a journal. A nonzero variance needs explicit approval and adjustment/accounting permissions: shortage **Dr EXPENSE / Cr CASH**; overage **Dr CASH / Cr OTHER_INCOME**. The 10 AFN shortage example leaves CASH 890 and total expense 110. No employee debt or salary deduction is invented. Owner `*` includes the explicit small-team self-review exception; ordinary reviewers cannot review their own count.
5. Offer the reviewed cash to an eligible named receiver. This does not transfer money between locations. The receiver accepts by opening their own shift with the matching actual count. If a pending receiver leaves, an authorized manager records a reasoned reassignment; original evidence remains. Accepted handovers cannot be redirected.

Opening, counts, review evidence, cash-entry links and handovers preserve their original documents. Requests are idempotent. Nested financial operations include ancestor unposted cash entries when enforcing held cash, preventing two child payments from spending the same amount.

## Limits

AFN physical cash instruments only. Foreign cash shifts, physical cash-drawer hardware and automatic employee-liability allocation are not implemented. A handover is custody evidence, not a cash transfer or revenue event. Use ordinary `cash_transfer` for actual transfers between selected cash/bank instruments, including distinct instruments at the same location. Browser printing does not certify a physical printer.
