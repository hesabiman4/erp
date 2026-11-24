"""Explicit accountant-reviewed late-cost allocation, never historical replay."""
from decimal import Decimal
from django.core.exceptions import PermissionDenied,ValidationError
from django.db.models import Sum
from .core import D,money,get_obj,get_product,get_warehouse,journal,execute,pool_for
from .models import Document,Party,StockPool,StockMovement,Entry,ForeignExposure
from .late_cost_models import LateCostBill,LateCostAllocation

ZERO=Decimal('0')
def fail(message):raise ValidationError(message)
def reason(p,key='reason'):
    value=str(p.get(key) or '').strip()
    if not value or len(value)>2000:fail(f'Record {key}, maximum 2000 characters.')
    return value
def authorized(ctx):
    ctx.require('accounting.post');ctx.require('cost.view');ctx.require('purchases.view')
def posted(ctx,identifier,kinds):
    from .api import doc_permission
    doc=get_obj(ctx,Document,identifier);doc_permission(ctx,doc)
    if doc.state!='posted' or doc.kind not in kinds:fail('Select an eligible posted source document.')
    ctx.lines.update(doc.product_lines)
    return doc
def available(bill):
    allocated=bill.allocations.filter(source__state='posted').aggregate(v=Sum('amount'))['v'] or ZERO
    production=ZERO
    for doc in Document.objects.filter(business=bill.business,state='posted',kind__in=['production','production_bom','production_consume']):
        production+=sum((D(row['amount']) for row in doc.data.get('conversion_allocations',[]) if row['document']==bill.invoice_id),ZERO)
    return bill.amount-allocated-production
def prior_allocated(source_id):
    return LateCostAllocation.objects.filter(bill__invoice_id=source_id,source__state='posted').aggregate(v=Sum('amount'))['v'] or ZERO

def related_products(ctx,bill):
    products=set()
    for receipt_id in bill.receipts:
        receipt=posted(ctx,receipt_id,{'purchase_receive'})
        products.update(row['product'] for row in receipt.result.get('lines',[]))
    # Provenance is a conservative product-level candidate check. Allocation
    # proportions remain explicit accountant evidence, not invented lot tracing.
    batches=list(Document.objects.filter(business=ctx.business,state='posted',kind__in=['production','production_bom','production_complete']))
    for _ in range(20):
        previous=set(products)
        for batch in batches:
            inputs=batch.result.get('inputs',[])
            if batch.reference_id:
                inputs=[row for event in Document.objects.filter(reference_id=batch.reference_id,state='posted') for row in event.result.get('inputs',[])]
            if any(row.get('product') in products for row in inputs):products.update(row['product'] for row in batch.result.get('outputs',[]))
        if previous==products:break
    return products

def bill_create(ctx,p,doc):
    authorized(ctx);supplier=get_obj(ctx,Party,p['supplier'])
    if supplier.kind!='supplier':fail('Choose the freight/customs/service supplier.')
    reference=reason(p,'supplier_reference')
    if len(reference)>100:fail('Supplier reference must be at most 100 characters.')
    if LateCostBill.objects.filter(business=ctx.business,supplier=supplier,reference=reference).exists():fail('This supplier late-cost invoice is already recorded.')
    receipts=[]
    for row in p.get('receipts',[]):
        receipt=posted(ctx,row,{'purchase_receive'})
        if receipt.date>doc.date:fail('Late costs cannot precede the goods receipt.')
        receipts.append(receipt.id)
    if not receipts:fail('Link at least one actual goods receipt.')
    amount=money(p['amount'])
    if amount<=0:fail('Late cost must be positive.')
    warehouse=get_warehouse(ctx,p['warehouse'])
    if not any(Document.objects.filter(pk=i,warehouse=warehouse).exists() for i in receipts):fail('Select a warehouse of the referenced receipts.')
    invoice=execute(ctx,'expense_post',{'date':str(doc.date),'supplier':supplier.id,'location':warehouse.location_id,'amount':str(amount),'expense_account':'COST_CLEARING','production_cost':True,'description':reason(p),'supplier_reference':reference},f'late-bill-{doc.id}')
    bill=LateCostBill.objects.create(business=ctx.business,supplier=supplier,reference=reference,invoice=invoice,amount=amount,receipts=sorted(set(receipts)),reason=reason(p),source=doc)
    for receipt in Document.objects.filter(pk__in=receipts):ctx.lines.update(receipt.product_lines)
    doc.reference=invoice;doc.location=warehouse.location;doc.warehouse=warehouse;doc.party=supplier;doc.amount=amount
    return {'late_cost_bill':bill.id,'invoice':invoice.id,'number':invoice.number,'amount':str(amount),'unallocated':str(amount),'receipts':receipts,'accounting':'The linked supplier bill debits COST_CLEARING and credits AP once.'}

def add_value(ctx,doc,pool,value):
    from .finance import _pool_allowance
    get_product(ctx,pool.product_id);get_warehouse(ctx,pool.warehouse_id)
    pool=StockPool.objects.select_for_update().get(pk=pool.pk)
    if pool.quantity<=0 or pool.warehouse.kind=='transit':fail('Only physically available nonempty inventory pools can receive cost.')
    if pool.last_date and pool.last_date>doc.date:fail('Late-cost allocation cannot precede a later pool event.')
    if _pool_allowance(ctx,pool)>0:fail('Review/reverse the inventory valuation allowance before increasing its gross carrying cost.')
    pool.value+=value;pool.last_date=doc.date;pool.save(update_fields=['value','last_date'])
    StockMovement.objects.create(document=doc,pool=pool,quantity=ZERO,value=value)
    return pool

def wip(ctx,p,doc):
    authorized(ctx);bill=get_obj(ctx,LateCostBill,p['bill']);posted(ctx,bill.invoice_id,{'expense_post'})
    if getattr(ctx,'late_cost_parent',None)!=p.get('allocation_event'):fail('WIP cost is an internal child of a reviewed allocation, not an independent adjustment.')
    batch=posted(ctx,p['batch'],{'production_start'})
    if batch.children.filter(kind='production_complete',state='posted').exists():fail('Late cost can enter only a batch with no completed outputs.')
    value=money(p['amount'])
    if value<=0 or value>available(bill):fail('The amount exceeds the unallocated supplier bill.')
    inputs=[row for child in batch.children.filter(state='posted') for row in child.result.get('inputs',[])]
    if not any(row['product'] in related_products(ctx,bill) for row in inputs):fail('The batch must actually consume a referenced receipt product.')
    if doc.date<max(batch.date,bill.invoice.date):fail('Allocation cannot precede source documents.')
    # Internal WIP children are already represented in the parent allocation.
    # Direct use is rejected unless created by a still-draft allocation event.
    parent=get_obj(ctx,Document,p['allocation_event'])
    if parent.kind!='late_cost_allocate' or parent.state!='draft' or parent.created_by_id!=ctx.user.pk:fail('WIP allocation must be created through the reviewed late-cost allocation form.')
    doc.reference=batch;doc.warehouse=batch.warehouse;doc.location=batch.location;doc.amount=value
    journal(ctx,doc,[{'account':'WIP','debit':value,'location':doc.location_id},{'account':'COST_CLEARING','credit':value,'location':bill.invoice.location_id}])
    return {'batch':batch.id,'bill':bill.id,'wip_in':str(value),'wip_out':'0','allocation_event':parent.id}

def allocate(ctx,p,doc):
    authorized(ctx);bill=get_obj(ctx,LateCostBill,p['bill']);posted(ctx,bill.invoice_id,{'expense_post'})
    if bill.invoice.date>doc.date:fail('Allocation cannot precede its supplier bill.')
    lines=p.get('lines',[])
    if not lines:fail('Enter reviewed cost allocation lines.')
    basis=reason(p,'basis');allowed=related_products(ctx,bill);total=ZERO;results=[];journals=[];children=[]
    # Validate every target and total before posting any nested WIP child.
    for item in lines:
        value=money(item['amount'])
        if value<=0:fail('Each cost allocation must be positive.')
        kind=item.get('target')
        if kind=='inventory':
            pool=get_obj(ctx,StockPool,item['pool']);get_product(ctx,pool.product_id);get_warehouse(ctx,pool.warehouse_id)
            if pool.product_id not in allowed:fail('Inventory must be a received product or an actual production descendant product.')
            results.append({'target':kind,'pool':pool.id,'product':pool.product_id,'amount':str(value)})
        elif kind=='cogs':
            sale=posted(ctx,item['invoice'],{'sale'});index=int(item['index'])
            if index<0 or index>=len(sale.result.get('lines',[])):fail('Choose an original sale line.')
            line=sale.result['lines'][index]
            if line['product'] not in allowed or sale.date>doc.date:fail('Choose a related product sold on or before this date.')
            if ForeignExposure.objects.filter(invoice=sale).exists():fail('Foreign invoice late-cost return handling requires a separate review.')
            if sale.children.filter(kind='sales_return',state='posted').exists():fail('Allocate to on-hand returned stock separately; this sale already has physical returns.')
            get_product(ctx,line['product'])
            results.append({'target':kind,'invoice':sale.id,'index':index,'product':line['product'],'quantity':line['quantity'],'amount':str(value)})
        elif kind=='wip':results.append({'target':kind,'batch':int(item['batch']),'amount':str(value)})
        else:fail('Choose on-hand inventory, sold cost or open WIP.')
        total+=value
    if total>available(bill):fail('Allocations exceed the remaining backed late-cost bill.')
    for row in results:
        value=D(row['amount'])
        if row['target']=='inventory':
            pool=add_value(ctx,doc,get_obj(ctx,StockPool,row['pool']),value)
            from .operations import inventory_account
            journals.append({'account':inventory_account(pool.product,pool.warehouse),'debit':value,'location':pool.warehouse.location_id,'warehouse':pool.warehouse_id,'line':pool.product.line})
        elif row['target']=='cogs':
            sale=get_obj(ctx,Document,row['invoice']);product=get_product(ctx,row['product'])
            journals.append({'account':'COGS','debit':value,'location':sale.location_id,'line':product.line})
        else:
            previous_parent=getattr(ctx,'late_cost_parent',None);ctx.late_cost_parent=doc.id
            try:child=execute(ctx,'late_cost_wip',{'date':str(doc.date),'bill':bill.id,'batch':row['batch'],'amount':row['amount'],'allocation_event':doc.id},f'late-wip-{doc.id}-{len(children)}')
            finally:ctx.late_cost_parent=previous_parent
            children.append(child.id);row['document']=child.id
    direct=sum((D(r['amount']) for r in results if r['target']!='wip'),ZERO)
    journals.append({'account':'COST_CLEARING','credit':direct,'location':bill.invoice.location_id})
    journal(ctx,doc,journals)
    LateCostAllocation.objects.create(business=ctx.business,bill=bill,amount=total,lines=results,basis=basis,source=doc)
    doc.reference=bill.invoice;doc.location=bill.invoice.location;doc.amount=total
    for row in results:
        if row.get('product'):get_product(ctx,row['product'])
    return {'bill':bill.id,'amount':str(total),'lines':results,'basis':basis,'wip_documents':children,'unallocated':str(available(bill)-total),'method':'Explicit reviewed current-period cost allocation; no historical average-cost replay.'}

def restore_return(ctx,p,doc,result):
    invoice=doc.reference
    if not invoice:return result
    restorations=[];current_quantity={};current_value={}
    for returned in result.get('lines',[]):
        late=ZERO
        for allocation in LateCostAllocation.objects.filter(business=ctx.business,source__state='posted'):
            for row_number,row in enumerate(allocation.lines):
                if row.get('target')=='cogs' and row.get('invoice')==invoice.id and row.get('index')==returned['index']:
                    tracking=(allocation.id,row_number)
                    original=D(row['quantity']);prior=ZERO
                    for previous in invoice.children.filter(kind='sales_return',state='posted'):
                        prior+=sum((D(r['quantity']) for r in previous.result.get('lines',[]) if r['index']==returned['index']),ZERO)
                    prior+=current_quantity.get(tracking,ZERO);qty=D(returned['quantity'])
                    previous_value=sum((money(D(row['amount'])*D(r['quantity'])/original) for previous in invoice.children.filter(kind='sales_return',state='posted') for r in previous.result.get('lines',[]) if r['index']==returned['index']),ZERO)
                    previous_value+=current_value.get(tracking,ZERO)
                    part=D(row['amount'])-previous_value if qty+prior==original else money(D(row['amount'])*qty/original)
                    late+=part;current_quantity[tracking]=current_quantity.get(tracking,ZERO)+qty;current_value[tracking]=current_value.get(tracking,ZERO)+part
        if late:
            product=get_product(ctx,returned['product']);warehouse=doc.warehouse
            profile=invoice.result['lines'][returned['index']].get('profile','')
            pool=pool_for(ctx,product,warehouse,profile);add_value(ctx,doc,pool,late)
            from .operations import inventory_account
            journal(ctx,doc,[{'account':inventory_account(product),'debit':late,'location':doc.location_id,'line':product.line},{'account':'COGS','credit':late,'location':doc.location_id,'line':product.line}])
            restorations.append({'index':returned['index'],'value':str(late)})
    if restorations:result={**result,'late_cost_restored':restorations}
    return result

def enrich_registry(registry):
    if 'sales_return' in registry:
        permission,handler=registry['sales_return']
        def returns(ctx,p,doc):return restore_return(ctx,p,doc,handler(ctx,p,doc))
        registry['sales_return']=(permission,returns)
    return registry

OPERATIONS={'late_cost_bill':('accounting.post',bill_create),'late_cost_allocate':('accounting.post',allocate),'late_cost_wip':('accounting.post',wip)}

from .api import Boundary,response,doc_permission
class LateCostAPI(Boundary):
    def get(self,request):
        ctx=self.ctx(request);authorized(ctx);rows=[];pools=[]
        for bill in LateCostBill.objects.filter(business=ctx.business).select_related('invoice','supplier'):
            try:doc_permission(ctx,bill.invoice);related_products(ctx,bill)
            except (PermissionDenied,ValidationError):continue
            rows.append({'id':bill.id,'invoice':bill.invoice_id,'number':bill.invoice.number,'supplier':bill.supplier.name,'reference':bill.reference,'amount':bill.amount,'available':available(bill),'allocations':[{'id':a.id,'amount':a.amount,'basis':a.basis,'lines':a.lines} for a in bill.allocations.all()]})
        for pool in StockPool.objects.filter(business=ctx.business,quantity__gt=0).select_related('product','warehouse'):
            try:get_product(ctx,pool.product_id);get_warehouse(ctx,pool.warehouse_id)
            except (PermissionDenied,ValidationError):continue
            pools.append({'id':pool.id,'name':f'{pool.product.name} · {pool.warehouse.name} · {pool.profile}','quantity':pool.quantity,'value':pool.value})
        return response({'bills':rows,'pools':pools})
