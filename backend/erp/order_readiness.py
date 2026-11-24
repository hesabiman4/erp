"""Read-only warehouse feasibility and reviewed delivery promises.

Feasibility is an unreserved-stock snapshot, not a reservation or guaranteed
delivery date. Physical block heights are consumed only in the local preview.
"""
from decimal import Decimal
from django.core.exceptions import PermissionDenied,ValidationError
from django.db.models import Sum
from .api import Boundary,doc_permission,response
from .core import D,get_obj,get_product,get_warehouse
from .models import Document,Block,StockPool,RecallBlockHold,RecallProductHold,QualityInspection,WorkOrder
from .cut_models import OrderCutDemand,OrderCutSheet

ZERO=Decimal('0')

def source(ctx,identifier):
    order=get_obj(ctx,Document,identifier);doc_permission(ctx,order)
    if order.kind!='sales_order' or order.state!='posted':raise ValidationError('Select a posted sales order for readiness.')
    return order

def passed(ctx,block):
    if not ctx.business.settings.get('require_inspection'):return True
    seen=set()
    while block:
        if block.pk in seen:return False
        seen.add(block.pk)
        inspection=QualityInspection.objects.filter(business=ctx.business,block=block).order_by('-pk').first()
        if inspection:return inspection.outcome=='passed'
        block=block.parent
    return False

def readiness(ctx,identifier,params):
    order=source(ctx,identifier)
    if not any(ctx.has(p) for p in ('inventory.view','sales.post')):raise PermissionDenied('Order readiness requires stock visibility.')
    warehouse=get_warehouse(ctx,order.warehouse_id)
    if warehouse.kind=='transit':raise ValidationError('Review order readiness in a physical warehouse, not transit.')
    from .sales_flow import commercial_flow
    flow=commercial_flow(ctx,order)
    if flow.get('restricted_progress'):raise PermissionDenied('Related order progress is outside your assignment.')
    from .operations import _commercial_cancelled
    closed=_commercial_cancelled(ctx,order) or not flow['can_continue']
    block_heights={};pool_left={};used_held=set();lines=[]
    holds=set(RecallBlockHold.objects.filter(business=ctx.business,released_by__isnull=True).values_list('block_id',flat=True))
    for original in flow['lines']:
        index=original['index'];product=get_product(ctx,original['product']);remaining=D(original['remaining_quantity']);profile=original.get('profile','')
        held_product=RecallProductHold.objects.filter(business=ctx.business,product=product,released_by__isnull=True).exists()
        row={'index':index,'product':product.pk,'product_name':product.name,'unit':product.unit,'profile':profile,'remaining':remaining,'status':'fulfilled' if remaining==0 else 'closed' if closed else 'checking','available':ZERO,'shortage':remaining,'allocations':[]}
        if remaining==0 or closed:lines.append(row);continue
        if not product.active:row['status']='inactive_product';lines.append(row);continue
        if held_product:row['status']='quality_hold';lines.append(row);continue
        if product.kind=='service':row.update(status='service_review',shortage=None);lines.append(row);continue
        if product.unit!='cm':
            key=(product.pk,profile)
            if key not in pool_left:pool_left[key]=StockPool.objects.filter(business=ctx.business,warehouse=warehouse,product=product,profile=profile).aggregate(q=Sum('quantity'))['q'] or ZERO
            allocated=min(remaining,pool_left[key]);pool_left[key]-=allocated
            row.update(available=allocated,shortage=remaining-allocated,status='ready_now' if allocated==remaining else 'shortage')
            lines.append(row);continue
        row['planned_cut_cm']=OrderCutDemand.objects.filter(business=ctx.business,order=order,order_index=index,state='planned').aggregate(q=Sum('quantity_cm'))['q'] or ZERO
        raw=params.get('thickness_'+str(index),'');loss=D(params.get('loss_'+str(index)) or '0')
        if loss<0 or loss!=loss.quantize(Decimal('.001')):raise ValidationError('Use a nonnegative cutting loss with at most three decimals.')
        if not raw or not profile:row['status']='needs_cut_details';lines.append(row);continue
        thickness=D(raw)
        if thickness<=0 or thickness!=thickness.quantize(Decimal('.001')):raise ValidationError('Use a positive sheet thickness with at most three decimals.')
        count=remaining*10/thickness
        if count!=count.to_integral_value() or count>1000:row['status']='needs_cut_details';lines.append(row);continue
        row.update(thickness_mm=thickness,sheet_count=int(count),cutting_loss_per_sheet_mm=loss)
        needed=int(count)
        # Identified sheets already cut for this order can be delivered once.
        own=OrderCutSheet.objects.filter(business=ctx.business,demand__order=order,demand__order_index=index,fulfilled_document__isnull=True,released_by__isnull=True).select_related('block')
        for sheet in own:
            block=sheet.block
            if not needed:break
            if block.pk in used_held or block.pk in holds or block.product_id!=product.pk or block.warehouse_id!=warehouse.pk or block.profile!=profile or block.status not in {'ready','reserved'} or block.remaining_height_mm!=thickness or not passed(ctx,block):continue
            used_held.add(block.pk);needed-=1;row['allocations'].append({'block':block.pk,'code':block.code,'sheets':1,'held_for_this_order':True})
        blocks=list(Block.objects.filter(business=ctx.business,warehouse=warehouse,product=product,profile=profile,status__in=['ready','reserved']).order_by('remaining_height_mm','pk'))
        for block in blocks:
            if block.pk not in block_heights:block_heights[block.pk]=max(ZERO,block.remaining_height_mm-block.reserved_height_mm) if block.pk not in holds and passed(ctx,block) else ZERO
        for _ in range(needed):
            fits=[b for b in blocks if block_heights[b.pk]>=thickness+loss]
            if not fits:break
            best=min(fits,key=lambda b:(block_heights[b.pk]-thickness-loss,b.pk));block_heights[best.pk]-=thickness+loss
            allocation=next((a for a in row['allocations'] if a['block']==best.pk),None)
            if allocation:allocation['sheets']+=1
            else:row['allocations'].append({'block':best.pk,'code':best.code,'sheets':1,'held_for_this_order':False})
        supplied=sum(a['sheets'] for a in row['allocations']);available=thickness*supplied/10
        row.update(available=available,shortage=remaining-available,status='ready_now' if available==remaining else 'shortage')
        lines.append(row)
    work=[]
    if any(ctx.has(p) for p in ('production.view','production.plan','production.post')):
        from .advanced_planning import latest_schedules
        schedules=latest_schedules(ctx.business)
        for item in WorkOrder.objects.filter(business=ctx.business,order=order).exclude(state='cancelled').select_related('product'):
            try:doc_permission(ctx,item.source);get_warehouse(ctx,item.warehouse_id);get_product(ctx,item.product_id)
            except PermissionDenied:continue
            schedule=schedules.get(item.pk)
            if schedule:doc_permission(ctx,schedule)
            dates=[s['date'] for s in schedule.result.get('slots',[])] if schedule else [item.scheduled_date.isoformat()]
            work.append({'id':item.pk,'number':item.number,'product_name':item.product.name,'state':item.state,'planned_quantity':item.planned_quantity,'unit':item.product.unit,'scheduled_through':max(dates) if dates else None})
    promises=[]
    for doc in Document.objects.filter(business=ctx.business,reference=order,kind='order_promise',state='posted').order_by('-pk')[:20]:
        doc_permission(ctx,doc);promises.append({'document':doc.pk,'number':doc.number,'date':doc.date,'promised_date':doc.result['promised_date'],'reason':doc.result['reason'],'basis':doc.result['basis']})
    return {'order':order.pk,'warehouse':warehouse.pk,'warehouse_name':warehouse.name,'closed':closed,'ready_now':bool(lines) and all(r['status'] in {'ready_now','fulfilled'} for r in lines),'lines':lines,'work':work,'promises':promises,'reserved':False,'financial_posting':False,'method':'Sequential best-fit snapshot of unreserved compatible physical pieces plus identified held sheets for this order; not an optimal allocator or delivery guarantee.'}

def promise(ctx,p,doc):
    order=source(ctx,p['order'])
    from .operations import _commercial_cancelled
    from .growth import day
    from .sales_flow import commercial_flow
    if _commercial_cancelled(ctx,order) or not commercial_flow(ctx,order)['can_continue']:raise ValidationError('The source order is closed.')
    promised=day(p['promised_date'])
    if promised<doc.date:raise ValidationError('Delivery promise cannot precede its review date.')
    reason=str(p.get('reason','')).strip();basis=str(p.get('basis','')).strip()
    if not reason or not basis or len(reason)>2000 or len(basis)>2000:raise ValidationError('A delivery promise requires a reason and reviewed availability or production basis.')
    doc.reference=order;doc.location=order.location;doc.warehouse=order.warehouse;doc.party=order.party;ctx.lines.update(order.product_lines)
    return {'order':order.pk,'promised_date':promised.isoformat(),'reason':reason,'basis':basis,'stock_reserved':False,'financial_posting':False}

OPERATIONS={'order_promise':('sales.promise',promise)}

class OrderReadinessAPI(Boundary):
    def get(self,request,pk):return response(readiness(self.ctx(request),pk,request.query_params))
