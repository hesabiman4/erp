"""Read-only daily attention, source timelines and ledger-derived owner trends."""
from datetime import timedelta
from decimal import Decimal
from django.core.exceptions import PermissionDenied,ValidationError
from django.db.models import Q,Sum
from django.utils import timezone
from .core import get_obj,money,outstanding,registry
from .models import Document,Allocation,AuditEvent,Location,StockMovement


def attention(ctx,location=None):
    from .daily_workspace import allowed_queue,queue
    groups=[]
    for key in ('approvals','receivables','payables'):
        if not allowed_queue(ctx,key):continue
        page=queue(ctx,key,location,limit=6)
        if key!='approvals':
            today=timezone.localdate()
            ids=[row['id'] for row in page['results']]
            dates={doc.pk:str(doc.data.get('due_date') or doc.date) for doc in Document.objects.filter(business=ctx.business,pk__in=ids)}
            page['results']=[row for row in page['results'] if dates[row['id']]<today.isoformat()]
        groups.append({'key':key,'title':page['title'],'results':page['results'],'more':page['next_cursor'] is not None})
    if ctx.has('settings.manage') and ctx.has('runtime.manage') and ctx.membership.all_locations and ctx.has('documents.all_lines'):
        from .backup_settings import configuration
        from .backup_health import summary
        health=summary(configuration())
        if health['state']!='current':groups.append({'key':'system','title':'سلامت و پشتیبان','results':[{'id':'backup-health','kind':'system_health','number':'پشتیبان نیازمند توجه','status':health['state'],'date':health['last_success_at'],'href':'/settings?section=security'}],'more':False})
    return {'groups':groups,'shown':sum(len(g['results']) for g in groups),'more':any(g['more'] for g in groups),
            'basis':'Recent authorized approvals and overdue invoices. This bounded alert page is not an unread count or a complete company total.'}


def timeline(ctx,identifier):
    from .api import doc_permission,document_data
    source=get_obj(ctx,Document,identifier);doc_permission(ctx,source)
    events=[{'id':f'created:{source.pk}','kind':'created','at':source.created_at,'actor':source.created_by.get_full_name() or source.created_by.username,'document':source.pk,'number':source.number}]
    if source.posted_at:events.append({'id':f'posted:{source.pk}','kind':'posted','at':source.posted_at,'document':source.pk,'number':source.number})
    # Source authorization applies independently to every linked original record.
    linked_ids=set(Document.objects.filter(business=ctx.business,reference=source).values_list('pk',flat=True)[:101])
    # Approval/conversion links are stored on the original request, not as a
    # financial reference on the posted document. Keep both directions visible
    # only after independently authorizing that original request.
    if source.state in {'approved','converted'} and source.result.get('posted_document'):
        linked_ids.add(source.result['posted_document'])
    linked_ids.update(Document.objects.filter(business=ctx.business,state__in=['approved','converted'],result__posted_document=source.pk).values_list('pk',flat=True)[:101])
    links=Allocation.objects.filter(document__business=ctx.business,invoice__business=ctx.business).filter(Q(invoice=source)|Q(document=source)).order_by('-pk')[:101]
    for link in links:linked_ids.update([link.invoice_id,link.document_id])
    linked_ids.discard(source.pk)
    authorized={str(source.pk):source}
    for doc in Document.objects.filter(business=ctx.business,pk__in=linked_ids).select_related('created_by').order_by('-id')[:100]:
        try:doc_permission(ctx,doc)
        except (PermissionDenied,ValidationError):continue
        authorized[str(doc.pk)]=doc
        events.append({'id':f'doc:{doc.pk}','kind':doc.kind,'at':doc.posted_at or doc.created_at,'document':doc.pk,'number':doc.number,'state':doc.state})
    # Do not expose arbitrary audit details, raw payloads, confidential amounts or
    # operator/session metadata merely because the source document is visible.
    allowed={'document.print':'printed','approval.request':'approval_requested','approval.approve':'approved','approval.reject':'rejected','draft.edit':'draft_edited','draft.undo':'draft_undo','draft.discard':'draft_discarded'}
    audit=AuditEvent.objects.filter(business=ctx.business,target__in=authorized,action__in=allowed).select_related('user').order_by('-id')[:100]
    for item in audit:
        original=authorized[item.target]
        events.append({'id':f'audit:{item.pk}','kind':allowed[item.action],'at':item.at,'actor':item.user.get_full_name() or item.user.username if item.user else '', 'document':original.pk,'number':original.number})
    events.sort(key=lambda event:(event['at'],event['id']))
    return {'results':events,'bounded':True,'basis':'Recorded events only. Printing records a print-view request, not proof of paper delivery; linked documents keep their original permissions.'}


def trends(ctx,params):
    from . import reports
    if not ctx.has('reports.view') or not ctx.has('accounting.view') or not ctx.has('cost.view'):raise PermissionDenied('Owner trends require reporting, accounting and cost permission.')
    try:days=int(params.get('days',30))
    except (ValueError,TypeError):raise ValidationError('Use a supported trend period.')
    if days not in (7,30,90):raise ValidationError('Choose7,30 or90 trend days.')
    through=reports._date(params.get('to'),timezone.localdate());first=through-timedelta(days=days-1)
    scope={'to':through.isoformat()}
    if params.get('location'):scope['location']=get_obj(ctx,Location,params['location']).pk
    entries=reports._entries(ctx,scope,period=False)
    rows=list(entries.filter(document__date__gte=first).values('document__date','account__code').annotate(dr=Sum('debit'),cr=Sum('credit')))
    inventory_codes={'RAW','FG','TRIM','TRANSIT','INVENTORY_ALLOWANCE'}
    opening=entries.filter(document__date__lt=first,account__code__in=inventory_codes).aggregate(dr=Sum('debit'),cr=Sum('credit'))
    value=(opening['dr'] or Decimal(0))-(opening['cr'] or Decimal(0))
    by_day={}
    for row in rows:by_day.setdefault(row['document__date'],[]).append(row)
    output=StockMovement.objects.filter(document__in=reports._documents(ctx,scope,{'production','production_bom','production_complete'}),quantity__gt=0,pool__product__kind='finished',document__date__gte=first)
    measured={}
    for row in output.values('document__date','pool__product_id','pool__product__name','pool__product__unit','pool__profile').annotate(quantity=Sum('quantity')):
        # Footprints stay separate: never draw incompatible cm as one series.
        key=(row['pool__product_id'],row['pool__product__name'],row['pool__product__unit'],row['pool__profile']);measured.setdefault(key,{})[row['document__date']]=row['quantity']
    sales=[];inventory=[]
    for index in range(days):
        day=first+timedelta(days=index);net=Decimal(0)
        for row in by_day.get(day,[]):
            amount=(row['dr'] or Decimal(0))-(row['cr'] or Decimal(0))
            if row['account__code']=='SALES':net-=amount
            if row['account__code'] in inventory_codes:value+=amount
        sales.append({'date':day.isoformat(),'amount':str(money(net))});inventory.append({'date':day.isoformat(),'amount':str(money(value))})
    aging=reports.aging(ctx,scope)['totals']
    production=[{'product':product,'name':name,'unit':unit,'profile':profile,'points':[{'date':(first+timedelta(days=i)).isoformat(),'quantity':str(values.get(first+timedelta(days=i),0))} for i in range(days)]} for (product,name,unit,profile),values in sorted(measured.items())]
    return {'sales':sales,'inventory':inventory,'aging':{key:aging[key] for key in ('current','1_30','31_60','61_90','over_90')},'production':production,'from':first,'to':through,
            'basis':'Posted net sales, historical physical-inventory control carrying value excluding WIP, current invoice aging at the selected date, and measured finished output by unit/footprint. No forecast, density conversion or sampled table totals.'}
