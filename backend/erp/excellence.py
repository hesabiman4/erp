"""Evidence-based closing and exact, explicitly attributed management results."""
import hashlib
from datetime import date
from django.core.exceptions import ValidationError, PermissionDenied
from django.db.models import Sum
from .core import D, ZERO, money, get_obj, execute, json_value,Context
from .models import (Document, Entry, StockMovement, Product, Membership, ClosingCycle,
                     ClosingReview, ProjectDocument)

TASKS = {'cash':'Cash count', 'bank':'Bank reconciliation', 'receivables':'Customer balances',
         'payables':'Supplier balances', 'inventory':'Inventory reconciliation', 'wip':'Work in progress',
         'payroll':'Wages and advances', 'foreign':'Foreign balances'}


def full_accountant(ctx):
    for permission in ('accounting.view','cost.view','finance.view','payroll.view','inventory.raw'):
        ctx.require(permission)
    from .reports import _company
    _company(ctx,{})
    if not ctx.has('documents.all_lines') and Product.objects.filter(business=ctx.business).exclude(line__in=ctx.membership.product_lines).exists():
        raise PermissionDenied('Complete business product scope is required for closing.')


def cycle_for(ctx, ident):
    full_accountant(ctx)
    return get_obj(ctx,ClosingCycle,ident)


def financial_fingerprint(ctx, through):
    docs=Document.objects.filter(business=ctx.business,state='posted',date__lte=through)
    rows=list(Entry.objects.filter(document__in=docs).order_by('pk').values_list('id','debit','credit'))
    stock=list(StockMovement.objects.filter(document__in=docs).order_by('pk').values_list('id','quantity','value'))
    from .foreign import reconcile
    current_fx=reconcile(ctx)
    return hashlib.sha256(str((rows,stock,current_fx)).encode()).hexdigest()


def eligible_reviewers(ctx):
    members=[]
    for member in Membership.objects.filter(business=ctx.business,active=True).select_related('user'):
        try:
            candidate=Context(member.user,ctx.business,member);candidate.require('accounting.close');full_accountant(candidate)
        except PermissionDenied:continue
        members.append(member)
    return members


def checks(ctx,cycle):
    full_accountant(ctx)
    from .reports import trial_balance,balance_sheet,inventory_reconciliation,_entries,_net
    from .foreign import reconcile
    params={'to':str(cycle.ends)}
    tb=trial_balance(ctx,params)['totals']; bs=balance_sheet(ctx,params)['totals']
    inventory=inventory_reconciliation(ctx,params)['totals']
    fx=reconcile(ctx) # explicitly current: foreign movement subledgers have no as-of replay
    fingerprint=financial_fingerprint(ctx,cycle.ends)
    rows=[]
    for key,label in TASKS.items():
        latest=cycle.reviews.filter(task=key).select_related('source','assignee__user','evidence').order_by('-id').first()
        accepted=bool(latest and latest.accepted and latest.source.result.get('fingerprint')==fingerprint and latest.assignee.active)
        rows.append({'key':key,'label':label,'accepted':accepted,'stale':bool(latest and latest.accepted and not accepted),
            'assignee':latest.assignee_id if latest else None,'assignee_name':latest.assignee.user.get_full_name() or latest.assignee.user.username if latest else '',
            'evidence':latest.evidence_id if latest else None,'note':latest.note if latest else '', 'review':latest.source_id if latest else None})
    blockers=[]
    for name,value in [('Trial balance',tb['difference']),('Balance sheet',bs['difference']),('Inventory',inventory['difference']),('Current foreign controls',fx['difference'])]:
        if D(value):blockers.append(f'{name} difference: {value}')
    return {'cycle':cycle.id,'starts':cycle.starts,'ends':cycle.ends,'tasks':rows,'blockers':blockers,
        'ready':not blockers and all(row['accepted'] for row in rows),'fingerprint':fingerprint,
        'inventory':inventory,'foreign_current':fx,'closed':bool(ctx.business.closed_through and ctx.business.closed_through>=cycle.ends),
        'basis':'Ledger/stock checks are as of the closing date; foreign control reconciliation is current. Reviews require evidence or a documented explanation. Open WIP is reviewed, not forced to zero.'}


def closing_open(ctx,p,doc):
    full_accountant(ctx)
    start=date.fromisoformat(str(p['starts']));end=date.fromisoformat(str(p['ends']))
    if start>end or end>doc.date:raise ValidationError('Choose a completed reporting window, on or before the posting date.')
    if ctx.business.closed_through and start<=ctx.business.closed_through:raise ValidationError('This window overlaps an already closed period.')
    if ClosingCycle.objects.filter(business=ctx.business,starts__lte=end,ends__gte=start).exists():raise ValidationError('An overlapping closing cycle already exists.')
    cycle=ClosingCycle.objects.create(business=ctx.business,starts=start,ends=end,source=doc)
    return {'cycle':cycle.id,'starts':start,'ends':end,'financial_posting':False}


def closing_review(ctx,p,doc):
    cycle=cycle_for(ctx,p['cycle']);key=p['task']
    if key not in TASKS:raise ValidationError('Choose a closing task.')
    if ctx.business.closed_through and cycle.ends<=ctx.business.closed_through:raise ValidationError('The cycle is already closed.')
    assignee=get_obj(ctx,Membership,p.get('assignee') or ctx.membership.id)
    if assignee.id not in {m.id for m in eligible_reviewers(ctx)}:raise ValidationError('Assign an active reviewer with complete closing, financial and payroll authority.')
    accepted=p.get('accepted',False)
    if not isinstance(accepted,bool):raise ValidationError('accepted must be true or false.')
    if accepted and assignee.user_id!=ctx.user.id:raise PermissionDenied('Only the assigned reviewer can attest completion.')
    note=str(p.get('note','')).strip()
    if not note or len(note)>4000:raise ValidationError('Explain the review and any unresolved items (maximum 4,000 characters).')
    evidence=get_obj(ctx,Document,p['evidence']) if p.get('evidence') else None
    if evidence:
        from .api import doc_permission
        doc_permission(ctx,evidence)
        if evidence.state!='posted' or evidence.date>doc.date:raise ValidationError('Use a posted evidence document on or before this review.')
        expected={'cash':{'cash_count'},'bank':{'bank_reconcile'}}.get(key)
        if expected and evidence.kind not in expected:raise ValidationError('Use the matching cash-count or bank-reconciliation evidence.')
        if key=='cash' and evidence.date!=cycle.ends:raise ValidationError('Cash evidence must be a count on the closing date.')
        if key=='bank' and evidence.result.get('through_date')!=str(cycle.ends):raise ValidationError('Bank evidence must cover the closing date.')
        if key=='cash' and D(evidence.result.get('variance',0)):raise ValidationError('Resolve/recount the cash difference before accepting the review.')
    review=ClosingReview.objects.create(business=ctx.business,cycle=cycle,task=key,assignee=assignee,evidence=evidence,note=note,accepted=accepted,source=doc)
    doc.reference=cycle.source
    return {'cycle':cycle.id,'review':review.id,'task':key,'accepted':accepted,'fingerprint':financial_fingerprint(ctx,cycle.ends),'financial_posting':False}


def closing_finish(ctx,p,doc):
    cycle=cycle_for(ctx,p['cycle']);state=checks(ctx,cycle)
    if not state['ready']:raise ValidationError('Complete all eight current reviews and resolve reconciliation differences before closing.')
    ctx.require('accounting.close')
    old=getattr(ctx,'closing_authorized_cycle',None);ctx.closing_authorized_cycle=cycle.id
    try:closed=execute(ctx,'period_close',{'date':str(doc.date),'through_date':str(cycle.ends)},f'close-cycle-{cycle.id}-{doc.id}')
    finally:ctx.closing_authorized_cycle=old
    doc.reference=cycle.source
    return {'cycle':cycle.id,'period_document':closed.id,'closed_through':cycle.ends,'fingerprint':state['fingerprint'],'financial_posting':False}


def guard_close(handler):
    def handle(ctx,p,doc):
        end=date.fromisoformat(str(p['through_date']))
        cycles=ClosingCycle.objects.filter(business=ctx.business,starts__lte=end)
        if ctx.business.closed_through:cycles=cycles.filter(ends__gt=ctx.business.closed_through)
        for cycle in cycles:
            if getattr(ctx,'closing_authorized_cycle',None)!=cycle.id or not checks(ctx,cycle)['ready']:
                raise ValidationError('An open closing checklist must be finalized from its reviewed closing workflow.')
        return handler(ctx,p,doc)
    return handle


def profitability(ctx,p):
    ctx.require('accounting.view');ctx.require('cost.view')
    from .reports import _entries,_bounds
    from .api import doc_permission
    group=p.get('group','customer')
    if group not in {'customer','branch','product','order','project'}:raise ValidationError('Choose customer, branch, product, order or project.')
    if group=='project' and not any(ctx.has(permission) for permission in ('jobs.view','jobs.manage','jobs.plan')):raise PermissionDenied('Job-costing access is required for project profitability.')
    entries=_entries(ctx,p).filter(account__category__in=['income','expense']).select_related('document__party','document__location','account')
    grouped={};document_entries={};totals={'revenue':ZERO,'cogs':ZERO,'other_expenses_net':ZERO,'profit':ZERO}
    for e in entries:
        try:doc_permission(ctx,e.document)
        except PermissionDenied:raise PermissionDenied('Profitability requires source-document access for every included transaction; narrow the reporting scope or obtain the required access.')
        if e.employee_id or e.document.employee_id:
            if not ctx.has('payroll.view'):raise PermissionDenied('Complete profitability includes payroll and requires payroll access.')
        document_entries.setdefault(e.document_id,[e.document,[]])[1].append(e)
    def add(key,label,revenue=ZERO,cogs=ZERO,other=ZERO):
        row=grouped.setdefault(str(key),{'id':str(key),'label':label,'revenue':ZERO,'cogs':ZERO,'other_expenses_net':ZERO})
        row['revenue']+=revenue;row['cogs']+=cogs;row['other_expenses_net']+=other
    for doc,items in document_entries.values():
        revenue=-sum((e.debit-e.credit for e in items if e.account.code in {'SALES','RETURNS'}),ZERO)
        cogs=sum((e.debit-e.credit for e in items if e.account.code=='COGS'),ZERO)
        other=sum((e.debit-e.credit for e in items if e.account.code not in {'SALES','RETURNS','COGS'}),ZERO)
        root=doc
        for _ in range(12):
            if root.kind=='sale' or not root.reference_id:break
            root=root.reference
        if root.id!=doc.id:doc_permission(ctx,root)
        if group=='product' and doc.kind in {'sale','sales_return'}:
            allocated_revenue=allocated_cogs=ZERO
            for line in doc.result.get('lines',[]):
                product=get_obj(ctx,Product,line['product'])
                if p.get('line') and product.line!=p['line']:continue
                r=D(line.get('amount','0'))*(1 if doc.kind=='sale' else -1)
                c=D(line.get('cost','0'))*(1 if doc.kind=='sale' else -1)
                measured=line
                if doc.kind=='sales_return' and root.kind=='sale':
                    measured=root.result['lines'][int(line['index'])]
                profile=measured.get('profile','')
                if not profile and measured.get('length_mm') and measured.get('width_mm'):
                    from .core import profile_for
                    profile=profile_for(measured['length_mm'],measured['width_mm'])
                add(f'p-{product.id}-{profile}',f'{product.name} · {profile}' if profile else product.name,r,c)
                allocated_revenue+=r;allocated_cogs+=c
            add('unattributed','Adjustments / expenses without product attribution',revenue-allocated_revenue,cogs-allocated_cogs,other)
        elif group=='customer':add(f'c-{root.party_id}' if root.party_id and root.kind=='sale' else 'unattributed',root.party.name if root.party_id and root.kind=='sale' else 'Company / unattributed',revenue,cogs,other)
        elif group=='branch':
            locations={e.location_id for e in items}
            loc=items[0].location if len(locations)==1 else None
            add(f'l-{loc.id}' if loc else 'unattributed',loc.name if loc else 'Company / multiple branches',revenue,cogs,other)
        elif group=='order':
            ident=root.result.get('order') if root.kind=='sale' else None
            order=get_obj(ctx,Document,ident) if ident else None
            if order:doc_permission(ctx,order)
            add(f'o-{order.id}' if order else 'unattributed',order.number if order else 'Direct sales / unattributed',revenue,cogs,other)
        elif group=='project':
            link=ProjectDocument.objects.filter(business=ctx.business,document=doc).select_related('project').first()
            if link:get_obj(ctx,type(link.project),link.project_id)
            add(f'j-{link.project_id}' if link else 'unattributed',link.project.name if link else 'Outside dedicated jobs',revenue,cogs,other)
        else:add('unattributed','Adjustments / expenses without product attribution',revenue,cogs,other)
        totals['revenue']+=revenue;totals['cogs']+=cogs;totals['other_expenses_net']+=other
    rows=[]
    for row in grouped.values():
        row['gross_profit']=row['revenue']-row['cogs'];row['profit']=row['gross_profit']-row['other_expenses_net']
        row['gross_margin_percent']=money(row['gross_profit']/row['revenue']*100) if row['revenue'] else None
        row['loss_flag']=row['profit']<0
        if any(row[k] for k in ('revenue','cogs','other_expenses_net')):rows.append(row)
    totals['profit']=totals['revenue']-totals['cogs']-totals['other_expenses_net']
    return {'rows':sorted(rows,key=lambda r:r['profit']),'totals':totals,'group':group,
        'basis':'Posted recognized sales/returns, COGS and other net expenses in the selected period. Product figures use original line attribution; remaining adjustments/shared costs stay explicitly unattributed. No guessed overhead allocation or density conversion.',
        'estimated':False,'through':_bounds(p)[1]}


OPERATIONS={'closing_open':('accounting.close',closing_open),'closing_review':('accounting.close',closing_review),'closing_finish':('accounting.close',closing_finish)}
