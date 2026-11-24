"""Shared decimal, isolation, stock, and atomic posting primitives."""
import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from .models import (Business, Membership, Location, Warehouse, Product, Account,
    Document, Sequence, StockPool, StockMovement, Entry, Allocation, AuditEvent, Position, Party)

ZERO = Decimal('0')
CENT = Decimal('0.01')
QTY = Decimal('0.000001')
MILLIMETER = Decimal('0.001')
NUMERALS = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩٫٬', '01234567890123456789.,')

def D(value):
    if isinstance(value, (float, bool)):
        raise ValidationError('Send exact decimal quantities as strings, not floating-point values.')
    try:
        normalized=str(value).translate(NUMERALS).strip()
        if ',' in normalized and not re.fullmatch(r'[+-]?\d{1,3}(,\d{3})+(\.\d+)?',normalized):
            raise ValidationError('Use a decimal point or correctly grouped thousands; an ambiguous comma is not accepted.')
        result = Decimal(normalized.replace(',', ''))
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError('Invalid decimal quantity.')
    if not result.is_finite() or abs(result) >= Decimal('1e16'):
        raise ValidationError('Quantity is not finite or exceeds the supported range.')
    return result

def money(value): return D(value).quantize(CENT, rounding=ROUND_HALF_UP)
def profile_for(length, width): return f'{D(length):.3f}x{D(width):.3f}'

def json_value(value):
    if isinstance(value, Decimal): return format(value, 'f')
    if isinstance(value, (date,)): return value.isoformat()
    if hasattr(value, 'pk'): return value.pk
    if isinstance(value, dict): return {str(k):json_value(v) for k,v in value.items()}
    if isinstance(value, (list,tuple,set)): return [json_value(v) for v in value]
    return value

@dataclass
class Context:
    user: object
    business: Business
    membership: object = None
    lines: set = field(default_factory=set)
    approval_source: object = None
    def __post_init__(self):
        if not self.membership:
            self.membership = Membership.objects.filter(user=self.user,business=self.business,active=True).first()
        if not self.membership or self.membership.business_id != self.business.pk or self.membership.user_id!=self.user.pk or not self.membership.active:
            raise PermissionDenied('You are not assigned to this business.')
    def has(self, permission):
        grants = self.membership.permissions
        return '*' in grants or permission in grants or permission.split('.')[0]+'.*' in grants
    def require(self, permission):
        if not self.has(permission): raise PermissionDenied('Permission required: '+permission)
    def location_allowed(self, location_id):
        return self.membership.all_locations or location_id in self.membership.location_ids
    def line_allowed(self, line):
        return line in self.membership.product_lines

def get_obj(ctx, Model, identifier):
    if isinstance(identifier,(bool,float)): raise ValidationError(f'Invalid {Model.__name__} identifier.')
    try: obj = Model.objects.get(pk=int(identifier),business=ctx.business)
    except (ValueError,TypeError,Model.DoesNotExist): raise ValidationError(f'Invalid {Model.__name__} reference for this business.')
    location_id = getattr(obj,'location_id',None)
    if isinstance(obj,Location): location_id=obj.pk
    if isinstance(obj,Warehouse): location_id=obj.location_id
    if isinstance(obj,Position) and obj.department_id: location_id=obj.department.location_id
    if hasattr(obj,'warehouse_id') and obj.warehouse_id:
        location_id=obj.warehouse.location_id
    if location_id and not ctx.location_allowed(location_id):
        incoming=False
        if isinstance(obj,Document) and obj.kind=='transfer_dispatch':
            incoming=Warehouse.objects.filter(pk=obj.result.get('destination'),business=ctx.business,location_id__in=ctx.membership.location_ids).exists()
        if not incoming: raise PermissionDenied('Location is outside your assignment.')
    if isinstance(obj,Product):
        if not ctx.line_allowed(obj.line): raise PermissionDenied('Product line is outside your assignment.')
        ctx.lines.add(obj.line)
    if isinstance(obj,Document):
        if not set(obj.product_lines).issubset(set(ctx.membership.product_lines)) and not ctx.has('documents.all_lines'):
            raise PermissionDenied('This document includes a restricted product line.')
    # A currency wallet is a shared physical cash/bank pool. Partial product-line
    # users cannot infer or spend balances contributed by restricted lines.
    from .models import ForeignWallet
    if isinstance(obj,ForeignWallet) and not ctx.has('documents.all_lines'):
        if obj.movements.exclude(document__product_lines__contained_by=ctx.membership.product_lines).exists():
            raise PermissionDenied('This currency wallet includes restricted product-line activity.')
    return obj

def get_warehouse(ctx, identifier): return get_obj(ctx,Warehouse,identifier)
def get_product(ctx, identifier):
    product=get_obj(ctx,Product,identifier)
    if product.kind=='raw' and not (ctx.has('inventory.raw') or ctx.has('consumption.view')):
        raise PermissionDenied('Raw-material operations require a separate inventory/consumption permission.')
    return product

def account(ctx, code):
    if isinstance(code,Account):
        if code.business_id != ctx.business.pk: raise ValidationError('Cross-business account.')
        return code
    try: return Account.objects.get(business=ctx.business,code=str(code))
    except Account.DoesNotExist: raise ValidationError('Unconfigured account: '+str(code))

def pool_for(ctx, product, warehouse, profile=''):
    product=get_product(ctx,product.pk if hasattr(product,'pk') else product)
    warehouse=get_warehouse(ctx,warehouse.pk if hasattr(warehouse,'pk') else warehouse)
    pool,_=StockPool.objects.get_or_create(business=ctx.business,product=product,warehouse=warehouse,profile=profile)
    return StockPool.objects.select_for_update().get(pk=pool.pk)

def _stock_date(pool, doc):
    if pool.last_date and doc.date < pool.last_date:
        raise ValidationError('Backdated stock valuation before a later pool event is unsupported.')

def stock_in(ctx, doc, product, warehouse, quantity, value, profile=''):
    quantity=D(quantity); value=D(value)
    if quantity <= 0 or value < 0: raise ValidationError('Receipt quantity must be positive and value nonnegative.')
    if quantity != quantity.quantize(QTY): raise ValidationError('Quantity exceeds six decimal places.')
    pool=pool_for(ctx,product,warehouse,profile); _stock_date(pool,doc)
    if pool.product.unit=='each' and quantity!=quantity.to_integral_value(): raise ValidationError('Counted items require whole units.')
    value=money(value)
    pool.quantity+=quantity; pool.value+=value; pool.last_date=doc.date
    pool.save(update_fields=['quantity','value','last_date'])
    StockMovement.objects.create(document=doc,pool=pool,quantity=quantity,value=value)
    return pool

def stock_out(ctx, doc, product, warehouse, quantity, profile=''):
    quantity=D(quantity)
    if quantity <= 0 or quantity != quantity.quantize(QTY): raise ValidationError('Issue quantity must be positive with at most six decimal places.')
    pool=pool_for(ctx,product,warehouse,profile); _stock_date(pool,doc)
    if pool.product.unit=='each' and quantity!=quantity.to_integral_value(): raise ValidationError('Counted items require whole units.')
    if quantity>pool.quantity: raise ValidationError('Insufficient stock in the selected warehouse/profile.')
    from .finance import release_inventory_allowance, _pool_allowance
    if doc.kind=='sale':
        release_inventory_allowance(ctx,doc,pool,quantity,pool.quantity,expense_account='COGS')
    elif _pool_allowance(ctx,pool)>0:
        raise ValidationError('This stock has an active valuation allowance. Reverse/review the write-down before transformation or transfer; only sale with proportional allowance release is currently supported.')
    cost=pool.value if quantity==pool.quantity else money(pool.value*quantity/pool.quantity)
    pool.quantity-=quantity; pool.value-=cost; pool.last_date=doc.date
    pool.save(update_fields=['quantity','value','last_date'])
    StockMovement.objects.create(document=doc,pool=pool,quantity=-quantity,value=-cost)
    return cost

def journal(ctx, doc, lines):
    pending=[];original_lines=[]
    for line in lines:
        debit=money(line.get('debit',0)); credit=money(line.get('credit',0))
        if debit<0 or credit<0 or (debit and credit): raise ValidationError('Journal lines need one nonnegative side.')
        if not debit and not credit: continue
        fields={}
        for key,Model in [('location',Location),('warehouse',Warehouse)]:
            supplied=line.get(key)
            if supplied is not None: fields[key]=get_obj(ctx,Model,getattr(supplied,'pk',supplied))
        from .models import Party, Employee
        for key,Model in [('party',Party),('employee',Employee)]:
            supplied=line.get(key)
            if supplied is not None: fields[key]=get_obj(ctx,Model,getattr(supplied,'pk',supplied))
        division=line.get('line','shared')
        if division!='shared' and not ctx.line_allowed(division): raise PermissionDenied('Restricted journal product line.')
        if division!='shared': ctx.lines.add(division)
        pending.append(Entry(document=doc,account=account(ctx,line['account']),debit=debit,credit=credit,line=division,**fields));original_lines.append(line)
    if sum((e.debit-e.credit for e in pending),ZERO)!=0:
        raise ValidationError('Journal is not balanced at currency precision.')
    Entry.objects.bulk_create(pending)
    from .money_instruments import bind_entries as bind_money
    bind_money(ctx,doc,pending,original_lines)
    from .cashier_shifts import bind_entries
    bind_entries(ctx,doc,pending)
    return pending

def outstanding(invoice):
    from .models import ForeignExposure
    exposure=ForeignExposure.objects.filter(invoice=invoice).first()
    if exposure:
        from .foreign import exposure_balance
        return exposure_balance(exposure)[1]
    settled=Allocation.objects.filter(invoice=invoice).aggregate(total=Sum('amount'))['total'] or ZERO
    return money(invoice.amount-settled)

def balance(ctx, code, employee=None, party=None, location=None, through=None):
    query=Entry.objects.filter(document__business=ctx.business,document__state='posted',account=account(ctx,code))
    for key,val in [('employee',employee),('party',party),('location',location)]:
        if val is not None: query=query.filter(**{key:getattr(val,'pk',val)})
    if through: query=query.filter(document__date__lte=through)
    sums=query.aggregate(dr=Sum('debit'),cr=Sum('credit'))
    return (sums['dr'] or ZERO)-(sums['cr'] or ZERO)

@transaction.atomic
def create_draft(ctx,kind,payload,key=None):
    """Shared non-posting draft boundary for staff forms and reviewed capture."""
    import uuid
    ctx.require('drafts.create')
    Business.objects.select_for_update().get(pk=ctx.business.pk)
    if not isinstance(kind,str) or kind not in registry():raise ValidationError('Unsupported document type.')
    ctx.require(registry()[kind][0])
    if not isinstance(payload,dict):raise ValidationError('Draft data must be an object.')
    if key and (not isinstance(key,str) or len(key)>100 or not key.strip()):raise ValidationError('Use an idempotency key of at most100 characters.')
    digest=hashlib.sha256(json.dumps(json_value({'user':ctx.user.pk,'kind':kind,'data':payload}),sort_keys=True,separators=(',',':')).encode()).hexdigest()
    if key:
        previous=Document.objects.filter(business=ctx.business,idempotency_key=key).first()
        if previous:
            if previous.created_by_id!=ctx.user.pk or previous.request_hash!=digest:raise ValidationError('This draft key was already used with different content.')
            previous._draft_replayed=True
            return previous
    # Capture metadata is validated by its domain before linking the draft and
    # again before posting. Ordinary drafts still need all ordinary permissions.
    ctx.lines.clear()
    doc=Document(business=ctx.business,kind=kind,number='DRAFT-'+uuid.uuid4().hex[:16],date=payload.get('date') or timezone.localdate(),data=payload,idempotency_key=key or 'draft-'+uuid.uuid4().hex,request_hash=digest,created_by=ctx.user)
    if payload.get('location'):doc.location=get_obj(ctx,Location,payload['location'])
    if payload.get('warehouse'):doc.warehouse=get_obj(ctx,Warehouse,payload['warehouse']);doc.location=doc.warehouse.location
    for group in ('lines','inputs','outputs'):
        items=payload.get(group,[])
        if not isinstance(items,list) or len(items)>1000 or not all(isinstance(row,dict) for row in items):raise ValidationError('Draft lines must be bounded lists of objects.')
        for item in items:
            if item.get('product'):get_obj(ctx,Product,item['product'])
    for field in ('party','supplier','customer'):
        if payload.get(field):get_obj(ctx,Party,payload[field])
    doc.product_lines=sorted(ctx.lines);doc.save()
    return doc


def registry():
    from .order_readiness import OPERATIONS as order_readiness
    from .operations import OPERATIONS as manufacturing
    from .finance import OPERATIONS as finance
    from .administration import OPERATIONS as administration
    from .corrections import OPERATIONS as corrections
    from .growth import OPERATIONS as growth
    from .foreign import OPERATIONS as foreign
    from .growth_hooks import enrich_registry
    from .dispatch import OPERATIONS as dispatch, enrich_registry as dispatch_guards
    from .jobs import OPERATIONS as jobs
    from .commissions import OPERATIONS as commissions
    from .late_cost import OPERATIONS as late_cost,enrich_registry as late_guards
    from .excellence import OPERATIONS as excellence,guard_close
    from .customer_requests import OPERATIONS as customer_requests
    from .customer_notices import OPERATIONS as customer_notices
    from .calendar_periods import registry as calendar_registry
    from .advanced_planning import OPERATIONS as advanced_planning
    from .procurement import OPERATIONS as procurement,enrich_registry as procurement_guards
    from .cashier_shifts import OPERATIONS as cashier,enrich_registry as cashier_guards
    from .statement_imports import OPERATIONS as statements
    from .sourcing import OPERATIONS as sourcing
    from .crm import OPERATIONS as crm,enrich_registry as crm_guards
    from .capture import OPERATIONS as capture,enrich_registry as capture_guards
    from .money_instruments import OPERATIONS as money_operations,enrich_registry as money_guards
    operations={**manufacturing,**finance,**administration,**corrections,**growth,**foreign,**dispatch,**jobs,**commissions,**late_cost,**excellence,**customer_requests,**customer_notices,**calendar_registry(),**advanced_planning,**procurement,**cashier,**statements,**sourcing,**crm,**capture,**money_operations}
    operations.update(order_readiness)
    permission,handler=operations['period_close'];operations['period_close']=(permission,guard_close(handler))
    return money_guards(capture_guards(crm_guards(cashier_guards(procurement_guards(dispatch_guards(late_guards(enrich_registry(operations))))))))

@transaction.atomic
def execute(ctx, action, payload, key):
    if not isinstance(payload,dict): raise ValidationError('Expected an operation object.')
    for name in ('lines','inputs','outputs','allocations','deductions','weights','entry_ids','conversion_sources'):
        if name in payload:
            value=payload[name]
            if not isinstance(value,list) or len(value)>1000: raise ValidationError(f'{name} must be a list with no more than 1,000 entries.')
            if name not in ('entry_ids','conversion_sources') and not all(isinstance(row,dict) for row in value): raise ValidationError(f'{name} entries must be objects.')
            if name in ('lines','outputs'):
                for row in value:
                    if 'blocks' in row and (not isinstance(row['blocks'],list) or len(row['blocks'])>1000 or not all(isinstance(block,dict) for block in row['blocks'])): raise ValidationError('blocks must be a list of measured block objects (maximum 1,000).')
    if not key or len(str(key))>100: raise ValidationError('A unique Idempotency-Key (max 100 characters) is required.')
    operations=registry()
    if action not in operations: raise ValidationError('Unknown or unsupported operation: '+action)
    permission,handler=operations[action]
    ctx.require(permission)
    if action=='opening_employee_advance' and not (ctx.has('payroll.view') or ctx.has('payroll.post')):
        raise PermissionDenied('Employee opening advances require payroll access as well as opening-balance authority.')
    business=Business.objects.select_for_update().get(pk=ctx.business.pk)
    ctx.lines.clear()
    ctx.business=business
    if action.startswith('production') and business.manufacturing_mode=='trading': raise ValidationError('Manufacturing is disabled for this trading business.')
    if action=='production_bom' and business.manufacturing_mode!='bom': raise ValidationError('BOM-assisted production is disabled for this business.')
    ctx.membership=Membership.objects.get(pk=ctx.membership.pk)
    if not ctx.membership.active: raise PermissionDenied('Membership is inactive.')
    ctx.require(permission)
    digest=hashlib.sha256(json.dumps(json_value({'action':action,'payload':payload}),sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
    existing=Document.objects.filter(business=business,idempotency_key=str(key)).first()
    if existing:
        get_obj(ctx,Document,existing.pk)
        if existing.request_hash!=digest: raise ValidationError('Idempotency key was used with another payload.')
        return existing
    try: effective=date.fromisoformat(str(payload.get('date') or timezone.localdate().isoformat()))
    except ValueError: raise ValidationError('Use an ISO YYYY-MM-DD date.')
    if business.closed_through and effective<=business.closed_through and action!='period_reopen':
        raise ValidationError('The accounting period is closed.')
    if payload.get('currency',business.currency)!=business.currency: raise ValidationError('The general ledger posts in the business functional currency. Use the foreign monetary workflows for USD/PKR terms and settlements.')
    seq,_=Sequence.objects.get_or_create(business=business,kind=action)
    seq.value+=1; seq.save(update_fields=['value'])
    # Keep complete action names: truncated prefixes collide for consume/complete
    # and write-down/reversal while their independent sequences both start at 1.
    action_code=action.upper()
    prefix=business.slug.upper()[:max(1,60-len(action_code)-1-1-len(f'{seq.value:06d}'))]
    number=f'{prefix}-{action_code}-{seq.value:06d}'
    doc=Document.objects.create(business=business,kind=action,number=number,date=effective,data=json_value(payload),idempotency_key=str(key),request_hash=digest,created_by=ctx.user)
    if payload.get('location'): doc.location=get_obj(ctx,Location,payload['location'])
    if payload.get('warehouse'):
        doc.warehouse=get_warehouse(ctx,payload['warehouse']); doc.location=doc.warehouse.location
    result=handler(ctx,payload,doc) or {}
    if doc.reference_id and doc.date<doc.reference.date:
        raise ValidationError('A linked event cannot precede its source document date.')
    moved=StockMovement.objects.filter(document=doc)
    incoming=moved.filter(value__gt=0).aggregate(v=Sum('value'))['v'] or ZERO
    outgoing=-(moved.filter(value__lt=0).aggregate(v=Sum('value'))['v'] or ZERO)
    approval_value=max(money(doc.amount),money(incoming),money(outgoing),*(money(result.get(field,0)) if isinstance(result.get(field,0),(str,int,Decimal)) else ZERO for field in ['total','gross','amount','total_cost','carrying_released']))
    if approval_value>ctx.membership.approval_limit and not ctx.has('approvals.override'):
        approved=ctx.has(permission.split('.')[0]+'.approve')
        if not approved or (business.settings.get('separate_approver',True) and not ctx.approval_source):
            raise PermissionDenied('This amount exceeds your posting limit. Submit it for approval by a different authorized colleague.')
    entries=Entry.objects.filter(document=doc)
    totals=entries.aggregate(dr=Sum('debit'),cr=Sum('credit'))
    if (totals['dr'] or ZERO)!=(totals['cr'] or ZERO): raise ValidationError('Posting would leave an unbalanced journal.')
    movements=StockMovement.objects.filter(document=doc).aggregate(value=Sum('value'))['value'] or ZERO
    controls=entries.filter(account__code__in=['RAW','FG','TRIM','TRANSIT']).aggregate(dr=Sum('debit'),cr=Sum('credit'))
    if money(movements)!=money((controls['dr'] or ZERO)-(controls['cr'] or ZERO)):
        raise ValidationError('Inventory movement value does not reconcile to its control-account posting.')
    if doc.amount<0: raise ValidationError('Document amount cannot be negative.')
    doc.result=json_value(result); doc.product_lines=sorted(ctx.lines); doc.state='posted'; doc.posted_at=timezone.now(); doc.full_clean(); doc.save()
    AuditEvent.objects.create(business=business,user=ctx.user,action='post:'+action,target=str(doc.pk),details={'number':number})
    return doc
