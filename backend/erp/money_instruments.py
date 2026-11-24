"""Immutable monetary dimensions; legacy entries are read, never rewritten."""
import re
from django.core.exceptions import PermissionDenied,ValidationError
from django.db.models import Q,Sum
from .core import ZERO,money,get_obj
from .models import MoneyInstrument,MoneyInstrumentEntry,Entry,Location,Product,Document,Account


def whole_pool(ctx):
    ctx.require('finance.view');ctx.require('payroll.view')
    if not ctx.has('documents.all_lines') and Product.objects.filter(business=ctx.business).exclude(line__in=ctx.membership.product_lines).exists():
        raise PermissionDenied('Complete financial product scope is required to view instrument balances.')


def instrument_for(ctx,ident,kind=None,location=None):
    instrument=get_obj(ctx,MoneyInstrument,ident)
    if not instrument.active or (kind and instrument.kind!=kind) or (location and instrument.location_id!=getattr(location,'pk',location)):
        raise ValidationError('Choose an active instrument of the selected cash/bank type and location.')
    return instrument


def legacy_for(ctx,location,kind,create=False):
    location=get_obj(ctx,Location,getattr(location,'pk',location))
    item=MoneyInstrument.objects.filter(business=ctx.business,location=location,kind=kind,legacy=True).first()
    if not item and create:
        item=MoneyInstrument.objects.create(business=ctx.business,location=location,kind=kind,legacy=True,
            code=f'LEGACY-{kind}-{location.pk}',name=f'{kind} · {location.name}')
    return item


def entries_for(instrument,posted=True):
    query=Entry.objects.filter(document__business=instrument.business,account__code=instrument.kind,location_id=instrument.location_id)
    if posted:query=query.filter(document__state='posted')
    selection=Q(money_link__instrument=instrument)
    if instrument.legacy:selection|=Q(money_link__isnull=True)
    return query.filter(selection)


def instrument_balance(instrument,through=None,posted=True,exclude_ids=None):
    query=entries_for(instrument,posted)
    if exclude_ids:query=query.exclude(pk__in=exclude_ids)
    if through:query=query.filter(document__date__lte=through)
    result=query.aggregate(dr=Sum('debit'),cr=Sum('credit'))
    return money((result['dr'] or ZERO)-(result['cr'] or ZERO))


def resolve(ctx,doc,kind,location,*,explicit=None,debit=None,credit=None):
    """Resolve one original line, including parent selections for atomic sales."""
    loc=getattr(location,'pk',location)
    if explicit:return instrument_for(ctx,explicit,kind,loc)
    payloads=[doc.data,*reversed(getattr(ctx,'money_payloads',[]))]
    for p in payloads:
        if not isinstance(p,dict):continue
        if doc.kind=='cash_transfer' or p.get('from_account') or p.get('to_account'):
            side='from' if credit else 'to'
            if p.get(f'{side}_instrument'):
                return instrument_for(ctx,p[f'{side}_instrument'],kind,loc)
        value=p.get('cash_instrument' if kind=='CASH' else 'bank_instrument')
        if value:return instrument_for(ctx,value,kind,loc)
    query=MoneyInstrument.objects.filter(business=ctx.business,active=True,kind=kind)
    if loc:query=query.filter(location_id=loc)
    else:
        if query.exists():raise ValidationError('Select an explicit location for instrument cash/bank posting.')
        return None
    found=list(query[:2])
    if len(found)>1:raise ValidationError('More than one cash/bank instrument exists here. Select the actual instrument explicitly.')
    return found[0] if found else None


def bind_entries(ctx,doc,pending,original_lines):
    plans=[]
    for entry,line in zip(pending,original_lines):
        if entry.account.code not in {'CASH','BANK'}:continue
        item=resolve(ctx,doc,entry.account.code,entry.location_id,explicit=line.get('instrument'),debit=entry.debit,credit=entry.credit)
        if item:plans.append((entry,item))
    # The business-wide original posting lock serializes all pools. Include
    # still-draft ancestor postings; nested atomic operations cannot overspend.
    changes={}
    for entry,item in plans:changes[item.pk]=changes.get(item.pk,ZERO)+entry.debit-entry.credit
    for ident,change in changes.items():
        item=next(i for _,i in plans if i.pk==ident)
        if not item.legacy and (doc.date<item.source.date or entries_for(item,False).exclude(pk__in=[e.pk for e in pending]).filter(document__date__gt=doc.date).exists()):
            raise ValidationError('Instrument activity cannot precede registration or a later instrument movement.')
        if change<0 and instrument_balance(item,posted=False,exclude_ids=[e.pk for e in pending])+change<0:
            raise ValidationError('This payout exceeds the recorded balance of the selected instrument.')
    for entry,item in plans:MoneyInstrumentEntry.objects.create(business=ctx.business,instrument=item,entry=entry)


def register(ctx,p,doc):
    ctx.require('settings.manage');ctx.require('finance.post');whole_pool(ctx)
    if ctx.business.currency!='AFN':raise ValidationError('These instruments use the AFN CASH/BANK controls; use foreign wallets for foreign currency.')
    location=get_obj(ctx,Location,p['location']);kind=str(p.get('kind','')).upper()
    if kind not in {'CASH','BANK'} or not Account.objects.filter(business=ctx.business,code=kind).exists():raise ValidationError('Choose a configured CASH or BANK control account.')
    code=str(p.get('code','')).strip();name=str(p.get('name','')).strip()
    institution=re.sub(r'\s+',' ',str(p.get('institution','')).strip());reference=re.sub(r'\s+',' ',str(p.get('account_reference','')).strip())
    if not code or len(code)>40 or not name or len(name)>150 or len(institution)>150 or len(reference)>100:raise ValidationError('Enter an instrument code, name and bank identity within their field limits.')
    if kind=='BANK' and (not institution or not reference):raise ValidationError('Provide the actual bank institution and account reference.')
    if kind=='CASH' and (institution or reference):raise ValidationError('A physical cash drawer cannot carry a bank account identity.')
    # Establish the original pool before adding a zero-opening separate pool.
    # Historical journals stay untouched; their original null links remain the
    # legacy instrument's auditable ledger bridge.
    legacy_for(ctx,location,kind,True)
    if kind=='BANK' and MoneyInstrument.objects.filter(business=ctx.business,kind=kind,location=location,institution__iexact=institution,account_reference__iexact=reference).exists():raise ValidationError('This bank account is already registered at this location.')
    item=MoneyInstrument.objects.create(business=ctx.business,location=location,kind=kind,code=code,name=name,
        institution=institution,account_reference=reference,source=doc)
    doc.location=location
    return {'instrument':item.pk,'kind':kind,'location':location.pk,'opening_balance':'0.00','financial_posting':False,
        'funding':'Use an ordinary cash transfer from the actual source instrument. Registration does not create funds.'}


def enrich_registry(operations):
    result={}
    for action,(permission,handler) in operations.items():
        def wrapped(ctx,p,doc,original=handler):
            old=getattr(ctx,'money_payloads',[]);ctx.money_payloads=[*old,p]
            try:return original(ctx,p,doc)
            finally:ctx.money_payloads=old
        result[action]=(permission,wrapped)
    return result


OPERATIONS={'money_instrument':('finance.post',register)}
