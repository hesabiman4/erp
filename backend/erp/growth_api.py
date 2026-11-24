from decimal import Decimal
from datetime import timedelta
from django.core.exceptions import PermissionDenied,ValidationError
from django.db.models import Sum
from django.utils import timezone
from .api import Boundary,response,serialize_model,can,document_scope,doc_permission,public_result
from .core import get_obj,get_product,get_warehouse,outstanding,D,balance
from .models import *
from . import growth

RESOURCES={
 'collections':(CollectionTask,['sales.view','sales.collect']), 'messages':(ReminderMessage,['messaging.send']),
 'purchase_requests':(PurchaseRequest,['purchases.view']), 'work_centers':(WorkCenter,['production.view','production.plan']),
 'work_orders':(WorkOrder,['production.view','production.plan']), 'job_cards':(JobCard,['production.view']),
 'cut_plans':(CutPlan,['inventory.view']), 'bins':(BinLocation,['inventory.view']), 'placements':(BlockPlacement,['inventory.view']),
 'inspection_templates':(InspectionTemplate,['quality.view','quality.post']), 'inspections':(QualityInspection,['quality.view','quality.post']),
 'lots':(MaterialLot,['inventory.raw']), 'budgets':(BudgetLine,['accounting.view']), 'forecast_items':(ForecastItem,['finance.view']),
 'equipment':(Equipment,['maintenance.view','maintenance.post']), 'maintenance':(MaintenanceJob,['maintenance.view','maintenance.post']),
 'prices':(CustomerPrice,['sales.pricing']),
 'fx_rates':(ExchangeRate,['finance.view','finance.fx']), 'fx_wallets':(ForeignWallet,['finance.view','finance.fx']),
 'fx_exposures':(ForeignExposure,['finance.view','finance.fx']), 'fx_remittances':(Remittance,['finance.view','finance.fx']),
}

def authorize(ctx,resource):
    if resource not in RESOURCES:raise ValidationError('Unknown operational resource.')
    model,permissions=RESOURCES[resource]
    if not can(ctx,*permissions):raise PermissionDenied('Operational resource is restricted.')
    return model

def visible(ctx,obj):
    get_obj(ctx,type(obj),obj.pk)
    if isinstance(obj,CutPlan):
        from .order_cutting import authorize_plan
        authorize_plan(ctx,obj)
    if hasattr(obj,'warehouse_id'):get_warehouse(ctx,obj.warehouse_id)
    if hasattr(obj,'product_id'):get_product(ctx,obj.product_id)
    if isinstance(obj,CollectionTask):get_obj(ctx,Document,obj.invoice_id)
    if isinstance(obj,ReminderMessage):get_obj(ctx,Document,obj.task.invoice_id)
    if isinstance(obj,PurchaseRequest):get_warehouse(ctx,obj.policy.warehouse_id);get_product(ctx,obj.policy.product_id)
    if isinstance(obj,JobCard):get_warehouse(ctx,obj.work_order.warehouse_id);get_product(ctx,obj.work_order.product_id)
    if isinstance(obj,BlockPlacement):get_obj(ctx,Block,obj.block_id);get_warehouse(ctx,obj.block.warehouse_id)
    if isinstance(obj,QualityInspection):get_product(ctx,obj.template.product_id);get_obj(ctx,Block,obj.block_id) if obj.block_id else get_obj(ctx,Document,obj.batch_id)
    if isinstance(obj,Equipment):get_obj(ctx,WorkCenter,obj.work_center_id)
    if isinstance(obj,MaintenanceJob):get_obj(ctx,WorkCenter,obj.equipment.work_center_id)
    if isinstance(obj,ForeignExposure):get_obj(ctx,Document,obj.invoice_id);doc_permission(ctx,obj.invoice)
    if isinstance(obj,ForeignWallet):get_obj(ctx,ForeignWallet,obj.id)
    if isinstance(obj,Remittance) and not (ctx.location_allowed(obj.source_wallet.location_id) or ctx.location_allowed(obj.destination_wallet.location_id)):raise PermissionDenied('Remittance is outside your locations.')

class GrowthAPI(Boundary):
    def get(self,request,section):
        ctx=self.ctx(request);params=dict(request.query_params.items());location=request.headers.get('X-Location-ID')
        if location:params['location']=location
        if section=='order_cutting':
            from .order_cutting import workspace_data
            return response(workspace_data(ctx,params))
        if section=='replenishment':return response(growth.replenishment(ctx,params))
        if section=='budgets_actual':return response(budgets_actual(ctx,params))
        if section=='cash_forecast':return response(cash_forecast(ctx,params))
        if section=='exceptions':return response(exceptions(ctx))
        if section=='traceability':return response(traceability(ctx,params))
        if section=='runtime':return response(runtime_status(ctx))
        if section=='effective_prices':return response(effective_prices(ctx,params))
        if section=='supplier_performance':return response(supplier_performance(ctx,params))
        if section=='fx_reconciliation':
            from .foreign import reconcile
            return response(reconcile(ctx))
        model=authorize(ctx,section)
        try:limit=max(1,min(200,int(params.get('limit',100))));offset=max(0,int(params.get('offset',0)))
        except ValueError:raise ValidationError('Use integer pagination.')
        records=[]
        for obj in model.objects.filter(business=ctx.business).order_by('-pk'):
            try:visible(ctx,obj)
            except (PermissionDenied,ValidationError):continue
            row=serialize_model(obj)
            obj_location=getattr(obj,'location_id',None)
            warehouse=getattr(obj,'warehouse',None)
            if warehouse:obj_location=warehouse.location_id
            if isinstance(obj,CollectionTask):
                obj_location=obj.invoice.location_id
                row.update({'number':obj.invoice.number,'customer':obj.invoice.party.name if obj.invoice.party_id else '', 'outstanding':outstanding(obj.invoice),'collector':obj.assignee.user.get_username() if obj.assignee_id else '', 'notes':[{'outcome':n.outcome,'note':n.note,'next_date':n.next_date,'document':n.document_id} for n in obj.notes.order_by('id')]})
            if isinstance(obj,PurchaseRequest):row.update({'product_name':obj.policy.product.name,'warehouse_name':obj.policy.warehouse.name,'unit':obj.policy.product.unit});obj_location=obj.policy.warehouse.location_id
            if isinstance(obj,WorkOrder):row.update({'product_name':obj.product.name,'unit':obj.product.unit,'actual_quantity':growth.produced(obj),'center_name':obj.work_center.name})
            if isinstance(obj,JobCard):obj_location=obj.work_order.warehouse.location_id;row['work_order_number']=obj.work_order.number
            if isinstance(obj,ReminderMessage):obj_location=obj.task.invoice.location_id
            if isinstance(obj,BlockPlacement):obj_location=obj.block.warehouse.location_id
            if isinstance(obj,ForeignExposure):
                from .foreign import exposure_balance
                qty,value=exposure_balance(obj);obj_location=obj.invoice.location_id
                row.update({'number':obj.invoice.number,'customer':obj.invoice.party.name,'foreign_remaining':qty,'carrying_amount':value,'invoice_date':obj.invoice.date})
            if isinstance(obj,ForeignWallet):
                from .foreign import wallet_balance
                qty,value=wallet_balance(obj);row.update({'foreign_balance':qty,'carrying_amount':value})
            if isinstance(obj,Remittance):
                from .foreign import transit_value
                row.update({'source_name':obj.source_wallet.name,'destination_name':obj.destination_wallet.name,'currency':obj.source_wallet.currency,'carrying_amount':transit_value(obj),'state':'received' if obj.completed_by_id else 'in_transit'})
                if location and int(location) not in {obj.source_wallet.location_id,obj.destination_wallet.location_id}:continue
            if isinstance(obj,Equipment):obj_location=obj.work_center.location_id;row['work_center_name']=obj.work_center.name
            if isinstance(obj,MaintenanceJob):obj_location=obj.equipment.work_center.location_id;row['equipment_name']=obj.equipment.name
            if isinstance(obj,QualityInspection):obj_location=obj.block.warehouse.location_id if obj.block_id else obj.batch.location_id;row.update({'block_code':obj.block.code if obj.block_id else None,'batch_number':obj.batch.number if obj.batch_id else None})
            if location and obj_location and obj_location!=int(location):continue
            records.append(row)
        return response({'results':records[offset:offset+limit],'count':len(records),'next_offset':offset+limit if len(records)>offset+limit else None})

class CutPreviewAPI(Boundary):
    def post(self,request):return response(growth.cut_preview(self.ctx(request),dict(request.data)))

class ScanAPI(Boundary):
    def get(self,request):
        ctx=self.ctx(request);ctx.require('inventory.view');value=str(request.query_params.get('code','')).strip()
        if len(value)>300:raise ValidationError('Invalid scanned code.')
        # Scan labels return a business-safe block code or its existing label URL.
        if value.startswith('{'):
            import json
            try:label=json.loads(value)
            except ValueError:raise ValidationError('Unrecognized QR content.')
            if label.get('type')!='erp-block' or label.get('version')!=1 or label.get('business')!=ctx.business.id:raise PermissionDenied('This label belongs to another business or unsupported format.')
            block=get_obj(ctx,Block,label.get('block'))
            if label.get('code')!=block.code:raise ValidationError('The QR label does not match the block identity.')
        elif '/api/blocks/' in value:
            import re
            match=re.search(r'/api/blocks/(\d+)/label/',value)
            if not match:raise ValidationError('Unrecognized block label.')
            block=get_obj(ctx,Block,match.group(1))
        else:
            try:block=Block.objects.get(business=ctx.business,code=value)
            except Block.DoesNotExist:raise ValidationError('No accessible block matches this code.')
            get_obj(ctx,Block,block.id)
        product=get_product(ctx,block.product_id);placement=BlockPlacement.objects.filter(business=ctx.business,block=block,bin__warehouse=block.warehouse).select_related('bin').first()
        return response({'block':serialize_model(block),'product_name':product.name,'warehouse_name':block.warehouse.name,'bin':serialize_model(placement.bin) if placement else None,'unit':'cm','available_cm':str((block.remaining_height_mm-block.reserved_height_mm)/10)})

def budgets_actual(ctx,p):
    from .reports import _entries
    from .calendar_periods import month_bounds,period_for
    ctx.require('accounting.view');calendar=p.get('period_calendar','gregorian');period=p.get('period') or period_for(timezone.localdate(),calendar);first,last=month_bounds(period,calendar)
    query=growth.scoped(ctx,BudgetLine.objects.filter(business=ctx.business,period=period)).filter(line__in=ctx.membership.product_lines).select_related('account','location')
    if p.get('location'):query=query.filter(location_id=p['location'])
    records=[]
    for item in query:
        entry=_entries(ctx,{'from':first.isoformat(),'to':last.isoformat(),'location':str(item.location_id),'line':item.line}).filter(account=item.account)
        amounts=entry.aggregate(dr=Sum('debit'),cr=Sum('credit'));actual=(amounts['dr'] or Decimal(0))-(amounts['cr'] or Decimal(0))
        if item.account.category=='income':actual=-actual
        records.append({'id':item.id,'account':item.account.code,'name':item.account.name,'location':item.location.name,'line':item.line,'budget':str(item.amount),'actual':str(actual),'variance':str(actual-item.amount),'favorable':actual>=item.amount if item.account.category=='income' else actual<=item.amount})
    return {'rows':records,'period':period,'period_calendar':calendar,'first':first.isoformat(),'last':last.isoformat(),'basis':'Posted ledger actuals inside explicit calendar-month boundaries; budget amounts are plans, not journals.'}

def cash_forecast(ctx,p):
    from .models import Location
    from .reports import _entries,_net
    ctx.require('finance.view');today=timezone.localdate();through=day=p.get('through')
    through=growth.day(day) if day else today+timedelta(days=28)
    if through<today or through>today+timedelta(days=366):raise ValidationError('Choose a forecast horizon within the next 366 days.')
    location=get_obj(ctx,Location,p['location']) if p.get('location') else None
    opening=_net(_entries(ctx,{'to':today.isoformat(),**({'location':str(location.id)} if location else {})},period=False).filter(account__code__in=['CASH','BANK','FX_CASH','FX_BANK']))
    events=[];unallocated={}
    for task in CollectionTask.objects.filter(business=ctx.business,state='open',due_date__range=[today,through]).order_by('due_date','pk'):
        try:visible(ctx,task)
        except (PermissionDenied,ValidationError):continue
        if location and task.invoice.location_id!=location.id:continue
        available=unallocated.setdefault(task.invoice_id,max(Decimal(0),outstanding(task.invoice)))
        amount=min(task.promised_amount,available);unallocated[task.invoice_id]-=amount
        if amount:events.append({'date':task.due_date.isoformat(),'description':task.invoice.number,'amount':amount,'source':'customer_promise','estimated':True})
    query=growth.scoped(ctx,ForecastItem.objects.filter(business=ctx.business,state='planned',date__range=[today,through]))
    if location:query=query.filter(location=location)
    for item in query:events.append({'date':item.date.isoformat(),'description':item.description,'amount':item.amount if item.direction=='in' else -item.amount,'source':'manual_forecast','estimated':True})
    running=opening
    for event in sorted(events,key=lambda r:(r['date'],r['source'],r['description'])):running+=event['amount'];event['projected_cash']=running
    return {'opening_recorded_cash':opening,'through':through,'rows':sorted(events,key=lambda r:(r['date'],r['source'],r['description'])),'projected_closing_cash':running,'forecast_not_actual':True,'basis':'Customer promises plus explicitly entered forecast items; unplanned invoices/payroll are not assumed to be paid.'}

def exceptions(ctx):
    records=[];today=timezone.localdate()
    if can(ctx,'sales.view','sales.collect'):
        for task in CollectionTask.objects.filter(business=ctx.business,state='open',due_date__lt=today):
            try:visible(ctx,task)
            except (PermissionDenied,ValidationError):continue
            if outstanding(task.invoice)>0:records.append({'id':'collection-'+str(task.id),'kind':'collection_overdue','reference':task.invoice.number,'due':task.due_date,'action':'collections'})
    if can(ctx,'maintenance.view','maintenance.post'):
        for item in Equipment.objects.filter(business=ctx.business,active=True,next_service__lte=today):
            try:visible(ctx,item)
            except (PermissionDenied,ValidationError):continue
            records.append({'id':'equipment-'+str(item.id),'kind':'maintenance_due','reference':item.name,'due':item.next_service,'action':'equipment'})
    if ctx.has('inventory.raw'):
        for lot in MaterialLot.objects.filter(business=ctx.business,expiry_date__lt=today):
            try:get_product(ctx,lot.product_id)
            except PermissionDenied:continue
            records.append({'id':'lot-'+str(lot.id),'kind':'lot_expired','reference':lot.code,'due':lot.expiry_date,'action':'lots'})
    return {'rows':records}

def traceability(ctx,p):
    ctx.require('inventory.raw');lot=get_obj(ctx,MaterialLot,p['lot']);get_product(ctx,lot.product_id);rows=[];documents=[]
    for move in LotMovement.objects.filter(business=ctx.business,lot=lot).select_related('warehouse','document'):
        if not ctx.location_allowed(move.warehouse.location_id):continue
        try:get_obj(ctx,Document,move.document_id)
        except PermissionDenied:continue
        rows.append({'date':move.document.date,'document':move.document.number,'kind':move.document.kind,'warehouse':move.warehouse.name,'quantity':move.quantity});documents.append(move.document_id)
    output_documents=set(documents)
    batches=Document.objects.filter(pk__in=documents,business=ctx.business,kind='production_consume').values_list('reference_id',flat=True)
    for completion in Document.objects.filter(business=ctx.business,reference_id__in=batches,kind='production_complete',state='posted'):
        try:get_obj(ctx,Document,completion.id)
        except PermissionDenied:continue
        output_documents.add(completion.id)
    blocks=Block.objects.filter(business=ctx.business,batch_id__in=output_documents)
    if not ctx.membership.all_locations:blocks=blocks.filter(warehouse__location_id__in=ctx.membership.location_ids)
    ids=set(blocks.values_list('id',flat=True));frontier=set(ids)
    while frontier:
        children=Block.objects.filter(business=ctx.business,parent_id__in=frontier)
        if not ctx.membership.all_locations:children=children.filter(warehouse__location_id__in=ctx.membership.location_ids)
        frontier=set(children.values_list('id',flat=True))-ids;ids|=frontier
    delivered=[]
    if ctx.has('sales.view'):
        for sale in document_scope(ctx).filter(kind='sale',state='posted'):
            try:doc_permission(ctx,sale)
            except PermissionDenied:continue
            if any(line.get('block') in ids for line in sale.result.get('lines',[])):delivered.append({'invoice':sale.number,'date':sale.date,'customer':sale.party.name if sale.party_id else '', 'document':sale.id})
    return {'lot':serialize_model(lot),'rows':rows,'output_blocks':[serialize_model(b) for b in Block.objects.filter(pk__in=ids)],'deliveries':delivered,'scope':'Recorded material lots, production and descendant pieces; legacy untracked quantities are not claimed to be traced.'}


def runtime_status(ctx):
    """Operational metadata only; never expose paths, credentials or other tenants' totals."""
    import hashlib,json,os
    from datetime import datetime,timezone as utc
    from django.conf import settings
    ctx.require('settings.manage')
    tag=hashlib.sha256(str(settings.DATABASES['default']['NAME']).encode()).hexdigest()[:12]
    path=settings.ROOT_DIR/f'.local/runtime-status-{tag}.json'
    try:data=json.loads(path.read_text(encoding='utf-8'))
    except (OSError,ValueError):data={}
    checked=data.get('checked_at');fresh=False
    try:fresh=(datetime.now(utc.utc)-datetime.fromisoformat(checked)).total_seconds()<180
    except (TypeError,ValueError):pass
    from .backup_settings import configuration
    destination=configuration().get('destination')
    backup=data.get('backup',{}) if destination else {'state':'not_configured'}
    return {'rows':[
      {'id':'worker','component':'Maintenance worker','state':'running' if fresh else 'not_verified','last_check':checked},
      {'id':'backup','component':'Scheduled encrypted backups','state':backup.get('state','not_verified'),'last_check':backup.get('finished_at'),'note':'Destination configuration is deferred; a successful backup does not verify off-device recovery.'},
      {'id':'reconciliation','component':'Scheduled ledger reconciliation','state':data.get('reconciliation',{}).get('state','not_verified'),'last_check':data.get('reconciliation',{}).get('finished_at')},
      {'id':'provider','component':'External reminder provider','state':'configured' if os.environ.get('ERP_MESSAGE_PROVIDER_URL') and os.environ.get('ERP_MESSAGE_PROVIDER_TOKEN') else 'not_configured','note':'Queued/accepted messages are not confirmed deliveries.'}],
      'backup_destination_configured':bool(destination),'recovery_verified':False}

def effective_prices(ctx,p):
    if not can(ctx,'sales.view','sales.post'):raise PermissionDenied('Customer rates are restricted to sales users.')
    party=get_obj(ctx,Party,p['party'])
    if party.kind!='customer':raise ValidationError('Select a customer.')
    day=growth.day(p.get('date') or timezone.localdate())
    from django.db.models import Q
    records=[]
    for price in CustomerPrice.objects.filter(business=ctx.business,party=party,effective_from__lte=day).filter(Q(effective_to__isnull=True)|Q(effective_to__gte=day)):
        try:get_product(ctx,price.product_id)
        except PermissionDenied:continue
        records.append(serialize_model(price))
    return {'results':records}

def supplier_performance(ctx,p):
    ctx.require('purchases.view');location=p.get('location');records={}
    query=document_scope(ctx).filter(kind='purchase_receive',state='posted',party__isnull=False).select_related('party')
    if location:query=query.filter(location=get_obj(ctx,Location,location))
    for receipt in query:
        try:doc_permission(ctx,receipt)
        except PermissionDenied:continue
        row=records.setdefault(receipt.party_id,{'id':receipt.party_id,'supplier':receipt.party.name,'receipts':0,'inspected_receipts':0,'rejected_receipts':0,'dated_order_receipts':0,'on_time':0,'late':0,'lead_days':[]})
        row['receipts']+=1
        inspections=QualityInspection.objects.filter(business=ctx.business,batch=receipt)
        if inspections.exists():
            row['inspected_receipts']+=1
            if inspections.filter(outcome='failed').exists():row['rejected_receipts']+=1
        order=Document.objects.filter(pk=receipt.result.get('order'),business=ctx.business,kind='purchase_order',state='posted').first()
        if order:
            row['lead_days'].append((receipt.date-order.date).days)
            if order.data.get('expected_date'):
                row['dated_order_receipts']+=1
                row['on_time' if receipt.date<=growth.day(order.data['expected_date']) else 'late']+=1
    for row in records.values():
        days=row.pop('lead_days');row['average_lead_days']=str((sum(map(Decimal,days))/len(days)).quantize(Decimal('.1'))) if days else None
    return {'rows':list(records.values()),'basis':'Recorded receipts and inspections only. On-time performance requires an explicit expected date on the linked order; missing inspection is not a quality pass.'}
