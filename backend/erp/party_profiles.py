"""Validated trading contacts and scoped duplicate advisories; no ledger writes."""
import re
import unicodedata
from django.core.exceptions import ValidationError,PermissionDenied
from django.core.validators import validate_email

def clean_contacts(value):
    if not isinstance(value,list) or len(value)>20:raise ValidationError('Enter no more than 20 structured contacts.')
    for item in value:
        if not isinstance(item,dict) or set(item)-{'name','role','phone','email'}:raise ValidationError('Select valid contact fields.')
        for key,limit in [('name',150),('role',80),('phone',50),('email',254)]:
            if not isinstance(item.get(key,''),str) or len(item.get(key,''))>limit:raise ValidationError('Contact fields must be text within their allowed lengths.')
        if not item.get('name','').strip():raise ValidationError('Each contact requires a name.')
        if item.get('email'):validate_email(item['email'])

def authorize(ctx,kind,edit=False):
    if kind not in {'customer','supplier'}:raise ValidationError('Select a customer or supplier.')
    permissions=['settings.manage',('sales.post' if kind=='customer' else 'purchases.post')]
    if not edit:permissions.extend(['sales.view','sales.collect'] if kind=='customer' else ['purchases.view','purchases.pay','finance.view','finance.post'])
    if not any(ctx.has(p) for p in permissions):raise PermissionDenied('Customer/supplier editing is restricted.' if edit else 'Customer/supplier details are restricted.')

def normalized_name(value):
    return re.sub(r'\s+',' ',unicodedata.normalize('NFKC',str(value)).translate(str.maketrans({'ك':'ک','ي':'ی','\u200c':' '}))).strip().casefold()

def snapshot(party):
    return {key:getattr(party,key) for key in ('name','phone','address','delivery_address','registration_number','group_name')}

def normalized_phone(value):
    return re.sub(r'[^0-9]','',str(value).translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩','01234567890123456789')))

def duplicates(ctx,kind,name,phone,exclude=None):
    from .models import Party
    authorize(ctx,kind)
    if len(name)>200 or len(phone)>50:raise ValidationError('Enter a valid customer/supplier search.')
    name=normalized_name(name);phone=normalized_phone(phone)
    query=Party.objects.filter(business=ctx.business,kind=kind).order_by('id')
    if exclude:
        from .core import get_obj
        own=get_obj(ctx,Party,exclude);authorize(ctx,own.kind);query=query.exclude(pk=own.pk)
    matches=[];count=0
    if name or phone:
        for party in query.iterator(chunk_size=200):
            reasons=[]
            if name and name==normalized_name(party.name):reasons.append('same_name')
            if phone and phone==normalized_phone(party.phone):reasons.append('same_phone')
            if reasons:
                count+=1
                if len(matches)<10:matches.append({'id':party.pk,'name':party.name,'phone':party.phone,'reasons':reasons})
    return {'results':matches,'count':count,'advisory_only':True,'automatic_merge':False}
