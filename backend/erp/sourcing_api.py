"""Purchasing-only RFQ lists and transparent original supplier comparisons."""
from datetime import timedelta
from django.core.exceptions import PermissionDenied,ValidationError
from django.utils import timezone
from .api import Boundary,response,can
from .core import get_obj,get_warehouse
from .models import Location
from .sourcing_models import SourcingRequest,SourcingAward
from .sourcing import request_for


def request_row(ctx,item):
    request_for(ctx,item.id)
    award=SourcingAward.objects.filter(request=item).select_related('purchase_order','offer__supplier').first()
    return {'id':item.id,'number':item.source.number,'date':item.source.date,'warehouse':item.warehouse_id,'warehouse_name':item.warehouse.name,'desired_date':item.desired_date,'state':item.state,'lines':item.lines,'note':item.note,'offer_count':item.offers.count(),'purchase_order':award.purchase_order_id if award else None,'purchase_order_number':award.purchase_order.number if award else None,'selected_supplier':award.offer.supplier.name if award else None}


def comparison(ctx,item,as_of):
    ctx.require('cost.view');request_for(ctx,item.id)
    award=SourcingAward.objects.filter(request=item).first();rows=[]
    for offer in item.offers.select_related('supplier','source').order_by('comparison_total','lead_days','id'):
        if offer.source.date>as_of:continue
        arrival=as_of+timedelta(days=offer.lead_days)
        rows.append({'id':offer.id,'supplier':offer.supplier_id,'supplier_name':offer.supplier.name,'reference':offer.reference,'recorded_date':offer.source.date,'valid_through':offer.valid_through,'expired':offer.valid_through<as_of,'lead_days':offer.lead_days,'estimated_arrival':arrival,'meets_desired_date':arrival<=item.desired_date,'payment_terms':offer.payment_terms,'merchandise_total':offer.merchandise_total,'freight_estimate':offer.freight_estimate,'comparison_total':offer.comparison_total,'currency':offer.currency,'lines':offer.lines,'note':offer.note,'selected':bool(award and award.offer_id==offer.id)})
    return {'request':request_row(ctx,item),'as_of':as_of,'rows':rows,'basis':'Whole-request AFN supplier prices plus separately identified freight estimates. Dates and lead times are supplier statements, not promised capacity. No automatic tax/FX calculation, purchase receipt, bill or inventory cost posting.'}


class SourcingAPI(Boundary):
    def get(self,request,section):
        ctx=self.ctx(request)
        if not can(ctx,'purchases.view','purchases.post','purchases.approve'):raise PermissionDenied('Purchasing access is required.')
        if section=='comparison':
            from .sourcing import day
            item=request_for(ctx,request.query_params.get('request'))
            as_of=day(request.query_params.get('as_of') or timezone.localdate())
            if as_of<item.source.date:raise ValidationError('Comparison cannot precede the request date.')
            return response(comparison(ctx,item,as_of))
        if section!='requests':raise ValidationError('Unknown sourcing workspace.')
        try:offset=max(0,int(request.query_params.get('offset',0)));limit=min(100,max(1,int(request.query_params.get('limit',50))))
        except ValueError:raise ValidationError('Use integer pagination.')
        location=request.headers.get('X-Location-ID') or request.query_params.get('location')
        if location:location=get_obj(ctx,Location,location).id
        rows=[]
        query=SourcingRequest.objects.filter(business=ctx.business).select_related('warehouse__location','source').order_by('-id')
        if location:query=query.filter(warehouse__location_id=location)
        for item in query:
            try:rows.append(request_row(ctx,item))
            except (PermissionDenied,ValidationError):continue
        return response({'results':rows[offset:offset+limit],'count':len(rows),'next_offset':offset+limit if len(rows)>offset+limit else None,'offer_currency':'AFN','comparison_requires_cost_access':True})
