"""Paginated pool register with grouped physical quantities and exact value totals."""
from decimal import Decimal
from django.core.exceptions import PermissionDenied,ValidationError
from django.db.models import Q,Sum,Case,When,Value,F,DecimalField,ExpressionWrapper
from .api import Boundary,can,scope_queryset,response
from .core import get_obj
from .models import StockPool,Warehouse,Location

def register(ctx,params,location_header=None):
    if not can(ctx,'inventory.view','sales.post','production.post','transfers.post','purchases.post'):
        raise PermissionDenied('Inventory access is restricted.')
    qs=StockPool.objects.filter(business=ctx.business,warehouse__in=scope_queryset(ctx,Warehouse),product__line__in=ctx.membership.product_lines).select_related('warehouse','product')
    if not can(ctx,'inventory.raw','consumption.view'):qs=qs.exclude(product__kind='raw')
    location=params.get('location') or location_header
    if location:qs=qs.filter(warehouse__location=get_obj(ctx,Location,location))
    if params.get('warehouse'):qs=qs.filter(warehouse=get_obj(ctx,Warehouse,params['warehouse']))
    query=params.get('q','').strip()
    if len(query)>100:raise ValidationError('Register search is limited to 100 characters.')
    if query:qs=qs.filter(Q(product__name__icontains=query)|Q(product__code__icontains=query)|Q(warehouse__name__icontains=query)|Q(profile__icontains=query))
    if params.get('availability'):
        if params['availability'] not in {'in_stock','empty'}:raise ValidationError('Select a valid stock filter.')
        qs=qs.filter(quantity__gt=0) if params['availability']=='in_stock' else qs.filter(quantity=0)
    try:limit=int(params.get('limit','100'));offset=int(params.get('offset','0'))
    except (ValueError,TypeError):raise ValidationError('Pagination requires integer limit/offset.')
    if not 1<=limit<=200 or offset<0:raise ValidationError('Select a valid register page.')
    sort=params.get('sort','id');reverse=sort.startswith('-');key=sort[1:] if reverse else sort
    mapping={'id':'id','product':'product__name','warehouse':'warehouse__name','profile':'profile','quantity':'quantity','value':'value','average_cost':'average_cost'}
    if key not in mapping:raise ValidationError('Select a valid register sort.')
    costs=ctx.has('cost.view')
    if key in {'value','average_cost'} and not costs:raise PermissionDenied('Inventory costs are restricted.')
    qs=qs.annotate(average_cost=Case(When(quantity=0,then=Value(Decimal('0'))),default=ExpressionWrapper(F('value')/F('quantity'),output_field=DecimalField()),output_field=DecimalField()))
    count=qs.count();total=qs.aggregate(value=Sum('value'))['value'] if costs else None
    # Never add cm of different products/footprints or mix kg, each and cm.
    groups=list(qs.values('product_id','product__name','product__unit','profile').annotate(quantity=Sum('quantity')).order_by('product_id','profile'))
    rows=[]
    for pool in qs.order_by(('-' if reverse else '')+mapping[key],'id')[offset:offset+limit]:
        row={'id':pool.pk,'product':pool.product_id,'product_name':pool.product.name,'unit':pool.product.unit,'warehouse':pool.warehouse_id,'warehouse_name':pool.warehouse.name,'profile':pool.profile,'quantity':pool.quantity}
        if costs:row.update(value=pool.value,average_cost=pool.average_cost)
        rows.append(row)
    return {'results':rows,'count':count,'offset':offset,'limit':limit,'next_offset':offset+limit if offset+limit<count else None,'totals':{'value':total or Decimal('0') if costs else None},'quantities':groups,'scope':'all_authorized_matching_pools'}

class StockRegisterAPI(Boundary):
    def get(self,request):return response(register(self.ctx(request),request.query_params,request.headers.get('X-Location-ID')))
