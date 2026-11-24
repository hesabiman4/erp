from datetime import date
from django.core.exceptions import ValidationError,PermissionDenied
from django.db.models import Q
from django.utils import timezone
from .api import Boundary,response
from .core import get_obj,get_product,D
from .models import Party,Product,Block,CustomerPrice
from .party_profiles import authorize,duplicates

def pricing(ctx,params):
    authorize(ctx,'customer')
    product=get_product(ctx,params.get('product'))
    if product.kind=='raw':raise PermissionDenied('Choose a saleable product for pricing.')
    party=get_obj(ctx,Party,params['party']) if params.get('party') else None
    if party and party.kind!='customer':raise ValidationError('Select a customer for the price agreement.')
    try:effective=date.fromisoformat(params.get('date') or timezone.localdate().isoformat())
    except (ValueError,TypeError):raise ValidationError('Use an ISO YYYY-MM-DD date.')
    profile=str(params.get('profile',''))
    if params.get('block'):
        block=get_obj(ctx,Block,params['block'])
        if block.product_id!=product.pk:raise ValidationError('The selected block does not match the product.')
        profile=block.profile
    if profile:
        from .growth import compatible_profile
        profile=compatible_profile(product,profile)
    agreement=None
    if party:
        agreement=CustomerPrice.objects.filter(business=ctx.business,party=party,product=product,profile=profile,effective_from__lte=effective).filter(Q(effective_to__isnull=True)|Q(effective_to__gte=effective)).order_by('-effective_from','-pk').first()
    selected=D(params['price']) if params.get('price') not in {None,''} else agreement.unit_price if agreement else product.price
    if selected<0:raise ValidationError('Unit price cannot be negative.')
    basis='catalog_match' if selected==product.price else 'agreement_match' if agreement and selected==agreement.unit_price else 'review_other'
    return {'product':product.pk,'unit':product.unit,'profile':profile,'date':effective,'catalog_price':product.price,'selected_price':selected,'basis':basis,'agreement':{'id':agreement.pk,'unit_price':agreement.unit_price,'effective_from':agreement.effective_from,'effective_to':agreement.effective_to} if agreement else None,'posting_performed':False}

class PartyToolsAPI(Boundary):
    def post(self,request,section):
        if section!='duplicates':raise ValidationError('Select a supported customer/supplier tool.')
        data=request.data
        return response(duplicates(self.ctx(request),data.get('kind','customer'),str(data.get('name','')),str(data.get('phone','')),data.get('exclude')))
    def get(self,request,section):
        ctx=self.ctx(request);params=request.query_params
        if section=='pricing':return response(pricing(ctx,params))
        kind=params.get('kind','customer');authorize(ctx,kind)
        if section=='duplicates':return response(duplicates(ctx,kind,params.get('name',''),params.get('phone',''),params.get('exclude')))
        if section=='groups':return response({'groups':list(Party.objects.filter(business=ctx.business,kind=kind).exclude(group_name='').order_by('group_name').values_list('group_name',flat=True).distinct())})
        raise ValidationError('Select a supported customer/supplier tool.')
