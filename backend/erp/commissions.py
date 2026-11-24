"""Reviewed commission earnings on collected net sales, settled as payroll.

No automatic deduction of previously paid wages is permitted. Returns trigger
an exception; only wholly unpaid earnings can be reversed and re-accrued.
"""
from decimal import Decimal
from datetime import date
from django.core.exceptions import PermissionDenied,ValidationError
from django.db.models import Sum,Q
from .core import D,money,get_obj,journal,balance
from .models import Employee,Document,Allocation,Entry
from .commission_models import CommissionPolicy,CommissionEarning

ZERO=Decimal('0')
def fail(message):raise ValidationError(message)
def required(p,key):
    value=str(p.get(key) or '').strip()
    if not value or len(value)>1000:fail(f'{key} is required, maximum 1000 characters.')
    return value

def policy(ctx,p,doc):
    ctx.require('payroll.manage');employee=get_obj(ctx,Employee,p['employee'])
    rate=D(p['rate']);start=date.fromisoformat(str(p['effective_from']));end=date.fromisoformat(str(p['effective_to'])) if p.get('effective_to') else None
    if not employee.active or not ZERO<rate<=100 or (end and end<start):fail('Choose an active employee, valid percentage and effective dates.')
    others=CommissionPolicy.objects.filter(business=ctx.business,employee=employee).filter(Q(effective_to__isnull=True)|Q(effective_to__gte=start))
    if end:others=others.filter(effective_from__lte=end)
    if others.exists():fail('Commission policy dates overlap. Use non-overlapping approved versions.')
    row=CommissionPolicy.objects.create(business=ctx.business,employee=employee,rate=rate,effective_from=start,effective_to=end,source=doc)
    doc.employee=employee;doc.location=employee.location
    return {'policy':row.id,'employee':employee.id,'rate':str(rate),'basis':'collected net sales after returns; excluding tax; unpaid reversals only'}

def calculation(ctx,rule,invoice,through):
    from .api import doc_permission
    ctx.require('payroll.view');ctx.require('sales.view');ctx.require('accounting.view')
    rule=get_obj(ctx,CommissionPolicy,rule.pk);employee=get_obj(ctx,Employee,rule.employee_id)
    invoice=get_obj(ctx,Document,invoice.pk);doc_permission(ctx,invoice)
    if invoice.kind!='sale' or invoice.state!='posted' or invoice.date>through or invoice.location_id!=employee.location_id:fail('Choose a posted sale at the employee location, on or before this date.')
    if invoice.date<rule.effective_from or (rule.effective_to and invoice.date>rule.effective_to):fail('The policy does not cover this invoice date.')
    # Registered FX invoices must use their reconciled foreign movements; this
    # first commission policy deliberately supports ordinary AFN sales only.
    from .models import ForeignExposure
    if ForeignExposure.objects.filter(invoice=invoice).exists():fail('This commission policy supports AFN invoices only.')
    returns=Document.objects.filter(business=ctx.business,kind='sales_return',reference=invoice,state='posted',date__lte=through)
    gross=max(ZERO,invoice.amount-sum((r.amount for r in returns),ZERO))
    posted=Entry.objects.filter(document__in=[invoice,*returns],account__code='SALES')
    sums=posted.aggregate(dr=Sum('debit'),cr=Sum('credit'));net=max(ZERO,(sums['cr'] or ZERO)-(sums['dr'] or ZERO))
    cash_kinds=['sale','receipt','allocate_deposit','payment_reverse']
    allocated=Allocation.objects.filter(invoice=invoice,document__state='posted',document__date__lte=through,document__kind__in=cash_kinds).aggregate(v=Sum('amount'))['v'] or ZERO
    collected=min(max(allocated,ZERO),gross)
    eligible=money(net*collected/gross) if gross else ZERO
    entitlement=money(eligible*rule.rate/100)
    earnings=CommissionEarning.objects.filter(business=ctx.business,policy=rule,invoice=invoice,source__date__lte=through)
    accrued=sum((e.amount for e in earnings if not e.source.children.filter(kind='commission_reverse',state='posted',date__lte=through).exists()),ZERO)
    return {'eligible_amount':eligible,'entitlement':entitlement,'accrued':accrued,'available':max(ZERO,entitlement-accrued),'over_accrued':max(ZERO,accrued-entitlement),'rate':rule.rate,'invoice':invoice.id,'policy':rule.id,'basis':'collected AFN net sales after returns, excluding tax'}

def accrue(ctx,p,doc):
    ctx.require('payroll.approve')
    rule=get_obj(ctx,CommissionPolicy,p['policy']);employee=get_obj(ctx,Employee,rule.employee_id)
    if not employee.active:fail('Inactive employees cannot receive new commission accruals.')
    invoice=get_obj(ctx,Document,p['invoice']);result=calculation(ctx,rule,invoice,doc.date)
    if result['over_accrued']:fail('Returns reduced the entitlement. Review/reverse unpaid accruals before new earnings.')
    amount=money(p.get('amount',result['available']))
    if amount<=0 or amount>result['available']:fail('Accrual must be positive and within unaccrued earned commission.')
    doc.employee=employee;doc.location=employee.location;doc.reference=invoice;doc.amount=amount;ctx.lines.update(invoice.product_lines)
    CommissionEarning.objects.create(business=ctx.business,policy=rule,invoice=invoice,eligible_amount=result['eligible_amount'],amount=amount,source=doc)
    journal(ctx,doc,[{'account':'COMMISSION','debit':amount,'employee':employee,'location':doc.location_id},{'account':'PAYROLL','credit':amount,'employee':employee,'location':doc.location_id}])
    return {**result,'gross':str(amount),'net':str(amount),'deductions':'0','remaining':str(amount),'employee':employee.id,'employee_snapshot':{'name':employee.name,'code':employee.code},'reason':required(p,'reason')}

def reverse(ctx,p,doc):
    ctx.require('payroll.approve');source=get_obj(ctx,Document,p['earning'])
    if source.kind!='commission_accrue' or source.state!='posted':fail('Choose a posted commission accrual.')
    if source.children.filter(kind__in=['payroll_settle','commission_reverse'],state='posted').exists():fail('Only wholly unpaid, unreversed commissions can be reversed. Paid clawbacks require a separately reviewed agreement.')
    get_obj(ctx,Employee,source.employee_id);ctx.lines.update(source.product_lines)
    doc.reference=source;doc.employee=source.employee;doc.location=source.location;doc.amount=source.amount
    journal(ctx,doc,[{'account':'PAYROLL','debit':source.amount,'employee':source.employee_id,'location':source.location_id},{'account':'COMMISSION','credit':source.amount,'employee':source.employee_id,'location':source.location_id}])
    return {'earning':source.id,'amount':str(source.amount),'gross':str(-source.amount),'reason':required(p,'reason')}

OPERATIONS={'commission_policy':('payroll.manage',policy),'commission_accrue':('payroll.post',accrue),'commission_reverse':('payroll.post',reverse)}

from .api import Boundary,response,doc_permission
from django.utils import timezone
class CommissionAPI(Boundary):
    def get(self,request):
        ctx=self.ctx(request);ctx.require('payroll.view');policies=[];earnings=[]
        for rule in CommissionPolicy.objects.filter(business=ctx.business).select_related('employee'):
            try:get_obj(ctx,Employee,rule.employee_id)
            except PermissionDenied:continue
            policies.append({'id':rule.id,'employee':rule.employee_id,'employee_name':rule.employee.name,'rate':rule.rate,'effective_from':rule.effective_from,'effective_to':rule.effective_to})
        for row in CommissionEarning.objects.filter(business=ctx.business).select_related('policy__employee','source','invoice'):
            try:
                doc_permission(ctx,row.source);doc_permission(ctx,row.invoice)
                calc=calculation(ctx,row.policy,row.invoice,timezone.localdate())
            except (PermissionDenied,ValidationError):continue
            reversed=row.source.children.filter(kind='commission_reverse',state='posted').exists()
            paid=sum((d.amount for d in row.source.children.filter(kind='payroll_settle',state='posted')),ZERO)
            earnings.append({'id':row.id,'document':row.source_id,'number':row.source.number,'employee_name':row.policy.employee.name,'invoice_number':row.invoice.number,'amount':row.amount,'remaining':ZERO if reversed else row.amount-paid,'reversed':reversed,'over_accrued':calc['over_accrued']})
        result={'policies':policies,'earnings':earnings}
        if request.query_params.get('policy') and request.query_params.get('invoice'):
            result['calculation']=calculation(ctx,get_obj(ctx,CommissionPolicy,request.query_params['policy']),get_obj(ctx,Document,request.query_params['invoice']),date.fromisoformat(request.query_params.get('date') or timezone.localdate().isoformat()))
        return response(result)
