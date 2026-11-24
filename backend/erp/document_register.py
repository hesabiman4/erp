"""Permission-checked whole-result transaction register; never a posting path.

Authorization precedes count, balance filters, sorting and totals. This deliberately
reuses the detail guard, including specialized document restrictions. It scans
matching candidates; large-register performance needs representative measurement.
"""
from datetime import date
from decimal import Decimal
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q, Sum
from django.utils import timezone
from .api import Boundary, can, document_scope, doc_permission, document_data, response
from .core import get_obj, outstanding, registry
from .models import Allocation, ForeignExposure, Location

COST_KINDS = {'stock_opening','stock_adjust','stock_count_adjust','production','production_start','production_consume','production_complete','production_bom','trim','cut','material_issue','material_return','transfer_dispatch','transfer_receive','transfer_resolve','production_material_return','inventory_write_down','inventory_write_down_reverse'}
STATES = {'draft','posted','requested','approved','rejected','converted','cancelled'}
BALANCE_KINDS = {'sale','purchase_bill','opening_receivable','opening_payable'}

def public_amount(ctx, doc):
    return None if doc.kind in COST_KINDS and not ctx.has('cost.view') else doc.amount

def iso_date(value):
    try:
        parsed = date.fromisoformat(value)
        if parsed.isoformat() != value: raise ValueError()
        return parsed
    except (ValueError,TypeError): raise ValidationError('Select a valid register date.')

def register(ctx, params, location_header=None):
    kind = params.get('kind','')
    if kind not in registry(): raise ValidationError('Select a valid document type.')
    permission = registry()[kind][0]; prefix = permission.split('.')[0]
    if not can(ctx, permission, prefix+'.view', prefix+'.post', 'documents.view'):
        raise PermissionDenied('Document access is restricted.')
    qs = document_scope(ctx).filter(kind=kind).order_by('pk')
    location = params.get('location') or location_header
    if location: qs = qs.filter(location=get_obj(ctx,Location,location))
    if not ctx.has('documents.all_lines'): qs = qs.filter(product_lines__contained_by=ctx.membership.product_lines)
    if not can(ctx,'payroll.view','payroll.post'): qs = qs.filter(employee__isnull=True)
    query = params.get('q','').strip()
    if len(query)>100: raise ValidationError('Register search is limited to 100 characters.')
    if query: qs = qs.filter(Q(number__icontains=query)|Q(party__name__icontains=query)|Q(party__phone__icontains=query)|Q(data__customer_name__icontains=query)|Q(data__phone__icontains=query))
    state = params.get('state','')
    if state:
        if state not in STATES: raise ValidationError('Select a valid document state.')
        qs = qs.filter(state=state)
    start, end = params.get('from',''), params.get('to','')
    if start: qs = qs.filter(date__gte=iso_date(start))
    if end: qs = qs.filter(date__lte=iso_date(end))
    if start and end and start>end: raise ValidationError('Start date must not be after end date.')
    try: limit=int(params.get('limit','100')); offset=int(params.get('offset','0'))
    except (ValueError,TypeError): raise ValidationError('Pagination requires integer limit/offset.')
    if not 1<=limit<=200 or offset<0: raise ValidationError('Select a valid register page.')
    sort = params.get('sort','-id'); descending=sort.startswith('-'); key=sort[1:] if descending else sort
    if key not in {'id','number','date','party','amount','balance','state'}: raise ValidationError('Select a valid register sort.')
    payment = params.get('payment','')
    if payment not in {'','paid','unpaid','partial','overdue'}: raise ValidationError('Select a valid payment filter.')
    # Never count hidden documents or use their values to sort the visible list.
    permitted=[]
    for doc in qs.iterator(chunk_size=200):
        try: doc_permission(ctx,doc)
        except PermissionDenied: continue
        permitted.append(doc)
    ids=[d.pk for d in permitted]
    allocations=dict(Allocation.objects.filter(invoice_id__in=ids).values('invoice_id').annotate(total=Sum('amount')).values_list('invoice_id','total'))
    foreign=set(ForeignExposure.objects.filter(invoice_id__in=ids).values_list('invoice_id',flat=True))
    today=timezone.localdate(); values=[]
    for doc in permitted:
        has_balance=doc.kind in BALANCE_KINDS or doc.kind in {'expense_post','asset_acquire'} and doc.party_id
        due=outstanding(doc) if doc.pk in foreign else doc.amount-allocations.get(doc.pk,Decimal('0')) if has_balance else None
        if payment:
            if not has_balance or doc.state!='posted': continue
            if payment=='paid' and due!=0: continue
            if payment=='unpaid' and due<=0: continue
            if payment=='partial' and not 0<due<doc.amount: continue
            if payment=='overdue' and not (due>0 and iso_date(doc.data.get('due_date') or doc.date.isoformat())<today): continue
        values.append((doc,public_amount(ctx,doc),due))
    def sort_value(row):
        doc, amount, due=row
        return {'id':doc.pk,'number':doc.number,'date':doc.date,'party':(doc.party.name if doc.party_id else doc.data.get('customer_name','')).casefold(),'amount':amount,'balance':due,'state':doc.state}[key]
    # Stable PK tie break; null/restricted amounts stay last in both directions.
    known=[r for r in values if sort_value(r) is not None]; unknown=[r for r in values if sort_value(r) is None]
    known.sort(key=lambda r:(sort_value(r),r[0].pk),reverse=descending); ordered=known+unknown
    amount_total=None if any(r[1] is None for r in ordered) else sum((r[1] for r in ordered),Decimal('0'))
    balance_total=sum((r[2] for r in ordered if r[2] is not None),Decimal('0'))
    count=len(ordered)
    return {'results':[document_data(ctx,r[0],include_flow=False) for r in ordered[offset:offset+limit]],
            'count':count,'offset':offset,'limit':limit,'next_offset':offset+limit if offset+limit<count else None,
            'totals':{'amount':amount_total,'balance':balance_total},'scope':'all_authorized_matching_documents'}

class DocumentRegisterAPI(Boundary):
    def get(self,request):
        return response(register(self.ctx(request),request.query_params,request.headers.get('X-Location-ID')))
