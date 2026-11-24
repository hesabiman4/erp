"""Posted finance workflows. All handlers run inside core.execute's atomic lock."""
from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.utils import timezone

from .models import Account, Allocation, Asset, Business, Document, Employee, Entry, Location, Party, Product, StockPool
from .core import D, account, balance, get_obj, journal, money, outstanding, pool_for


ZERO = Decimal("0")
CASH_CODES = {"CASH", "BANK"}
LINES = {"shared", "sponge", "adhesive"}


def _fail(message):
    raise ValidationError(message)


def _amount(value, *, allow_zero=False):
    try:
        amount = money(D(value))
    except (ValidationError, InvalidOperation, TypeError, ValueError):
        _fail("Enter a valid monetary amount.")
    if not amount.is_finite() or amount < 0 or (not allow_zero and amount == 0):
        _fail("Amount must be positive." if not allow_zero else "Amount cannot be negative.")
    return amount


def _date(value, default=None):
    try:
        return value if isinstance(value, date) else date.fromisoformat(str(value)) if value else default
    except (TypeError, ValueError):
        _fail("Enter a valid ISO date.")


def _period(value):
    try:
        first = date.fromisoformat(str(value) + "-01")
        return first, date(first.year, first.month, monthrange(first.year, first.month)[1])
    except (TypeError, ValueError):
        _fail("Period must use YYYY-MM.")


def _payroll_window(payroll):
    if payroll.data.get('earning_from') and payroll.data.get('earning_through'):
        return _date(payroll.data['earning_from']),_date(payroll.data['earning_through'])
    return _period(payroll.data.get('period'))


def _cash(ctx, value="CASH"):
    code = str(value or "CASH").upper()
    if code not in CASH_CODES:
        _fail("Select CASH or BANK.")
    account(ctx, code)
    return code


def _line(value):
    value = value or "shared"
    if value not in LINES:
        _fail("Invalid product line.")
    return value


def _record(doc, **values):
    for key, value in values.items():
        setattr(doc, key, value)
    if values:
        doc.save(update_fields=list(values))


def _location(ctx, doc, fallback=None):
    selected = doc.location_id or getattr(fallback, "pk", fallback)
    if not selected:
        _fail("Select an assigned accounting/cash location.")
    location = get_obj(ctx, Location, selected)
    _record(doc, location=location)
    return location


def _posted(ctx, ident, kinds=None):
    obj = get_obj(ctx, Document, ident)
    if obj.state != "posted" or (kinds and obj.kind not in kinds):
        _fail("Select an eligible posted document.")
    return obj


def _employee(ctx, ident):
    employee = get_obj(ctx, Employee, ident)
    if not employee.active:
        _fail("Employee is inactive.")
    return employee


def update_employee_rate(employee, new_rate, effective_date):
    """Append a rate change without rewriting rates used by posted payroll.

    The caller performs business authorization/atomic save and excludes direct
    writes to terms.rates. Existing DB state is authoritative for PATCH.
    """
    rate = D(new_rate)
    if rate < 0:
        _fail("Employee rate cannot be negative.")
    effective = _date(effective_date)
    if not effective:
        _fail("A rate change requires an effective_date in YYYY-MM-DD format.")
    original = Employee.objects.get(pk=employee.pk, business_id=employee.business_id) if employee.pk else None
    old_rate = D(original.rate) if original else rate
    original_terms = original.terms if original else employee.terms
    history = list((original_terms or {}).get("rates", []))
    normalized = []
    for item in history:
        changed = _date(item.get("effective_date"))
        if not changed:
            _fail("Existing rate history contains an invalid effective date.")
        normalized.append({"effective_date": changed.isoformat(), "rate": str(D(item.get("rate")))})
    normalized.sort(key=lambda item: item["effective_date"])
    if len({item["effective_date"] for item in normalized}) != len(normalized):
        _fail("Existing rate history contains duplicate effective dates.")
    if original and old_rate == rate:
        employee.rate = rate
        employee.terms = {**(employee.terms or {}), "rates": normalized or [{"effective_date": "1900-01-01", "rate": str(old_rate)}]}
        return
    if original:
        for payroll in Document.objects.filter(business_id=employee.business_id, employee=employee, kind="payroll_accrue", state="posted"):
            _, period_end = _payroll_window(payroll)
            if effective <= period_end:
                _fail("A rate change cannot alter a period already accrued. Use a later effective date and a separately approved correction if needed.")
    if normalized and effective.isoformat() <= normalized[-1]["effective_date"]:
        _fail("Rate changes must append a later effective date; recorded rate history is immutable.")
    if original and not normalized:
        normalized.append({"effective_date": "1900-01-01", "rate": str(old_rate)})
    normalized.append({"effective_date": effective.isoformat(), "rate": str(rate)})
    employee.rate = rate
    employee.terms = {**(employee.terms or {}), "rates": normalized}


def _ref_docs(ctx, reference, kinds):
    return Document.objects.filter(business=ctx.business, reference=reference, state="posted", kind__in=kinds)


def _sum_amount(query):
    return query.aggregate(value=Sum("amount"))["value"] or ZERO


def employee_advance(ctx, payload, doc):
    employee = _employee(ctx, payload.get("employee"))
    _location(ctx, doc, employee.location_id)
    amount = _amount(payload.get("amount"))
    existing = max(ZERO, balance(ctx, "ADVANCES", employee=employee))
    if existing + amount > employee.advance_limit:
        ctx.require("payroll.approve")
        if not payload.get("reason"):
            _fail("A reason is required for an advance above the employee limit.")
    cash = _cash(ctx, payload.get("cash_account"))
    location = employee.location_id or doc.location_id
    _record(doc, employee=employee, amount=amount)
    journal(ctx, doc, [
        {"account": "ADVANCES", "debit": amount, "employee": employee, "location": location},
        {"account": cash, "credit": amount, "location": doc.location_id or location},
    ])
    return {"employee": employee.id, "employee_snapshot": {"name": employee.name, "kind": employee.kind}, "amount": str(amount), "advance_limit": str(employee.advance_limit), "outstanding_advance": str(existing + amount)}


def attendance_record(ctx, payload, doc):
    employee = _employee(ctx, payload.get("employee"))
    _record(doc, location=employee.location)
    if (employee.join_date and doc.date<employee.join_date) or (employee.end_date and doc.date>employee.end_date):
        _fail('Attendance must fall within the employment dates.')
    days = D(payload.get("days", "1"))
    hours = D(payload.get("hours", "0"))
    if not days.is_finite() or not hours.is_finite() or days < 0 or days > 1 or hours < 0 or hours > 24:
        _fail("Attendance days must be between 0 and 1 and hours between 0 and 24.")
    if Document.objects.filter(business=ctx.business, employee=employee, kind="attendance_record", state="posted", date=doc.date).exists():
        _fail("Attendance has already been approved for this employee and date.")
    for payroll in Document.objects.filter(business=ctx.business,employee=employee,kind='payroll_accrue',state='posted'):
        start,end=_payroll_window(payroll)
        if start<=doc.date<=end: _fail('Attendance falls in an already accrued earning window. Use a reviewed correction instead of silently adding unpaid historical attendance.')
    _record(doc, employee=employee, amount=ZERO, data={**doc.data, "days": str(days), "hours": str(hours)})
    return {"employee": employee.id, "date": doc.date.isoformat(), "days": str(days), "hours": str(hours)}


def payroll_accrue(ctx, payload, doc):
    employee = _employee(ctx, payload.get("employee"))
    _record(doc, location=employee.location)
    calendar = str(payload.get('period_calendar') or 'gregorian')
    selected_period = payload.get('period')
    if employee.kind=='weekly':
        first=_date(payload.get('week_start_date'))
        if not first or first.weekday()!=employee.week_start:
            _fail('Select the configured first day of the employee payroll week.')
        last=first+timedelta(days=6)
        if doc.date<last: _fail('Weekly earnings can only be accrued on or after the end of the seven-day week.')
        payload={**payload,'period':first.strftime('%Y-%m')}
        calendar='gregorian'
        selected_period=payload['period']
        denominator_days=7
    else:
        from .calendar_periods import earning_month,period_for
        first, last, denominator_days = earning_month(ctx.business, selected_period, calendar)
        selected_period=period_for(first,calendar)
        # Preserve existing canonical month keys; the namespaced earning key and
        # exact dates disambiguate Jalali months that span Gregorian months.
        payload={**payload,'period':first.strftime('%Y-%m')}
    if doc.date < first:
        _fail('Payroll cannot be accrued before its earning month begins.')
    if employee.kind=='monthly' and doc.date < last:
        _fail("Accrue payroll on or after the end of its earning period.")
    previous = Document.objects.filter(business=ctx.business, employee=employee, kind="payroll_accrue", state="posted")
    earning_from=max(first,employee.join_date) if employee.join_date else first
    earning_through=last if employee.kind in {'monthly','weekly'} else min(last,doc.date)
    if employee.end_date: earning_through=min(earning_through,employee.end_date)
    if earning_from>earning_through: _fail('There are no employed days within this earning period.')
    project = str(payload.get("project_reference") or "").strip()
    if employee.kind == "project":
        if not project:
            _fail("Project-based earnings require an accepted project/milestone reference.")
        if previous.filter(data__project_reference=project).exists():
            _fail("This project/milestone earning has already been accrued.")
    elif employee.kind=='weekly':
        for prior in previous:
            old_start,old_end=_payroll_window(prior)
            if old_start<=earning_through and old_end>=earning_from:
                _fail('This weekly earning window overlaps payroll already accrued.')
    elif employee.kind=='monthly':
        for prior in previous:
            old_start,old_end=_payroll_window(prior)
            if old_start<=earning_through and old_end>=earning_from:
                _fail('This monthly earning window overlaps payroll already accrued.')
    elif employee.kind in {'daily','part_time','hourly'}:
        covered=[]
        for prior in previous:
            old_start,old_end=_payroll_window(prior)
            if old_start<=earning_through and old_end>=earning_from:
                covered.append(old_end)
        if covered: earning_from=max(earning_from,max(covered)+timedelta(days=1))
        if earning_from>earning_through: _fail('The selected daily/hourly earning window is already accrued.')
    rate = D(employee.rate)
    history=(employee.terms or {}).get('rates',[])
    if history and not any(_date(change.get('effective_date'))<=earning_from for change in history) and payload.get('gross') is None:
        _fail('No contractual rate is effective at the start of this earning window.')
    for change in sorted(history, key=lambda x: x.get("effective_date", "")):
        effective = _date(change.get("effective_date"))
        if not effective:
            _fail("Employee rate history contains an invalid effective date.")
        if earning_from < effective <= earning_through and payload.get("gross") is None:
            _fail("A rate changed during this period; enter an approved prorated gross amount explicitly.")
        if effective <= earning_from:
            rate = D(change["rate"])
    approved_days = approved_hours = None
    rate_basis = 'week' if employee.kind=='weekly' else 'hour' if employee.kind=='hourly' else "month" if employee.kind == "monthly" else "project" if employee.kind == "project" else (employee.terms or {}).get("rate_basis", "day")
    if employee.kind in {"daily", "part_time", "hourly"} and rate_basis not in {"day", "hour"}:
        _fail("Daily/part-time rate_basis must be day or hour.")
    if payload.get("hours") is not None and rate_basis != "hour":
        _fail("An hours override requires an employee configured with rate_basis=hour.")
    if payload.get("days") is not None and rate_basis == "hour":
        _fail("Hourly payroll uses approved hours rather than a days override.")
    if payload.get('days') is not None and rate_basis not in {'day','hour'}:
        _fail('Days overrides are only supported for attendance-based contracts.')
    if payload.get("gross") is not None:
        ctx.require("payroll.approve")
        if employee.kind=='weekly' and not str(payload.get('reason') or '').strip(): _fail('An approved weekly earnings override requires a reason.')
        gross = _amount(payload["gross"])
        if payload.get("hours") is not None:
            reviewed_hours = D(payload["hours"])
            if reviewed_hours < 0 or reviewed_hours > D((earning_through - earning_from).days + 1) * 24:
                _fail("Reviewed hours exceed the supported earning period.")
            approved_hours = str(reviewed_hours)
    elif employee.kind in {'monthly','weekly'}:
        gross = _amount(rate*D((earning_through-earning_from).days+1)/D(denominator_days))
    elif employee.kind in {"daily", "part_time", "hourly"}:
        unit_field = "hours" if rate_basis == "hour" else "days"
        worked = payload.get(unit_field)
        if worked is not None:
            ctx.require("payroll.approve")
        if worked is None:
            records = Document.objects.filter(business=ctx.business, employee=employee, state="posted", kind="attendance_record", date__gte=earning_from, date__lte=earning_through)
            worked = sum((D(item.data.get(unit_field, "0")) for item in records), ZERO)
        worked = D(worked)
        maximum = D((earning_through - earning_from).days + 1) * (24 if rate_basis == "hour" else 1)
        if not worked.is_finite() or worked <= 0 or worked > maximum:
            _fail(f"Enter valid approved working {unit_field} or record attendance first.")
        gross = _amount(rate * worked)
        if rate_basis == "hour":
            approved_hours = str(worked)
        else:
            approved_days = str(worked)
    else:
        _fail("Accepted project earnings require an explicit gross amount.")
    line = _line(payload.get("line"))
    location = employee.location_id or doc.location_id
    deductions = []
    deduction_total = ZERO
    if payload.get("deductions"):
        ctx.require("payroll.approve")
    for deduction in payload.get("deductions", []):
        amount = _amount(deduction.get("amount"))
        code = deduction.get("account", "TAX")
        deduction_account = account(ctx, code)
        if deduction_account.category != "liability" or code in {"PAYROLL", "AP", "DEPOSITS"}:
            _fail("Payroll deductions must credit an appropriate deduction liability account.")
        deduction_total += amount
        deductions.append({"account": code, "credit": amount, "employee": employee, "location": location, "line": line})
    if deduction_total > gross:
        _fail("Deductions cannot exceed gross earnings.")
    net = gross - deduction_total
    # Production absorption is a separate linked transaction. This accrual never silently adds WIP.
    expense = payload.get("expense_account", "SALARY")
    if expense not in {"SALARY", "LABOR_CLEARING"}:
        _fail("Payroll accrual must use salary expense or the production labor clearing account.")
    if expense == "LABOR_CLEARING":
        ctx.require("production.post")
    lines = [{"account": expense, "debit": gross, "employee": employee, "location": location, "line": line}]
    if net:
        lines.append({"account": "PAYROLL", "credit": net, "employee": employee, "location": location, "line": line})
    journal(ctx, doc, lines + deductions)
    calendar_snapshot={'period_calendar':calendar,'calendar_period':selected_period,'period_key':f'{calendar}:{selected_period}',
                       'period_first':first.isoformat(),'period_last':last.isoformat(),'denominator_days':denominator_days}
    _record(doc, employee=employee, amount=net, data={**doc.data, **calendar_snapshot, "period": payload["period"], "project_reference": project, "gross": str(gross), "deductions_total": str(deduction_total), "expense_account": expense, "rate_basis_snapshot": rate_basis, "approved_days_snapshot": approved_days, "approved_hours_snapshot": approved_hours,'earning_from':earning_from.isoformat(),'earning_through':earning_through.isoformat()})
    return {**calendar_snapshot,"employee": employee.id, "employee_snapshot": {"name": employee.name, "code":employee.code, "kind": employee.kind, "location": employee.location_id,'department':employee.department.name if employee.department_id else '', 'position':employee.position.name if employee.position_id else ''}, "period": payload["period"], "rate_used": str(rate), "rate_basis": rate_basis, "approved_days": approved_days, "approved_hours": approved_hours, "gross": str(gross), "deductions": str(deduction_total), "net": str(net), "remaining": str(net),'earning_from':earning_from.isoformat(),'earning_through':earning_through.isoformat(),'proration_basis':'employed calendar days / full contractual calendar month or week' if employee.kind in {'monthly','weekly'} else None}


def payroll_settle(ctx, payload, doc):
    payroll = _posted(ctx, payload.get("payroll"), {"payroll_accrue","commission_accrue"})
    if payroll.kind=='commission_accrue' and payroll.children.filter(kind='commission_reverse',state='posted').exists():
        _fail('This commission accrual has been reversed.')
    if payroll.date > doc.date:
        _fail("Payroll settlement cannot precede the earnings accrual; use an employee advance.")
    # Termination/deactivation stops new earnings, not settlement of an existing liability.
    employee = get_obj(ctx, Employee, payroll.employee_id)
    _location(ctx, doc, employee.location_id)
    settled = _sum_amount(_ref_docs(ctx, payroll, {"payroll_settle"}))
    remaining = money(payroll.amount - settled)
    recovery = _amount(payload.get("advance_recovery", "0"), allow_zero=True)
    paid = _amount(payload.get("amount", "0"), allow_zero=True)
    if not recovery + paid or recovery + paid > remaining:
        _fail("Settlement must be positive and cannot exceed the remaining net payroll payable.")
    advance = max(ZERO, balance(ctx, "ADVANCES", employee=employee, through=doc.date))
    if recovery > advance:
        _fail("Advance recovery exceeds the employee's outstanding advance.")
    if recovery:
        ctx.require("payroll.approve")
    max_recovery = (employee.terms or {}).get("max_recovery_per_payroll")
    prior_recovery = sum((D(item.result.get("advance_recovery", "0")) for item in _ref_docs(ctx, payroll, {"payroll_settle"})), ZERO)
    if max_recovery is not None and recovery + prior_recovery > D(max_recovery):
        _fail("Recovery exceeds the employee's authorized payroll recovery limit.")
    location = payroll.location_id or employee.location_id or doc.location_id
    lines = [{"account": "PAYROLL", "debit": recovery + paid, "employee": employee, "location": location}]
    if recovery:
        lines.append({"account": "ADVANCES", "credit": recovery, "employee": employee, "location": location})
    if paid:
        lines.append({"account": _cash(ctx, payload.get("cash_account")), "credit": paid, "location": doc.location_id or location})
    journal(ctx, doc, lines)
    _record(doc, employee=employee, reference=payroll, amount=recovery + paid)
    return {"payroll": payroll.id, "employee": employee.id, "paid": str(paid), "advance_recovery": str(recovery), "remaining_payable": str(remaining - recovery - paid), "advance_remaining": str(advance - recovery)}


def expense_post(ctx, payload, doc):
    _location(ctx, doc)
    amount = _amount(payload.get("amount"))
    code = payload.get("expense_account", "EXPENSE")
    expense = account(ctx, code)
    production_cost = payload.get("production_cost") is True and code == "COST_CLEARING"
    if production_cost:
        ctx.require("production.post")
    elif expense.category != "expense" or expense.control:
        _fail("Select a non-control expense account.")
    supplier = get_obj(ctx, Party, payload["supplier"]) if payload.get("supplier") else None
    if supplier and supplier.kind != "supplier":
        _fail("Select a supplier account.")
    if supplier and payload.get("cash_account"):
        _fail("Choose a supplier payable or immediate cash payment, not both.")
    credit = "AP" if supplier else _cash(ctx, payload.get("cash_account"))
    line = _line(payload.get("line"))
    _record(doc, party=supplier, amount=amount)
    journal(ctx, doc, [
        {"account": code, "debit": amount, "location": doc.location_id, "line": line},
        {"account": credit, "credit": amount, "party": supplier, "location": doc.location_id, "line": line},
    ])
    return {"amount": str(amount), "supplier": supplier.id if supplier else None, "payment_status": "unpaid" if supplier else "paid"}


def shared_cost_allocate(ctx, payload, doc):
    """Reclassify a backed ordinary shared expense without creating a new cost."""
    source = _posted(ctx, payload.get("source"), {"expense_post"})
    if source.date > doc.date:
        _fail("Shared-cost allocation cannot precede the source expense.")
    reason = str(payload.get("reason") or "").strip()
    if not reason:
        _fail("Record the approved allocation driver and reason.")
    code = source.data.get("expense_account", "EXPENSE")
    selected = account(ctx, code)
    excluded = {"SALARY", "COGS", "WASTE", "DEPRECIATION", "IMPAIRMENT", "LABOR_CLEARING", "COST_CLEARING"}
    if selected.category != "expense" or selected.control or code in excluded or source.data.get("production_cost"):
        _fail("This workflow supports ordinary shared operating expenses, not payroll, inventory, production clearing, or asset/valuation costs.")
    source_lines = list(source.entries.filter(account=selected))
    if not source_lines or any(item.line != "shared" or item.credit or not item.debit for item in source_lines):
        _fail("Only an original expense recorded entirely as Shared can be allocated.")
    eligible = sum((item.debit for item in source_lines), ZERO)
    # Ordinary expense_post is a single expense debit with an actual paid/payable counterpart.
    if len(source_lines) != 1 or eligible != source.amount:
        _fail("The source expense has an unsupported posting structure.")
    used = _sum_amount(_ref_docs(ctx, source, {"shared_cost_allocate"}))
    amount = _amount(payload.get("amount", eligible))
    if amount > eligible - used:
        _fail("Allocation exceeds the source expense's remaining Shared amount.")
    weights = payload.get("weights", [])
    if not isinstance(weights, list) or not weights:
        _fail("Provide product-line allocation weights.")
    normalized, seen, total_weight = [], set(), ZERO
    for item in weights:
        if not isinstance(item, dict):
            _fail("Each allocation weight must identify a product line and weight.")
        line = item.get("line")
        if line not in {"sponge", "adhesive"} or line in seen:
            _fail("Each destination must be Sponge or Adhesive and appear once.")
        if not ctx.line_allowed(line):
            _fail("Allocation destination is outside your permitted product lines.")
        weight = D(item.get("weight"))
        if weight <= 0:
            _fail("Allocation weights must be positive.")
        seen.add(line)
        total_weight += weight
        normalized.append({"line": line, "weight": str(weight)})
    location = source_lines[0].location or source.location
    if location:
        get_obj(ctx, Location, location.pk)
    remaining, allocations, entries = amount, [], []
    # Rounding goes to the final explicitly ordered destination and is captured below.
    for index, weight in enumerate(normalized):
        portion = remaining if index == len(normalized) - 1 else money(amount * D(weight["weight"]) / total_weight)
        remaining -= portion
        allocations.append({**weight, "amount": str(portion)})
        if portion:
            entries.append({"account": code, "debit": portion, "location": location, "line": weight["line"]})
    entries.append({"account": code, "credit": amount, "location": location, "line": "shared"})
    _record(doc, reference=source, location=location, amount=amount, data={**doc.data, "account_snapshot": code, "source_amount_snapshot": str(eligible), "driver_reason": reason, "weights_snapshot": normalized})
    journal(ctx, doc, entries)
    return {"source": source.id, "expense_account": code, "source_shared_amount": str(eligible), "allocated": str(amount), "remaining_shared": str(eligible - used - amount), "driver_reason": reason, "weights": allocations, "company_expense_change": "0.00", "cash_change": "0.00"}


def cash_transfer(ctx, payload, doc):
    amount = _amount(payload.get("amount"))
    source = _cash(ctx, payload.get("from_account"))
    target = _cash(ctx, payload.get("to_account"))
    source_location = get_obj(ctx, Location, payload["from_location"])
    target_location = get_obj(ctx, Location, payload["to_location"])
    from .money_instruments import resolve
    source_instrument=resolve(ctx,doc,source,source_location,explicit=payload.get('from_instrument'),credit=amount)
    target_instrument=resolve(ctx,doc,target,target_location,explicit=payload.get('to_instrument'),debit=amount)
    if source == target and source_location.id == target_location.id and getattr(source_instrument,'pk',None)==getattr(target_instrument,'pk',None):
        _fail("Source and destination cash instruments must differ.")
    _record(doc, amount=amount, location=source_location)
    journal(ctx, doc, [
        {"account": source, "credit": amount, "location": source_location,"instrument":getattr(source_instrument,"pk",None)},
        {"account": target, "debit": amount, "location": target_location,"instrument":getattr(target_instrument,"pk",None)},
    ])
    return {"amount": str(amount), "from_account": source, "to_account": target, "from_location": source_location.id, "to_location": target_location.id,"from_instrument":getattr(source_instrument,"pk",None),"to_instrument":getattr(target_instrument,"pk",None)}


def cash_count(ctx, payload, doc):
    code = _cash(ctx, payload.get("cash_account"))
    location = get_obj(ctx, Location, payload.get("location") or doc.location_id)
    counted = _amount(payload.get("counted"), allow_zero=True)
    from .money_instruments import resolve,instrument_balance
    instrument=resolve(ctx,doc,code,location)
    expected=instrument_balance(instrument,doc.date) if instrument else money(balance(ctx,code,location=location,through=doc.date))
    _record(doc, location=location, amount=counted)
    return {"cash_account": code, "location": location.id, "expected": str(expected), "counted": str(counted), "variance": str(counted - expected), "note": "A count records evidence; an approved separate adjustment is required for variance."}


def bank_reconcile(ctx, payload, doc):
    code = _cash(ctx, payload.get("account", "BANK"))
    through = _date(payload.get("through_date"), doc.date)
    if through > doc.date:
        _fail("A reconciliation cannot cover a statement date after its posting date.")
    statement = money(D(payload.get("statement_balance")))
    location = get_obj(ctx, Location, payload.get("location") or doc.location_id) if (payload.get("location") or doc.location_id) else None
    if not location and not ctx.membership.all_locations:
        _fail("A location-scoped user must select the bank location.")
    ids = payload.get("entry_ids", [])
    entries = Entry.objects.filter(pk__in=ids, document__business=ctx.business, document__state="posted", document__date__lte=through, account__code=code)
    if not ctx.has('documents.all_lines'): entries=entries.filter(document__product_lines__contained_by=ctx.membership.product_lines)
    if not ctx.has('payroll.view'): entries=entries.filter(employee__isnull=True,document__employee__isnull=True)
    if location:
        entries = entries.filter(location=location)
    if len(set(map(str, ids))) != len(ids) or entries.count() != len(ids):
        _fail("Reconciliation contains duplicate or ineligible bank entries.")
    from .money_instruments import resolve,instrument_balance,entries_for
    instrument=resolve(ctx,doc,code,location)
    if instrument:entries=entries.filter(pk__in=entries_for(instrument).values('pk'))
    if entries.count()!=len(ids):_fail('Selected entries belong to a different bank instrument.')
    ledger=instrument_balance(instrument,through) if instrument else money(balance(ctx,code,location=location,through=through))
    cleared = sum((item.debit - item.credit for item in entries), ZERO)
    if money(cleared) != statement:
        _fail("Selected cleared transactions must reconcile to the statement balance. Include the opening bank entry when applicable.")
    _record(doc, amount=statement)
    return {"account": code, "through_date": through.isoformat(), "statement_balance": str(statement), "ledger_balance": str(ledger), "cleared_balance": str(money(cleared)), "uncleared": str(money(ledger - cleared)), "entry_ids": ids}


def _invoice_allocations(ctx, payload, *, supplier=False):
    raw = payload.get("allocations")
    if raw is None and payload.get("invoice"):
        invoice = _posted(ctx, payload["invoice"])
        raw = [{"invoice": invoice.id, "amount": min(_amount(payload["amount"]), outstanding(invoice))}]
    raw = raw or []
    result, seen, party = [], set(), None
    kinds = {"purchase_bill", "expense_post", "asset_acquire", "opening_payable"} if supplier else {"sale", "opening_receivable"}
    for allocation in raw:
        invoice = _posted(ctx, allocation.get("invoice"), kinds)
        from .models import ForeignExposure
        if ForeignExposure.objects.filter(invoice=invoice).exists():_fail('Use foreign-currency settlement for this invoice; AFN allocation cannot bypass its monetary subledger.')
        ctx.lines.update(invoice.product_lines)
        if invoice.date > _date(payload.get("date"), timezone.localdate()):
            _fail("Payment allocation cannot precede the invoice date; record an unallocated deposit instead.")
        if invoice.id in seen:
            _fail("An invoice can appear only once in a payment allocation.")
        seen.add(invoice.id)
        if not invoice.party_id:
            _fail("Credit documents require an identifiable invoice-linked debtor/supplier.")
        if party and party.id != invoice.party_id:
            _fail("A payment cannot settle unrelated parties.")
        party = invoice.party
        amount = _amount(allocation.get("amount"), allow_zero=True)
        if amount > outstanding(invoice):
            _fail("Allocation exceeds the invoice's outstanding balance.")
        if amount:
            result.append((invoice, amount))
    if payload.get("party"):
        supplied = get_obj(ctx, Party, payload["party"])
        if party and supplied.id != party.id:
            _fail("Payment party does not match the invoice party.")
        party = supplied
    if party and party.kind != ("supplier" if supplier else "customer"):
        _fail("Select a party of the correct customer/supplier type.")
    return party, result


def _payment(ctx, payload, doc, supplier=False):
    _location(ctx, doc)
    amount = _amount(payload.get("amount"))
    party, allocations = _invoice_allocations(ctx, payload, supplier=supplier)
    if not party:
        _fail("Select a party or a party-linked invoice for the payment/deposit.")
    allocated = sum((value for _, value in allocations), ZERO)
    if allocated > amount:
        _fail("Invoice allocations exceed the payment amount.")
    deposit = amount - allocated
    cash = _cash(ctx, payload.get("cash_account"))
    lines = [{"account": cash, "credit" if supplier else "debit": amount, "location": doc.location_id}]
    for invoice, value in allocations:
        lines.append({"account": "AP" if supplier else "AR", "debit" if supplier else "credit": value, "party": party, "location": invoice.location_id})
    if deposit:
        lines.append({"account": "SUPPLIER_DEPOSITS" if supplier else "DEPOSITS", "debit" if supplier else "credit": deposit, "party": party, "location": doc.location_id})
    _record(doc, party=party, amount=amount)
    journal(ctx, doc, lines)
    for invoice, value in allocations:
        Allocation.objects.create(document=doc, invoice=invoice, amount=value)
    return {"amount": str(amount), "allocated": str(allocated), "deposit_amount": str(deposit), "deposit_side": "supplier" if supplier else "customer", "party": party.id, "allocations": [{"invoice": invoice.id, "amount": str(value)} for invoice, value in allocations]}


def receipt(ctx, payload, doc):
    return _payment(ctx, payload, doc)


def supplier_payment(ctx, payload, doc):
    return _payment(ctx, payload, doc, supplier=True)


def _available_deposit(ctx, deposit):
    if _ref_docs(ctx, deposit, {"payment_reverse"}).exists():
        return ZERO
    original = D(deposit.result.get("deposit_amount", "0"))
    used = _sum_amount(_ref_docs(ctx, deposit, {"allocate_deposit", "customer_refund", "supplier_refund"}))
    return money(original - used)


def allocate_deposit(ctx, payload, doc):
    deposit = _posted(ctx, payload.get("deposit"))
    ctx.lines.update(deposit.product_lines)
    _location(ctx, doc, deposit.location_id)
    if deposit.date > doc.date:
        _fail("Deposit allocation cannot precede its source receipt/credit.")
    side = deposit.result.get("deposit_side")
    if side not in {"customer", "supplier"}:
        _fail("Selected document has no supported deposit/customer credit.")
    supplier = side == "supplier"
    ctx.require("purchases.pay" if supplier else "sales.collect")
    party, allocations = _invoice_allocations(ctx, payload, supplier=supplier)
    amount = sum((value for _, value in allocations), ZERO)
    if not amount or amount > _available_deposit(ctx, deposit):
        _fail("Allocation must be positive and cannot exceed available deposit credit.")
    if not party or party.id != deposit.party_id:
        _fail("Deposit and target invoices must belong to the same party.")
    _record(doc, reference=deposit, party=party, amount=amount)
    if supplier:
        lines = [{"account": "SUPPLIER_DEPOSITS", "credit": amount, "party": party, "location": deposit.location_id}]
        lines += [{"account": "AP", "debit": value, "party": party, "location": invoice.location_id} for invoice, value in allocations]
    else:
        lines = [{"account": "DEPOSITS", "debit": amount, "party": party, "location": deposit.location_id}]
        lines += [{"account": "AR", "credit": value, "party": party, "location": invoice.location_id} for invoice, value in allocations]
    journal(ctx, doc, lines)
    for invoice, value in allocations:
        Allocation.objects.create(document=doc, invoice=invoice, amount=value)
    return {"deposit": deposit.id, "allocated": str(amount), "deposit_remaining": str(_available_deposit(ctx, deposit) - amount)}


def _refund(ctx, payload, doc, supplier=False):
    source = _posted(ctx, payload.get("deposit") or payload.get("receipt"))
    ctx.lines.update(source.product_lines)
    _location(ctx, doc, source.location_id)
    if source.date > doc.date:
        _fail("Refund cannot precede the receipt/credit being refunded.")
    if source.result.get("deposit_side") != ("supplier" if supplier else "customer"):
        _fail("Select an available deposit/credit for the appropriate party type.")
    amount = _amount(payload.get("amount"))
    if amount > _available_deposit(ctx, source):
        _fail("Refund exceeds available unallocated deposit/credit.")
    if not payload.get("reason"):
        _fail("A refund requires a reason.")
    cash = _cash(ctx, payload.get("cash_account"))
    _record(doc, reference=source, party=source.party, amount=amount)
    journal(ctx, doc, [
        {"account": cash, "debit" if supplier else "credit": amount, "location": doc.location_id},
        {"account": "SUPPLIER_DEPOSITS" if supplier else "DEPOSITS", "credit" if supplier else "debit": amount, "party": source.party, "location": source.location_id},
    ])
    return {"amount": str(amount), "party": source.party_id, "deposit_remaining": str(_available_deposit(ctx, source) - amount)}


def customer_refund(ctx, payload, doc):
    return _refund(ctx, payload, doc)


def supplier_refund(ctx, payload, doc):
    return _refund(ctx, payload, doc, supplier=True)


def payment_reverse(ctx, payload, doc):
    """Compensate an unused receipt/payment; never edit its entries/allocations."""
    source = _posted(ctx, payload.get("payment") or payload.get("source"), {"receipt", "supplier_payment"})
    ctx.lines.update(source.product_lines)
    supplier = source.kind == "supplier_payment"
    ctx.require("purchases.pay" if supplier else "sales.collect")
    ctx.require("finance.reverse")
    if not str(payload.get("reason") or "").strip():
        _fail("Payment reversal requires a documented correction reason.")
    if source.date > doc.date:
        _fail("Payment reversal cannot precede its original payment.")
    if _ref_docs(ctx, source, {"payment_reverse"}).exists():
        _fail("This payment has already been reversed.")
    if _ref_docs(ctx, source, {"allocate_deposit", "customer_refund", "supplier_refund"}).exists():
        _fail("This payment's deposit has downstream allocations/refunds and cannot be fully reversed.")
    originals = list(Allocation.objects.filter(document=source).select_related("invoice"))
    for allocated in originals:
        invoice = _posted(ctx, allocated.invoice_id)
        if Allocation.objects.filter(invoice=invoice, document__state="posted", document__kind__in=["sales_return", "purchase_return", "receivable_writeoff"]).exists():
            _fail("An allocated invoice has a posted return/write-off; resolve those credit effects before reversing this payment.")
    entries = list(Entry.objects.filter(document=source).select_related("account", "location", "warehouse", "party", "employee"))
    if not entries:
        _fail("The source payment has no posted journal to reverse.")
    lines = []
    for original in entries:
        if original.location_id:
            get_obj(ctx, Location, original.location_id)
        if original.employee_id:
            ctx.require("payroll.view")
        from .money_instruments import legacy_for,instrument_balance
        instrument=getattr(getattr(original,'money_link',None),'instrument',None) if original.account.code in CASH_CODES else None
        if not instrument and original.account.code in CASH_CODES and original.location_id:instrument=legacy_for(ctx,original.location_id,original.account.code)
        # Reversing a receipt spends money. A supplier payment reversal receives money.
        if original.account.code in CASH_CODES and original.debit:
            available = instrument_balance(instrument,doc.date) if instrument else balance(ctx, original.account.code, location=original.location_id, through=doc.date)
            if available < original.debit:
                _fail("Insufficient recorded cash/bank balance to reverse the receipt at this location.")
        lines.append({"account": original.account.code, "debit": original.credit, "credit": original.debit, "location": original.location, "warehouse": original.warehouse, "party": original.party, "employee": original.employee, "line": original.line,"instrument":getattr(instrument,"pk",None)})
    _record(doc, reference=source, party=source.party, location=source.location, amount=source.amount)
    journal(ctx, doc, lines)
    for original in originals:
        Allocation.objects.create(document=doc, invoice=original.invoice, amount=-original.amount)
    asset_allocations = [item for item in originals if item.invoice.kind == "asset_acquire"]
    flow = "operating"
    if supplier and asset_allocations:
        flow = "investing" if len(asset_allocations) == len(originals) and not D(source.result.get("deposit_amount", "0")) else "unclassified"
    return {"payment": source.id, "reversed_kind": source.kind, "amount": str(source.amount), "deposit_amount": "0", "cash_flow_class": flow, "reopened_invoices": [{"invoice": item.invoice_id, "amount": str(item.amount)} for item in originals]}


def opening_cash(ctx, payload, doc):
    amount = _amount(payload.get("amount"))
    cash = _cash(ctx, payload.get("account", "CASH"))
    if not payload.get("reason") or not doc.location_id:
        _fail("Reviewed opening cash requires a location and source/reason.")
    _record(doc, amount=amount)
    journal(ctx, doc, [{"account": cash, "debit": amount, "location": doc.location_id}, {"account": "EQUITY", "credit": amount, "location": doc.location_id}])
    return {"amount": str(amount), "account": cash, "opening": True}


def opening_receivable(ctx, payload, doc):
    _location(ctx, doc)
    party = get_obj(ctx, Party, payload.get("party"))
    if party.kind != "customer":
        _fail("Opening receivable requires a customer/debtor.")
    amount = _amount(payload.get("amount"))
    _record(doc, party=party, amount=amount)
    journal(ctx, doc, [{"account": "AR", "debit": amount, "party": party, "location": doc.location_id}, {"account": "EQUITY", "credit": amount, "location": doc.location_id}])
    return {"party": party.id, "amount": str(amount), "outstanding": str(amount), "opening": True}


def opening_payable(ctx, payload, doc):
    _location(ctx, doc)
    party = get_obj(ctx, Party, payload.get("party"))
    if party.kind != "supplier":
        _fail("Opening payable requires a supplier.")
    amount = _amount(payload.get("amount"))
    _record(doc, party=party, amount=amount)
    journal(ctx, doc, [{"account": "EQUITY", "debit": amount, "location": doc.location_id}, {"account": "AP", "credit": amount, "party": party, "location": doc.location_id}])
    return {"party": party.id, "amount": str(amount), "outstanding": str(amount), "opening": True}


def opening_employee_advance(ctx, payload, doc):
    employee = get_obj(ctx, Employee, payload.get("employee"))
    amount = _amount(payload.get("amount"))
    _record(doc, employee=employee, location=employee.location, amount=amount)
    journal(ctx, doc, [{"account": "ADVANCES", "debit": amount, "employee": employee, "location": employee.location}, {"account": "EQUITY", "credit": amount, "location": employee.location}])
    return {"employee": employee.id, "amount": str(amount), "opening": True}


def receivable_writeoff(ctx, payload, doc):
    invoice = _posted(ctx, payload.get("invoice"), {"sale", "opening_receivable"})
    amount = _amount(payload.get("amount"))
    if invoice.date > doc.date or amount > outstanding(invoice):
        _fail("Write-off cannot precede the invoice or exceed its outstanding debt.")
    if not payload.get("reason"):
        _fail("Receivable write-off requires an approved reason.")
    code = payload.get("expense_account", "EXPENSE")
    expense = account(ctx, code)
    if expense.category != "expense" or expense.control:
        _fail("Select a non-control bad-debt expense account.")
    _record(doc, reference=invoice, party=invoice.party, amount=amount)
    journal(ctx, doc, [
        {"account": code, "debit": amount, "party": invoice.party, "location": invoice.location_id},
        {"account": "AR", "credit": amount, "party": invoice.party, "location": invoice.location_id},
    ])
    Allocation.objects.create(document=doc, invoice=invoice, amount=amount)
    return {"invoice": invoice.id, "written_off": str(amount), "remaining": str(outstanding(invoice))}


def asset_acquire(ctx, payload, doc):
    _location(ctx, doc)
    cost = _amount(payload.get("cost"))
    residual = _amount(payload.get("residual", "0"), allow_zero=True)
    try:
        life = int(payload.get("life_months", 0))
    except (TypeError, ValueError):
        _fail("Asset life must be a whole number of months.")
    if life <= 0 or life > 1200 or residual > cost:
        _fail("Asset life must be 1–1200 months and residual value cannot exceed cost.")
    acquired = _date(payload.get("acquired"), doc.date)
    if acquired > doc.date:
        _fail("Asset acquisition cannot be after its accounting posting date.")
    default_start = date(acquired.year + (acquired.month == 12), acquired.month % 12 + 1, 1)
    start = _date(payload.get("depreciation_start"), default_start)
    if start.day != 1 or start < acquired.replace(day=1):
        _fail("Depreciation starts on the first day of an acquisition or later month.")
    name = str(payload.get("name") or "").strip()
    if not name:
        _fail("Asset name is required.")
    location = get_obj(ctx, Location, payload["location"]) if payload.get("location") else doc.location
    supplier = get_obj(ctx, Party, payload["supplier"]) if payload.get("supplier") else None
    if supplier and supplier.kind != "supplier":
        _fail("Select a supplier account.")
    if supplier and payload.get("cash_account"):
        _fail("Choose supplier credit or immediate cash payment.")
    asset = Asset.objects.create(business=ctx.business, name=name, cost=cost, residual=residual, life_months=life, acquired=acquired, location=location, accounting={"depreciation_start": start.isoformat(), "acquisition_document": doc.id})
    _record(doc, party=supplier, amount=cost)
    journal(ctx, doc, [
        {"account": "ASSETS", "debit": cost, "location": location},
        {"account": "AP" if supplier else _cash(ctx, payload.get("cash_account")), "credit": cost, "party": supplier, "location": doc.location_id or location},
    ])
    return {"asset": asset.id, "cost": str(cost), "residual": str(residual), "life_months": life, "depreciation_start": start.isoformat(), "deposit_amount": "0"}


def asset_depreciate(ctx, payload, doc):
    asset = get_obj(ctx, Asset, payload.get("asset"))
    if asset.location_id:
        _record(doc, location=asset.location)
    first, through = _period(payload.get("through_month"))
    if doc.date < through:
        _fail("Post depreciation on or after the end of its covered month.")
    start = _date((asset.accounting or {}).get("depreciation_start"))
    if not start or first < start:
        _fail("Depreciation month precedes this asset's depreciation start.")
    elapsed = min(asset.life_months, (first.year - start.year) * 12 + first.month - start.month + 1)
    history = Document.objects.filter(business=ctx.business, kind="asset_depreciate", state="posted", data__asset=asset.id)
    acquisition = (asset.accounting or {}).get("acquisition_document")
    if acquisition and Document.objects.filter(pk=acquisition, business=ctx.business, date__gt=doc.date).exists():
        _fail("Depreciation cannot precede the asset acquisition posting.")
    if history.filter(date__gt=doc.date).exists():
        _fail("Backdating depreciation before an existing asset charge is unsupported.")
    already = _sum_amount(history)
    target = money((asset.cost - asset.residual) * D(elapsed) / D(asset.life_months))
    amount = money(target - already)
    if amount <= 0:
        _fail("No additional depreciation is due for the selected month.")
    _record(doc, amount=amount, data={**doc.data, "asset": asset.id})
    journal(ctx, doc, [
        {"account": "DEPRECIATION", "debit": amount, "location": asset.location_id},
        {"account": "ACCUM_DEPR", "credit": amount, "location": asset.location_id},
    ])
    return {"asset": asset.id, "amount": str(amount), "accumulated": str(target), "carrying_value": str(asset.cost - target), "through_month": payload["through_month"]}


def journal_adjust(ctx, payload, doc):
    if not str(payload.get("reason") or "").strip():
        _fail("Adjustment journals require a reason.")
    raw = payload.get("lines", [])
    if len(raw) < 2:
        _fail("Provide at least two journal lines.")
    lines = []
    debit_total = credit_total = ZERO
    cash_affected = False
    for item in raw:
        code = str(item.get("account", ""))
        selected = account(ctx, code)
        if selected.control:
            _fail("Direct manual posting to subledger control accounts is prohibited; use the linked workflow.")
        debit = _amount(item.get("debit", "0"), allow_zero=True)
        credit = _amount(item.get("credit", "0"), allow_zero=True)
        if bool(debit) == bool(credit):
            _fail("Each journal line must have exactly one positive debit or credit.")
        location = get_obj(ctx, Location, item["location"]) if item.get("location") else doc.location
        lines.append({"account": code, "debit": debit, "credit": credit, "location": location, "line": _line(item.get("line"))})
        debit_total += debit
        credit_total += credit
        cash_affected = cash_affected or code in CASH_CODES
    if debit_total != credit_total:
        _fail("Journal debits and credits must balance.")
    if cash_affected and payload.get("cash_flow_class") not in {"operating", "investing", "financing"}:
        _fail("A cash adjustment requires an explicit cash-flow classification.")
    _record(doc, amount=debit_total)
    journal(ctx, doc, lines)
    return {"debit": str(debit_total), "credit": str(credit_total), "lines": len(lines)}


def period_close(ctx, payload, doc):
    through = _date(payload.get("through_date"))
    if not through or through > doc.date:
        _fail("Close-through date must be on or before the posting date.")
    if ctx.business.closed_through and through <= ctx.business.closed_through:
        _fail("Period is already closed through this date.")
    ctx.business.closed_through = through
    ctx.business.save(update_fields=["closed_through"])
    return {"closed_through": through.isoformat()}


def period_reopen(ctx, payload, doc):
    if not payload.get("reason"):
        _fail("Reopening a period requires a documented reason.")
    through = _date(payload.get("through_date"))
    old = ctx.business.closed_through
    if not old or (through and through >= old):
        _fail("New lock date must precede the current closed-through date; omit to reopen all periods.")
    ctx.business.closed_through = through
    ctx.business.save(update_fields=["closed_through"])
    return {"previous_closed_through": old.isoformat(), "closed_through": through.isoformat() if through else None}


def _pool_allowance(ctx, pool):
    created = Document.objects.filter(business=ctx.business, kind="inventory_write_down", state="posted", data__pool=pool.id)
    total = ZERO
    for original in created:
        total += original.amount - _sum_amount(_ref_docs(ctx, original, {"inventory_write_down_reverse", "inventory_allowance_release"}))
    return money(total)


def inventory_write_down(ctx, payload, doc):
    ctx.require("cost.view")
    pool = get_obj(ctx, StockPool, payload.get("pool"))
    get_obj(ctx, type(pool.warehouse), pool.warehouse_id)
    get_obj(ctx, Product, pool.product_id)
    if pool.last_date and doc.date < pool.last_date:
        _fail("Backdated valuation before a later stock event is unsupported.")
    amount = _amount(payload.get("amount"))
    previous = _pool_allowance(ctx, pool)
    if pool.quantity <= 0 or amount > pool.value - previous:
        _fail("Write-down cannot exceed the pool's remaining carrying value.")
    if not payload.get("reason"):
        _fail("Write-down requires an approved NRV estimate and reason.")
    _record(doc, amount=amount, warehouse=pool.warehouse, location=pool.warehouse.location, data={**doc.data, "pool": pool.id, "quantity_at_write_down": str(pool.quantity), "expense_account": "IMPAIRMENT"})
    journal(ctx, doc, [
        {"account": "IMPAIRMENT", "debit": amount, "warehouse": pool.warehouse, "location": pool.warehouse.location_id, "line": pool.product.line},
        {"account": "INVENTORY_ALLOWANCE", "credit": amount, "warehouse": pool.warehouse, "location": pool.warehouse.location_id, "line": pool.product.line},
    ])
    pool.last_date = doc.date
    pool.save(update_fields=["last_date"])
    return {"pool": pool.id, "cost_value": str(pool.value), "allowance": str(previous + amount), "carrying_value": str(pool.value - previous - amount)}


def inventory_write_down_reverse(ctx, payload, doc):
    ctx.require("cost.view")
    original = _posted(ctx, payload.get("write_down"), {"inventory_write_down"})
    pool = get_obj(ctx, StockPool, original.data["pool"])
    get_obj(ctx, Product, pool.product_id)
    if original.date > doc.date or (pool.last_date and doc.date < pool.last_date):
        _fail("Valuation reversal cannot precede its write-down or a later stock event.")
    amount = _amount(payload.get("amount"))
    available = original.amount - _sum_amount(_ref_docs(ctx, original, {"inventory_write_down_reverse", "inventory_allowance_release"}))
    if amount > available or pool.quantity <= 0:
        _fail("Reversal cannot exceed the remaining original write-down on stock still held.")
    if not payload.get("reason"):
        _fail("Write-down reversal requires a documented revised NRV estimate.")
    _record(doc, reference=original, warehouse=pool.warehouse, location=pool.warehouse.location, amount=amount)
    journal(ctx, doc, [
        {"account": "INVENTORY_ALLOWANCE", "debit": amount, "warehouse": pool.warehouse, "location": pool.warehouse.location_id, "line": pool.product.line},
        {"account": original.data.get("expense_account", "IMPAIRMENT"), "credit": amount, "warehouse": pool.warehouse, "location": pool.warehouse.location_id, "line": pool.product.line},
    ])
    pool.last_date = doc.date
    pool.save(update_fields=["last_date"])
    return {"write_down": original.id, "reversed": str(amount), "remaining_write_down": str(available - amount)}


def release_inventory_allowance(ctx, doc, pool, quantity_issued, quantity_before, *, expense_account="COGS"):
    """Called by inventory issue services before shrinking a pool; no quantity/cost mutation."""
    if D(quantity_before) <= 0:
        return ZERO
    quantity_issued = D(quantity_issued)
    total = ZERO
    originals = Document.objects.filter(business=ctx.business, state="posted", kind="inventory_write_down", data__pool=pool.id).order_by("id")
    for original in originals:
        remaining = original.amount - _sum_amount(_ref_docs(ctx, original, {"inventory_write_down_reverse", "inventory_allowance_release"}))
        if remaining <= 0:
            continue
        released = remaining if quantity_issued >= quantity_before else money(remaining * quantity_issued / D(quantity_before))
        if not released:
            continue
        part = Document.objects.filter(business=ctx.business, kind="inventory_allowance_release", reference=original, data__issue_document=doc.id).count() + 1
        release = Document.objects.create(business=ctx.business, kind="inventory_allowance_release", number=f"NRV-{doc.id}-{original.id}-{part}", state="draft", date=doc.date, location=doc.location, warehouse=pool.warehouse, reference=original, amount=released, data={"issue_document": doc.id, "pool": pool.id}, result={"amount": str(released)}, created_by=ctx.user, idempotency_key=f"nrv:{doc.id}:{original.id}:{part}", request_hash=doc.request_hash, product_lines=[pool.product.line])
        journal(ctx, release, [
            {"account": "INVENTORY_ALLOWANCE", "debit": released, "warehouse": pool.warehouse, "location": pool.warehouse.location_id, "line": pool.product.line},
            {"account": expense_account, "credit": released, "warehouse": pool.warehouse, "location": pool.warehouse.location_id, "line": pool.product.line},
        ])
        release.state = "posted"
        release.posted_at = timezone.now()
        release.save(update_fields=["state", "posted_at"])
        total += released
    return total


def restore_inventory_allowance(ctx, return_doc, invoice, original_line, returned_quantity, prior_returned_quantity):
    """Reinstate the original sale's net carrying cost on an inspected sales return."""
    released = D(original_line.get("allowance_released", "0"))
    if released <= 0:
        return ZERO
    quantity = D(original_line["quantity"])
    returned_quantity = D(returned_quantity)
    prior_returned_quantity = D(prior_returned_quantity)
    if quantity <= 0 or returned_quantity <= 0 or prior_returned_quantity < 0 or returned_quantity + prior_returned_quantity > quantity:
        _fail("Invalid quantity for reinstating a returned inventory allowance.")
    # Cumulative rounding guarantees that a final full return reinstates the exact release.
    before = money(released * prior_returned_quantity / quantity)
    after = released if prior_returned_quantity + returned_quantity == quantity else money(released * (prior_returned_quantity + returned_quantity) / quantity)
    restored = after - before
    if restored <= 0:
        return ZERO
    if not return_doc.warehouse_id:
        _fail("Returned stock requires a receiving warehouse.")
    product = get_obj(ctx, Product, original_line["product"])
    pool = pool_for(ctx, product, return_doc.warehouse, original_line.get("profile", ""))
    index = original_line.get("index", 0)
    part = Document.objects.filter(business=ctx.business, kind="inventory_write_down", data__return_document=return_doc.id, data__line_index=index).count() + 1
    allowance = Document.objects.create(
        business=ctx.business, kind="inventory_write_down", number=f"NRVRETURN-{return_doc.id}-{index}-{part}", state="draft", date=return_doc.date,
        warehouse=return_doc.warehouse, location=return_doc.warehouse.location, reference=invoice, amount=restored,
        data={"pool": pool.id, "restored_from_invoice": invoice.id, "return_document": return_doc.id, "line_index": index, "expense_account": "COGS", "quantity_at_write_down": str(returned_quantity)},
        result={"restored_allowance": str(restored)}, created_by=ctx.user, idempotency_key=f"nrvreturn:{return_doc.id}:{index}:{part}", request_hash=return_doc.request_hash, product_lines=[product.line],
    )
    journal(ctx, allowance, [
        {"account": "COGS", "debit": restored, "warehouse": pool.warehouse, "location": pool.warehouse.location, "line": product.line},
        {"account": "INVENTORY_ALLOWANCE", "credit": restored, "warehouse": pool.warehouse, "location": pool.warehouse.location, "line": product.line},
    ])
    allowance.state = "posted"
    allowance.posted_at = timezone.now()
    allowance.save(update_fields=["state", "posted_at"])
    return restored


OPERATIONS = {
    "opening_cash": ("accounting.opening", opening_cash),
    "opening_receivable": ("accounting.opening", opening_receivable),
    "opening_payable": ("accounting.opening", opening_payable),
    "opening_employee_advance": ("accounting.opening", opening_employee_advance),
    "employee_advance": ("payroll.post", employee_advance),
    "attendance_record": ("payroll.post", attendance_record),
    "payroll_accrue": ("payroll.post", payroll_accrue),
    "payroll_settle": ("payroll.post", payroll_settle),
    "expense_post": ("finance.post", expense_post),
    "shared_cost_allocate": ("accounting.allocate", shared_cost_allocate),
    "cash_transfer": ("finance.post", cash_transfer),
    "cash_count": ("finance.post", cash_count),
    "bank_reconcile": ("finance.post", bank_reconcile),
    "receipt": ("sales.collect", receipt),
    "supplier_payment": ("purchases.pay", supplier_payment),
    "allocate_deposit": ("finance.post", allocate_deposit),
    "customer_refund": ("sales.refund", customer_refund),
    "supplier_refund": ("purchases.pay", supplier_refund),
    "payment_reverse": ("finance.reverse", payment_reverse),
    "receivable_writeoff": ("accounting.post", receivable_writeoff),
    "asset_acquire": ("accounting.post", asset_acquire),
    "asset_depreciate": ("accounting.post", asset_depreciate),
    "journal_adjust": ("accounting.post", journal_adjust),
    "period_close": ("accounting.close", period_close),
    "period_reopen": ("accounting.close", period_reopen),
    "inventory_write_down": ("inventory.adjust", inventory_write_down),
    "inventory_write_down_reverse": ("inventory.adjust", inventory_write_down_reverse),
}
