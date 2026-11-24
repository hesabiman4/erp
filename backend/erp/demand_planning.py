"""Explainable review-only demand. Never infer recipes or reserve/post inventory."""
from datetime import timedelta
from decimal import Decimal,ROUND_CEILING
from django.core.exceptions import PermissionDenied,ValidationError
from django.db.models import Sum
from django.utils import timezone
from .api import doc_permission
from .core import D,get_obj,get_product,get_warehouse,profile_for
from .models import Document,Block,StockPool,RecallBlockHold,RecallProductHold,WorkCenter
from .order_readiness import passed

ZERO=Decimal('0')


def integer(value,low,high):
    number=D(value)
    if number!=number.to_integral_value() or not low<=number<=high:raise ValidationError('Review planning days and rounding assumptions.')
    return int(number)


def quantity(value,positive=False):
    number=D(value)
    if number<0 or number>Decimal('1000000000000') or (positive and number==0) or number!=number.quantize(Decimal('.000001')):raise ValidationError('Use nonnegative planning quantities with at most six decimals.')
    return number


def suggestion(ctx,p):
    ctx.require('production.plan');ctx.require('sales.view');ctx.require('inventory.view')
    if ctx.business.manufacturing_mode=='trading':raise ValidationError('Production planning is disabled for this trading business.')
    warehouse=get_warehouse(ctx,p.get('warehouse'));product=get_product(ctx,p.get('product'))
    if warehouse.kind=='transit' or product.kind!='finished' or not product.active:raise ValidationError('Choose an active finished product and physical warehouse for demand review.')
    if p.get('location') and str(warehouse.location_id)!=str(p['location']):raise PermissionDenied('Warehouse is outside the selected location.')
    profile=''
    if product.unit=='cm':
        length=quantity(p.get('length_mm'),True);width=quantity(p.get('width_mm'),True)
        if length!=length.quantize(Decimal('.001')) or width!=width.quantize(Decimal('.001')):raise ValidationError('Use footprint dimensions with at most three decimals.')
        profile=profile_for(length,width)
    from .growth import day
    today=timezone.localdate();end=day(p.get('to') or today);days=integer(p.get('lookback_days',30),7,366);start=end-timedelta(days=days-1)
    if end>today:raise ValidationError('Demand history cannot end in the future.')
    lead=integer(p.get('lead_days',7),0,365);cover=integer(p.get('cover_days',7),1,365);horizon=lead+cover
    if horizon>366:raise ValidationError('Review planning days and rounding assumptions.')
    safety=quantity(p.get('safety_quantity',0));step=quantity(p.get('rounding_quantity',1),True)
    if product.unit=='each' and (safety!=safety.to_integral_value() or step!=step.to_integral_value()):raise ValidationError('Counted finished products require whole planning quantities.')
    sold=ZERO;returned=ZERO;events=0
    def guard(doc):
        try:doc_permission(ctx,doc)
        except PermissionDenied:raise PermissionDenied('Demand review includes restricted related records. Complete scope is required for a reliable suggestion.')
    def matches(line):return str(line.get('product'))==str(product.pk) and (product.unit!='cm' or line.get('profile')==profile)
    history=Document.objects.filter(business=ctx.business,warehouse=warehouse,state='posted',kind__in=['sale','sales_return'],date__range=[start,end]).order_by('date','pk')
    for doc in history:
        # Guard every candidate before inspecting quantities or related references.
        guard(doc)
        if doc.kind=='sale':
            amount=sum((D(line['quantity']) for line in doc.result.get('lines',[]) if matches(line)),ZERO);sold+=amount;events+=amount>0
        else:
            original=doc.reference;guard(original)
            for line in doc.result.get('lines',[]):
                source=original.result['lines'][int(line['index'])]
                if matches(source):returned+=D(line['quantity'])
    backlog=ZERO;orders=0;open_lines=set()
    from .sales_flow import commercial_flow
    from .operations import _commercial_cancelled
    for doc in Document.objects.filter(business=ctx.business,warehouse=warehouse,state='posted',kind='sales_order'):
        guard(doc)
        if _commercial_cancelled(ctx,doc):continue
        flow=commercial_flow(ctx,doc)
        if flow.get('restricted_progress'):raise PermissionDenied('Demand review includes restricted related records. Complete scope is required for a reliable suggestion.')
        relevant=[line for line in flow['lines'] if matches(line) and D(line['remaining_quantity'])>0]
        open_lines.update((doc.pk,line['index']) for line in relevant)
        amount=sum((D(line['remaining_quantity']) for line in relevant),ZERO)
        backlog+=amount;orders+=amount>0
    held_product=RecallProductHold.objects.filter(business=ctx.business,product=product,released_by__isnull=True).exists()
    ready=ZERO;reserved=ZERO;reserved_budget={}
    if not held_product:
        if product.unit=='cm':
            holds=set(RecallBlockHold.objects.filter(business=ctx.business,released_by__isnull=True).values_list('block_id',flat=True))
            for block in Block.objects.filter(business=ctx.business,warehouse=warehouse,product=product,profile=profile,status__in=['ready','reserved']):
                if block.pk in holds or not passed(ctx,block):continue
                ready+=block.remaining_height_mm/10;reserved+=block.reserved_height_mm/10;reserved_budget[block.pk]=block.reserved_height_mm/10
        else:ready=StockPool.objects.filter(business=ctx.business,warehouse=warehouse,product=product,profile=profile).aggregate(q=Sum('quantity'))['q'] or ZERO
    # Credit reserved material only when its live provenance covers an included
    # open-order line. Generic reservations must never become free supply.
    from .cut_models import OrderCutDemand,OrderCutSheet
    assigned=ZERO
    for demand in OrderCutDemand.objects.filter(business=ctx.business,state='planned',plan__state='planned',plan__warehouse=warehouse,plan__product=product,plan__profile=profile).select_related('plan'):
        if (demand.order_id,demand.order_index) not in open_lines:continue
        guard(demand.plan.source)
        for allocation in demand.plan.allocations:
            if allocation.get('order_cut_demand')!=demand.pk:continue
            ident=allocation['block'];budget=reserved_budget.get(ident,ZERO)
            billable=D(allocation['thickness_mm'])*D(allocation['sheet_count'])/10
            loss=D(allocation.get('cutting_loss_mm',0))*D(allocation['sheet_count'])/10
            assigned+=min(billable,max(ZERO,budget-loss));reserved_budget[ident]=max(ZERO,budget-billable-loss)
    for sheet in OrderCutSheet.objects.filter(business=ctx.business,fulfilled_document__isnull=True,released_by__isnull=True,block_id__in=reserved_budget).select_related('demand','demand__plan__source'):
        if (sheet.demand.order_id,sheet.demand.order_index) not in open_lines:continue
        guard(sheet.demand.plan.source)
        amount=min(sheet.quantity_cm,reserved_budget[sheet.block_id]);assigned+=amount;reserved_budget[sheet.block_id]-=amount
    physical_ready=ready;unreserved=ready-reserved;ready=unreserved+assigned
    net=sold-returned;daily=max(ZERO,net)/days;projected=daily*horizon
    target=max(projected,backlog)+safety
    short=max(ZERO,target-ready);suggested=(short/step).to_integral_value(rounding=ROUND_CEILING)*step
    capacity=None;center_id=p.get('work_center')
    if center_id:
        center=get_obj(ctx,WorkCenter,center_id)
        if not center.active or center.location_id!=warehouse.location_id:raise ValidationError('Choose an active work center at this warehouse location.')
        minutes=quantity(p.get('minutes_per_unit'),True)
        weekdays=p.get('working_weekdays','0,1,2,3,4,5,6')
        try:weekdays=sorted(set(int(x) for x in str(weekdays).split(',')))
        except (ValueError,TypeError):raise ValidationError('Select valid planning weekdays.')
        if not weekdays or any(x<0 or x>6 for x in weekdays):raise ValidationError('Select valid planning weekdays.')
        from .advanced_planning import capacity_usage
        used=capacity_usage(ctx.business,center.pk);free=0;slots=[]
        for offset in range(horizon):
            date=today+timedelta(days=offset)
            available=max(0,center.daily_minutes-used.get(date,0)) if date.weekday() in weekdays else 0
            free+=available;slots.append({'date':date,'available_minutes':available})
        needed=int((suggested*minutes).to_integral_value(rounding=ROUND_CEILING))
        capacity={'work_center':center.pk,'name':center.name,'minutes_per_unit':minutes,'needed_minutes':needed,'free_minutes':free,'shortage_minutes':max(0,needed-free),'working_weekdays':weekdays,'slots':slots,'reserved':False}
    return {'product':product.pk,'product_name':product.name,'warehouse':warehouse.pk,'warehouse_name':warehouse.name,'unit':product.unit,'profile':profile,'history_from':start,'history_to':end,'lookback_days':days,'lead_days':lead,'cover_days':cover,'horizon_days':horizon,'safety_quantity':safety,'rounding_quantity':step,'sold_quantity':sold,'returned_quantity':returned,'net_quantity':net,'sales_events':events,'daily_rate':daily,'projected_quantity':projected,'open_order_quantity':backlog,'open_orders':orders,'ready_quantity':ready,'reserved_quantity':reserved,'unreserved_quantity':unreserved,'physical_ready_quantity':physical_ready,'assigned_reserved_quantity':assigned,'target_quantity':target,'suggested_quantity':suggested,'capacity':capacity,'stock_as_of':timezone.now(),'snapshot_only':True,'financial_posting':False,'formula_inferred':False,'basis':'max(nonnegative net daily sales × (lead days + cover days), all current open-order quantity) + safety − current ready stock; round a positive shortage upward. Backlog replaces forecast when larger, rather than adding the same demand twice. Ready supply includes unreserved stock and only identified live reservations covering included backlog. Generic reservations are excluded. No inbound/WIP credit, seasonality, material formula, cutting feasibility or delivery guarantee. Capacity minutes per unit and working days are operator assumptions.'}
