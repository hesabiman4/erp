"""Versioned tax research/admin and exact previews; no financial posting here.

TaxSchedule is deliberately separate from legacy invoice percentage TaxRule.
Confirming a schedule does not activate statutory document/payroll integration.
"""
import hashlib
import json
import re
from datetime import date
from decimal import Decimal,ROUND_HALF_UP
from urllib.parse import urlsplit
from django.core.exceptions import PermissionDenied,ValidationError
from django.core.validators import URLValidator
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from .core import D,Context,get_obj,json_value
from .models import Business,AuditEvent
from .tax_models import TaxSchedule,TaxScheduleChange

BASIS = {'salary_wht':{'monthly_payroll'},'brt':{'gross_receipts','gross_turnover'},'cit':{'net_taxable_profit'},
         'rent_wht':{'payment'},'contractor_wht':{'payment'},'vat':{'taxable_supply'},
         'import_income_advance':{'import_value'},'import_brt_advance':{'import_value'}}
CONTENT = ('name_fa','name_en','name_ps','tax_type','sector','schedule_version','effective_from','effective_to',
           'currency_code','basis','rate','brackets','rounding_places','source_url','source_retrieved_on','notes','supersedes')


def fail():
    raise ValidationError('Review the tax schedule fields, dates, source and exact decimal brackets.')


def day(value):
    if not isinstance(value,str):fail()
    try:
        parsed=date.fromisoformat(value)
        if parsed.isoformat()!=value:fail()
        return parsed
    except (ValueError,TypeError):fail()


def bounded(value,places=6):
    value=D(value)
    if value<0 or value!=value.quantize(Decimal(1).scaleb(-places)):fail()
    return value


def validate_content(data):
    if not isinstance(data,dict) or set(data)-set(CONTENT):fail()
    clean={}
    for key,maximum,required in [('name_fa',180,True),('name_en',180,False),('name_ps',180,False),('sector',80,True),
                                  ('schedule_version',64,True),('source_url',1000,True),('notes',4000,False)]:
        value=data.get(key,'general' if key=='sector' else '')
        if not isinstance(value,str) or len(value)>maximum or (required and not value.strip()):fail()
        clean[key]=value.strip()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}',clean['schedule_version']):fail()
    if not isinstance(data.get('tax_type'),str) or not isinstance(data.get('basis'),str):fail()
    if data['tax_type'] not in BASIS or data['basis'] not in BASIS[data['tax_type']]:fail()
    clean.update(tax_type=data['tax_type'],basis=data['basis'])
    clean['effective_from']=day(data.get('effective_from'))
    clean['effective_to']=day(data['effective_to']) if data.get('effective_to') else None
    if clean['effective_to'] and clean['effective_to']<clean['effective_from']:fail()
    clean['source_retrieved_on']=day(data.get('source_retrieved_on'))
    if clean['source_retrieved_on']>timezone.localdate():fail()
    try:URLValidator(schemes=['https'])(clean['source_url'])
    except ValidationError:fail()
    url=urlsplit(clean['source_url'])
    if url.username or url.password or url.fragment:fail()
    clean['currency_code']=data.get('currency_code','AFN')
    if not isinstance(clean['currency_code'],str) or clean['currency_code'] not in {'AFN','USD'}:fail()
    places=data.get('rounding_places',2)
    if isinstance(places,bool) or not isinstance(places,int) or not 0<=places<=6:fail()
    clean['rounding_places']=places
    rows=data.get('brackets',[])
    if not isinstance(rows,list) or len(rows)>20:fail()
    rate=data.get('rate')
    if (rate is not None and rate!='')==bool(rows):fail()
    if rows and data['tax_type']!='salary_wht':fail()
    clean['rate']=bounded(rate) if rate is not None and rate!='' else None
    if clean['rate'] is not None and clean['rate']>100:fail()
    clean['brackets']=[];previous=None
    for row in rows:
        if not isinstance(row,dict) or set(row)!={'lower','rate','fixed'}:fail()
        low,pct,fixed=bounded(row['lower']),bounded(row['rate']),bounded(row['fixed'])
        if pct>100 or (previous is None and (low!=0 or fixed!=0)):fail()
        if previous and (low<=previous[0] or fixed!=previous[2]+(low-previous[0])*previous[1]/100):fail()
        clean['brackets'].append({'lower':str(low),'rate':str(pct),'fixed':str(fixed)})
        previous=low,pct,fixed
    if data['tax_type']=='salary_wht' and not rows:fail()
    parent=data.get('supersedes')
    if parent is not None and (isinstance(parent,bool) or not isinstance(parent,int) or parent<1):fail()
    clean['supersedes_id']=parent
    return clean


def snapshot(rule):
    result={key:getattr(rule,key) for key in CONTENT if key!='supersedes'}
    result.update(id=rule.pk,supersedes=rule.supersedes_id,requires_confirmation=rule.requires_confirmation,
                  verified_at=rule.verified_at.isoformat() if rule.verified_at else None,
                  confirmation_revision=rule.confirmation_revision,created_at=rule.created_at.isoformat())
    return json_value(result)


def read_permission(ctx):
    if not any(ctx.has(p) for p in ('accounting.view','accounting.tax_view','accounting.tax_manage','accounting.tax_confirm')):
        raise PermissionDenied('Tax schedule access requires accounting permission.')


def full_scope(ctx):
    if not ctx.membership.all_locations or not {'sponge','adhesive','shared'}.issubset(ctx.membership.product_lines):
        raise PermissionDenied('Tax configuration requires full business scope.')


def schedule_for(ctx,identifier):
    try:return get_obj(ctx,TaxSchedule,identifier)
    except ValidationError:
        raise ValidationError('Select a tax revision belonging to this business.')


def change_permission(ctx,operation):
    if operation=='create':ctx.require('accounting.tax_manage')
    elif operation in {'confirm','revoke'}:ctx.require('accounting.tax_confirm')
    else:fail()
    full_scope(ctx)


@transaction.atomic
def change(ctx,operation,data,key,identifier=None):
    change_permission(ctx,operation)
    if not isinstance(data,dict) or not isinstance(key,str) or not re.fullmatch(r'[A-Za-z0-9._:-]{8,128}',key):fail()
    Business.objects.select_for_update().get(pk=ctx.business.pk)
    # Role changes use this same business lock; don't rely on a stale membership.
    ctx=Context(ctx.user,ctx.business)
    change_permission(ctx,operation)
    digest=hashlib.sha256(json.dumps(json_value({'operation':operation,'data':data,'id':identifier,'actor':ctx.user.pk}),sort_keys=True,separators=(',',':')).encode()).hexdigest()
    previous=TaxScheduleChange.objects.filter(business=ctx.business,request_key=key).first()
    if previous:
        if previous.request_hash!=digest:raise ValidationError('This tax request key was used for different content.')
        return previous.after
    reason=data.get('reason','')
    if not isinstance(reason,str) or not 8<=len(reason.strip())<=4000:
        raise ValidationError('Explain the tax source review and applicability in at least eight characters.')
    before={}
    if operation=='create':
        if set(data)-{'reason','rule'}:fail()
        clean=validate_content(data.get('rule'))
        if clean['supersedes_id']:
            old=schedule_for(ctx,clean['supersedes_id'])
            if (old.tax_type,old.sector,old.currency_code)!=(clean['tax_type'],clean['sector'],clean['currency_code']):fail()
        if TaxSchedule.objects.filter(business=ctx.business,tax_type=clean['tax_type'],sector=clean['sector'],schedule_version=clean['schedule_version']).exists():
            raise ValidationError('Use a new tax schedule version; existing revisions are retained.')
        rule=TaxSchedule(business=ctx.business,created_by=ctx.user,**clean);rule.full_clean();rule.save()
        after=snapshot(rule)
    else:
        if set(data)-{'reason','expected_revision'}:fail()
        rule=schedule_for(ctx,identifier);before=snapshot(rule)
        expected=data.get('expected_revision')
        if isinstance(expected,bool) or not isinstance(expected,int) or expected!=rule.confirmation_revision:
            raise ValidationError('This tax confirmation changed. Reload its history before deciding.')
        required=operation=='revoke'
        if rule.requires_confirmation==required:raise ValidationError('This tax schedule already has that confirmation state.')
        rule.requires_confirmation=required;rule.verified_at=None if required else timezone.now()
        rule.confirmation_revision+=1
        after=snapshot(rule)
    event=TaxScheduleChange.objects.create(business=ctx.business,schedule=rule,operation=operation,actor=ctx.user,
        reason=reason.strip(),before=before,after=after,request_key=key,request_hash=digest)
    if operation!='create':
        TaxSchedule.objects.filter(pk=rule.pk,business=ctx.business).update(requires_confirmation=rule.requires_confirmation,
            verified_at=rule.verified_at,confirmation_revision=rule.confirmation_revision)
    AuditEvent.objects.create(business=ctx.business,user=ctx.user,action='tax.schedule.'+operation,target=str(rule.pk),
                              details={'change':event.pk,'reason':reason.strip(),'before':before,'after':after,'financial_posting':False})
    return after


def calculate(rule,amount,*,require_confirmed=True):
    if require_confirmed and rule.requires_confirmation:raise ValidationError('Confirm this tax schedule before using it for calculation.')
    value=bounded(amount)
    if rule.brackets:
        row=next(row for row in reversed(rule.brackets) if value>=D(row['lower']))
        raw=D(row['fixed'])+(value-D(row['lower']))*D(row['rate'])/100
    else:
        row=None;raw=value*rule.rate/100
    result=raw.quantize(Decimal(1).scaleb(-rule.rounding_places),rounding=ROUND_HALF_UP)
    return {'base_amount':str(value),'tax_amount':str(result),'unrounded_tax':str(raw),'currency_code':rule.currency_code,
            'rule':snapshot(rule),'bracket':row,'rounding':'ROUND_HALF_UP','rounding_places':rule.rounding_places,
            'requires_confirmation':rule.requires_confirmation,'financial_posting':False}


def select_schedule(ctx,tax_type,sector,on_date,*,currency_code='AFN',override=None,reason=''):
    """Dates come from a document's explicit policy, never the UI calendar toggle."""
    when=day(on_date)
    read_permission(ctx)
    if not isinstance(tax_type,str) or tax_type not in BASIS:fail()
    if not isinstance(sector,str) or not isinstance(currency_code,str) or currency_code not in {'AFN','USD'}:fail()
    eligible=TaxSchedule.objects.filter(business=ctx.business,tax_type=tax_type,sector=sector,currency_code=currency_code,
                                        requires_confirmation=False,effective_from__lte=when).filter(Q(effective_to__isnull=True)|Q(effective_to__gte=when))
    if override:
        ctx.require('accounting.tax_override')
        if not isinstance(reason,str) or len(reason.strip())<8:raise ValidationError('Explain the tax source review and applicability in at least eight characters.')
        rule=schedule_for(ctx,override)
        if rule.requires_confirmation or (rule.tax_type,rule.sector,rule.currency_code)!=(tax_type,sector,currency_code):fail()
        return rule
    choices=list(eligible.order_by('-effective_from','-pk')[:2])
    if not choices:raise ValidationError('No confirmed tax schedule applies to this date and sector.')
    if len(choices)>1:
        raise ValidationError('Tax schedules overlap for this date; review the version explicitly.')
    return choices[0]
