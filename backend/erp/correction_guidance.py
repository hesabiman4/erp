"""Source-linked correction choices and remaining-return evidence, without posting.

Choices authorize entry to existing workflows, never promise that a transaction
will post. Their handlers recheck periods, stock, funds and downstream events
under the normal business lock.
"""
from decimal import Decimal
from django.core.exceptions import PermissionDenied,ValidationError
from .api import Boundary,doc_permission,document_data,response
from .core import D,get_obj,registry
from .models import Document,Product,ForeignExposure

def visible(ctx,docs):
    result=[]
    for doc in docs:
        doc_permission(ctx,doc);result.append(doc)
    return result

def return_details(ctx,source,bill_id=None):
    permission='sales.refund' if source.kind=='sale' else 'purchases.post'
    ctx.require(permission)
    if source.state!='posted' or source.kind not in {'sale','purchase_receive'}:
        raise ValidationError('Select a posted sale or goods receipt for a return.')
    if ForeignExposure.objects.filter(invoice=source).exists():
        raise ValidationError('Use the source-linked foreign correction workflow for this invoice.')
    sale=source.kind=='sale'
    prior_qs=Document.objects.filter(business=ctx.business,state='posted',kind='sales_return' if sale else 'purchase_return')
    prior_qs=prior_qs.filter(reference=source) if sale else prior_qs.filter(result__receipt=source.pk)
    prior=visible(ctx,prior_qs)
    bills=[];bill=None
    if not sale:
        bills=visible(ctx,Document.objects.filter(business=ctx.business,reference=source,kind='purchase_bill',state='posted'))
        if bill_id:
            bill=get_obj(ctx,Document,bill_id);doc_permission(ctx,bill)
            if bill.pk not in {d.pk for d in bills}:raise ValidationError('The supplier bill does not belong to this receipt.')
    result=[]
    for index,line in enumerate(source.result.get('lines',[])):
        product=get_obj(ctx,Product,line['product']);original=D(line['quantity'])
        returned=sum((D(r['quantity']) for d in prior for r in d.result.get('lines',[]) if r['index']==index),Decimal('0'))
        remaining=original-returned
        if not sale:
            if bill:
                billed=sum((D(r['quantity']) for r in bill.result.get('lines',[]) if r['index']==index),Decimal('0'))
                bill_returned=sum((D(r['quantity']) for d in prior if d.reference_id==bill.pk for r in d.result.get('lines',[]) if r['index']==index),Decimal('0'))
                remaining=min(remaining,billed-bill_returned)
            else:
                billed=sum((D(r['quantity']) for d in bills for r in d.result.get('lines',[]) if r['index']==index),Decimal('0'))
                unbilled_returned=sum((D(r['quantity']) for d in prior if not d.result.get('bill') for r in d.result.get('lines',[]) if r['index']==index),Decimal('0'))
                remaining=min(remaining,original-billed-unbilled_returned)
        row={'index':index,'product':product.pk,'product_name':product.name,'unit':product.unit,'original_quantity':original,'remaining_quantity':max(remaining,Decimal('0'))}
        if sale and product.unit=='cm':
            thickness=D(line['thickness_mm']);row.update(thickness_mm=thickness,remaining_sheets=max(remaining,Decimal('0'))*10/thickness)
        result.append(row)
    return {'lines':result,'bills':[{'id':b.pk,'number':b.number} for b in bills],'bill':bill.pk if bill else None,'source':source.pk,'warehouse':source.warehouse_id}

def guidance(ctx,source,bill_id=None):
    doc_permission(ctx,source)
    options=[];details=None;operations=registry()
    def add(action,title,effect,initial,extra=()):
        canonical='sales_return' if action=='sale_return' else action
        if canonical in operations and ctx.has(operations[canonical][0]) and all(ctx.has(p) for p in extra):
            options.append({'action':action,'title':title,'effect':effect,'initial':initial})
    if source.state=='posted':
        foreign=ForeignExposure.objects.filter(invoice=source).first()
        if foreign:
            add('fx_return','برگشت کالای بل ارزی','مقدار ارز، ارزش دفتری و کالای برگشتی از بل اصلی بررسی می‌شود.',{'exposure':foreign.pk})
            if source.kind=='sale':add('fx_credit','اصلاح قیمت بل ارزی','اصلاح قیمت، برگشت فزیکی کالا نیست.',{'exposure':foreign.pk})
        elif source.kind=='sale':
            add('sale_return','برگشت کالا و اعتبار بل','اعتبار بل و بهای کالای برگشتی جدا محاسبه می‌شود؛ ورق برگشتی قطعه جدا تحت بررسی می‌گردد.',{'invoice':source.pk})
            if options:details=return_details(ctx,source)
        elif source.kind in {'purchase_receive','purchase_bill'}:
            receipt=source if source.kind=='purchase_receive' else source.reference
            if receipt and receipt.kind=='purchase_receive':
                doc_permission(ctx,receipt)
                initial={'receipt':receipt.pk}
                if source.kind=='purchase_bill':initial['bill']=source.pk
                add('purchase_return','برگشت خرید و اعتبار تأمین‌کننده','کالا از موجودی خارج می‌شود؛ اعتبار به بل مربوط یا حساب دریافت‌نشده خرید وصل می‌گردد.',initial)
                if options:details=return_details(ctx,receipt,bill_id or initial.get('bill'))
        elif source.kind in {'receipt','supplier_payment'}:
            reversed_already=source.children.filter(business=ctx.business,kind='payment_reverse',state='posted').exists()
            if not reversed_already:add('payment_reverse','برگشت پول اشتباه','سند پول اصلی حفظ و ثبت معکوس با همان حساب‌ها ساخته می‌شود؛ مانده بل دوباره باز می‌گردد.',{'payment':source.pk},('purchases.pay' if source.kind=='supplier_payment' else 'sales.collect',))
        elif source.kind=='fx_settle':
            add('fx_settlement_reverse','برگشت تسویه ارزی اشتباه','فقط تسویه مجاز با قواعد ارز و سابقه اصلی جبران می‌شود.',{'settlement':source.pk})
        if source.kind in {'quotation','sales_order','purchase_order'}:
            add('order_cancel','بستن مانده سفارش','مانده ادامه‌نیافته بسته می‌شود؛ بل، دریافت و موجودی ثبت‌شده حفظ می‌شود.',{'order':source.pk})
        if source.kind in {'sales_return','purchase_return','receipt','supplier_payment','sale'} and D(source.result.get('deposit_amount','0'))>0:
            supplier=source.result.get('deposit_side')=='supplier'
            from .finance import _available_deposit
            remaining=_available_deposit(ctx,source)
            if remaining>0:
                add('supplier_refund' if supplier else 'customer_refund','استرداد اعتبار باقی‌مانده','پول فقط از اعتبار موجود و حساب صندوق یا بانک مجاز استرداد می‌شود؛ فروش دوباره ثبت نمی‌شود.',{'deposit':source.pk,'location':source.location_id,'amount':str(remaining)})
        if source.kind=='inventory_write_down':
            add('inventory_write_down_reverse','برگشت کاهش ارزش','برگشت فقط تا مانده مجاز کاهش ارزش قبلی است و مقدار فزیکی تغییر نمی‌کند.',{'write_down':source.pk},('cost.view',))
    related=[]
    for doc in Document.objects.filter(business=ctx.business,reference=source,state='posted').order_by('-pk')[:100]:
        try:doc_permission(ctx,doc)
        except PermissionDenied:continue
        related.append({'id':doc.pk,'number':doc.number,'kind':doc.kind,'date':doc.date})
    return {'document':document_data(ctx,source,include_flow=False),'options':options,'returns':details,'related':related,'posting_performed':False}

class CorrectionGuidanceAPI(Boundary):
    def get(self,request,pk):
        ctx=self.ctx(request)
        return response(guidance(ctx,get_obj(ctx,Document,pk),request.query_params.get('bill')))
