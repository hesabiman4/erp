"""Permission-derived work queues, with bounded scans and no financial posting."""
from django.core.exceptions import PermissionDenied,ValidationError
from django.db import transaction
from django.db.models import Q
from .core import get_obj,outstanding,registry
from .models import Document,Location,WorkspacePreference,AuditEvent

PERSONAS=[
 ('owner','مدیریت','Management','مدیریت',['reports.view'],['sale','receipt','production','transfer_dispatch'],['receivables','approvals','drafts']),
 ('cashier','صندوق و فروش','Cashier and sales','صندوق او پلور',['sales.post','sales.collect','cash_shifts.open'],['sale','receipt','cash_shift_open'],['receivables','drafts']),
 ('warehouse','انبار','Warehouse','ګودام',['inventory.view','transfers.receive','purchases.post','inventory.count_record'],['purchase_receive','transfer_dispatch','transfer_receive','stock_count'],['dispatches','drafts']),
 ('factory','تولید','Production','تولید',['production.post','production.view'],['production_start','production_consume','production_complete','trim'],['batches','drafts']),
 ('accountant','حسابداری','Accounting','حسابداري',['accounting.view','accounting.post','finance.view'],['expense_post','supplier_payment','receipt','journal_adjust'],['receivables','payables','approvals','drafts']),
 ('sales','پیگیری فروش','Sales follow-up','د پلور تعقیب',['sales.view','crm.view'],['quotation','sales_order','receipt'],['quotations','receivables','drafts']),
 ('payroll','کارمندان','People and payroll','کارکوونکي او معاشونه',['payroll.view','payroll.post','payroll.manage'],['employee_advance','attendance_record','payroll_accrue','payroll_settle'],['drafts']),
 ('general','کارهای من','My work','زما چارې',[],[],['drafts'])
]
QUEUE_PASHTO={'receivables':'د پېرودونکو بلونه چې پاتې پور لري','payables':'د عرضه کوونکو بلونه چې پاتې پور لري','dispatches':'وروستي لېږل شوي انتقالونه','batches':'وروستي پیل شوي تولیدي بچونه','quotations':'وروستي نرخ وړاندیزونه','approvals':'د تایید غوښتنې','drafts':'زما مسودې'}
QUEUES={
 'receivables':('بل‌های مشتری دارای مانده','Customer invoices with balances','sale',['sales.view','sales.collect'],True),
 'payables':('بل‌های تأمین‌کننده دارای مانده','Supplier bills with balances','purchase_bill',['purchases.view','purchases.pay'],True),
 'dispatches':('آخرین ارسال‌های انتقال','Recent transfer dispatches','transfer_dispatch',['transfers.view','transfers.receive','transfers.post'],False),
 'batches':('آخرین بچ‌های آغازشده','Recent production batches','production_start',['production.view','production.post'],False),
 'quotations':('آخرین نرخ‌دهی‌ها','Recent quotations','quotation',['sales.view','sales.post','sales.quote'],False),
 'approvals':('درخواست‌های تأیید','Approval requests',None,[],False),
 'drafts':('مسوده‌های من','My drafts',None,['drafts.create'],False)
}


def personas(ctx):return [p for p in PERSONAS if not p[4] or any(ctx.has(v) for v in p[4])]


def allowed_queue(ctx,key):
    if key=='approvals':return any(ctx.has(v+'.approve') for v in ('sales','purchases','production','finance','accounting','payroll','inventory','transfers'))
    return key in QUEUES and any(ctx.has(v) for v in QUEUES[key][3])


def queue(ctx,key,location=None,before=None,limit=6):
    from .api import document_scope,doc_permission
    if not allowed_queue(ctx,key):raise PermissionDenied('This work queue is outside your permission scope.')
    title,en,kind,_,has_balance=QUEUES[key]
    qs=document_scope(ctx)
    if location:qs=qs.filter(location=get_obj(ctx,Location,location))
    if not ctx.has('documents.all_lines'):qs=qs.filter(product_lines__contained_by=ctx.membership.product_lines)
    if not ctx.has('payroll.view') and not ctx.has('payroll.post'):qs=qs.filter(employee__isnull=True)
    if kind:qs=qs.filter(kind=kind,state='posted')
    elif key=='drafts':qs=qs.filter(state='draft',created_by=ctx.user)
    else:qs=qs.filter(state='requested')
    if before:
        try:before=int(before)
        except (TypeError,ValueError):raise ValidationError('Use a numeric work queue cursor.')
        if before<=0:raise ValidationError('Use a positive work queue cursor.')
        qs=qs.filter(pk__lt=before)
    candidates=list(qs.order_by('-id')[:81]);rows=[];scanned=0;last=None
    actions=registry()
    for doc in candidates[:80]:
        scanned+=1;last=doc.pk
        if key=='approvals':
            permission=actions.get(doc.kind,('documents.view',))[0]
            if not ctx.has(permission.split('.')[0]+'.approve'):continue
        try:doc_permission(ctx,doc)
        except (PermissionDenied,ValidationError):continue
        remaining=outstanding(doc) if has_balance else None
        if has_balance and remaining<=0:continue
        rows.append({'id':doc.pk,'number':doc.number,'kind':doc.kind,'date':doc.date,'party_name':doc.party.name if doc.party else '',
            'state':doc.state,'balance':remaining})
        if len(rows)>=limit:break
    more=scanned<len(candidates)
    return {'key':key,'title':title,'en':en,'ps':QUEUE_PASHTO[key],'results':rows,'next_cursor':last if more else None,
        'scan_limit':80,'shown':len(rows),'basis':'Authorized original documents only. Shown rows are a bounded page, not a company total.'}


def workspace(ctx,selected=None,location=None):
    choices=personas(ctx);saved=WorkspacePreference.objects.filter(business=ctx.business,membership=ctx.membership).first()
    preferred=selected or (saved.persona if saved else '')
    valid={p[0] for p in choices}
    if selected and selected not in valid:raise PermissionDenied('This workspace is outside your current permissions.')
    # A revoked preference falls back without exposing a stale workspace.
    person=next((p for p in choices if p[0]==preferred),choices[0])
    operations=registry()
    actions=[a for a in person[5] if a in operations and ctx.has(operations[a][0])]
    return {'persona':person[0],'personas':[{'id':p[0],'title':p[1],'en':p[2],'ps':p[3]} for p in choices],
        'actions':actions,'queues':[queue(ctx,k,location) for k in person[6] if allowed_queue(ctx,k)],
        'basis':'Task profile changes presentation only; server permissions still authorize every action.'}


@transaction.atomic
def select_persona(ctx,persona):
    if not isinstance(persona,str):raise ValidationError('Select a task profile.')
    if persona not in {p[0] for p in personas(ctx)}:raise PermissionDenied('This workspace is outside your current permissions.')
    type(ctx.membership).objects.select_for_update().get(pk=ctx.membership.pk)
    item,_=WorkspacePreference.objects.update_or_create(business=ctx.business,membership=ctx.membership,defaults={'persona':persona})
    AuditEvent.objects.create(business=ctx.business,user=ctx.user,action='workspace.preference',target=str(item.pk),details={'persona':persona,'financial_effect':False})
    return {'persona':persona,'financial_effect':False}
