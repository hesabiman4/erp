"""Customer proposals are isolated from staff posting authority."""
import hashlib,json,re
from django.core.exceptions import ValidationError,PermissionDenied
from django.db import transaction
from django.utils import timezone
from .core import D,QTY,execute,get_obj,get_product,json_value,profile_for
from .models import (Business,PortalGrant,PortalListing,PortalSubmission,PortalReview,
                     Document,AuditEvent,Product)


def listing_set(ctx,p,doc):
    ctx.require('users.manage');ctx.require('sales.view')
    from .portal import PortalAccessAPI
    if not ctx.membership.all_locations:raise PermissionDenied('Full location scope is required to publish customer items.')
    grant=get_obj(ctx,PortalGrant,p['grant']);product=get_product(ctx,p['product'])
    if not grant.active or product.kind in {'raw','service'} or not product.active:raise ValidationError('Publish an active saleable stock product to an active customer account.')
    profile=str(p.get('profile','')).strip()
    if product.unit=='cm':
        parts=profile.split('x')
        if len(parts)!=2 or any(D(x)<=0 for x in parts):raise ValidationError('Sponge requires its agreed full-face length x width in millimeters.')
        profile=profile_for(*parts)
    elif profile:raise ValidationError('Only sponge items have a sheet footprint.')
    active=p.get('active',True)
    if not isinstance(active,bool):raise ValidationError('active must be true or false.')
    listing,created=PortalListing.objects.get_or_create(business=ctx.business,grant=grant,product=product,profile=profile,defaults={'active':active,'source':doc})
    if not created:listing.active=active;listing.save(update_fields=['active'])
    doc.party=grant.party
    return {'listing':listing.id,'active':active,'product':product.id,'financial_posting':False}


def submission_row(item,staff=False):
    review=PortalReview.objects.filter(submission=item).select_related('commercial_document').first()
    row={'id':item.id,'kind':item.kind,'created_at':item.created_at,'payload':item.payload,'invoice':item.invoice_id,
         'state':review.outcome if review else 'pending','review_note':review.reason if review else '',
         'commercial_number':review.commercial_document.number if review and review.commercial_document_id else None}
    if staff:row.update({'customer':item.grant.party.name,'grant':item.grant_id,'commercial_document':review.commercial_document_id if review else None})
    return row


def staff_submission(ctx,ident):
    ctx.require('sales.view')
    if not ctx.membership.all_locations:raise PermissionDenied('Customer requests await assignment to a warehouse; complete location scope is required to review them.')
    item=get_obj(ctx,PortalSubmission,ident)
    for line in item.payload.get('lines',[]):get_product(ctx,line['product'])
    if item.invoice_id:
        from .api import doc_permission
        doc_permission(ctx,item.invoice)
    return item


@transaction.atomic
def submit_request(request,grant):
    Business.objects.select_for_update().get(pk=grant.business_id)
    grant=PortalGrant.objects.select_for_update().filter(pk=grant.id,active=True,user=request.user).first()
    if not grant:raise PermissionDenied('Customer portal access was revoked before submission.')
    data=dict(request.data);kind=data.get('kind','quotation')
    if kind not in {'quotation','order','delivery'}:raise ValidationError('Select quotation, order request or delivery acknowledgement.')
    key=str(request.headers.get('Idempotency-Key',''))
    if not key or len(key)>100:raise ValidationError('A unique Idempotency-Key is required.')
    digest=hashlib.sha256(json.dumps(data,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
    old=PortalSubmission.objects.filter(business=grant.business,grant=grant,key=key).first()
    if old:
        if old.digest!=digest:raise ValidationError('This request key was used with different content.')
        return old,False
    note=str(data.get('note','')).strip()
    if len(note)>2000:raise ValidationError('Keep the note within 2,000 characters.')
    invoice=None
    if kind=='delivery':
        invoice=Document.objects.filter(business=grant.business,party=grant.party,pk=data.get('invoice'),kind='sale',state='posted').first()
        if not invoice:raise PermissionDenied('Choose a delivered invoice from your own customer account.')
        if PortalSubmission.objects.filter(grant=grant,invoice=invoice,kind='delivery').exists():raise ValidationError('An acknowledgement already exists for this invoice.')
        recipient=str(data.get('recipient','')).strip()
        if not recipient or len(recipient)>200 or data.get('accepted') is not True:raise ValidationError('Confirm receipt and enter the recipient name.')
        payload={'recipient':recipient,'note':note,'accepted':True,'acknowledged_at':timezone.now().isoformat()}
    else:
        raw=data.get('lines')
        if not isinstance(raw,list) or not 1<=len(raw)<=50:raise ValidationError('Request between one and 50 product lines.')
        lines=[]
        for row in raw:
            if not isinstance(row,dict):raise ValidationError('Each product line must be an object.')
            listing=PortalListing.objects.filter(pk=row.get('listing'),business=grant.business,grant=grant,active=True,product__active=True).select_related('product').first()
            if not listing:raise PermissionDenied('An item is not published for your customer account.')
            product=listing.product
            if product.unit=='cm':
                thickness=D(row.get('thickness_mm','0'));count=D(row.get('sheet_count','1'))
                if thickness<=0 or thickness>100000 or thickness!=thickness.quantize(D('.001')) or count<=0 or count>10000 or count!=count.to_integral_value():raise ValidationError('Enter a positive measured thickness and whole sheet count.')
                quantity=thickness*count/10
                measured={'thickness_mm':str(thickness),'sheet_count':str(count)}
            else:
                quantity=D(row.get('quantity','0'));measured={}
                if product.unit=='each' and quantity!=quantity.to_integral_value():raise ValidationError('Piece counts must be whole.')
            if quantity<=0 or quantity>10000000 or quantity!=quantity.quantize(QTY):raise ValidationError('Enter a valid positive quantity with at most six decimal places.')
            lines.append({'listing':listing.id,'product':product.id,'product_name':product.name,'profile':listing.profile,'unit':product.unit,'quantity':str(quantity),**measured})
        payload={'lines':lines,'note':note}
    item=PortalSubmission.objects.create(business=grant.business,grant=grant,kind=kind,payload=payload,invoice=invoice,key=key,digest=digest,submitted_by=request.user)
    AuditEvent.objects.create(business=grant.business,user=request.user,action='portal.submit',target=str(item.id),details={'kind':kind})
    return item,True


def review_request(ctx,p,doc):
    item=staff_submission(ctx,p['submission']);outcome=p['outcome']
    if PortalReview.objects.filter(submission=item).exists():raise ValidationError('This request was already reviewed.')
    note=str(p.get('reason','')).strip()
    if not note or len(note)>2000:raise ValidationError('Record the review reason (maximum 2,000 characters).')
    if outcome not in {'accepted','rejected'}:raise ValidationError('Accept or reject the request.')
    commercial=None
    if outcome=='accepted' and item.kind!='delivery':
        if not item.grant.active:raise ValidationError('Customer access was revoked; reject the old request or obtain a new authorized request.')
        from .core import get_warehouse
        warehouse=get_warehouse(ctx,p['warehouse']);quoted=p.get('lines',[])
        if len(quoted)!=len(item.payload['lines']):raise ValidationError('Review a price for each requested line.')
        lines=[]
        for index,line in enumerate(item.payload['lines']):
            product=get_product(ctx,line['product'])
            if not product.active:raise ValidationError('A requested item has been deactivated.')
            row={'product':product.id,'quantity':line['quantity'],'unit_price':str(D(quoted[index]['unit_price']))}
            if line['profile']:
                row['length_mm'],row['width_mm']=line['profile'].split('x')
                row.update({k:line[k] for k in ('thickness_mm','sheet_count')})
            lines.append(row)
        action='quotation' if item.kind=='quotation' else 'sales_order'
        commercial=execute(ctx,action,{'date':str(doc.date),'warehouse':warehouse.id,'party':item.grant.party_id,'lines':lines,'notes':note},f'portal-convert-{item.id}-{doc.id}')
        doc.location=warehouse.location;doc.warehouse=warehouse
    if outcome=='accepted' and item.kind=='delivery':
        # Evidence acknowledgement is not a warehouse receipt or another sale.
        if Document.objects.filter(business=ctx.business,kind='delivery_confirm',reference=item.invoice,state='posted').exists():raise ValidationError('The invoice already has a confirmed recipient; retain this portal request as evidence or reject it.')
        commercial=execute(ctx,'delivery_confirm',{'date':str(doc.date),'invoice':item.invoice_id,'recipient':item.payload['recipient'],'note':note},f'portal-delivery-{item.id}-{doc.id}')
        doc.location=item.invoice.location
    review=PortalReview.objects.create(business=ctx.business,submission=item,outcome=outcome,reason=note,commercial_document=commercial,source=doc)
    doc.party=item.grant.party;doc.reference=commercial or item.invoice
    return {'submission':item.id,'review':review.id,'outcome':outcome,'commercial_document':commercial.id if commercial else None,'financial_posting':False}


OPERATIONS={'portal_listing':('sales.post',listing_set),'portal_review':('sales.post',review_request)}
