"""Integrate new controls with existing, independently tested posting handlers."""
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db.models import Sum,Q
from .models import (Document,Block,StockPool,StockMovement,MaterialLot,LotMovement,QualityInspection,CustomerPrice)
from .core import D,get_obj,get_product,get_warehouse

ZERO=Decimal('0')
def lot_balance(lot,warehouse):
    return LotMovement.objects.filter(lot=lot,warehouse=warehouse).aggregate(q=Sum('quantity'))['q'] or ZERO

def lot_opening(ctx,p,doc):
    lot=get_obj(ctx,MaterialLot,p['lot']);product=get_product(ctx,lot.product_id);warehouse=get_warehouse(ctx,p['warehouse']);qty=D(p['quantity'])
    if product.unit=='cm' or qty<=0:raise ValidationError('Tag a positive counted/weight quantity of existing stock.')
    physical=StockPool.objects.filter(business=ctx.business,product=product,warehouse=warehouse,profile='').aggregate(q=Sum('quantity'))['q'] or ZERO
    tagged=LotMovement.objects.filter(business=ctx.business,lot__product=product,warehouse=warehouse).aggregate(q=Sum('quantity'))['q'] or ZERO
    if qty+tagged>physical:raise ValidationError('Lot assignment would exceed the actual unassigned warehouse stock.')
    LotMovement.objects.create(business=ctx.business,lot=lot,warehouse=warehouse,document=doc,quantity=qty)
    doc.warehouse=warehouse;doc.location=warehouse.location
    return {'lot':lot.id,'quantity':str(qty),'stock_changed':False,'accounting_changed':False}

def lot_tracking_enable(ctx,p,doc):
    if not p.get('confirm'):raise ValidationError('Confirm that every existing raw-material pool has been assigned and checked.')
    for pool in StockPool.objects.filter(business=ctx.business,product__kind='raw'):
        get_product(ctx,pool.product_id);get_warehouse(ctx,pool.warehouse_id)
        tagged=LotMovement.objects.filter(business=ctx.business,lot__product=pool.product,warehouse=pool.warehouse).aggregate(q=Sum('quantity'))['q'] or ZERO
        if tagged!=pool.quantity:raise ValidationError('Assign and reconcile all existing raw material lots before enabling strict tracking.')
    ctx.business.settings={**ctx.business.settings,'lot_tracking':True};ctx.business.save(update_fields=['settings'])
    return {'lot_tracking':True,'legacy_quantities_verified':True}

def apply_lots(ctx,p,doc):
    moves=list(StockMovement.objects.filter(document=doc,pool__product__kind='raw').select_related('pool__product','pool__warehouse').order_by('pk'))
    if not moves:return
    strict=ctx.business.settings.get('lot_tracking',False);declared=[]
    supplied=p.get('lot_allocations',[])
    if not isinstance(supplied,list):raise ValidationError('Lot allocations must be a list.')
    if p.get('lot'):supplied=[*supplied,{'lot':p['lot'],'quantity':p['quantity'],'warehouse':p.get('warehouse')}]
    for line in [*p.get('lines',[]),*p.get('inputs',[])]:
        if line.get('lot'):supplied=[*supplied,{'lot':line['lot'],'quantity':line['quantity'],'warehouse':line.get('warehouse')}]
    for item in supplied:
        lot=get_obj(ctx,MaterialLot,item['lot']);get_product(ctx,lot.product_id);qty=D(item['quantity'])
        if qty<=0:raise ValidationError('Lot allocation quantities must be positive.')
        declared.append({'lot':lot,'remaining':qty,'warehouse':int(item['warehouse']) if item.get('warehouse') else None})
    carried={};physical={}
    for move in moves:
        pool=move.pool;warehouse=pool.warehouse;product=pool.product;get_product(ctx,product.id)
        key=(product.id,warehouse.id)
        if key not in physical:
            net=sum((m.quantity for m in moves if m.pool_id==pool.id),ZERO);physical[key]=pool.quantity-net
        if move.quantity<0:
            needed=-move.quantity
            balances={lot.id:(lot,lot_balance(lot,warehouse)) for lot in MaterialLot.objects.filter(business=ctx.business,product=product).order_by('expiry_date','id')}
            total_tagged=sum((value[1] for value in balances.values()),ZERO)
            untracked=max(ZERO,physical[key]-total_tagged);allocated=[]
            explicit=[d for d in declared if d['lot'].product_id==product.id and d['remaining'] and d['warehouse'] in (None,warehouse.id)]
            candidates=explicit or [{'lot':lot,'remaining':max(ZERO,quantity)} for lot,quantity in balances.values() if quantity>0]
            for candidate in candidates:
                lot=candidate['lot']
                if lot.state!='released' or (lot.expiry_date and lot.expiry_date<doc.date):
                    if explicit:raise ValidationError('Expired or held material lot cannot be consumed.')
                    continue
                available=lot_balance(lot,warehouse);take=min(needed,candidate['remaining'],available)
                if explicit and candidate['remaining']>available:raise ValidationError('Lot allocation exceeds its actual warehouse balance.')
                if take>0:
                    LotMovement.objects.create(business=ctx.business,lot=lot,warehouse=warehouse,document=doc,quantity=-take)
                    allocated.append([lot,take]);candidate['remaining']-=take;needed-=take
                if not needed:break
            if needed and (strict or explicit or needed>untracked):raise ValidationError('Insufficient released, unexpired lot stock. Record incoming lots or assign legacy stock first.')
            carried.setdefault(product.id,[]).extend(allocated);physical[key]+=move.quantity
        else:
            needed=move.quantity;pending=carried.get(product.id,[])
            for item in pending:
                take=min(needed,item[1])
                if take:
                    LotMovement.objects.create(business=ctx.business,lot=item[0],warehouse=warehouse,document=doc,quantity=take);item[1]-=take;needed-=take
            for candidate in declared:
                lot=candidate['lot']
                if not needed or lot.product_id!=product.id or candidate['warehouse'] not in (None,warehouse.id):continue
                take=min(needed,candidate['remaining'])
                if take:
                    LotMovement.objects.create(business=ctx.business,lot=lot,warehouse=warehouse,document=doc,quantity=take);candidate['remaining']-=take;needed-=take
            if needed and strict:raise ValidationError('Every incoming raw-material quantity requires a lot when strict tracking is enabled.')
            physical[key]+=move.quantity
    if any(item['remaining'] for item in declared):raise ValidationError('Lot allocations do not match this document’s raw-material movements.')

def wrap(action,handler):
    def enriched(ctx,p,doc):
        if action=='production_complete' and p.get('batch') and not p.get('work_order'):
            batch=get_obj(ctx,Document,p['batch'])
            if batch.data.get('work_order'):p={**p,'work_order':batch.data['work_order']}
        if action in {'sale','cut'} and ctx.business.settings.get('require_inspection'):
            for line in p.get('lines',[p]):
                if not line.get('block'):continue
                current=get_obj(ctx,Block,line['block']);inspection=None
                while current:
                    inspection=QualityInspection.objects.filter(business=ctx.business,block=current).order_by('-id').first()
                    if inspection:break
                    current=current.parent
                if not inspection or inspection.outcome!='passed':raise ValidationError('A passing quality inspection is required before cutting or selling this block.')
        if action=='purchase_order' and p.get('expected_date'):
            from .growth import day
            if day(p['expected_date'])<doc.date:raise ValidationError('Expected supplier delivery cannot precede the purchase order.')
        if action in {'sales_return','purchase_return','receivable_writeoff'}:
            from .models import ForeignExposure
            ids=[p.get('invoice'),p.get('receipt')]
            if ForeignExposure.objects.filter(business=ctx.business).filter(Q(invoice_id__in=ids)|Q(invoice__reference_id__in=ids)).exists():
                raise ValidationError('Foreign-currency credits/write-offs need a linked foreign correction workflow. They cannot bypass the monetary subledger.')
        if action=='quality_release':
            block=get_obj(ctx,Block,p['block'])
            inspection=QualityInspection.objects.filter(business=ctx.business,block=block).order_by('-id').first()
            if (ctx.business.settings.get('require_inspection') or inspection) and (not inspection or inspection.outcome!='passed'):
                raise ValidationError('A passing latest inspection is required before releasing this block.')
        if action=='sale' and p.get('party'):
            # Contract prices are defaults; discount/override authorization remains in the sale handler.
            from .operations import sheet_thickness
            from .core import profile_for
            updated=[]
            for item in p.get('lines',[]):
                row=dict(item);profile=''
                if row.get('block'):profile=get_obj(ctx,Block,row['block']).profile
                price=CustomerPrice.objects.filter(business=ctx.business,party_id=p['party'],product_id=row['product'],profile=profile,effective_from__lte=doc.date).filter(Q(effective_to__isnull=True)|Q(effective_to__gte=doc.date)).order_by('-effective_from').first()
                if price and row.get('unit_price') in (None,''):row['unit_price']=str(price.unit_price)
                updated.append(row)
            p={**p,'lines':updated}
        result=handler(ctx,p,doc)
        if action in {'production','production_complete','production_bom'} and ctx.business.settings.get('require_inspection'):
            Block.objects.filter(business=ctx.business,batch=doc,status='ready').update(status='inspection')
        apply_lots(ctx,p,doc)
        if action in {'production','production_complete','production_bom'}:
            from .growth import production_link
            result=production_link(ctx,p,doc,result)
        return result
    return enriched

def enrich_registry(registry):
    actions={'quality_release','sale','cut','sales_return','receivable_writeoff','purchase_order','purchase_receive','production','production_consume','production_complete','production_bom','material_issue','material_return','production_material_return','transfer_dispatch','transfer_receive','transfer_resolve','purchase_return','stock_opening','stock_adjust','stock_count_adjust','maintenance_complete'}
    for action in actions&registry.keys():
        permission,handler=registry[action];registry[action]=(permission,wrap(action,handler))
    registry.update({'lot_opening':('inventory.raw',lot_opening),'lot_tracking_enable':('inventory.raw',lot_tracking_enable)})
    return registry
