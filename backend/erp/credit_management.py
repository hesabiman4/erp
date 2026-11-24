"""Whole-customer credit exposure, source snapshots and reasoned exceptions.

Checks are inside the ordinary business posting lock. Cash receipts/deposits
reduce exposure only when allocated; no unposted proposal creates debt.
"""
from datetime import timedelta
from decimal import Decimal
from django.core.exceptions import PermissionDenied,ValidationError
from django.db import transaction
from django.utils import timezone
from .models import Business,Document,Party,AuditEvent
from .core import D,money,ZERO,outstanding,get_obj
from .api import Boundary,response


def policy(business):return business.settings.get('credit_management',{}).get('reserve_orders',False) is True

def commitments(ctx,party):
    from .operations import _commercial_cancelled
    total=ZERO
    for order in Document.objects.filter(business=ctx.business,party=party,kind='sales_order',state='posted').select_related('reference'):
        if _commercial_cancelled(ctx,order):continue
        delivered=list(Document.objects.filter(business=ctx.business,kind='sale',state='posted',result__order=order.pk))
        for index,line in enumerate(order.result.get('lines',[])):
            used=sum((D(row['quantity']) for doc in delivered for row in doc.result.get('lines',[]) if row.get('order_index')==index),ZERO)
            total+=money(max(ZERO,D(line['quantity'])-used)*D(line['unit_price']))
    return money(total)

def exposure(ctx,party,day=None):
    day=day or timezone.localdate();debt=overdue=ZERO
    for invoice in Document.objects.filter(business=ctx.business,party=party,kind__in=['sale','opening_receivable'],state='posted'):
        value=max(ZERO,outstanding(invoice));debt+=value
        due=str(invoice.data.get('due_date') or invoice.date.isoformat())
        if due<day.isoformat():overdue+=value
    orders=commitments(ctx,party) if policy(ctx.business) else ZERO
    return {'debt':money(debt),'overdue':money(overdue),'orders':orders,'total':money(debt+orders)}

def release_for_order(ctx,order_id,lines):
    if not order_id:return ZERO
    order=get_obj(ctx,Document,order_id)
    return sum((money(D(row['quantity'])*D(order.result['lines'][row['order_index']]['unit_price'])) for row in lines),ZERO)

def enforce(ctx,party,new_debt,payload,doc,*,release=ZERO):
    if new_debt<=0:return
    values=exposure(ctx,party);projected=money(values['total']-min(release,values['orders'])+new_debt)
    exceeded=party.credit_limit is not None and projected>party.credit_limit
    if party.credit_hold or (party.block_overdue and values['overdue']>0) or exceeded:
        ctx.require('sales.credit_override')
        if not str(payload.get('credit_override_reason') or '').strip():raise ValidationError('A credit exception requires an authorized override and a reason.')
        AuditEvent.objects.create(business=ctx.business,user=ctx.user,action='sales.credit_override',target=str(doc.pk),details={'party':party.pk,'reason':str(payload['credit_override_reason'])[:1000],'hold':party.credit_hold,'overdue_block':party.block_overdue,'limit_exceeded':exceeded})

def apply_terms(party,payload,doc):
    from datetime import date
    due=payload.get('due_date') or (doc.date+timedelta(days=party.payment_terms_days)).isoformat()
    try:parsed=date.fromisoformat(str(due))
    except ValueError:raise ValidationError('Use an ISO YYYY-MM-DD due date.')
    if parsed<doc.date:raise ValidationError('Payment due date cannot precede the document date.')
    doc.data={**doc.data,'due_date':parsed.isoformat(),'payment_terms_days_snapshot':party.payment_terms_days}

class CreditAPI(Boundary):
    def get(self,request):
        ctx=self.ctx(request)
        if not (ctx.has('settings.manage') or ctx.has('sales.credit_summary') or ctx.has('sales.credit_manage')):raise PermissionDenied('Customer credit summary requires explicit credit access.')
        party=get_obj(ctx,Party,request.query_params.get('party'))
        if party.kind!='customer':raise ValidationError('Select a customer for credit review.')
        values=exposure(ctx,party)
        return response({'party':party.pk,'limit':party.credit_limit,'payment_terms_days':party.payment_terms_days,'credit_hold':party.credit_hold,'block_overdue':party.block_overdue,'reserve_orders':policy(ctx.business),'debt':values['debt'],'overdue':values['overdue'],'order_commitments':values['orders'],'exposure':values['total'],'available':max(ZERO,party.credit_limit-values['total']) if party.credit_limit is not None else None,'as_of':timezone.localdate(),'scope':'Current aggregate customer credit across this business; invoice details retain their original scope.'})
    @transaction.atomic
    def patch(self,request):
        ctx=self.ctx(request);ctx.require('settings.manage');business=Business.objects.select_for_update().get(pk=ctx.business.pk)
        value=request.data.get('reserve_orders')
        if not isinstance(value,bool):raise ValidationError('Select whether sales orders reserve credit.')
        before=policy(business);business.settings={**business.settings,'credit_management':{'reserve_orders':value}};business.save(update_fields=['settings'])
        AuditEvent.objects.create(business=business,user=ctx.user,action='credit.policy',details={'before':before,'reserve_orders':value})
        return response({'reserve_orders':value})
