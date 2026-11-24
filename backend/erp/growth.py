"""Real operational workflows, called atomically through core.execute."""
from datetime import date,timedelta
from decimal import Decimal,ROUND_CEILING
from django.core.exceptions import PermissionDenied,ValidationError
from django.db.models import Sum,Q
from django.utils import timezone
from .models import (Document,Membership,Party,Product,Warehouse,Block,StockPool,StockMovement,Entry,Employee,Account,
 CollectionTask,CollectionNote,ReminderMessage,ReorderPolicy,PurchaseRequest,WorkCenter,WorkOrder,JobCard,WorkProduction,
 CutPlan,BinLocation,BlockPlacement,DeliveryConfirmation,InspectionTemplate,QualityInspection,MaterialLot,LotMovement,
 BudgetLine,ForecastItem,Equipment,MaintenanceJob,CustomerPrice)
from .core import D,money,get_obj,get_product,get_warehouse,outstanding,execute,Context,journal,stock_out

ZERO=Decimal('0')
def fail(message): raise ValidationError(message)
def positive(value):
    value=D(value)
    if value<=0: fail('Enter a positive quantity or amount.')
    return value
def nonnegative(value):
    value=D(value)
    if value<0: fail('Negative values are not permitted.')
    return value
def day(value):
    try:return date.fromisoformat(str(value))
    except (ValueError,TypeError):fail('Use a valid YYYY-MM-DD date.')
def text(payload,key,limit=5000):
    value=str(payload.get(key) or '').strip()
    if not value or len(value)>limit: fail(f'{key} is required (maximum {limit} characters).')
    return value

def compatible_profile(product,value):
    value=str(value or '').replace(' ','')
    if product.unit!='cm':
        if value:fail('Only sponge stock uses a dimensional footprint.')
        return ''
    import re
    from .core import profile_for
    from .operations import geometry
    parts=re.split('[x×]',value.lower())
    if len(parts)!=2:fail('Enter the compatible footprint as length × width in millimeters, for example 2000 × 1000.')
    return profile_for(geometry(parts[0],'length'),geometry(parts[1],'width'))
def scoped(ctx,query,location=None):
    if not ctx.membership.all_locations:query=query.filter(**{(location or 'location_id')+'__in':ctx.membership.location_ids})
    return query
def invoice(ctx,ident):
    record=get_obj(ctx,Document,ident)
    if record.kind not in {'sale','opening_receivable'} or record.state!='posted':fail('Select a posted customer debt.')
    ctx.lines.update(record.product_lines)
    return record
def subpost(ctx,action,payload,parent,suffix):
    child=Context(ctx.user,ctx.business,ctx.membership,approval_source=ctx.approval_source)
    result=execute(child,action,{'date':parent.date.isoformat(),**payload},f'growth:{parent.id}:{suffix}')
    ctx.lines.update(result.product_lines)
    return result

def collection_create(ctx,p,doc):
    bill=invoice(ctx,p['invoice']);amount=money(positive(p['promised_amount']));due=day(p['due_date'])
    if bill.date>doc.date or due<doc.date:fail('A new promise must follow its invoice and cannot already be past due.')
    if amount>outstanding(bill):fail('Promise exceeds the unpaid invoice balance.')
    assignee=get_obj(ctx,Membership,p['assignee']) if p.get('assignee') else ctx.membership
    collector=Context(assignee.user,ctx.business,assignee)
    if not (collector.has('sales.view') or collector.has('sales.collect')):fail('Collector must have permission to view or collect customer debts.')
    if not assignee.active or not (assignee.all_locations or bill.location_id in assignee.location_ids):fail('Collector must have access to the invoice location.')
    if not (set(bill.product_lines)<=set(assignee.product_lines)):fail('Collector must be assigned all invoice product lines.')
    active=sum((t.promised_amount for t in CollectionTask.objects.filter(invoice=bill,state='open')),ZERO)
    if active+amount>outstanding(bill):fail('Existing open promises already cover this debt.')
    task=CollectionTask.objects.create(business=ctx.business,invoice=bill,assignee=assignee,due_date=due,promised_amount=amount,note=str(p.get('note','')),created_by=ctx.user)
    doc.reference=bill;doc.location=bill.location;doc.party=bill.party
    return {'task':task.id,'invoice':bill.id,'promised_amount':str(amount),'due_date':due.isoformat()}

def collection_note(ctx,p,doc):
    task=get_obj(ctx,CollectionTask,p['task']);bill=invoice(ctx,task.invoice_id)
    if task.state!='open':fail('This follow-up is closed.')
    outcome=p.get('outcome','contacted')
    if outcome not in {'contacted','no_answer','rescheduled','broken','cancelled','kept'}:fail('Unknown follow-up outcome.')
    next_date=day(p['next_date']) if p.get('next_date') else None
    if outcome=='rescheduled':
        if not next_date or next_date<doc.date:fail('Choose a future follow-up date.')
        task.due_date=next_date
    if outcome=='kept' and outstanding(bill)>0:fail('The invoice must be settled before closing its promise as kept.')
    if outcome in {'broken','cancelled','kept'}:task.state=outcome;task.closed_by=doc
    task.save()
    note=CollectionNote.objects.create(business=ctx.business,task=task,document=doc,outcome=outcome,note=text(p,'note'),next_date=next_date)
    doc.reference=bill;doc.location=bill.location;doc.party=bill.party
    return {'note':note.id,'task':task.id,'state':task.state,'outstanding':str(outstanding(bill))}

def reminder_prepare(ctx,p,doc):
    task=get_obj(ctx,CollectionTask,p['task']);bill=invoice(ctx,task.invoice_id)
    if task.state!='open' or outstanding(bill)<=0:fail('Only open unpaid follow-ups can receive reminders.')
    channel=p.get('channel','manual')
    if channel not in {'manual','sms','whatsapp'}:fail('Select a supported reminder channel.')
    phone=str(p.get('recipient') or bill.party.phone or '').strip()
    if channel!='manual' and (not phone or not p.get('consent_confirmed')):fail('Confirm the recipient and communication consent before authorizing delivery.')
    body=f'{ctx.business.name}\n{bill.number}\nباقی‌مانده / Outstanding: {outstanding(bill)} {ctx.business.currency}\nتاریخ وعده / Promised date: {task.due_date}'
    message=ReminderMessage.objects.create(business=ctx.business,task=task,channel=channel,recipient=phone,body=body,authorized_by=ctx.user,source=doc,state='prepared' if channel=='manual' else 'queued')
    doc.reference=bill;doc.location=bill.location;doc.party=bill.party
    return {'message':message.id,'state':message.state,'body':body,'channel':channel,'outstanding_snapshot':str(outstanding(bill)),'delivered':False}

def reorder_policy(ctx,p,doc):
    warehouse=get_warehouse(ctx,p['warehouse']);product=get_product(ctx,p['product']);profile=compatible_profile(product,p.get('profile'))
    if warehouse.kind=='transit' or product.kind=='service':fail('Reorder policies require a physical stock item and warehouse.')
    if product.unit=='cm' and not profile:fail('Sponge replenishment requires a specific compatible footprint.')
    minimum=nonnegative(p.get('minimum',0));target=positive(p['target'])
    if target<minimum:fail('Target must not be below minimum.')
    supplier=get_obj(ctx,Party,p['supplier']) if p.get('supplier') else None
    if supplier and supplier.kind!='supplier':fail('Select a supplier.')
    lead=int(p.get('lead_days',0))
    if lead<0 or lead>3650:fail('Invalid supplier lead time.')
    policy,_=ReorderPolicy.objects.update_or_create(business=ctx.business,warehouse=warehouse,product=product,profile=profile,defaults={'minimum':minimum,'target':target,'safety_stock':nonnegative(p.get('safety_stock',0)),'daily_usage':nonnegative(p.get('daily_usage',0)),'lead_days':lead,'supplier':supplier,'active':bool(p.get('active',True))})
    doc.warehouse=warehouse;doc.location=warehouse.location
    return {'policy':policy.id}

def replenishment(ctx,params=None):
    params=params or {};ctx.require('purchases.view')
    policies=scoped(ctx,ReorderPolicy.objects.filter(business=ctx.business,active=True).select_related('product','warehouse','supplier'),'warehouse__location_id')
    if params.get('warehouse'):policies=policies.filter(warehouse=get_warehouse(ctx,params['warehouse']))
    if params.get('location'):policies=policies.filter(warehouse__location_id=get_obj(ctx,__import__('erp.models',fromlist=['Location']).Location,params['location']).id)
    result=[]
    for rule in policies:
        product=get_product(ctx,rule.product_id)
        pool=StockPool.objects.filter(business=ctx.business,warehouse=rule.warehouse,product=product,profile=rule.profile).first()
        quantity=pool.quantity if pool else ZERO
        reserved=sum((b.reserved_height_mm/10 for b in Block.objects.filter(business=ctx.business,warehouse=rule.warehouse,product=product,profile=rule.profile)),ZERO) if product.unit=='cm' else ZERO
        incoming=ZERO
        orders=Document.objects.filter(business=ctx.business,kind='purchase_order',state='posted',warehouse=rule.warehouse)
        if not ctx.has('documents.all_lines'):orders=orders.filter(product_lines__contained_by=ctx.membership.product_lines)
        for order in orders:
            if Document.objects.filter(reference=order,kind='order_cancel',state='posted').exists():continue
            receipts=Document.objects.filter(business=ctx.business,kind='purchase_receive',state='posted',result__order=order.id)
            for index,line in enumerate(order.result.get('lines',[])):
                if line['product']!=product.id or line.get('profile','')!=rule.profile:continue
                used=sum((D(r['quantity']) for receipt in receipts for r in receipt.result.get('lines',[]) if r.get('order_index')==index),ZERO)
                incoming+=max(ZERO,D(line['quantity'])-used)
        requested=sum((r.quantity for r in PurchaseRequest.objects.filter(policy=rule,state='open')),ZERO)
        projected=quantity-reserved+incoming+requested
        trigger=max(rule.minimum,rule.safety_stock+rule.daily_usage*rule.lead_days)
        suggested=max(ZERO,max(rule.target,trigger)-projected) if projected<trigger else ZERO
        if product.unit=='each':suggested=suggested.to_integral_value(rounding=ROUND_CEILING)
        result.append({'id':rule.id,'product':product.id,'product_name':product.name,'unit':product.unit,'warehouse':rule.warehouse_id,'warehouse_name':rule.warehouse.name,'profile':rule.profile,'on_hand':str(quantity),'reserved':str(reserved),'on_order':str(incoming),'requested':str(requested),'projected':str(projected),'trigger':str(trigger),'target':str(rule.target),'suggested_quantity':str(suggested),'lead_days':rule.lead_days,'supplier':rule.supplier_id})
    return {'rows':result,'basis':'Current physical stock minus reservations plus unreceived purchase orders and open purchase requests. Usage/lead-time inputs are owner-configured assumptions.'}

def request_purchase(ctx,p,doc):
    ctx.require('purchases.view');rule=get_obj(ctx,ReorderPolicy,p['policy']);get_warehouse(ctx,rule.warehouse_id);get_product(ctx,rule.product_id)
    row=next((r for r in replenishment(ctx)['rows'] if r['id']==rule.id),None)
    if not row or D(row['suggested_quantity'])<=0:fail('No replenishment shortage remains for this policy.')
    amount=positive(p.get('quantity',row['suggested_quantity']))
    if amount>D(row['suggested_quantity']):fail('Requested quantity exceeds the current suggestion; review the policy instead.')
    request=PurchaseRequest.objects.create(business=ctx.business,policy=rule,quantity=amount,source=doc)
    doc.warehouse=rule.warehouse;doc.location=rule.warehouse.location
    return {'request':request.id,'quantity':str(amount),'unit':rule.product.unit}

def request_order(ctx,p,doc):
    request=get_obj(ctx,PurchaseRequest,p['request']);rule=request.policy;get_warehouse(ctx,rule.warehouse_id);get_product(ctx,rule.product_id)
    if request.state!='open':fail('This purchase request is already converted or cancelled.')
    supplier=get_obj(ctx,Party,p.get('supplier') or rule.supplier_id)
    if supplier.kind!='supplier':fail('Select a supplier.')
    order=subpost(ctx,'purchase_order',{'warehouse':rule.warehouse_id,'party':supplier.id,'supplier':supplier.id,'lines':[{'product':rule.product_id,'quantity':str(request.quantity),'unit_price':str(nonnegative(p.get('unit_price',0))),'profile':rule.profile}],'notes':f'Replenishment request {request.id}'},doc,'purchase-order')
    request.order=order;request.state='ordered';request.save();doc.reference=order;doc.warehouse=rule.warehouse;doc.location=rule.warehouse.location
    return {'request':request.id,'order':order.id,'number':order.number}

def work_center(ctx,p,doc):
    from .models import Location
    location=get_obj(ctx,Location,p['location']);minutes=int(p.get('daily_minutes',480))
    if not 1<=minutes<=1440:fail('Work center capacity must be 1–1440 minutes per day.')
    name=text(p,'name',150);existing=WorkCenter.objects.filter(business=ctx.business,name=name).first()
    if existing:
        get_obj(ctx,WorkCenter,existing.id)
        if existing.location_id!=location.id:fail('Create a new work center instead of moving recorded capacity to a different location.')
        from .advanced_planning import capacity_usage
        if any(total>minutes for total in capacity_usage(ctx.business,existing.id).values()):fail('Daily capacity cannot be reduced below already scheduled work.')
    center,_=WorkCenter.objects.update_or_create(business=ctx.business,name=name,defaults={'location':location,'daily_minutes':minutes,'active':True})
    doc.location=location;return {'work_center':center.id}

def work_order(ctx,p,doc):
    center=get_obj(ctx,WorkCenter,p['work_center']);warehouse=get_warehouse(ctx,p['warehouse']);product=get_product(ctx,p['product'])
    if not center.active or center.location_id!=warehouse.location_id or product.kind!='finished':fail('Choose an active work center, its warehouse and a finished product.')
    scheduled=day(p['scheduled_date']);minutes=int(p['planned_minutes']);quantity=positive(p['planned_quantity'])
    if scheduled<doc.date or minutes<=0:fail('Schedule work on/after the planning date with positive minutes.')
    from .advanced_planning import capacity_usage
    occupied=capacity_usage(ctx.business,center.id,scheduled)
    if occupied+minutes>center.daily_minutes:fail('The work center has insufficient daily capacity; reschedule or split this work.')
    order=get_obj(ctx,Document,p['order']) if p.get('order') else None
    if order and (order.kind!='sales_order' or order.state!='posted' or order.warehouse_id!=warehouse.id):fail('Choose a posted sales order for this warehouse.')
    if order:
        from .operations import _commercial_cancelled
        if _commercial_cancelled(ctx,order):fail('This sales order or its quotation is closed; no new work can be planned against it.')
    if order and order.date>doc.date:fail('A work order cannot precede its sales order.')
    work=WorkOrder.objects.create(business=ctx.business,number=doc.number,product=product,warehouse=warehouse,work_center=center,order=order,planned_quantity=quantity,scheduled_date=scheduled,planned_minutes=minutes,notes=str(p.get('notes','')),source=doc)
    doc.warehouse=warehouse;doc.location=warehouse.location;doc.reference=order
    return {'work_order':work.id,'state':work.state,'planned_quantity':str(quantity),'unit':product.unit}

def job_card(ctx,p,doc):
    work=get_obj(ctx,WorkOrder,p['work_order']);get_warehouse(ctx,work.warehouse_id);get_product(ctx,work.product_id)
    if work.order_id:
        from .operations import _commercial_cancelled
        if _commercial_cancelled(ctx,work.order):fail('The source quotation/order is closed. Close the remaining work order instead of starting further work.')
    if work.state not in {'planned','in_progress'}:fail('Work order is not open.')
    employee=get_obj(ctx,Employee,p['employee']) if p.get('employee') else None
    if employee and (not employee.active or employee.location_id!=work.warehouse.location_id):fail('Choose an active worker at this factory.')
    minutes=int(p['minutes'])
    if minutes<=0 or minutes>1440:fail('Actual work minutes must be 1–1440.')
    card=JobCard.objects.create(business=ctx.business,work_order=work,employee=employee,operation=text(p,'operation',150),minutes=minutes,date=doc.date,note=str(p.get('note','')),source=doc)
    work.state='in_progress';work.save(update_fields=['state']);doc.location=work.warehouse.location;doc.warehouse=work.warehouse
    return {'job_card':card.id,'minutes':minutes,'work_order':work.id,'payroll_posted':False}

def produced(work):
    return sum((m.quantity for m in StockMovement.objects.filter(document__in=work.production_links.values('document'),pool__product=work.product,quantity__gt=0)),ZERO)

def work_close(ctx,p,doc):
    work=get_obj(ctx,WorkOrder,p['work_order']);get_warehouse(ctx,work.warehouse_id);get_product(ctx,work.product_id)
    if work.state not in {'planned','in_progress'}:fail('Work order is already closed.')
    action=p.get('state','completed');actual=produced(work)
    if action=='completed' and actual<work.planned_quantity:fail('Posted production has not yet fulfilled the planned output.')
    if action=='cancelled' and not p.get('reason'):fail('A cancellation reason is required.')
    if action not in {'completed','cancelled'}:fail('Unsupported closure state.')
    work.state=action;work.save(update_fields=['state']);doc.location=work.warehouse.location
    return {'work_order':work.id,'state':action,'actual_quantity':str(actual)}

def before_production(ctx,p,doc):
    if not p.get('work_order'):return None
    work=get_obj(ctx,WorkOrder,p['work_order']);get_product(ctx,work.product_id)
    finishing_existing_wip=False
    if work.order_id:
        from .operations import _commercial_cancelled
        if _commercial_cancelled(ctx,work.order):
            source_ids=[work.order_id]
            if work.order.reference_id and work.order.reference.kind=='quotation':source_ids.append(work.order.reference_id)
            first_closure=Document.objects.filter(business=ctx.business,kind='order_cancel',state='posted',reference_id__in=source_ids).order_by('created_at').first()
            batch=doc.reference if doc.reference_id else None
            finishing_existing_wip=bool(doc.kind=='production_complete' and batch and batch.kind=='production_start' and str(batch.data.get('work_order'))==str(work.id) and batch.created_at<first_closure.created_at)
            if not finishing_existing_wip:fail('The source quotation/order is closed; only completion of its already-started WIP is allowed. New linked production is blocked.')
    if (work.state not in {'planned','in_progress'} and not finishing_existing_wip) or doc.warehouse_id!=work.warehouse_id:fail('Select an open work order at the production warehouse.')
    return work

def production_link(ctx,p,doc,result):
    work=before_production(ctx,p,doc)
    if work:
        if not doc.movements.filter(pool__product=work.product,quantity__gt=0).exists():fail('Work order product does not match the actual finished output.')
        WorkProduction.objects.create(business=ctx.business,work_order=work,document=doc)
        if work.state!='cancelled':work.state='in_progress';work.save(update_fields=['state'])
        result['work_order']=work.id
    return result

def cut_preview(ctx,p):
    from .order_cutting import preview
    return preview(ctx,p)

def cut_plan(ctx,p,doc):
    preview=cut_preview(ctx,p)
    reservation=subpost(ctx,'reserve',{'warehouse':preview['warehouse'],'lines':preview['allocations']},doc,'reserve')
    plan=CutPlan.objects.create(business=ctx.business,warehouse_id=preview['warehouse'],product_id=preview['product'],profile=preview['profile'],allocations=preview['allocations'],reservation=reservation,source=doc)
    from .order_cutting import record_demands
    record_demands(ctx,plan,preview.get('demands',[]))
    doc.warehouse=plan.warehouse;doc.location=plan.warehouse.location
    return {**preview,'plan':plan.id,'reservation':reservation.id,'reserved':True}

def cut_execute(ctx,p,doc):
    plan=get_obj(ctx,CutPlan,p['plan']);get_warehouse(ctx,plan.warehouse_id);get_product(ctx,plan.product_id)
    from .order_cutting import validate_execution,hold_children,release_held,authorize_plan
    authorize_plan(ctx,plan)
    if plan.state=='executed' and p.get('cancel'):return release_held(ctx,plan,p,doc)
    if plan.state!='planned':fail('This plan is already executed or cancelled.')
    if not p.get('cancel'):validate_execution(ctx,plan)
    # Release its reservation once; the outer business lock excludes intervening cuts.
    release=subpost(ctx,'reservation_release',{'warehouse':plan.warehouse_id,'reservation':plan.reservation_id},doc,'release')
    children=[]
    if p.get('cancel'):
        plan.state='cancelled'
        plan.order_demands.filter(state='planned').update(state='cancelled')
    else:
        for index,line in enumerate(plan.allocations):
            cut=subpost(ctx,'cut',{'warehouse':plan.warehouse_id,'product':plan.product_id,**line},doc,f'cut-{index}')
            children.extend(cut.result['blocks'])
            hold_children(ctx,plan,line,cut.result['blocks'])
        plan.order_demands.filter(state='planned').update(state='cut')
        plan.state='executed'
    plan.completed_by=doc;plan.save();doc.warehouse=plan.warehouse;doc.location=plan.warehouse.location
    return {'plan':plan.id,'state':plan.state,'blocks':children,'release':release.id,'sales_posted':False}

def bin_create(ctx,p,doc):
    warehouse=get_warehouse(ctx,p['warehouse'])
    if warehouse.kind=='transit':fail('Transit is not a physical bin warehouse.')
    place,_=BinLocation.objects.update_or_create(business=ctx.business,warehouse=warehouse,code=text(p,'code',50),defaults={'description':str(p.get('description','')),'active':True})
    doc.warehouse=warehouse;doc.location=warehouse.location;return {'bin':place.id,'code':place.code}

def block_place(ctx,p,doc):
    block=get_obj(ctx,Block,p['block']);get_product(ctx,block.product_id);place=get_obj(ctx,BinLocation,p['bin']);get_warehouse(ctx,place.warehouse_id)
    if not place.active or block.warehouse_id!=place.warehouse_id:fail('Bin and block must be in the same current warehouse.')
    BlockPlacement.objects.update_or_create(business=ctx.business,block=block,defaults={'bin':place,'source':doc})
    doc.location=place.warehouse.location;doc.warehouse=place.warehouse;return {'block':block.id,'bin':place.id,'stock_deducted':False}

def delivery_confirm(ctx,p,doc):
    bill=invoice(ctx,p['invoice'])
    if bill.kind!='sale':fail('Delivery confirmation requires a real sale; an opening balance is not a delivery.')
    if DeliveryConfirmation.objects.filter(invoice=bill).exists():fail('Delivery is already confirmed.')
    confirmation=DeliveryConfirmation.objects.create(business=ctx.business,invoice=bill,recipient=text(p,'recipient',200),received_at=timezone.now(),note=str(p.get('note','')),source=doc)
    doc.reference=bill;doc.location=bill.location;doc.party=bill.party
    return {'confirmation':confirmation.id,'revenue_posted':False,'stock_deducted':False}

def inspection_template(ctx,p,doc):
    product=get_product(ctx,p['product']);criteria=p.get('criteria')
    if not isinstance(criteria,list) or not 1<=len(criteria)<=30:fail('Define 1–30 inspection checks.')
    names=set()
    for criterion in criteria:
        if not isinstance(criterion,dict):fail('Invalid inspection check.')
        name=text(criterion,'name',100)
        if name in names:fail('Inspection check names must be unique.')
        names.add(name)
        if criterion.get('type') not in {'number','pass_fail'}:fail('Check type must be number or pass_fail.')
        if criterion['type']=='number' and D(criterion['min'])>D(criterion['max']):fail('Inspection minimum exceeds maximum.')
    template=InspectionTemplate.objects.create(business=ctx.business,name=text(p,'name',150),product=product,criteria=criteria)
    return {'template':template.id,'version_immutable':True}

def quality_inspect(ctx,p,doc):
    template=get_obj(ctx,InspectionTemplate,p['template']);get_product(ctx,template.product_id)
    block=get_obj(ctx,Block,p['block']) if p.get('block') else None;batch=get_obj(ctx,Document,p['batch']) if p.get('batch') else None
    if bool(block)==bool(batch):fail('Link exactly one physical block or production/receipt batch.')
    if block and block.product_id!=template.product_id:fail('Inspection template does not match the block product.')
    if batch and (batch.state!='posted' or batch.kind not in {'production','production_complete','production_bom','purchase_receive'} or not batch.movements.filter(pool__product=template.product,quantity__gt=0).exists()):fail('Inspection requires a posted receipt/production output for this product.')
    values=p.get('measurements',{});passed=True
    if not isinstance(values,dict):fail('Measurements must be an object.')
    for criterion in template.criteria:
        name=criterion['name']
        if name not in values:fail('Record all required inspection measurements.')
        if criterion['type']=='pass_fail':
            if not isinstance(values[name],bool):fail('Pass/fail measurements must be true or false.')
            passed=passed and values[name]
        else:
            measurement=D(values[name]);within=D(criterion['min'])<=measurement<=D(criterion['max'])
            passed=within and passed
    outcome='passed' if passed else 'failed'
    inspection=QualityInspection.objects.create(business=ctx.business,template=template,block=block,batch=batch,measurements=values,outcome=outcome,source=doc,note=str(p.get('note','')))
    if block:
        if block.status in {'in_transit','exhausted'}:fail('This block cannot be inspected in its current state.')
        block.status='inspection';block.save(update_fields=['status']);doc.warehouse=block.warehouse;doc.location=block.warehouse.location
    elif batch:doc.location=batch.location;doc.warehouse=batch.warehouse
    return {'inspection':inspection.id,'outcome':outcome,'release_required':bool(block)}

def lot_create(ctx,p,doc):
    product=get_product(ctx,p['product']);supplier=get_obj(ctx,Party,p['supplier']) if p.get('supplier') else None
    if product.kind!='raw':fail('Material lots currently track raw materials. Finished sponge is tracked by physical blocks.')
    if supplier and supplier.kind!='supplier':fail('Select a supplier.')
    lot=MaterialLot.objects.create(business=ctx.business,code=text(p,'code',100),product=product,supplier=supplier,expiry_date=day(p['expiry_date']) if p.get('expiry_date') else None,state='released')
    return {'lot':lot.id,'product':product.id}

def lot_status(ctx,p,doc):
    lot=get_obj(ctx,MaterialLot,p['lot']);get_product(ctx,lot.product_id)
    if not ctx.membership.all_locations:raise PermissionDenied('A lot hold affects every warehouse; complete location scope is required.')
    state=p.get('state')
    if state not in {'held','released'}:fail('Choose held or released.')
    reason=text(p,'reason')
    lot.state=state;lot.save(update_fields=['state'])
    return {'lot':lot.id,'state':state,'reason':reason,'stock_changed':False,'accounting_changed':False}

def budget_set(ctx,p,doc):
    from .models import Location
    from .calendar_periods import month_bounds,period_for
    calendar=p.get('period_calendar','gregorian');first,last=month_bounds(p['period'],calendar)
    p={**p,'period':period_for(first,calendar)}
    location=get_obj(ctx,Location,p['location']);account=get_obj(ctx,Account,p['account']);line=p.get('line','shared')
    if account.category not in {'income','expense'} or not ctx.line_allowed(line):fail('Budget an authorized income/expense account and product line.')
    budget,_=BudgetLine.objects.update_or_create(business=ctx.business,period=p['period'],account=account,location=location,line=line,defaults={'amount':money(nonnegative(p['amount']))})
    doc.location=location;ctx.lines.add(line);return {'budget':budget.id,'posted_to_ledger':False}

def forecast_add(ctx,p,doc):
    from .models import Location
    location=get_obj(ctx,Location,p['location']);direction=p.get('direction')
    if direction not in {'in','out'}:fail('Forecast direction must be in or out.')
    item=ForecastItem.objects.create(business=ctx.business,date=day(p['forecast_date']),location=location,direction=direction,amount=money(positive(p['amount'])),description=text(p,'description',250),source=doc)
    doc.location=location;return {'forecast':item.id,'posted_to_ledger':False}

def equipment_create(ctx,p,doc):
    from .models import Asset
    center=get_obj(ctx,WorkCenter,p['work_center']);asset=get_obj(ctx,Asset,p['asset']) if p.get('asset') else None
    if asset and asset.location_id and asset.location_id!=center.location_id:fail('Equipment asset and work center locations differ.')
    interval=int(p.get('service_interval_days',30))
    if not 1<=interval<=3650:fail('Service interval must be 1–3650 days.')
    equipment=Equipment.objects.create(business=ctx.business,name=text(p,'name',150),work_center=center,asset=asset,service_interval_days=interval,next_service=day(p['next_service']))
    doc.location=center.location;return {'equipment':equipment.id}

def maintenance_open(ctx,p,doc):
    equipment=get_obj(ctx,Equipment,p['equipment']);get_obj(ctx,WorkCenter,equipment.work_center_id)
    job=MaintenanceJob.objects.create(business=ctx.business,equipment=equipment,due_date=day(p['due_date']),reason=text(p,'reason'),source=doc)
    doc.location=equipment.work_center.location;return {'maintenance':job.id}

def maintenance_complete(ctx,p,doc):
    from .operations import inventory_account
    job=get_obj(ctx,MaintenanceJob,p['maintenance']);get_obj(ctx,WorkCenter,job.equipment.work_center_id)
    if job.state!='open':fail('Maintenance job is already completed.')
    downtime=int(p.get('downtime_minutes',0))
    if downtime<0:fail('Downtime cannot be negative.')
    costs=ZERO;journals=[]
    for part in p.get('lines',[]):
        product=get_product(ctx,part['product']);warehouse=get_warehouse(ctx,part['warehouse'])
        if product.unit=='cm' or warehouse.location_id!=job.equipment.work_center.location_id:fail('Select counted/weight spare parts from this location.')
        quantity=positive(part['quantity']);cost=stock_out(ctx,doc,product,warehouse,quantity)
        costs+=cost;journals.append({'account':inventory_account(product),'credit':money(cost),'location':warehouse.location_id,'warehouse':warehouse.id,'line':product.line})
    if costs:journal(ctx,doc,[{'account':'REPAIRS','debit':money(costs),'location':job.equipment.work_center.location_id},*journals])
    job.state='completed';job.downtime_minutes=downtime;job.completed_by=doc;job.save();equipment=job.equipment;equipment.next_service=doc.date+timedelta(days=equipment.service_interval_days);equipment.save(update_fields=['next_service'])
    doc.location=equipment.work_center.location;doc.amount=money(costs)
    return {'maintenance':job.id,'cost':str(money(costs)),'downtime_minutes':downtime,'next_service':equipment.next_service.isoformat()}

def customer_price(ctx,p,doc):
    party=get_obj(ctx,Party,p['party']);product=get_product(ctx,p['product']);start=day(p['effective_from']);end=day(p['effective_to']) if p.get('effective_to') else None;profile=str(p.get('profile',''))
    profile=compatible_profile(product,profile)
    if party.kind!='customer' or (end and end<start):fail('Invalid customer or price effective dates.')
    if product.unit=='cm' and not profile:fail('Sponge prices require their compatible footprint.')
    overlapping=CustomerPrice.objects.filter(business=ctx.business,party=party,product=product,profile=profile,effective_from__lte=end or date.max).filter(Q(effective_to__isnull=True)|Q(effective_to__gte=start))
    if overlapping.exists():fail('Customer price dates overlap an existing price.')
    price=CustomerPrice.objects.create(business=ctx.business,party=party,product=product,profile=profile,unit_price=nonnegative(p['unit_price']),effective_from=start,effective_to=end)
    return {'customer_price':price.id}

def validate_print_profile(profile):
    import re
    limits={'legal_name':200,'address':600,'phone':100,'footer':1000,'payment_instructions':1000,'signature_left':120,'signature_right':120}
    options={'accent_color','receipt_paper','show_signatures','show_printed_at','logo_data_url','document_language','document_templates','printer_profiles'}
    if not isinstance(profile,dict) or set(profile)-set(limits)-options:fail('Unknown print profile field.')
    for key,value in profile.items():
        if key in limits and (not isinstance(value,str) or len(value)>limits[key]):fail(f'Invalid print profile {key}.')
        if key in ('show_signatures','show_printed_at') and not isinstance(value,bool):fail(f'Invalid print profile {key}.')
    if 'accent_color' in profile and (not isinstance(profile['accent_color'],str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',profile['accent_color'])):fail('Select a six-digit print accent color.')
    if 'receipt_paper' in profile and profile['receipt_paper'] not in ('A4','80mm'):fail('Select A4 or 80mm receipt paper.')
    from .print_profiles import validate_advanced
    return validate_advanced({key:value.strip() if isinstance(value,str) else value for key,value in profile.items()})

def print_profile(ctx,p,doc):
    # The older operation updates its original fields without discarding newer
    # appearance choices from the dedicated Settings screen.
    profile=validate_print_profile({**ctx.business.settings.get('print_profile',{}),**{key:p.get(key,'') for key in ['legal_name','address','phone','footer','payment_instructions']}})
    ctx.business.settings={**ctx.business.settings,'print_profile':profile};ctx.business.save(update_fields=['settings'])
    return {'print_profile':profile,'posted_to_ledger':False}

OPERATIONS={
 'collection_create':('sales.collect',collection_create),'collection_note':('sales.collect',collection_note),'reminder_prepare':('messaging.send',reminder_prepare),
 'reorder_policy':('purchases.plan',reorder_policy),'purchase_request':('purchases.plan',request_purchase),'request_order':('purchases.post',request_order),
 'work_center':('production.plan',work_center),'work_order':('production.plan',work_order),'job_card':('production.post',job_card),'work_close':('production.plan',work_close),
 'cut_plan':('inventory.post',cut_plan),'cut_execute':('inventory.post',cut_execute),'bin_create':('inventory.manage',bin_create),'block_place':('inventory.post',block_place),'delivery_confirm':('sales.post',delivery_confirm),
 'inspection_template':('quality.manage',inspection_template),'quality_inspect':('quality.post',quality_inspect),'lot_create':('inventory.raw',lot_create),
 'lot_status':('quality.manage',lot_status),
 'budget_set':('accounting.manage',budget_set),'forecast_add':('finance.plan',forecast_add),
 'equipment_create':('maintenance.manage',equipment_create),'maintenance_open':('maintenance.post',maintenance_open),'maintenance_complete':('maintenance.post',maintenance_complete),
 'customer_price':('sales.pricing',customer_price),
 'print_profile':('settings.manage',print_profile),
}
