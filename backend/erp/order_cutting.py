"""Commercial demand reservation and physical held-sheet fulfillment.

All mutations are invoked within core.execute's business lock and transaction.
Preview is read-only; posting recalculates physical and commercial availability.
"""
from decimal import Decimal
from django.core.exceptions import PermissionDenied,ValidationError
from django.db.models import Q,Sum
from .core import D,get_obj,get_product,get_warehouse
from .models import Block,CutPlan,Document
from .cut_models import OrderCutDemand,OrderCutSheet

ZERO=Decimal('0')

def reserved_quantity(ctx,order_id,index):
    planned=OrderCutDemand.objects.filter(business=ctx.business,order_id=order_id,order_index=index,state='planned').aggregate(q=Sum('quantity_cm'))['q'] or ZERO
    held=OrderCutSheet.objects.filter(business=ctx.business,demand__order_id=order_id,demand__order_index=index,fulfilled_document__isnull=True,released_by__isnull=True).aggregate(q=Sum('quantity_cm'))['q'] or ZERO
    return planned+held

def fulfilled_quantity(ctx,order,index):
    return sum((D(line['quantity']) for invoice in Document.objects.filter(business=ctx.business,kind='sale',state='posted',result__order=order.id) for line in invoice.result.get('lines',[]) if line.get('order_index')==index),ZERO)

def source_order(ctx,identifier,warehouse=None):
    from .operations import posted,_commercial_cancelled
    from .api import doc_permission
    order=posted(ctx,identifier,['sales_order']);doc_permission(ctx,order)
    ctx.lines.update(order.product_lines)
    if warehouse and order.warehouse_id!=warehouse.id:raise ValidationError('The sales order and cut plan must use the same warehouse.')
    if _commercial_cancelled(ctx,order):raise ValidationError('The sales order or its quotation is closed; release outstanding cut reservations instead.')
    return order

def preview(ctx,p):
    from .operations import geometry,geometry_zero,_commercial_index
    ctx.require('inventory.view')
    warehouse=get_warehouse(ctx,p['warehouse']);product=get_product(ctx,p['product'])
    from .growth import compatible_profile,day
    profile=compatible_profile(product,p.get('profile',''))
    if warehouse.kind=='transit' or product.unit!='cm' or not profile:raise ValidationError('Choose a physical warehouse, sponge product and compatible footprint.')
    loss=geometry_zero(p.get('cutting_loss_mm','0'),'cutting loss')
    strategy=p.get('strategy','best_fit')
    if strategy not in {'best_fit','preserve_remnants','oldest_first'}:raise ValidationError('Choose best_fit, preserve_remnants or oldest_first cutting strategy.')
    threshold=geometry_zero(p.get('reusable_remnant_mm','100'),'minimum reusable remnant')
    source_lines=p.get('lines',[])
    if not isinstance(source_lines,list) or not 1<=len(source_lines)<=1000:raise ValidationError('Plan between 1 and 1,000 demand lines.')
    demands=[];sheets=[];pending={}
    for index,line in enumerate(source_lines):
        if not isinstance(line,dict):raise ValidationError('Each cutting demand must be an object.')
        thickness=geometry(line['thickness_mm'],'sheet thickness');count=D(line.get('sheet_count',1))
        if count!=count.to_integral_value() or not 1<=count<=1000:raise ValidationError('Use whole sheet counts, maximum 1,000 per demand.')
        demand={'index':index,'thickness_mm':str(thickness),'sheet_count':int(count),'quantity_cm':str(thickness*count/10)}
        if line.get('order'):
            order=source_order(ctx,line['order'],warehouse)
            if p.get('date') and day(p['date'])<order.date:raise ValidationError('A customer cutting plan cannot precede its sales order.')
            order_index=_commercial_index(line.get('order_index',0))
            originals=order.result.get('lines',[])
            if not 0<=order_index<len(originals):raise ValidationError('Invalid sales-order line for this cutting demand.')
            original=originals[order_index]
            if original['product']!=product.id or (original.get('profile') and original['profile']!=profile):raise ValidationError('Demand product and footprint must match the sales-order line.')
            key=(order.id,order_index)
            remaining=D(original['quantity'])-fulfilled_quantity(ctx,order,order_index)-reserved_quantity(ctx,order.id,order_index)-pending.get(key,ZERO)
            quantity=thickness*count/10
            if quantity>remaining:raise ValidationError('Cutting demand exceeds the unfulfilled, unreserved sales-order quantity.')
            pending[key]=pending.get(key,ZERO)+quantity
            demand.update(order=order.id,order_index=order_index,order_number=order.number,customer=order.party.name)
        demands.append(demand)
        sheets.extend((thickness,index) for _ in range(int(count)))
    if len(sheets)>1000:raise ValidationError('A cutting plan is limited to 1,000 physical sheets.')
    blocks=list(Block.objects.filter(business=ctx.business,warehouse=warehouse,product=product,profile=profile,status__in=['ready','reserved']).order_by('remaining_height_mm','id'))
    available={block.id:block.remaining_height_mm-block.reserved_height_mm for block in blocks};codes={block.id:block.code for block in blocks}
    allocations=[]
    for thickness,demand_index in sorted(sheets,key=lambda row:(-row[0],row[1])):
        fits=[identifier for identifier,height in available.items() if height>=thickness+loss]
        if not fits:raise ValidationError('No feasible allocation remains among individual compatible blocks. Remnants cannot be joined.')
        def score(candidate):
            remainder=available[candidate]-thickness-loss
            if strategy=='oldest_first':return (candidate,)
            if strategy=='preserve_remnants':return (0 if remainder==0 or remainder>=threshold else 1,remainder,candidate)
            return (remainder,candidate)
        identifier=min(fits,key=score);available[identifier]-=thickness+loss
        existing=next((row for row in allocations if row['block']==identifier and row['demand_index']==demand_index),None)
        if existing:existing['sheet_count']+=1
        else:allocations.append({'block':identifier,'code':codes[identifier],'thickness_mm':str(thickness),'sheet_count':1,'cutting_loss_mm':str(loss),'loss_policy':'per_cut','demand_index':demand_index})
    used={row['block'] for row in allocations}
    remnants=[{'block':identifier,'height_mm':str(height),'reusable':height>=threshold and height>0} for identifier,height in available.items() if identifier in used]
    return {'warehouse':warehouse.id,'product':product.id,'profile':profile,'allocations':allocations,'demands':demands,'remaining':remnants,'billable_cm':str(sum((row[0] for row in sheets),ZERO)/10),'loss_mm':str(loss*len(sheets)),'strategy':strategy,'reusable_remnant_mm':str(threshold),'used_blocks':len(used),'small_remnant_mm':str(sum((height for identifier,height in available.items() if identifier in used and 0<height<threshold),ZERO)),'reusable_remaining_mm':str(sum((height for identifier,height in available.items() if identifier in used and height>=threshold),ZERO)),'method':f'{strategy} decreasing heuristic; physical and commercial feasibility checked, not a proof of global optimality. Remnant threshold is an operator-reviewed planning preference, not an automatic write-off.','reserved':False}

def record_demands(ctx,plan,demands):
    identifiers={}
    for row in demands:
        if row.get('order'):
            demand=OrderCutDemand.objects.create(business=ctx.business,plan=plan,order_id=row['order'],order_index=row['order_index'],thickness_mm=row['thickness_mm'],sheet_count=row['sheet_count'],quantity_cm=row['quantity_cm'])
            identifiers[row['index']]=demand.id
    for allocation in plan.allocations:
        if allocation.get('demand_index') in identifiers:allocation['order_cut_demand']=identifiers[allocation['demand_index']]
    if identifiers:plan.save(update_fields=['allocations'])

def validate_execution(ctx,plan):
    for demand in plan.order_demands.select_related('order'):
        order=source_order(ctx,demand.order_id,plan.warehouse)
        if fulfilled_quantity(ctx,order,demand.order_index)+reserved_quantity(ctx,order.id,demand.order_index)>D(order.result['lines'][demand.order_index]['quantity']):raise ValidationError('Outstanding cut demand no longer fits the remaining sales order.')

def authorize_plan(ctx,plan):
    from .api import doc_permission
    for demand in plan.order_demands.select_related('order'):
        doc_permission(ctx,demand.order);ctx.lines.update(demand.order.product_lines)

def hold_children(ctx,plan,allocation,children):
    if not allocation.get('order_cut_demand'):return
    demand=get_obj(ctx,OrderCutDemand,allocation['order_cut_demand'])
    if demand.plan_id!=plan.id or demand.state!='planned':raise ValidationError('Invalid demand provenance in this cutting plan.')
    for identifier in children:
        block=get_obj(ctx,Block,identifier)
        if block.reserved_height_mm or block.remaining_height_mm!=demand.thickness_mm:raise ValidationError('A held sheet must be a newly cut, whole physical piece.')
        block.reserved_height_mm=block.remaining_height_mm;block.save(update_fields=['reserved_height_mm'])
        OrderCutSheet.objects.create(business=ctx.business,demand=demand,block=block,quantity_cm=block.remaining_height_mm/10)

def bind_sale(ctx,payload,doc):
    """Identify reserved sheets before the sale handler creates a walk-in party."""
    lines=[dict(row) for row in payload.get('lines',[])];held=[]
    for line in lines:
        if not line.get('block'):continue
        allocation=OrderCutSheet.objects.filter(business=ctx.business,block_id=line['block'],released_by__isnull=True).select_related('demand__order','block').first()
        if not allocation:continue
        get_obj(ctx,OrderCutSheet,allocation.id);block=get_obj(ctx,Block,allocation.block_id)
        get_product(ctx,block.product_id)
        order=source_order(ctx,allocation.demand.order_id)
        if allocation.fulfilled_document_id:raise ValidationError('This order-linked sheet has already been invoiced.')
        from .operations import sheet_thickness
        if D(line.get('sheet_count',1))!=1 or sheet_thickness(line)!=allocation.demand.thickness_mm or D(line.get('cutting_loss_mm','0'))!=0:raise ValidationError('An order-linked held sheet must be sold whole, once, without another cutting loss.')
        if block.remaining_height_mm!=allocation.demand.thickness_mm or block.reserved_height_mm!=block.remaining_height_mm:raise ValidationError('Held-sheet stock and reservation no longer reconcile.')
        if payload.get('order') and str(payload['order'])!=str(order.id):raise ValidationError('The held sheet belongs to a different sales order.')
        if payload.get('party') and str(payload['party'])!=str(order.party_id):raise ValidationError('The held sheet belongs to a different customer.')
        if payload.get('warehouse') and str(payload['warehouse'])!=str(block.warehouse_id):raise ValidationError('The held sheet is in another warehouse.')
        original=order.result['lines'][allocation.demand.order_index]
        line.update(order_index=allocation.demand.order_index)
        if line.get('unit_price') in (None,''):line['unit_price']=original['unit_price']
        held.append((allocation,order,block))
    if not held:return payload
    if len({order.id for _,order,_ in held})!=1:raise ValidationError('Invoice held sheets for one sales order at a time.')
    if len({allocation.id for allocation,_,_ in held})!=len(held):raise ValidationError('A held sheet can appear only once on an invoice.')
    order=held[0][1]
    for allocation,_,block in held:
        block.reserved_height_mm-=allocation.demand.thickness_mm;block.save(update_fields=['reserved_height_mm'])
        allocation.fulfilled_document=doc;allocation.save(update_fields=['fulfilled_document'])
    return {**payload,'order':order.id,'party':order.party_id,'warehouse':order.warehouse_id,'lines':lines}

def release_held(ctx,plan,p,doc):
    reason=str(p.get('reason') or '').strip()
    if not reason:raise ValidationError('Record a reason for releasing cut sheets from customer demand.')
    rows=OrderCutSheet.objects.filter(business=ctx.business,demand__plan=plan,fulfilled_document__isnull=True,released_by__isnull=True).select_related('demand__order','block')
    if p.get('release_order'):
        order=get_obj(ctx,Document,p['release_order']);rows=rows.filter(demand__order=order)
    rows=list(rows)
    if not rows:raise ValidationError('No unsold held sheets remain for this plan/customer order.')
    for allocation in rows:
        get_obj(ctx,Document,allocation.demand.order_id);block=get_obj(ctx,Block,allocation.block_id);get_product(ctx,block.product_id)
        if block.remaining_height_mm!=allocation.demand.thickness_mm or block.reserved_height_mm!=block.remaining_height_mm:raise ValidationError('The held sheet reservation is inconsistent; release cannot hide a stock discrepancy.')
        block.reserved_height_mm=ZERO;block.save(update_fields=['reserved_height_mm'])
        allocation.released_by=doc;allocation.save(update_fields=['released_by'])
    for demand in plan.order_demands.filter(state='cut'):
        if not demand.sheets.filter(fulfilled_document__isnull=True,released_by__isnull=True).exists() and not demand.sheets.filter(fulfilled_document__isnull=False).exists():demand.state='cancelled';demand.save(update_fields=['state'])
    doc.warehouse=plan.warehouse;doc.location=plan.warehouse.location
    return {'plan':plan.id,'state':'held_released','released_blocks':[row.block_id for row in rows],'reason':reason,'sales_posted':False,'stock_deducted':False}

def workspace_data(ctx,params=None):
    from .api import document_scope,doc_permission
    from .operations import _commercial_cancelled
    ctx.require('inventory.view');params=params or {};warehouse=get_warehouse(ctx,params['warehouse']) if params.get('warehouse') else None
    orders=[];sheets=[];plans=[]
    query=document_scope(ctx).filter(kind='sales_order',state='posted').order_by('-id')
    if warehouse:query=query.filter(warehouse=warehouse)
    for order in query:
        try:doc_permission(ctx,order)
        except (PermissionDenied,ValidationError):continue
        if _commercial_cancelled(ctx,order):continue
        for index,line in enumerate(order.result.get('lines',[])):
            try:product=get_product(ctx,line['product'])
            except (PermissionDenied,ValidationError):continue
            if product.unit!='cm':continue
            fulfilled=fulfilled_quantity(ctx,order,index);reserved=reserved_quantity(ctx,order.id,index);remaining=max(D(line['quantity'])-fulfilled-reserved,ZERO)
            orders.append({'id':f'{order.id}:{index}','order':order.id,'order_index':index,'number':order.number,'customer':order.party.name,'party':order.party_id,'warehouse':order.warehouse_id,'product':product.id,'product_name':product.name,'profile':line.get('profile',''),'unit_price':line['unit_price'],'ordered_cm':line['quantity'],'fulfilled_cm':str(fulfilled),'reserved_cm':str(reserved),'available_cm':str(remaining)})
    for sheet in OrderCutSheet.objects.filter(business=ctx.business).select_related('block','demand__order','demand__plan').order_by('-id'):
        block=sheet.block;order=sheet.demand.order
        if warehouse and block.warehouse_id!=warehouse.id:continue
        try:get_obj(ctx,Block,block.id);get_product(ctx,block.product_id);doc_permission(ctx,order)
        except (PermissionDenied,ValidationError):continue
        state='delivered' if sheet.fulfilled_document_id else 'released' if sheet.released_by_id else 'held'
        sheets.append({'id':sheet.id,'block':block.id,'code':block.code,'order':order.id,'order_index':sheet.demand.order_index,'number':order.number,'customer':order.party.name,'party':order.party_id,'warehouse':block.warehouse_id,'product':block.product_id,'profile':block.profile,'thickness_mm':str(sheet.demand.thickness_mm),'quantity_cm':str(sheet.quantity_cm),'unit_price':order.result['lines'][sheet.demand.order_index]['unit_price'],'plan':sheet.demand.plan_id,'state':state,'order_closed':_commercial_cancelled(ctx,order),'invoice':sheet.fulfilled_document_id})
    for plan in CutPlan.objects.filter(business=ctx.business,order_demands__isnull=False).distinct().select_related('warehouse','source').order_by('-id'):
        if warehouse and plan.warehouse_id!=warehouse.id:continue
        try:
            get_warehouse(ctx,plan.warehouse_id);get_product(ctx,plan.product_id)
            for demand in plan.order_demands.select_related('order'):doc_permission(ctx,demand.order)
        except (PermissionDenied,ValidationError):continue
        plans.append({'id':plan.id,'number':plan.source.number,'warehouse':plan.warehouse_id,'product':plan.product_id,'profile':plan.profile,'state':plan.state,'sheets':sum(d.sheet_count for d in plan.order_demands.all())})
    return {'orders':orders,'sheets':sheets,'plans':plans,'method':'Best-fit decreasing across compatible identified blocks; one invoice per customer sales order.'}
