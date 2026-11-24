"""Measured period activity, not recipe inference, payroll or inventory posting."""
from collections import defaultdict
from decimal import Decimal
from django.core.exceptions import PermissionDenied,ValidationError
from django.utils import timezone
from .api import Boundary,document_scope,doc_permission,response
from .core import D,get_obj,get_product,get_warehouse
from .models import Document,StockMovement,Block,JobCard,MaintenanceJob,Location

ZERO=Decimal('0')

def review(ctx,params):
    if not any(ctx.has(p) for p in ('production.view','production.post','production.plan')):raise PermissionDenied('Factory access is restricted.')
    from .growth import day
    end=day(params.get('to') or timezone.localdate());start=day(params.get('from') or end)
    if start>end or (end-start).days>365:raise ValidationError('Select a factory review period of at most 366 days.')
    location=get_obj(ctx,Location,params['location']) if params.get('location') else None
    qs=document_scope(ctx).filter(state='posted',date__range=[start,end])
    if location:qs=qs.filter(location=location)
    kinds={'production','production_bom','production_start','production_consume','production_material_return','production_complete','trim'}
    allowed=[]
    for doc in qs.filter(kind__in=kinds).select_related('warehouse','location').order_by('date','pk'):
        try:doc_permission(ctx,doc)
        except PermissionDenied:continue
        allowed.append(doc)
    ids=[d.pk for d in allowed];outputs={};inputs={};trims={};daily=defaultdict(lambda:defaultdict(lambda:ZERO))
    produced_kinds={'production','production_bom','production_complete'}
    output_ids=[d.pk for d in allowed if d.kind in produced_kinds]
    block_counts=defaultdict(int)
    for b in Block.objects.filter(business=ctx.business,batch_id__in=output_ids):block_counts[(b.batch_id,b.product_id,b.profile)]+=1
    movements=StockMovement.objects.filter(document_id__in=ids).select_related('document','pool__product','pool__warehouse')
    for move in movements:
        p=move.pool.product;key=(p.pk,move.pool.profile,move.pool.warehouse_id)
        base={'product':p.pk,'product_name':p.name,'profile':move.pool.profile,'unit':p.unit,'warehouse':move.pool.warehouse_id,'warehouse_name':move.pool.warehouse.name}
        if move.document.kind in produced_kinds and move.quantity>0 and p.kind!='raw':
            row=outputs.setdefault(key,{**base,'quantity':ZERO,'blocks':0,**({'carrying_value':ZERO} if ctx.has('cost.view') else {})})
            row['quantity']+=move.quantity;row['blocks']+=block_counts[(move.document_id,p.pk,move.pool.profile)]
            block_counts[(move.document_id,p.pk,move.pool.profile)]=0
            if ctx.has('cost.view'):row['carrying_value']+=move.value
            daily[move.document.date.isoformat()][(p.pk,move.pool.profile,p.unit)]+=move.quantity
        if ctx.has('consumption.view') and p.kind=='raw' and move.document.kind in {'production','production_bom','production_consume','production_material_return'}:
            row=inputs.setdefault(key,{**base,'quantity':ZERO,**({'carrying_value':ZERO} if ctx.has('cost.view') else {})});row['quantity']-=move.quantity
            if ctx.has('cost.view'):row['carrying_value']-=move.value
    for doc in allowed:
        if doc.kind!='trim':continue
        # The authorized historical trim belongs to its original warehouse.
        # A later transfer must not change that history's location scope.
        block=Block.objects.get(business=ctx.business,pk=doc.result['block']);p=get_product(ctx,block.product_id)
        # Compare original full-face heights in one profile, never kg inputs / cm outputs.
        total=sum((D(doc.result.get(k,0)) for k in ('main_height_mm','top_height_mm','bottom_height_mm','loss_mm')),ZERO)
        key=(p.pk,block.profile,doc.warehouse_id)
        row=trims.setdefault(key,{'product_name':p.name,'profile':block.profile,'warehouse_name':doc.warehouse.name,'original_mm':ZERO,'main_mm':ZERO,'top_mm':ZERO,'bottom_mm':ZERO,'loss_mm':ZERO,'events':0})
        row['original_mm']+=total;row['events']+=1
        for result_key,name in [('main_height_mm','main_mm'),('top_height_mm','top_mm'),('bottom_height_mm','bottom_mm'),('loss_mm','loss_mm')]:row[name]+=D(doc.result.get(result_key,0))
    for row in trims.values():row['loss_percent']=row['loss_mm']/row['original_mm']*100 if row['original_mm'] else None
    times=defaultdict(int)
    for card in JobCard.objects.filter(business=ctx.business,date__range=[start,end],source__state='posted').select_related('source','work_order__work_center','work_order__warehouse','work_order__product'):
        work=card.work_order
        if location and work.warehouse.location_id!=location.pk:continue
        try:doc_permission(ctx,card.source);doc_permission(ctx,work.source);get_warehouse(ctx,work.warehouse_id);get_product(ctx,work.product_id)
        except PermissionDenied:continue
        times[(work.work_center_id,work.work_center.name)]+=card.minutes
    downtime=None
    if any(ctx.has(p) for p in ('maintenance.view','maintenance.post')):
        downtime=defaultdict(int)
        jobs=MaintenanceJob.objects.filter(business=ctx.business,state='completed',completed_by__date__range=[start,end],completed_by__state='posted').select_related('completed_by','equipment__work_center')
        for job in jobs:
            center=job.equipment.work_center
            if location and center.location_id!=location.pk:continue
            try:doc_permission(ctx,job.completed_by);get_obj(ctx,type(center),center.pk)
            except PermissionDenied:continue
            downtime[(center.pk,center.name)]+=job.downtime_minutes
    result={'from':start,'to':end,'outputs':list(outputs.values()),'trims':list(trims.values()),'job_time':[{'work_center':key[0],'name':key[1],'minutes':minutes} for key,minutes in sorted(times.items())],
            'downtime':[{'work_center':key[0],'name':key[1],'minutes':minutes} for key,minutes in sorted(downtime.items())] if downtime is not None else None,
            'daily':[{'date':date,'product':key[0],'profile':key[1],'unit':key[2],'quantity':qty} for date,groups in sorted(daily.items()) for key,qty in sorted(groups.items())],
            'batch_starts':sum(d.kind=='production_start' for d in allowed),'output_events':len(output_ids),'financial_posting':False,
            'basis':'Effective-date activity from authorized posted output/consumption/return/trim movements and recorded job cards/maintenance completions. Quantities remain separated by product, footprint and unit; initial output is not current saleable stock or a kg-to-cm yield. Job-card minutes are not payroll accrual or certified machine utilization.'}
    if ctx.has('consumption.view'):result['inputs']=list(inputs.values())
    if ctx.has('cost.view'):
        result['costs']={'capitalized_labor':sum((D(d.data.get('labor_cost',0)) for d in allowed if d.kind in {'production','production_bom','production_consume'}),ZERO),
                         'capitalized_overhead':sum((D(d.data.get('overhead_cost',0)) for d in allowed if d.kind in {'production','production_bom','production_consume'}),ZERO),
                         'abnormal_loss':sum((D(d.result.get('abnormal_loss',0)) for d in allowed),ZERO)}
    return result

class FactoryReviewAPI(Boundary):
    def get(self,request):
        params=dict(request.query_params.items())
        if request.headers.get('X-Location-ID'):params['location']=request.headers['X-Location-ID']
        return response(review(self.ctx(request),params))
