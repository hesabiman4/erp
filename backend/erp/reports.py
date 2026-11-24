"""Permission-scoped reports derived from posted ledgers, never fixture arrays."""
from datetime import date, timedelta
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q, Sum
from django.utils import timezone

from .models import Account, Allocation, Asset, Document, Employee, Entry, Location, Party, StockMovement, StockPool
from .core import D, balance, get_obj, money
from .chart import account_group


ZERO = Decimal("0")
INVENTORY_CODES = {"RAW", "WIP", "FG", "TRIM", "TRANSIT"}
CASH_CODES = {"CASH", "BANK", "FX_CASH", "FX_BANK"}


def _date(value, default=None):
    try:
        return date.fromisoformat(str(value)) if value else default
    except (TypeError, ValueError):
        raise ValidationError("Report dates must use YYYY-MM-DD.")


def _bounds(params):
    if params.get('calendar_period'):
        from .calendar_periods import month_bounds
        first,last=month_bounds(params['calendar_period'],params.get('period_calendar','gregorian'))
        for key,expected in [('date_from',first),('from',first),('date_to',last),('as_of',last),('to',last)]:
            if params.get(key) and _date(params[key])!=expected:
                raise ValidationError('Calendar period and explicit report dates must have the same boundaries.')
        return first,last
    through = _date(params.get("date_to") or params.get("as_of") or params.get("to"), timezone.localdate())
    since = _date(params.get("date_from") or params.get("from"))
    if since and since > through:
        raise ValidationError("Report start date cannot be after its end date.")
    return since, through


def _scope(ctx, query, params, *, relation="", location_field="location_id", line_field=None):
    if not ctx.membership.all_locations:
        query = query.filter(**{relation + location_field + "__in": ctx.membership.location_ids})
    location = params.get("location")
    if location:
        selected = get_obj(ctx, Location, location)
        query = query.filter(**{relation + location_field: selected.id})
    if line_field:
        query = query.filter(**{relation + line_field + "__in": ctx.membership.product_lines})
        if params.get("line"):
            if not ctx.line_allowed(params["line"]):
                raise PermissionDenied("Product line is outside your assignment.")
            query = query.filter(**{relation + line_field: params["line"]})
    return query


def _entries(ctx, params, *, period=True):
    since, through = _bounds(params)
    query = Entry.objects.filter(document__business=ctx.business, document__state="posted", document__date__lte=through)
    if period and since:
        query = query.filter(document__date__gte=since)
    if not ctx.has("documents.all_lines"):
        query = query.filter(document__product_lines__contained_by=list(ctx.membership.product_lines))
    return _scope(ctx, query, params, line_field="line")


def _documents(ctx, params, kinds=None):
    since, through = _bounds(params)
    query = Document.objects.filter(business=ctx.business, state="posted", date__lte=through)
    if since:
        query = query.filter(date__gte=since)
    if kinds:
        query = query.filter(kind__in=kinds)
    query = _scope(ctx, query, params)
    # Documents spanning restricted lines must not leak their full amounts.
    if not ctx.has("documents.all_lines"):
        permitted = set(ctx.membership.product_lines)
        query = query.filter(pk__in=[doc.pk for doc in query.only("pk", "product_lines") if set(doc.product_lines).issubset(permitted)])
    if params.get("line"):
        if not ctx.line_allowed(params["line"]):
            raise PermissionDenied("Product line is outside your assignment.")
        query = query.filter(product_lines__contains=[params["line"]])
    return query


def _net(query):
    values = query.aggregate(dr=Sum("debit"), cr=Sum("credit"))
    return money((values["dr"] or ZERO) - (values["cr"] or ZERO))


def _sum(query, field="amount"):
    return query.aggregate(value=Sum(field))["value"] or ZERO


def _table(name, columns, rows, totals, params, **extra):
    _, through = _bounds(params)
    return {"name": name, "columns": [{"key": key, "label": label} for key, label in columns], "rows": rows, "totals": totals, "as_of": through.isoformat(), **extra}


def _company(ctx, params):
    if params.get("location") or params.get("line"):
        raise ValidationError("Company trial balance and balance sheet do not support branch/product filters. Use branch profit reports.")
    _, through = _bounds(params)
    used_lines = set(Entry.objects.filter(document__business=ctx.business, document__state="posted", document__date__lte=through).values_list("line", flat=True))
    if not ctx.membership.all_locations or not used_lines.issubset(set(ctx.membership.product_lines)):
        raise PermissionDenied("Complete business accounting scope is required for company financial statements.")


def trial_balance(ctx, params):
    _company(ctx, params)
    query = _entries(ctx, params, period=False)
    rows, total_debit, total_credit = [], ZERO, ZERO
    for item in query.values("account__code", "account__name", "account__category").annotate(dr=Sum("debit"), cr=Sum("credit")).order_by("account__code"):
        net = money((item["dr"] or ZERO) - (item["cr"] or ZERO))
        debit, credit = max(net, ZERO), max(-net, ZERO)
        total_debit += debit
        total_credit += credit
        rows.append({"account": item["account__code"], "name": item["account__name"], "category": item["account__category"], "debit": str(debit), "credit": str(credit), "balance": str(net)})
    return _table("trial_balance", [("account", "Account"), ("name", "Name"), ("debit", "Debit"), ("credit", "Credit")], rows, {"debit": str(total_debit), "credit": str(total_credit), "difference": str(total_debit - total_credit)}, params)


def profit_loss(ctx, params):
    query = _entries(ctx, params).filter(account__category__in=["income", "expense"])
    rows, revenue, expense = [], ZERO, ZERO
    grouped={}
    accounts={a.code:a for a in Account.objects.filter(business=ctx.business)}
    for item in query.values("account__code", "account__name", "account__category").annotate(dr=Sum("debit"), cr=Sum("credit")).order_by("account__category", "account__code"):
        net = money((item["dr"] or ZERO) - (item["cr"] or ZERO))
        amount = -net if item["account__category"] == "income" else net
        if item["account__category"] == "income":
            revenue += amount
        else:
            expense += amount
        group=account_group(accounts[item['account__code']])
        grouped.setdefault(group,[]).append({'account':item['account__code'],'number':accounts[item['account__code']].number,'name':item['account__name'],'amount':str(amount)})
        rows.append({"account": item["account__code"], "name": item["account__name"], "category": item["account__category"], "amount": str(amount),'group':group})
    cogs = _net(query.filter(account__code="COGS"))
    group_total=lambda key:sum((D(r['amount']) for r in grouped.get(key,[])),ZERO)
    sales=group_total('revenue'); cost=group_total('cost_of_sales')
    operating=sales-cost+group_total('other_operating_income')-sum((group_total(k) for k in ['administrative_expenses','selling_expenses','other_operating_expenses']),ZERO)
    before_financing=operating+group_total('investing_income')+group_total('finance_income')
    before_tax=before_financing-group_total('finance_costs')
    order=['revenue','cost_of_sales','other_operating_income','administrative_expenses','selling_expenses','other_operating_expenses','investing_income','finance_income','finance_costs','income_tax']
    sections=[{'key':key,'rows':sorted(grouped.get(key,[]),key=lambda r:(r.get('number') or '99999',r['account'])),'total':str(group_total(key))} for key in order]
    return _table("profit_loss", [("account", "Account"), ("name", "Name"), ("category", "Type"), ("amount", "Amount")], rows, {"revenue": str(revenue), "cost_of_goods_sold": str(cogs), "gross_profit": str(sales-cost), "expenses": str(expense), "profit": str(revenue - expense),'operating_profit':str(operating),'profit_before_financing_and_tax':str(before_financing),'profit_before_tax':str(before_tax)}, params, sections=sections,statement=True,date_from=(_bounds(params)[0].isoformat() if _bounds(params)[0] else None),note="Manufacturing management statement with function-based expenses and operating/investing/financing subtotals. This is not a full IFRS disclosure package; branch/product figures precede separately posted shared-cost allocations.")


def balance_sheet(ctx, params):
    _company(ctx, params)
    query = _entries(ctx, params, period=False)
    rows = [];grouped={};accounts={a.code:a for a in Account.objects.filter(business=ctx.business)}
    totals = {"asset": ZERO, "liability": ZERO, "equity": ZERO}
    for item in query.filter(account__category__in=totals).values("account__code", "account__name", "account__category").annotate(dr=Sum("debit"), cr=Sum("credit")).order_by("account__category", "account__code"):
        category = item["account__category"]
        net = money((item["dr"] or ZERO) - (item["cr"] or ZERO))
        amount = net if category == "asset" else -net
        totals[category] += amount
        group=account_group(accounts[item['account__code']])
        grouped.setdefault(group,[]).append({'account':item['account__code'],'number':accounts[item['account__code']].number,'name':item['account__name'],'amount':str(amount)})
        rows.append({"account": item["account__code"], "name": item["account__name"], "category": category, "amount": str(amount)})
    earnings = -_net(query.filter(account__category__in=["income", "expense"]))
    rows.append({"account": "UNAPPROPRIATED_EARNINGS", "name": "Accumulated unclosed earnings", "category": "equity", "amount": str(earnings)})
    equity = totals["equity"] + earnings
    grouped.setdefault('equity',[]).append({'account':'UNAPPROPRIATED_EARNINGS','number':'','name':'Accumulated unclosed earnings','amount':str(earnings)})
    sections=[{'key':key,'rows':sorted(grouped.get(key,[]),key=lambda r:(r.get('number') or '99999',r['account'])),'total':str(sum((D(r['amount']) for r in grouped.get(key,[])),ZERO))} for key in ['noncurrent_assets','current_assets','noncurrent_liabilities','current_liabilities','equity']]
    return _table("balance_sheet", [("category", "Type"), ("account", "Account"), ("name", "Name"), ("amount", "Amount")], rows, {"assets": str(totals["asset"]), "liabilities": str(totals["liability"]), "equity_including_earnings": str(equity), "unclosed_earnings": str(earnings), "difference": str(totals["asset"] - totals["liability"] - equity),"liabilities_and_equity":str(totals["liability"]+equity)}, params,sections=sections,statement=True)


def cash_flow(ctx, params):
    if params.get("line"):
        raise ValidationError("Cash flow is measured by business/location; product-line cash allocation is not implemented.")
    since, through = _bounds(params)
    scoped = _entries(ctx, params)
    cash_entries = scoped.filter(account__code__in=CASH_CODES)
    totals = {"operating": ZERO, "investing": ZERO, "financing": ZERO, "internal_transfer": ZERO, "exchange_effect": ZERO, "unclassified": ZERO}
    rows = []
    restricted_payroll = ZERO
    for item in cash_entries.values("document_id", "document__number", "document__date", "document__kind").annotate(dr=Sum("debit"), cr=Sum("credit")).order_by("document__date", "document_id"):
        value = money((item["dr"] or ZERO) - (item["cr"] or ZERO))
        if not value:
            continue
        doc = Document.objects.get(pk=item["document_id"])
        classified = doc.reference if doc.kind == "payment_reverse" and doc.reference_id else doc
        if classified.kind in {'fx_remit_dispatch','fx_remit_receive'}:
            if classified.kind=='fx_remit_dispatch':
                fee=-_net(cash_entries.filter(document=doc,account__code__in=['CASH','BANK']))
                parts=[('operating',-fee),('internal_transfer',value+fee)]
            else:
                from .models import Remittance
                remit=Remittance.objects.get(completed_by=doc,business=ctx.business)
                effect=D(doc.result['carrying_amount'])-remit.carrying_amount
                parts=[('exchange_effect',effect),('internal_transfer',value-effect)]
            for kind,part in parts:
                if part:
                    totals[kind]+=part;rows.append({'date':item['document__date'].isoformat(),'document':item['document__number'],'kind':doc.kind,'category':kind,'cash_change':str(part)})
            continue
        if classified.kind=='fx_exchange':
            from .models import ForeignWallet
            wallet=ForeignWallet.objects.get(pk=classified.data['wallet'],business=ctx.business)
            location=int(params['location']) if params.get('location') else None
            gain=D(classified.result.get('exchange_gain','0')) if (not location or location==wallet.location_id) else ZERO
            fee=D(classified.result.get('fee','0')) if (not location or location==classified.location_id) else ZERO
            for kind,part in [('exchange_effect',gain),('operating',-fee),('internal_transfer',value-gain+fee)]:
                if part:
                    totals[kind]+=part;rows.append({'date':item['document__date'].isoformat(),'document':item['document__number'],'kind':doc.kind,'category':kind,'cash_change':str(part)})
            continue
        if classified.kind=='fx_revalue':
            category='exchange_effect'
        elif classified.kind in {"cash_transfer", "internal_settlement", "fx_remit_dispatch", "fx_remit_receive"}:
            category = "internal_transfer"
        elif classified.kind == "asset_acquire":
            category = "investing"
        elif classified.kind=='expense_post' and classified.data.get('expense_account')=='INTEREST_EXPENSE':
            category = 'financing'
        elif classified.kind == "journal_adjust":
            category = classified.data.get("cash_flow_class", "unclassified")
            if category not in totals:
                category = "unclassified"
        else:
            # Supplier settlement of a fixed-asset invoice is investing.
            asset_payment = classified.kind == "supplier_payment" and classified.allocations.filter(invoice__kind="asset_acquire").exists()
            if asset_payment and (classified.allocations.exclude(invoice__kind="asset_acquire").exists() or D(classified.result.get("deposit_amount", "0"))):
                category = "unclassified"
            elif asset_payment:
                category = "investing"
            elif classified.kind in {"opening_cash","fx_opening"} or classified.kind.startswith("opening") or classified.kind in {"owner_contribution", "owner_drawing", "loan_receipt", "loan_repayment"}:
                category = "financing" if classified.kind == "opening_cash" or not classified.kind.startswith("opening") else "unclassified"
            else:
                category = "operating"
        totals[category] += value
        if doc.employee_id and not ctx.has("payroll.view"):
            restricted_payroll += value
        else:
            rows.append({"date": item["document__date"].isoformat(), "document": item["document__number"], "kind": doc.kind, "category": category, "cash_change": str(value)})
    if restricted_payroll:
        rows.append({"date": "", "document": "Employee cash movements — detail restricted", "kind": "restricted_employee_summary", "category": "operating", "cash_change": str(restricted_payroll)})
    cumulative = _entries(ctx, params, period=False).filter(account__code__in=CASH_CODES)
    closing = _net(cumulative)
    opening = _net(cumulative.filter(document__date__lt=since)) if since else ZERO
    change = sum(totals.values(), ZERO)
    return _table("cash_flow", [("date", "Date"), ("document", "Document"), ("category", "Classification"), ("cash_change", "Cash change")], rows, {**{key: str(value) for key, value in totals.items()}, "opening_cash": str(opening), "closing_cash": str(closing), "net_change": str(change), "difference": str(closing - opening - change)}, params, method="Direct method from posted cash/bank entries. Internal transfers net to zero for the complete business. Unclassified movements require review.")


def cash_balances(ctx, params):
    if params.get("line"):
        raise ValidationError("Cash balances are not allocated between product lines.")
    query = _entries(ctx, params, period=False).filter(account__code__in=CASH_CODES)
    values = query.values("account__code", "location_id", "location__name").annotate(dr=Sum("debit"), cr=Sum("credit")).order_by("location__name", "account__code")
    rows, cash, bank, negative_cash, negative_bank = [], ZERO, ZERO, 0, 0
    for item in values:
        amount = money((item["dr"] or ZERO) - (item["cr"] or ZERO))
        code = item["account__code"]
        if code in {"CASH","FX_CASH"}:
            cash += amount
            negative_cash += int(amount < 0)
        else:
            bank += amount
            negative_bank += int(amount < 0)
        rows.append({"account": code, "location_id": item["location_id"], "location": item["location__name"] or "Unassigned — review required", "balance": str(amount), "negative": amount < 0, "review_required": amount < 0 or item["location_id"] is None})
    return _table("cash_balances", [("location", "Location"), ("account", "Account"), ("balance", "Recorded balance"), ("negative", "Negative"), ("review_required", "Review required")], rows, {"cash": str(cash), "bank": str(bank), "total": str(cash + bank), "negative_cash_accounts": negative_cash, "negative_bank_accounts": negative_bank}, params, note="Negative physical cash indicates missing/incorrect records and requires reconciliation. A negative bank balance may reflect an authorized overdraft; this report does not grant spending authority.")


def chart_of_accounts(ctx, params):
    entries=_entries(ctx,params,period=False)
    balances={r['account_id']:money((r['dr'] or ZERO)-(r['cr'] or ZERO)) for r in entries.values('account_id').annotate(dr=Sum('debit'),cr=Sum('credit'))}
    records=[]
    for item in Account.objects.filter(business=ctx.business).order_by('number','code'):
        records.append({'id':item.id,'number':item.number,'code':item.code,'name':item.name,'category':item.category,'group':account_group(item),'control':item.control,'balance':str(balances.get(item.id,ZERO)),'classification_review':not item.statement_group})
    return _table('chart_of_accounts',[(key,label) for key,label in [('number','Number'),('code','Posting key'),('name','Account'),('category','Type'),('group','Report group'),('balance','Debit less credit'),('control','Control account')]],records,{},params)


def changes_equity(ctx, params):
    _company(ctx,params)
    since,_=_bounds(params);cumulative=_entries(ctx,params,period=False)
    before=cumulative.filter(document__date__lt=since) if since else cumulative.none()
    opening=-_net(before.filter(account__category__in=['equity','income','expense']))
    activity=_entries(ctx,params);records=[{'account':'OPENING','name':'Opening equity','amount':str(opening)}]
    for row in activity.filter(account__category='equity').values('account__code','account__name').annotate(dr=Sum('debit'),cr=Sum('credit')).order_by('account__code'):
        records.append({'account':row['account__code'],'name':row['account__name'],'amount':str(money((row['cr'] or ZERO)-(row['dr'] or ZERO)))})
    profit=-_net(activity.filter(account__category__in=['income','expense']))
    records.append({'account':'PERIOD_PROFIT','name':'Profit for the period','amount':str(profit)})
    closing=-_net(cumulative.filter(account__category__in=['equity','income','expense']))
    return _table('changes_equity',[('account','Account'),('name','Description'),('amount','Amount')],records,{'opening_equity':str(opening),'profit':str(profit),'closing_equity':str(closing),'difference':str(closing-sum((D(r['amount']) for r in records),ZERO))},params,statement=True,sections=[{'key':'equity_movements','rows':records,'total':str(closing)}],date_from=since.isoformat() if since else None)


def aging(ctx, params, *, supplier=False):
    if params.get("line"):
        raise ValidationError("Invoice debt is not allocated between product lines. Use complete invoice/party balances.")
    _, through = _bounds(params)
    kinds = {"purchase_bill", "expense_post", "asset_acquire", "opening_payable"} if supplier else {"sale", "opening_receivable"}
    # Aging is cumulative through the as-of date; the start-date filter does not drop old debts.
    cumulative = {key: value for key, value in params.items() if key not in {"date_from", "from"}}
    invoices = _documents(ctx, cumulative, kinds).filter(party__isnull=False).select_related("party")
    rows, total = [], ZERO
    buckets = {"current": ZERO, "1_30": ZERO, "31_60": ZERO, "61_90": ZERO, "over_90": ZERO}
    for invoice in invoices.order_by("date", "id"):
        # Immediate cash expenses have no payable, even though they have an operational amount.
        if supplier and not invoice.entries.filter(account__code="AP", credit__gt=0).exists():
            continue
        settled = Allocation.objects.filter(invoice=invoice, document__state="posted", document__date__lte=through).aggregate(value=Sum("amount"))["value"] or ZERO
        remaining = money(invoice.amount - settled)
        from .models import ForeignExposure
        exposure=ForeignExposure.objects.filter(invoice=invoice).first()
        if exposure:
            from .foreign import exposure_balance
            foreign_remaining,remaining=exposure_balance(exposure,through)
        if remaining <= 0:
            continue
        due = _date(invoice.data.get("due_date"), invoice.date)
        days = (through - due).days
        bucket = "current" if days <= 0 else "1_30" if days <= 30 else "31_60" if days <= 60 else "61_90" if days <= 90 else "over_90"
        buckets[bucket] += remaining
        total += remaining
        rows.append({"invoice_id": invoice.id, "invoice": invoice.number, "party_id": invoice.party_id, "party": invoice.party.name, "date": invoice.date.isoformat(), "due_date": due.isoformat(), "days_overdue": max(0, days), "amount": str(invoice.amount), "settled": str(money(settled)), "outstanding": str(remaining), "bucket": bucket})
    return _table("payables" if supplier else "receivables", [("invoice", "Invoice"), ("party", "Party"), ("due_date", "Due date"), ("days_overdue", "Days overdue"), ("outstanding", "Outstanding")], rows, {"outstanding": str(total), **{key: str(value) for key, value in buckets.items()}}, params)


def employee_balances(ctx, params):
    _, through = _bounds(params)
    employees = _scope(ctx, Employee.objects.filter(business=ctx.business), params)
    rows, advances, payable = [], ZERO, ZERO
    for employee in employees.order_by("name"):
        advance = money(balance(ctx, "ADVANCES", employee=employee, through=through))
        owed = -money(balance(ctx, "PAYROLL", employee=employee, through=through))
        advances += advance
        payable += owed
        rows.append({"employee_id": employee.id, "employee": employee.name, "kind": employee.kind, "advance": str(advance), "payroll_payable": str(owed)})
    return _table("employee_balances", [("employee", "Employee"), ("kind", "Type"), ("advance", "Employee advance"), ("payroll_payable", "Payroll payable")], rows, {"advances": str(advances), "payroll_payable": str(payable)}, params)


def assets(ctx, params):
    _, through = _bounds(params)
    records = _scope(ctx, Asset.objects.filter(business=ctx.business, acquired__lte=through), params)
    rows, cost_total, depreciation_total = [], ZERO, ZERO
    for asset in records.order_by("name"):
        depreciation = _sum(Document.objects.filter(business=ctx.business, state="posted", kind="asset_depreciate", date__lte=through, data__asset=asset.id))
        cost_total += asset.cost
        depreciation_total += depreciation
        rows.append({"asset_id": asset.id, "name": asset.name, "acquired": asset.acquired.isoformat(), "cost": str(asset.cost), "residual": str(asset.residual), "life_months": asset.life_months, "depreciation": str(money(depreciation)), "carrying_value": str(money(asset.cost - depreciation))})
    return _table("assets", [("name", "Asset"), ("acquired", "Acquired"), ("cost", "Cost"), ("depreciation", "Depreciation"), ("carrying_value", "Carrying value")], rows, {"cost": str(cost_total), "depreciation": str(depreciation_total), "carrying_value": str(cost_total - depreciation_total)}, params)


def inventory_reconciliation(ctx, params):
    if not (ctx.has("inventory.raw") or ctx.has("consumption.view")):
        raise PermissionDenied("Full stock reconciliation includes confidential raw-material quantities and requires raw inventory access.")
    _, through = _bounds(params)
    pools = StockPool.objects.filter(business=ctx.business, product__line__in=ctx.membership.product_lines).select_related("product", "warehouse__location")
    pools = _scope(ctx, pools, params, location_field="warehouse__location_id")
    if params.get("line"):
        if not ctx.line_allowed(params["line"]):
            raise PermissionDenied("Restricted product line.")
        pools = pools.filter(product__line=params["line"])
    rows, total_cost = [], ZERO
    history = {row['pool_id']:row for row in StockMovement.objects.filter(pool__in=pools,document__state='posted',document__date__lte=through).values('pool_id').annotate(quantity=Sum('quantity'),value=Sum('value'))}
    for pool in pools.order_by("product__code", "warehouse_id", "profile"):
        values = history.get(pool.pk,{})
        quantity, cost = values.get("quantity") or ZERO, money(values.get("value") or ZERO)
        total_cost += cost
        rows.append({"pool_id": pool.id, "product": pool.product.name, "code": pool.product.code, "warehouse": pool.warehouse.name, "profile": pool.profile, "unit": pool.product.unit, "quantity": str(quantity), "cost_value": str(cost), "unit_cost": str(cost / quantity if quantity else ZERO)})
    entries = _entries(ctx, params, period=False)
    # WIP need not have a finished-stock pool while an actual batch is open.
    physical_controls = INVENTORY_CODES - {"WIP"}
    gl_cost = _net(entries.filter(account__code__in=physical_controls))
    allowance = -_net(entries.filter(account__code="INVENTORY_ALLOWANCE"))
    wip = _net(entries.filter(account__code="WIP"))
    return _table("inventory_reconciliation", [("product", "Product"), ("warehouse", "Warehouse"), ("profile", "Size profile"), ("quantity", "Quantity"), ("unit", "Unit"), ("cost_value", "Cost value")], rows, {"stock_cost": str(total_cost), "inventory_controls_excluding_wip": str(gl_cost), "difference": str(total_cost - gl_cost), "valuation_allowance": str(allowance), "net_stock_value": str(total_cost - allowance), "work_in_progress": str(wip)}, params)


def general_ledger(ctx, params):
    query = _entries(ctx, params).select_related("account", "document", "location", "party", "employee").order_by("document__date", "document_id", "id")
    if not ctx.has("payroll.view"):
        query = query.filter(employee__isnull=True, document__employee__isnull=True)
    if params.get("account"):
        query = query.filter(account__code=params["account"])
    rows = [{"date": item.document.date.isoformat(), "document": item.document.number, "account": item.account.code, "name": item.account.name, "debit": str(item.debit), "credit": str(item.credit), "line": item.line, "location": item.location.name if item.location else "", "party": item.party.name if item.party else "", "employee": item.employee.name if item.employee and ctx.has("payroll.view") else ""} for item in query[:10000]]
    sums = query.aggregate(dr=Sum("debit"), cr=Sum("credit"))
    return _table("general_ledger", [("date", "Date"), ("document", "Document"), ("account", "Account"), ("debit", "Debit"), ("credit", "Credit"), ("line", "Product line")], rows, {"debit": str(sums["dr"] or ZERO), "credit": str(sums["cr"] or ZERO)}, params, truncated=query.count() > 10000, payroll_detail_included=ctx.has("payroll.view"), note="Employee-linked journal detail is excluded without payroll permission; financial statements retain aggregate control balances.")


def party_center(ctx, params, *, supplier=False, statement=False):
    """AR/AP control activity only; deposits are separate, never extra revenue/payment."""
    if params.get("line"):
        raise ValidationError("Party debt is not allocated between product lines.")
    since, through = _bounds(params)
    control, deposit = ("AP", "SUPPLIER_DEPOSITS") if supplier else ("AR", "DEPOSITS")
    sign = Decimal("-1") if supplier else Decimal("1")
    parties = Party.objects.filter(business=ctx.business, kind="supplier" if supplier else "customer")
    entries = _entries(ctx, params, period=False).filter(account__code__in=[control, deposit], party__in=parties)
    if statement:
        party = get_obj(ctx, Party, params.get("party"))
        if party.kind != ("supplier" if supplier else "customer"):
            raise ValidationError("The selected party has the wrong account type.")
        entries = entries.filter(party=party)
        opening = sign * _net(entries.filter(account__code=control, document__date__lt=since)) if since else ZERO
        activity = entries.filter(account__code=control)
        if since:
            activity = activity.filter(document__date__gte=since)
        running, records = opening, []
        for item in activity.select_related("document").order_by("document__date", "document_id", "id"):
            running += sign * (item.debit - item.credit)
            records.append({"id": item.id, "document_id": item.document_id, "date": item.document.date.isoformat(), "number": item.document.number, "kind": item.document.kind, "debit": str(item.debit), "credit": str(item.credit), "balance": str(money(running))})
        debts = aging(ctx, params, supplier=supplier)
        open_invoices = [r for r in debts["rows"] if r["party_id"] == party.id]
        deposit_balance = money((-sign) * _net(entries.filter(account__code=deposit)) + ZERO)
        return _table("supplier_statement" if supplier else "customer_statement", [("date", "Date"), ("number", "Document"), ("debit", "Debit"), ("credit", "Credit"), ("balance", "Balance")], records, {"opening": str(opening), "balance": str(money(running)), "deposit": str(deposit_balance)}, params, party={"id": party.id, "name": party.name, "phone": party.phone, "address": party.address, "notes": party.notes,"group_name":party.group_name,"registration_number":party.registration_number,"delivery_address":party.delivery_address,"contacts":party.contacts,"payment_terms_days":party.payment_terms_days,**({"credit_limit":str(party.credit_limit) if party.credit_limit is not None else None,"payment_terms_days":party.payment_terms_days,"credit_hold":party.credit_hold,"block_overdue":party.block_overdue} if any(ctx.has(p) for p in ["settings.manage","sales.credit_manage"]) else {})}, open_invoices=open_invoices)
    grouped = {}
    for item in entries.values("party_id", "account__code").annotate(dr=Sum("debit"), cr=Sum("credit")):
        grouped[(item["party_id"], item["account__code"])] = money((item["dr"] or ZERO) - (item["cr"] or ZERO))
    overdue = {}
    for invoice in aging(ctx, params, supplier=supplier)["rows"]:
        if invoice["days_overdue"] > 0:
            overdue[invoice["party_id"]] = overdue.get(invoice["party_id"], ZERO) + D(invoice["outstanding"])
    records = []
    query = str(params.get("q") or "").strip()
    if query:
        parties = parties.filter(Q(name__icontains=query) | Q(phone__icontains=query) | Q(address__icontains=query))
    for party in parties.order_by("name", "id"):
        records.append({"id": party.id, "name": party.name, "phone": party.phone, "address": party.address,"group_name":party.group_name, "balance": str(money(sign * grouped.get((party.id, control), ZERO) + ZERO)), "deposit": str(money(-sign * grouped.get((party.id, deposit), ZERO) + ZERO)), "overdue": str(money(overdue.get(party.id, ZERO)))})
    return _table("supplier_balances" if supplier else "customer_balances", [("name", "Name"), ("phone", "Phone"), ("balance", "Balance"), ("deposit", "Deposit"), ("overdue", "Overdue")], records, {key: str(money(sum((D(r[key]) for r in records), ZERO))) for key in ("balance", "deposit", "overdue")}, params)


def dashboard(ctx, params):
    entries = _entries(ctx, params)
    cumulative = _entries(ctx, params, period=False)
    can_cost = ctx.has("cost.view")
    can_finance = ctx.has("finance.view") or ctx.has("accounting.view")
    can_sales = ctx.has("sales.view") or ctx.has("accounting.view")
    values = {
        "sales": str(-_net(entries.filter(account__code="SALES"))) if can_sales else None,
        "collections": None,
        "receivables": str(_net(cumulative.filter(account__code="AR"))) if can_sales else None,
        "payables": str(-_net(cumulative.filter(account__code="AP"))) if can_finance else None,
        "cash": str(_net(cumulative.filter(account__code__in=CASH_CODES))) if can_finance else None,
        "inventory_value": str(_net(cumulative.filter(account__code__in=INVENTORY_CODES | {"INVENTORY_ALLOWANCE"}))) if can_cost else None,
        "production_cm": "0",
        "waste_value": str(_net(entries.filter(account__code="WASTE"))) if can_cost else None,
    }
    if can_finance or can_sales:
        customer_cash = entries.filter(account__code__in=CASH_CODES).filter(
            Q(document__kind__in=["receipt", "sale", "customer_refund"])
            | Q(document__kind="payment_reverse", document__reference__kind="receipt")
            | Q(document__kind="fx_settle",document__reference__kind__in=['sale','opening_receivable'])
            | Q(document__kind="fx_settlement_reverse",document__reference__reference__kind__in=['sale','opening_receivable'])
            | Q(document__kind__in=['fx_deposit','fx_refund'],document__party__kind='customer'))
        values["collections"] = str(_net(customer_cash))
    if params.get("line"):
        for key in ("collections", "receivables", "payables", "cash"):
            values[key] = None
    produced = _documents(ctx, params, {"production_complete", "production", "production_bom"})
    # Output is measured from positive finished-sponge movements on production documents.
    movement_query = StockMovement.objects.filter(document__in=produced, quantity__gt=0, pool__product__unit="cm", pool__product__kind="finished")
    values["production_cm"] = str(_sum(movement_query, "quantity"))
    _, through = _bounds(params)
    chart_params = {**params, "date_from": (through - timedelta(days=6)).isoformat()}
    # Bound the chart independently of the selected KPI period and never sample a document page.
    chart_params.pop("from", None)
    amounts = {}
    if can_sales:
        for item in _entries(ctx, chart_params).filter(account__code="SALES").values("document__date").annotate(dr=Sum("debit"), cr=Sum("credit")):
            amounts[item["document__date"]] = money((item["cr"] or ZERO) - (item["dr"] or ZERO))
    values["sales_series"] = [{"date": (through - timedelta(days=6-i)).isoformat(), "amount": str(amounts.get(through - timedelta(days=6-i), ZERO))} for i in range(7)] if can_sales else None
    values["profit"] = profit_loss(ctx, params)["totals"]["profit"] if can_cost and ctx.has("accounting.view") else None
    values["as_of"] = through.isoformat()
    return values


REPORTS = {
    "employee_statement": ("payroll.view",lambda ctx,params: __import__('erp.employee_reports',fromlist=['employee_statement']).employee_statement(ctx,params)),
    "chart_of_accounts": ("accounting.view",chart_of_accounts),
    "changes_equity": ("accounting.view",changes_equity),
    "customer_balances": ("sales.view", party_center),
    "supplier_balances": ("purchases.view", lambda ctx, params: party_center(ctx, params, supplier=True)),
    "customer_statement": ("sales.view", lambda ctx, params: party_center(ctx, params, statement=True)),
    "supplier_statement": ("purchases.view", lambda ctx, params: party_center(ctx, params, supplier=True, statement=True)),
    "trial_balance": ("accounting.view", trial_balance),
    "profit_loss": ("accounting.view", profit_loss),
    "balance_sheet": ("accounting.view", balance_sheet),
    "cash_flow": ("accounting.view", cash_flow),
    "cash_balances": ("finance.view", cash_balances),
    "general_ledger": ("accounting.view", general_ledger),
    "receivables": ("sales.view", lambda ctx, params: aging(ctx, params)),
    "payables": ("purchases.view", lambda ctx, params: aging(ctx, params, supplier=True)),
    "employee_balances": ("payroll.view", employee_balances),
    "assets": ("accounting.view", assets),
    "inventory_reconciliation": ("cost.view", inventory_reconciliation),
    "dashboard": ("reports.view", dashboard),
    "summary": ("reports.view", dashboard),
}


def report(ctx, name, params=None):
    params = params or {}
    if name not in REPORTS:
        if name in {"production_batches", "production_waste", "stock_movements", "block_history", "transfer_status"}:
            from .operations import manufacturing_report
            return manufacturing_report(ctx, name, params)
        raise ValidationError("Unknown report.")
    permission, handler = REPORTS[name]
    ctx.require(permission)
    result=handler(ctx, params)
    if params.get('compare_to') and name in {'profit_loss','balance_sheet','changes_equity'}:
        comparative={k:v for k,v in params.items() if k not in {'compare_to','compare_from','from','to','date_from','date_to','as_of','calendar_period','period_calendar'}}
        comparative.update({'from':params.get('compare_from',''),'to':params['compare_to']})
        result['comparative']=handler(ctx,comparative)
    return result
