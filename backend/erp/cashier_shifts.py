"""Accountable custody and denomination evidence over the original CASH ledger.

Each drawer maps to a selected physical CASH instrument at its location. No hidden per-user cash balances are
invented. Managed locations are opt-in; old locations keep existing behavior.
"""
from decimal import Decimal
from django.core.exceptions import PermissionDenied,ValidationError
from django.db.models import Sum,Q
from .core import D,ZERO,money,get_obj,balance,journal,Context
from .money_instruments import legacy_for,instrument_for,instrument_balance,entries_for
from .models import (CashDrawer,CashShift,CashShiftEntry,CashShiftCount,CashHandover,
                     Document,Entry,Membership,Location,Product,MoneyInstrument)


def custody_scope(ctx,location):
    get_obj(ctx,Location,location)
    if not ctx.has('documents.all_lines') and Product.objects.filter(business=ctx.business).exclude(line__in=ctx.membership.product_lines).exists():
        raise PermissionDenied('Cash custody spans the complete location cash pool and requires every business product line.')


def drawer_for(ctx,ident):
    drawer=get_obj(ctx,CashDrawer,ident);custody_scope(ctx,drawer.location_id)
    return drawer


def shift_for(ctx,ident,manager=False):
    shift=get_obj(ctx,CashShift,ident);drawer_for(ctx,shift.drawer_id)
    if manager:ctx.require('cash_shifts.review')
    elif shift.cashier_id!=ctx.membership.pk and not (ctx.has('cash_shifts.manage') or ctx.has('cash_shifts.review')):
        raise PermissionDenied('This cash shift belongs to another cashier.')
    return shift


def denominations(value):
    if not isinstance(value,list) or len(value)>30:raise ValidationError('Enter no more than 30 denomination rows, including an empty list for zero cash.')
    rows=[];seen=set();total=ZERO
    for row in value:
        if not isinstance(row,dict):raise ValidationError('Each denomination needs value and count.')
        unit=D(row.get('value'));count=D(row.get('count'))
        if unit<=0 or unit!=money(unit) or unit>100000 or unit in seen:raise ValidationError('Each denomination must be a unique positive value with currency precision.')
        if count<0 or count!=count.to_integral_value() or count>100000000:raise ValidationError('Denomination counts must be nonnegative whole numbers.')
        seen.add(unit);amount=money(unit*count);total+=amount
        rows.append({'value':str(unit),'count':str(count),'amount':str(amount)})
    return rows,money(total)


def drawer_instrument(drawer):
    if drawer.instrument_id:return drawer.instrument
    from .models import MoneyInstrument
    return MoneyInstrument.objects.filter(business_id=drawer.business_id,location_id=drawer.location_id,kind='CASH',legacy=True).first()


def drawer_balance(ctx,drawer):
    item=drawer_instrument(drawer)
    return instrument_balance(item) if item else money(balance(ctx,'CASH',location=drawer.location_id))


def cash_lines(drawer):
    item=drawer_instrument(drawer)
    if item:return entries_for(item)
    return Entry.objects.filter(document__business=drawer.business,document__state='posted',account__code='CASH',location_id=drawer.location_id)


def ensure_date(drawer,date):
    if date<drawer.source.date or cash_lines(drawer).filter(document__date__gt=date).exists():
        raise ValidationError('Cash custody cannot be backdated before registration or later cash events.')


def expected(shift):
    values=shift.cash_entries.filter(entry__document__state='posted').aggregate(dr=Sum('entry__debit'),cr=Sum('entry__credit'))
    return money(shift.opening_amount+(values['dr'] or ZERO)-(values['cr'] or ZERO))


def current_receiver(handover):
    amendment=Document.objects.filter(business=handover.business,kind='cash_handover_redirect',state='posted',reference=handover.source).order_by('-id').first()
    return (amendment.result['receiver'] if amendment else handover.receiver_id),amendment


def create_drawer(ctx,p,doc):
    location=get_obj(ctx,Location,p['location']);custody_scope(ctx,location.id)
    if ctx.business.currency!='AFN':raise ValidationError('This first physical-shift workflow supports the AFN CASH account only.')
    if Entry.objects.filter(document__business=ctx.business,document__state='posted',account__code='CASH',location=location,document__date__gt=doc.date).exists():raise ValidationError('Registration cannot precede later recorded cash activity.')
    name=str(p.get('name','')).strip();code=str(p.get('code','')).strip()
    if not name or len(name)>150 or not code or len(code)>40:raise ValidationError('Enter a drawer code and name within their supported lengths.')
    instrument=instrument_for(ctx,p['cash_instrument'],'CASH',location) if p.get('cash_instrument') else legacy_for(ctx,location,'CASH',True)
    if not p.get('cash_instrument') and MoneyInstrument.objects.filter(business=ctx.business,location=location,kind='CASH').count()>1:raise ValidationError('Choose the actual cash instrument for this drawer.')
    if p.get('confirm_location_pool') is not True:raise ValidationError('Confirm that this drawer represents all cash in its selected physical instrument.')
    if CashDrawer.objects.filter(business=ctx.business,location=location).filter(Q(instrument=instrument)|(Q(instrument__isnull=True) if instrument.legacy else Q(pk__in=[]))).exists():raise ValidationError('This cash instrument already has a registered drawer.')
    drawer=CashDrawer.objects.create(business=ctx.business,location=location,instrument=instrument,code=code,name=name,source=doc)
    doc.location=location
    return {'drawer':drawer.id,'location':location.id,'cash_account':'CASH','instrument':instrument.id,'physical_scope':'Selected physical AFN cash instrument','financial_posting':False,'managed':False,'activation':'First accepted opening count activates custody controls.'}


def open_shift(ctx,p,doc):
    drawer=drawer_for(ctx,p['drawer']);ensure_date(drawer,doc.date)
    if CashShift.objects.filter(drawer=drawer,state__in=['open','counted']).exists():raise ValidationError('This drawer already has an active or awaiting-review shift.')
    rows,counted=denominations(p.get('denominations',[]));book=drawer_balance(ctx,drawer)
    if counted!=book or book<0:raise ValidationError('Opening counted cash must equal the nonnegative balance of the selected cash instrument. Resolve the original cash records before accepting custody; opening a shift does not invent funds.')
    previous=drawer.shifts.order_by('-id').first();handover=None
    if previous:
        handover=CashHandover.objects.filter(business=ctx.business,shift=previous,accepted_by__isnull=True).first()
        if not handover or current_receiver(handover)[0]!=ctx.membership.pk:raise PermissionDenied('The prior reviewed shift must hand over to this cashier before a new shift can open.')
        amendment=current_receiver(handover)[1]
        if amendment and doc.date<amendment.date:raise ValidationError('Acceptance cannot precede the latest handover assignment.')
        if handover.amount!=counted or doc.date<handover.source.date:raise ValidationError('Recount the handed-over cash and verify its exact amount/date.')
    shift=CashShift.objects.create(business=ctx.business,drawer=drawer,cashier=ctx.membership,opening_amount=counted,opening_denominations=rows,source=doc)
    if drawer.activated_by_id is None:drawer.activated_by=doc;drawer.save(update_fields=['activated_by'])
    if handover:handover.accepted_by=doc;handover.save(update_fields=['accepted_by'])
    doc.location_id=drawer.location_id;doc.reference=handover.source if handover else drawer.source
    return {'shift':shift.id,'drawer':drawer.id,'opening_amount':str(counted),'denominations':rows,'handover':handover.id if handover else None,'financial_posting':False}


def bind_entries(ctx,doc,entries):
    """Called only by core.journal inside its atomic posting transaction."""
    if not any(entry.account.code=='CASH' for entry in entries):return
    drawers={(drawer_instrument(row).pk if drawer_instrument(row) else None):row for row in CashDrawer.objects.filter(business=ctx.business,activated_by__isnull=False).select_related('source','instrument')}
    for entry in entries:
        if entry.account.code!='CASH' or not drawers:continue
        if entry.location_id is None:raise ValidationError('Managed cash requires an explicit location; a company-wide cash entry would bypass drawer custody.')
        instrument=getattr(getattr(entry,'money_link',None),'instrument_id',None)
        drawer=drawers.get(instrument)
        if drawer and drawer.location_id!=entry.location_id:drawer=None
        if not drawer:continue
        custody_scope(ctx,drawer.location_id);ensure_date(drawer,doc.date)
        shift=CashShift.objects.select_for_update().filter(drawer=drawer,state__in=['open','counted']).first()
        reviewing=getattr(ctx,'cash_review_shift',None)
        if not shift or (shift.state!='open' and reviewing!=shift.pk):raise ValidationError('Open a cashier shift before posting physical cash. A counted shift is frozen until review or recount.')
        if doc.date<shift.source.date:raise ValidationError('A cash movement cannot precede its active custody shift.')
        reason=str(doc.data.get('cash_reason') or getattr(ctx,'cash_reason','')).strip()
        if shift.cashier_id!=ctx.membership.pk and reviewing!=shift.pk:
            ctx.require('cash_shifts.delegate')
            if not reason or len(reason)>1000:raise ValidationError('Record the reason for moving cash held by another cashier.')
        projected=expected(shift)
        # Include unposted ancestor/child journals too. The business posting
        # lock serializes this whole transaction; nested execute() calls must
        # not spend cash already consumed by their still-draft parent.
        draft=shift.cash_entries.exclude(entry__document__state='posted').aggregate(dr=Sum('entry__debit'),cr=Sum('entry__credit'))
        projected+=(draft['dr'] or ZERO)-(draft['cr'] or ZERO)+entry.debit-entry.credit
        if projected<0:raise ValidationError('This cash payout exceeds the amount currently held in the drawer.')
        CashShiftEntry.objects.create(business=ctx.business,shift=shift,entry=entry,reason=reason)


def count_shift(ctx,p,doc):
    shift=shift_for(ctx,p['shift']);ensure_date(shift.drawer,doc.date)
    if shift.cashier_id!=ctx.membership.pk:raise PermissionDenied('Only the responsible cashier signs the closing count.')
    if shift.state!='open':raise ValidationError('Only an open shift can record a closing count.')
    rows,counted=denominations(p.get('denominations',[]));amount=expected(shift)
    if amount!=drawer_balance(ctx,shift.drawer):raise ValidationError('Drawer custody and the CASH ledger disagree; review links before counting.')
    note=str(p.get('note','')).strip()
    if not note or len(note)>4000:raise ValidationError('Record the count note and evidence within 4,000 characters.')
    count=CashShiftCount.objects.create(business=ctx.business,shift=shift,denominations=rows,expected=amount,counted=counted,variance=counted-amount,note=note,source=doc)
    shift.state='counted';shift.save(update_fields=['state'])
    doc.location_id=shift.drawer.location_id;doc.reference=shift.source
    return {'shift':shift.id,'count':count.id,'expected':str(amount),'counted':str(counted),'variance':str(counted-amount),'denominations':rows,'financial_posting':False,'state':'counted'}


def recount(ctx,p,doc):
    shift=shift_for(ctx,p['shift'])
    if shift.state!='counted':raise ValidationError('Only a counted, unreviewed shift can return for recount.')
    note=str(p.get('reason','')).strip()
    if not note or len(note)>2000:raise ValidationError('Record why a fresh count or further activity is needed.')
    latest=shift.counts.order_by('-id').first()
    if doc.date<latest.source.date:raise ValidationError('Recount authorization cannot precede the original count.')
    shift.state='open';shift.save(update_fields=['state'])
    doc.reference=latest.source;doc.location_id=shift.drawer.location_id
    return {'shift':shift.id,'state':'open','reason':note,'old_count_preserved':latest.id,'financial_posting':False}


def review(ctx,p,doc):
    shift=shift_for(ctx,p['shift'],manager=True);ensure_date(shift.drawer,doc.date)
    if shift.state!='counted':raise ValidationError('Review one counted shift exactly once.')
    if shift.cashier_id==ctx.membership.pk and not ctx.has('cash_shifts.self_review'):raise PermissionDenied('A separate supervisor must review this cashier count.')
    count=shift.counts.select_related('source').order_by('-id').first()
    if doc.date<count.source.date or expected(shift)!=count.expected:raise ValidationError('The count date or cash movement evidence changed; request a recount.')
    note=str(p.get('reason','')).strip()
    if not note or len(note)>4000:raise ValidationError('Record supervisor evidence and the variance decision.')
    variance=count.variance
    if variance:
        if p.get('post_variance') is not True:raise ValidationError('Recount or explicitly approve the actual cash variance; it cannot be silently erased.')
        ctx.require('cash_shifts.adjust');ctx.require('accounting.post')
        old=getattr(ctx,'cash_review_shift',None);ctx.cash_review_shift=shift.id
        try:
            location=shift.drawer.location_id
            journal(ctx,doc,[{'account':'CASH','debit':max(variance,ZERO),'credit':max(-variance,ZERO),'location':location,'instrument':getattr(drawer_instrument(shift.drawer),'pk',None)},
                             {'account':'OTHER_INCOME' if variance>0 else 'EXPENSE','debit':max(-variance,ZERO),'credit':max(variance,ZERO),'location':location,'line':'shared'}])
        finally:ctx.cash_review_shift=old
        doc.amount=abs(variance)
    shift.state='closed';shift.reviewed_by=doc;shift.save(update_fields=['state','reviewed_by'])
    doc.reference=count.source;doc.location_id=shift.drawer.location_id
    return {'shift':shift.id,'count':count.id,'state':'closed','expected_before':str(count.expected),'actual_cash':str(count.counted),'variance':str(variance),'reason':note,'financial_posting':bool(variance),'variance_accounts':['CASH','OTHER_INCOME' if variance>0 else 'EXPENSE'] if variance else [],'employee_debt_created':False}


def handover(ctx,p,doc):
    shift=shift_for(ctx,p['shift'])
    if shift.state!='closed' or not shift.reviewed_by_id:raise ValidationError('A supervisor must close the counted shift before handover.')
    if shift.cashier_id!=ctx.membership.pk and not ctx.has('cash_shifts.manage'):raise PermissionDenied('Only the responsible cashier or cash manager may offer custody.')
    receiver=get_obj(ctx,Membership,p['receiver']);target=Context(receiver.user,ctx.business,receiver)
    if not receiver.active or not receiver.user.is_active:raise ValidationError('Select an active cashier.')
    target.require('cash_shifts.open');custody_scope(target,shift.drawer.location_id)
    if CashHandover.objects.filter(shift=shift).exists():raise ValidationError('This shift already has a recorded handover.')
    note=str(p.get('note','')).strip()
    if not note or len(note)>2000:raise ValidationError('Record the signed handover reference and note.')
    value=expected(shift)
    if doc.date<shift.reviewed_by.date or value!=drawer_balance(ctx,shift.drawer):raise ValidationError('Handover must match the latest reviewed drawer balance and date.')
    item=CashHandover.objects.create(business=ctx.business,shift=shift,receiver=receiver,amount=value,note=note,source=doc)
    doc.location_id=shift.drawer.location_id;doc.reference=shift.reviewed_by
    return {'shift':shift.id,'handover':item.id,'receiver':receiver.id,'amount':str(value),'state':'awaiting_receiver_count','financial_posting':False}


def redirect_handover(ctx,p,doc):
    item=get_obj(ctx,CashHandover,p['handover']);shift=shift_for(ctx,item.shift_id)
    if item.accepted_by_id:raise ValidationError('An accepted handover cannot be reassigned; the new cashier must complete their own shift.')
    previous,amendment=current_receiver(item)
    if doc.date<(amendment.date if amendment else item.source.date):raise ValidationError('Reassignment cannot precede the latest custody instruction.')
    receiver=get_obj(ctx,Membership,p['receiver']);target=Context(receiver.user,ctx.business,receiver)
    if not receiver.user.is_active:raise ValidationError('Select an active receiving user.')
    target.require('cash_shifts.open');custody_scope(target,shift.drawer.location_id)
    if receiver.id==previous:raise ValidationError('Select a different receiving cashier.')
    reason=str(p.get('reason','')).strip()
    if not reason or len(reason)>2000:raise ValidationError('Record the reason and handover evidence for changing the pending receiver.')
    doc.reference=item.source;doc.location_id=shift.drawer.location_id
    return {'shift':shift.id,'handover':item.id,'previous_receiver':previous,'receiver':receiver.id,'reason':reason,'financial_posting':False,'original_handover_preserved':True}


def enrich_registry(operations):
    result={}
    for action,(permission,handler) in operations.items():
        def wrapped(ctx,p,doc,original=handler):
            previous=getattr(ctx,'cash_reason','')
            ctx.cash_reason=p.get('cash_reason') or previous
            try:return original(ctx,p,doc)
            finally:ctx.cash_reason=previous
        result[action]=(permission,wrapped)
    return result


def document_guard(ctx,doc):
    if not doc.kind.startswith(('cash_drawer','cash_shift_','cash_handover')):return
    if doc.kind=='cash_drawer':ctx.require('cash_shifts.manage');custody_scope(ctx,doc.location_id or doc.data.get('location'));return
    ident=doc.result.get('shift') or doc.data.get('shift')
    if ident:shift_for(ctx,ident)
    elif doc.kind=='cash_shift_open':drawer_for(ctx,doc.data['drawer'])


OPERATIONS={'cash_drawer':('cash_shifts.manage',create_drawer),'cash_shift_open':('cash_shifts.open',open_shift),
 'cash_shift_count':('cash_shifts.open',count_shift),'cash_shift_recount':('cash_shifts.open',recount),
 'cash_shift_review':('cash_shifts.review',review),'cash_handover':('cash_shifts.handover',handover),
 'cash_handover_redirect':('cash_shifts.manage',redirect_handover)}
