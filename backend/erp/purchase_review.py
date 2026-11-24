"""Source-linked purchasing exceptions, never an alternative posting ledger."""
from collections import Counter
from decimal import Decimal
from django.core.exceptions import PermissionDenied,ValidationError
from django.utils import timezone
from .api import Boundary,document_scope,doc_permission,can,response
from .core import D,get_obj,get_product,outstanding
from .models import Document,Location
from .procurement_models import SupplierClaim

ZERO=Decimal('0')

def review(ctx,params,location_header=None):
    if not can(ctx,'purchases.view','purchases.post','purchases.claim','purchases.approve'):raise PermissionDenied('Purchasing review is restricted.')
    location=params.get('location') or location_header
    location=get_obj(ctx,Location,location) if location else None
    qs=document_scope(ctx).filter(state='posted',kind__in=['purchase_order','purchase_receive','purchase_bill']).select_related('party','warehouse','location')
    if location:qs=qs.filter(location=location)
    issues=[];today=timezone.localdate()
    def authorize(docs):
        docs=list(docs)
        for doc in docs:doc_permission(ctx,doc)
        return docs
    def issue(doc,kind,lines=None,**extra):
        issues.append({'id':f'{kind}:{doc.pk}','document':doc.pk,'number':doc.number,'date':doc.date,'supplier_name':doc.party.name if doc.party_id else '', 'warehouse_name':doc.warehouse.name if doc.warehouse_id else '', 'kind':kind,'lines':lines or [],**extra})
    for doc in qs.order_by('date','pk'):
        try:doc_permission(ctx,doc)
        except PermissionDenied:continue
        if doc.kind=='purchase_order':
            if Document.objects.filter(business=ctx.business,reference=doc,kind='order_cancel',state='posted').exists():continue
            receipts=Document.objects.filter(business=ctx.business,kind='purchase_receive',state='posted',result__order=doc.pk)
            try:receipts=authorize(receipts)
            except PermissionDenied:issue(doc,'restricted_links');continue
            lines=[]
            for index,line in enumerate(doc.result.get('lines',[])):
                product=get_product(ctx,line['product'])
                delivered=sum((D(r['quantity']) for receipt in receipts for r in receipt.result.get('lines',[]) if r.get('order_index')==index),ZERO)
                remaining=max(ZERO,D(line['quantity'])-delivered)
                if remaining:lines.append({'product_name':product.name,'remaining':remaining,'unit':product.unit,'index':index})
            if lines:issue(doc,'undelivered',lines,expected_date=doc.data.get('expected_date'),late=bool(doc.data.get('expected_date') and doc.data['expected_date']<today.isoformat()))
        elif doc.kind=='purchase_receive':
            try:
                from .procurement import receipt_match
                matched=receipt_match(ctx,doc)
            except PermissionDenied:issue(doc,'restricted_links');continue
            bills=authorize(Document.objects.filter(business=ctx.business,reference=doc,kind='purchase_bill',state='posted'))
            returns=authorize(Document.objects.filter(business=ctx.business,result__receipt=doc.pk,kind='purchase_return',state='posted'))
            lines=[]
            for index,line in enumerate(doc.result.get('lines',[])):
                product=get_product(ctx,line['product'])
                billed=sum((D(r['quantity']) for bill in bills for r in bill.result.get('lines',[]) if r['index']==index),ZERO)
                unbilled_returns=sum((D(r['quantity']) for returned in returns if not returned.result.get('bill') for r in returned.result.get('lines',[]) if r['index']==index),ZERO)
                remaining=max(ZERO,D(line['quantity'])-billed-unbilled_returns)
                if remaining:lines.append({'product_name':product.name,'remaining':remaining,'unit':product.unit,'index':index})
            if lines:issue(doc,'unbilled',lines,has_order=bool(matched['order']))
            differences=[r for r in matched['lines'] if 'purchase_price_difference' in r['flags']]
            if differences:issue(doc,'price_review',[{'product_name':r['product_name'],'unit':r['unit'],'difference':r['unit_price_variance']} for r in differences])
        else:
            due=outstanding(doc)
            if due>0:issue(doc,'unpaid',outstanding=due,due_date=doc.data.get('due_date') or doc.date.isoformat(),overdue=(doc.data.get('due_date') or doc.date.isoformat())<today.isoformat())
    for claim in SupplierClaim.objects.filter(business=ctx.business,state='open').select_related('document__party','source','product'):
        if location and claim.document.location_id!=location.pk:continue
        try:doc_permission(ctx,claim.document);doc_permission(ctx,claim.source)
        except PermissionDenied:continue
        issue(claim.document,'claim',[{'product_name':claim.product.name,'remaining':claim.quantity,'unit':claim.product.unit}],claim=claim.pk,claim_document=claim.source_id,reason=claim.reason)
    query=params.get('q','').strip().casefold()
    if len(query)>100:raise ValidationError('Register search is limited to 100 characters.')
    if query:issues=[r for r in issues if query in ' '.join([r['number'],r['supplier_name'],r['warehouse_name'],*(line.get('product_name','') for line in r['lines'])]).casefold()]
    kind=params.get('kind','')
    if kind and kind not in {'undelivered','unbilled','unpaid','claim','price_review','restricted_links'}:raise ValidationError('Select a valid purchasing exception filter.')
    if kind:issues=[r for r in issues if r['kind']==kind]
    try:limit=int(params.get('limit',100));offset=int(params.get('offset',0))
    except (ValueError,TypeError):raise ValidationError('Pagination requires integer limit/offset.')
    if not 1<=limit<=200 or offset<0:raise ValidationError('Select a valid register page.')
    issues.sort(key=lambda r:(not r.get('overdue',r.get('late',False)),r['date'],r['document'],r['kind']))
    counts=Counter(r['kind'] for r in issues)
    total=sum((r['outstanding'] for r in issues if r['kind']=='unpaid'),ZERO)
    count=len(issues)
    return {'results':issues[offset:offset+limit],'count':count,'offset':offset,'limit':limit,'next_offset':offset+limit if offset+limit<count else None,'counts':dict(counts),'unpaid_total':total,'as_of':today,'financial_posting':False,'basis':'Current authorized operational exceptions. Counts identify review items, not journal balances; unpaid total includes only listed supplier bills. Linked hidden progress is not disclosed.'}

class PurchaseReviewAPI(Boundary):
    def get(self,request):return response(review(self.ctx(request),request.query_params,request.headers.get('X-Location-ID')))

class BillableReceiptAPI(Boundary):
    def get(self,request,pk):
        ctx=self.ctx(request);ctx.require('purchases.post')
        receipt=get_obj(ctx,Document,pk);doc_permission(ctx,receipt)
        if receipt.kind!='purchase_receive' or receipt.state!='posted':raise ValidationError('Select a posted goods receipt to bill.')
        from .correction_guidance import return_details
        result=return_details(ctx,receipt)
        result['supplier']=receipt.party_id
        result['receipt_number']=receipt.number
        result.pop('bills',None)
        return response(result)
