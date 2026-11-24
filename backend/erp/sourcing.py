"""Reviewed AFN supplier comparison and one-time purchase order conversion."""
from datetime import date,timedelta
from decimal import Decimal
from django.core.exceptions import PermissionDenied,ValidationError
from .core import D,QTY,ZERO,money,get_obj,get_product,get_warehouse,profile_for,execute
from .models import Product,Party,Document
from .sourcing_models import SourcingRequest,SupplierOffer,SourcingAward


def text(value,name,maximum,required=True):
    value=str(value or '').strip()
    if (required and not value) or len(value)>maximum:raise ValidationError(f'{name} is required and must fit within {maximum} characters.' if required else f'{name} must fit within {maximum} characters.')
    return value


def day(value):
    try:return date.fromisoformat(str(value))
    except (ValueError,TypeError):raise ValidationError('Use a valid canonical YYYY-MM-DD date.')


def request_for(ctx,identifier,open_only=False):
    if not any(ctx.has(x) for x in ('purchases.view','purchases.post','purchases.approve')):raise PermissionDenied('Purchasing access is required.')
    item=get_obj(ctx,SourcingRequest,identifier);get_warehouse(ctx,item.warehouse_id)
    get_obj(ctx,Document,item.source_id)
    for line in item.lines:get_product(ctx,line['product'])
    if open_only and item.state!='open':raise ValidationError('The sourcing request is no longer open.')
    return item


def offer_for(ctx,identifier):
    ctx.require('cost.view')
    item=get_obj(ctx,SupplierOffer,identifier);request_for(ctx,item.request_id)
    get_obj(ctx,Party,item.supplier_id)
    return item


def create_request(ctx,p,doc):
    warehouse=get_warehouse(ctx,p['warehouse'])
    if warehouse.kind=='transit':raise ValidationError('Select an actual receiving warehouse, not transit.')
    desired=day(p['desired_date'])
    if desired<doc.date:raise ValidationError('Desired receipt cannot precede the request date.')
    requested=p.get('lines',[])
    if not isinstance(requested,list) or not 1<=len(requested)<=100:raise ValidationError('Request one to 100 item lines.')
    lines=[];seen=set()
    for row in requested:
        product=get_product(ctx,row['product'])
        if not product.active or product.kind=='service':raise ValidationError('Select active physical products. Services use the existing supplier expense workflow.')
        qty=D(row['quantity'])
        if qty<=0 or qty!=qty.quantize(QTY):raise ValidationError('Quantities must be positive with at most six decimal places.')
        if product.unit=='each' and qty!=qty.to_integral_value():raise ValidationError('Piece quantities must be whole numbers.')
        profile='';length=width=None
        if product.unit=='cm':
            length=D(row.get('length_mm','0'));width=D(row.get('width_mm','0'))
            if length<=0 or width<=0 or length!=length.quantize(Decimal('.001')) or width!=width.quantize(Decimal('.001')):raise ValidationError('Sponge requires positive full-face length/width in millimeters, with at most three decimal places.')
            profile=profile_for(length,width)
        key=(product.id,profile)
        if key in seen:raise ValidationError('Combine repeated product/footprint demand into one line.')
        seen.add(key)
        lines.append({'index':len(lines),'product':product.id,'product_name':product.name,'unit':product.unit,'quantity':str(qty),'profile':profile,'length_mm':str(length) if length else None,'width_mm':str(width) if width else None})
    note=text(p.get('note',''),'Request note',2000,False)
    item=SourcingRequest.objects.create(business=ctx.business,warehouse=warehouse,desired_date=desired,lines=lines,note=note,source=doc)
    doc.warehouse=warehouse;doc.location=warehouse.location
    return {'request':item.id,'desired_date':desired,'lines':lines,'state':'open','financial_posting':False,'note':'A supplier request is not an order, stock reservation, bill or payment.'}


def record_offer(ctx,p,doc):
    ctx.require('cost.view');request=request_for(ctx,p['request'],True)
    supplier=get_obj(ctx,Party,p['supplier'])
    if supplier.kind!='supplier':raise ValidationError('Choose a supplier account.')
    currency=p.get('offer_currency','AFN')
    if currency!='AFN' or ctx.business.currency!='AFN':raise ValidationError('Supplier comparison currently supports AFN offers only. Convert and document a separately approved AFN quote; foreign offer conversion is not implemented.')
    valid=day(p['valid_through'])
    if valid<doc.date:raise ValidationError('Offer validity cannot end before its recorded date.')
    lead=D(p.get('lead_days','0'))
    if lead!=lead.to_integral_value() or lead<0 or lead>3650:raise ValidationError('Lead time must be zero to 3,650 whole calendar days.')
    freight=money(p.get('freight_estimate','0'))
    if freight<0:raise ValidationError('Freight estimate cannot be negative.')
    reference=text(p.get('reference'),'Supplier offer reference',150)
    terms=text(p.get('payment_terms'),'Payment terms',250)
    if len(p.get('lines',[]))!=len(request.lines):raise ValidationError('Quote every requested item once. Partial supplier awards are not supported by this release.')
    offered=[];total=ZERO
    for index,line in enumerate(request.lines):
        row=p['lines'][index]
        if str(row.get('index',index))!=str(index):raise ValidationError('Offer prices must use the original request item order.')
        price=D(row['unit_cost'])
        if price<0 or price!=price.quantize(QTY):raise ValidationError('Offer prices must be nonnegative with at most six decimal places.')
        value=money(D(line['quantity'])*price);total+=value
        offered.append({**line,'unit_cost':str(price),'amount':str(value)})
    if total<=0:raise ValidationError('A supplier offer must have a positive merchandise amount.')
    item=SupplierOffer.objects.create(business=ctx.business,request=request,supplier=supplier,reference=reference,valid_through=valid,lead_days=int(lead),payment_terms=terms,lines=offered,freight_estimate=freight,merchandise_total=total,comparison_total=total+freight,currency='AFN',note=text(p.get('note',''),'Offer note',2000,False),source=doc)
    doc.reference=request.source;doc.warehouse=request.warehouse;doc.location=request.warehouse.location;doc.party=supplier;doc.amount=total+freight
    return {'request':request.id,'offer':item.id,'supplier':supplier.id,'lines':offered,'merchandise_total':str(total),'freight_estimate':str(freight),'comparison_total':str(total+freight),'offer_currency':'AFN','financial_posting':False,'freight_basis':'Supplier estimate for comparison only; not an inventory capitalization or supplier payable.'}


def award_offer(ctx,p,doc):
    ctx.require('cost.view');ctx.require('purchases.post')
    offer=offer_for(ctx,p['offer']);request=request_for(ctx,offer.request_id,True)
    if offer.valid_through<doc.date:raise ValidationError('This supplier offer expired. Obtain a new dated offer before award.')
    if SourcingAward.objects.filter(request=request).exists():raise ValidationError('This request has already been awarded. Create a new request for additional demand.')
    reason=text(p.get('reason'),'Reviewed selection reason',2000)
    lines=[]
    for line in offer.lines:
        product=get_product(ctx,line['product'])
        if not product.active:raise ValidationError('A requested product is inactive.')
        lines.append({**{key:line[key] for key in ('product','quantity','unit_cost','length_mm','width_mm') if line.get(key) is not None},'sourcing_index':line['index']})
    expected=doc.date+timedelta(days=offer.lead_days)
    order=execute(ctx,'purchase_order',{'date':str(doc.date),'warehouse':request.warehouse_id,'supplier':offer.supplier_id,'expected_date':str(expected),'lines':lines,'sourcing_request':request.id,'supplier_offer':offer.id,'supplier_reference':offer.reference,'payment_terms':offer.payment_terms,'notes':reason},f'sourcing-order-{request.id}-{doc.id}')
    award=SourcingAward.objects.create(business=ctx.business,request=request,offer=offer,purchase_order=order,reason=reason,source=doc)
    request.state='awarded';request.closed_by=doc;request.save(update_fields=['state','closed_by'])
    doc.reference=offer.source;doc.warehouse=request.warehouse;doc.location=request.warehouse.location;doc.party=offer.supplier;doc.amount=offer.comparison_total
    return {'request':request.id,'offer':offer.id,'award':award.id,'purchase_order':order.id,'purchase_order_number':order.number,'line_mapping':[{'request_index':line['index'],'order_index':index,'quantity':line['quantity']} for index,line in enumerate(offer.lines)],'comparison_total':str(offer.comparison_total),'freight_estimate':str(offer.freight_estimate),'expected_date':expected,'reason':reason,'financial_posting':False,'note':'One purchase order created. No goods received, bill, payment or freight capitalization is posted by this award.'}


def close_request(ctx,p,doc):
    request=request_for(ctx,p['request'],True);reason=text(p.get('reason'),'Closure reason',2000)
    request.state='cancelled';request.closed_by=doc;request.save(update_fields=['state','closed_by'])
    doc.reference=request.source;doc.warehouse=request.warehouse;doc.location=request.warehouse.location
    return {'request':request.id,'state':'cancelled','reason':reason,'financial_posting':False,'offers_preserved':True}


def document_guard(ctx,doc):
    if doc.kind=='purchase_order' and doc.data.get('sourcing_request'):
        # A generated PO keeps ordinary commercial pricing permissions, but
        # cannot bypass its original request's raw-item/whole-line scope.
        request_for(ctx,doc.data['sourcing_request'])
    if doc.kind not in OPERATIONS:return
    if doc.kind in {'rfq_offer','rfq_award'}:ctx.require('cost.view')
    ident=doc.result.get('request') or doc.data.get('request')
    if ident:request_for(ctx,ident)
    elif doc.kind=='rfq_award' and doc.data.get('offer'):offer_for(ctx,doc.data['offer'])
    else:
        if doc.data.get('warehouse'):get_warehouse(ctx,doc.data['warehouse'])
        for row in doc.data.get('lines',[]):
            if row.get('product'):get_product(ctx,row['product'])


OPERATIONS={'rfq_create':('purchases.post',create_request),'rfq_offer':('purchases.post',record_offer),'rfq_award':('purchases.approve',award_offer),'rfq_close':('purchases.post',close_request)}
