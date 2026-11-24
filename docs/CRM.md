# Opportunities and quotation follow-up

Open **Operations & planning → Opportunities and sales follow-up** (`/operations?view=crm`). The workspace uses original PostgreSQL records and the active business, location and complete product-line scope. It is a commercial follow-up tool; expected values and won opportunities are not revenue, cash or customer receivables.

## Permissions and responsibility

- `crm.view`: read assigned opportunities, including opportunities where you were explicitly assigned a follow-up activity.
- `crm.post`: record your opportunity's stages, notes and activities; complete your own assigned follow-ups. Activity assignment alone does not grant opportunity editing.
- `crm.read_all`: read other opportunities within the same authorized location/product scope. It does not grant editing or reassignment.
- `crm.manage`: manage other opportunities within the same authorized scope and reassign their salesperson. Assignment requires a reason and an active member with CRM viewing/posting and the complete opportunity scope.
- `crm_quote` additionally needs `sales.post`; ordinary pricing, approval/value limits and quote visibility apply. Existing memberships are not silently granted new permissions.

## Daily workflow

1. **New opportunity:** record a clear title, location, product lines, expected AFN amount, expected decision date and assigned salesperson. Select an existing customer or record a prospect name/phone. No customer account, opening balance, stock reservation or journal is invented for a prospect.
2. **Follow-up:** record a specific next action, responsible member and due date, such as “Confirm full-face sheet dimensions with the furniture workshop.” The workspace shows pending/overdue tasks. Completing a task requires the action and actual outcome; original task and date remain preserved.
3. **Quotation:** select an actual warehouse at that opportunity location, an existing customer account, saleable products, quantities and AFN prices. For sponge, enter centimetres of height and explicit full-face length/width in millimetres; grade45 is not block mass or a conversion formula. This creates one ordinary linked quotation through the existing posting service. A prospect's later quotations retain the same first-linked customer. Nothing is received, sold or paid at this stage.
4. **Stages:** New → Qualified → Quoted → Negotiation → Won/Lost is a working sequence, not a compulsory automatic conversion. Stage changes require a reason. Quoted/Won need a current non-cancelled linked quotation. A won stage records commercial acceptance only; proceed through the ordinary quotation → sales order → delivered invoice → receipt workflow for actual accounting. Closing an opportunity never cancels an order, reverses an invoice or writes off a customer balance.
5. **Reassignment:** an authorized manager records a reason when moving open opportunity ownership. The original salesperson and every later change remain in immutable event history. Existing activity assignments remain as originally recorded; a manager can complete them with the actual outcome. Reassignment does not silently change another person's signed activity evidence.
6. **Loss or historical note:** record the real loss reason. Quotation cancellation remains a separate controlled action from the original document. Closed opportunities preserve notes and allow historical notes; new demand should be a new opportunity. Open follow-ups can still be completed with their actual outcome after closure.

## Examples and accounting effects

An opportunity may have expected value 10,000 AFN, while its real quotation totals 8,500 AFN. Both values stay separate and neither becomes sales. “Won” also creates no journal. A later delivered invoice follows the existing `sale` posting: receivable/cash versus sales/tax and COGS versus inventory as applicable. The CRM screen does not repeat that posting. Follow-up tasks send no SMS, email or WhatsApp message.

| Action | Effect |
|---|---|
| `crm_create` | Original prospect/customer opportunity and expected commercial amount; no financial/stock posting. |
| `crm_transition` | Reasoned stage event; no quotation cancellation or revenue recognition. |
| `crm_assign` | Reasoned owner change; original opportunity/activity identities remain. |
| `crm_activity` | Assigned due task; no external message or journal. |
| `crm_activity_done` | One immutable completion outcome; no reopening or duplicate completion. |
| `crm_note` | Append-only historical commercial note. |
| `crm_quote` | One linked ordinary quotation per submitted operation; quantities/prices and customer follow the normal quote rules. No financial/stock movement. |

Requests use idempotency keys. Changing an already-used request's payload is rejected. Event dates cannot predate later opportunity evidence. Source documents, direct JSON/print and commercial conversion recheck original scope and assignment; hiding a menu alone does not grant protection. Original records, events, activity identity and completion evidence have PostgreSQL tenant/history guards. List stage counts/pagination use SQL scope filters and bounded page loading; they do not reveal global pipeline totals. The pipeline shows current recorded stage and ownership. The API reference date evaluates activity overdue status; it is not a historical reconstruction of pipeline stages.

## Limits and acceptance

AFN expected/quoted values only; no statistical forecast, probability-weighted revenue claim, automatic lead scoring, marketing email capture, unattended contact import, external messaging or automatic task reassignment. Tasks are staff-recorded commitments. Prospects do not automatically become customer accounts; create/select a real customer through the existing authorized customer setup before quotation. Native Dari/Pashto terminology and representative staff acceptance remain rollout checks; an automated browser journey is not human acceptance.
