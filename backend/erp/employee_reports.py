"""Employee statements derived from scoped, posted payroll/advance entries."""
from decimal import Decimal
from django.db.models import Q,Sum
from django.core.exceptions import ValidationError
from .core import get_obj,money,D
from .models import Employee

ZERO=Decimal('0')
def employee_statement(ctx,params,all_rows=False):
    from .reports import _bounds,_entries,_documents,_net,_table
    ctx.require('payroll.view');employee=get_obj(ctx,Employee,params.get('employee'));since,through=_bounds(params)
    account=params.get('account','PAYROLL')
    if account not in {'PAYROLL','ADVANCES'}:raise ValidationError('Employee statements support PAYROLL or ADVANCES.')
    base=_entries(ctx,params,period=False).filter(Q(employee=employee)|Q(document__employee=employee))
    current=base.filter(document__date__gte=since) if since else base
    opening_query=base.filter(document__date__lt=since) if since else base.none()
    direction=Decimal(-1) if account=='PAYROLL' else Decimal(1)
    opening=direction*_net(opening_query.filter(account__code=account));closing=direction*_net(base.filter(account__code=account))
    grouped=current.filter(account__code=account).values('document_id','document__number','document__date','document__kind','document__reference_id').annotate(debit=Sum('debit'),credit=Sum('credit')).order_by('document__date','document_id')
    count=grouped.count()
    try:offset=max(0,int(params.get('offset',0)));limit=max(1,min(200,int(params.get('limit',100))))
    except (ValueError,TypeError):raise ValidationError('Use integer statement pagination.')
    rows=[];running=opening
    # Compute running balances before slicing, so page2 includes page1 movements.
    for item in grouped.iterator():
        debit=money(item['debit'] or ZERO);credit=money(item['credit'] or ZERO);running+=direction*(debit-credit)
        rows.append({'document_id':item['document_id'],'number':item['document__number'],'date':item['document__date'].isoformat(),'kind':item['document__kind'],'reference_id':item['document__reference_id'],'debit':str(debit),'credit':str(credit),'balance':str(money(running))})
    docs=_documents(ctx,params).filter(employee=employee)
    earned=sum((D(doc.result.get('gross',0)) for doc in docs.filter(kind__in=['payroll_accrue','commission_accrue','commission_reverse'])),ZERO)
    deductions=sum((D(doc.result.get('deductions',0)) for doc in docs.filter(kind='payroll_accrue')),ZERO)
    paid=-_net(current.filter(account__code__in=['CASH','BANK'],document__kind='payroll_settle'))
    advances_paid=-_net(current.filter(account__code__in=['CASH','BANK'],document__kind='employee_advance'))
    recovered=_net(current.filter(account__code='ADVANCES',document__kind='payroll_settle'))*-1
    totals={'opening':str(opening),'closing':str(closing),'salary_earned':str(money(earned)),'salary_paid':str(paid),'advances_paid':str(advances_paid),'advance_recovered':str(recovered),'deductions':str(money(deductions)),'salary_payable':str(-_net(base.filter(account__code='PAYROLL'))),'advance_outstanding':str(_net(base.filter(account__code='ADVANCES'))),'debit':str(sum((D(r['debit']) for r in rows),ZERO)),'credit':str(sum((D(r['credit']) for r in rows),ZERO))}
    profile={key:getattr(employee,key) for key in ['id','code','name','kind','rate','join_date','end_date','active','phone']}
    profile.update({'location_id':employee.location_id,'location':employee.location.name,'department':employee.department.name if employee.department_id else '', 'position':employee.position.name if employee.position_id else ''})
    return _table('employee_statement',[('date','Date'),('kind','Transaction'),('number','Reference'),('debit','Debit'),('credit','Credit'),('balance','Balance')],rows if all_rows else rows[offset:offset+limit],totals,params,employee=profile,account=account,count=count,offset=offset,next_offset=None if all_rows or offset+limit>=count else offset+limit,date_from=since.isoformat() if since else None,basis='PAYROLL: credits increase wages owed; ADVANCES: debits increase employee advance debt. Opening balances and adjustments remain separate from cash payments. All amounts follow assigned business/location/product scope.')
