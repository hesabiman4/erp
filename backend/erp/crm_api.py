"""Scoped, paginated commercial pipeline with preserved follow-up evidence."""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q, OuterRef, Subquery, Value, F, Count, Prefetch, BigIntegerField
from django.db.models.functions import Coalesce
from django.utils import timezone
from .api import Boundary, response, doc_permission
from .core import get_obj
from .models import Location
from .crm_models import CRMOpportunity, CRMEvent
from .crm import opportunity_for, scope, state, eligible, STAGES, day


def row(ctx,item,as_of):
    stage,assigned=scope(ctx,item)
    activities=list(item.activities.all())
    pending=[a for a in activities if not a.completed_by_id]
    next_action=min(pending,key=lambda a:(a.due_date,a.id)) if pending else None
    owner=next((event.assigned for event in reversed(list(item.events.all())) if event.assigned_id),item.assigned)
    return {'id':item.id,'number':item.source.number,'title':item.title,'date':item.source.date,'location':item.location_id,'location_name':item.location.name,'product_lines':item.product_lines,
        'prospect_name':item.prospect_name,'party':item.party_id,'phone':item.phone,'stage':stage,'assigned':assigned,'assigned_name':(owner.user.get_full_name() or owner.user.username) if owner else 'Inactive / scope changed',
        'expected_amount':item.expected_amount,'expected_date':item.expected_date,'currency':'AFN','next_action':{'id':next_action.id,'task':next_action.task,'due_date':next_action.due_date,'overdue':next_action.due_date<as_of} if next_action else None,
        'pending_activities':len(pending),'can_act':assigned==ctx.membership.id or ctx.has('crm.manage'),'note':item.note,'financial_posting':False,'overdue_as_of':as_of,'pipeline_basis':'Current recorded stage and ownership; the reference date only evaluates overdue activities.'}


def detail(ctx,item,as_of):
    value=row(ctx,item,as_of);events=[];quotes=[]
    for event in item.events.select_related('source','assigned__user','quotation'):
        record={'id':event.id,'date':event.source.date,'kind':event.kind,'stage':event.stage,'assigned':event.assigned_id,'reason':event.reason,'number':event.source.number}
        if event.quotation_id:
            try:
                doc_permission(ctx,event.quotation)
                quotes.append({'id':event.quotation_id,'number':event.quotation.number,'date':event.quotation.date,'amount':event.quotation.amount,'state':event.quotation.state})
                record['quotation']=event.quotation_id
            except (PermissionDenied,ValidationError):record['quotation_restricted']=True
        events.append(record)
    value['events']=events;value['quotations']=quotes
    value['activities']=[{'id':a.id,'assigned':a.assigned_id,'assigned_name':a.assigned.user.get_full_name() or a.assigned.user.username,'due_date':a.due_date,'task':a.task,'date':a.source.date,
        'done':bool(a.completed_by_id),'completed_date':a.completed_by.date if a.completed_by_id else None,'outcome':a.completed_by.result.get('outcome','') if a.completed_by_id else '',
        'overdue':not a.completed_by_id and a.due_date<as_of,'can_complete':not a.completed_by_id and (a.assigned_id==ctx.membership.id or ctx.has('crm.manage'))} for a in item.activities.select_related('assigned__user','source','completed_by').order_by('due_date','id')]
    value['assignees']=[{'id':m.id,'name':m.user.get_full_name() or m.user.username} for m in eligible(ctx,item)] if value['can_act'] else []
    return value


class CRMAPI(Boundary):
    def get(self,request):
        ctx=self.ctx(request);ctx.require('crm.view')
        as_of=day(request.query_params.get('as_of') or timezone.localdate())
        if request.query_params.get('opportunity'):
            return response(detail(ctx,opportunity_for(ctx,request.query_params['opportunity']),as_of))
        try:offset=int(request.query_params.get('offset',0));limit=int(request.query_params.get('limit',30))
        except (TypeError,ValueError):raise ValidationError('Use integer pagination.')
        if offset<0 or not 1<=limit<=100:raise ValidationError('Use a nonnegative offset and limit one to 100.')
        requested_stage=request.query_params.get('stage')
        if requested_stage and requested_stage not in STAGES:raise ValidationError('Unknown pipeline stage.')
        event_query=CRMEvent.objects.filter(opportunity_id=OuterRef('pk')).order_by('-id')
        query=CRMOpportunity.objects.filter(business=ctx.business,product_lines__contained_by=ctx.membership.product_lines).annotate(
            current_stage=Coalesce(Subquery(event_query.exclude(stage='').values('stage')[:1]),Value('new')),
            current_owner=Coalesce(Subquery(event_query.filter(assigned__isnull=False).values('assigned_id')[:1]),F('assigned_id'),output_field=BigIntegerField()))
        if not (ctx.has('crm.manage') or ctx.has('crm.read_all')):
            query=query.filter(Q(current_owner=ctx.membership.id)|Q(activities__assigned=ctx.membership)).distinct()
        location=request.headers.get('X-Location-ID') or request.query_params.get('location')
        if location:query=query.filter(location=get_obj(ctx,Location,location))
        elif not ctx.membership.all_locations:query=query.filter(location_id__in=ctx.membership.location_ids)
        search=str(request.query_params.get('q','')).strip()
        if len(search)>180:raise ValidationError('Search is too long.')
        if search:query=query.filter(Q(title__icontains=search)|Q(prospect_name__icontains=search)|Q(phone__icontains=search))
        # All count filters are the same business/location/line/assignment boundary
        # as detail. SQL counts/page selection do not load the entire CRM history.
        counts={stage:0 for stage in STAGES}
        for value in query.order_by().values('current_stage').annotate(total=Count('id',distinct=True)):
            counts[value['current_stage']]=value['total']
        if requested_stage:query=query.filter(current_stage=requested_stage)
        visible=query.count();results=[]
        query=query.select_related('location','source','assigned__user').prefetch_related(Prefetch('events',queryset=CRMEvent.objects.select_related('assigned__user').order_by('id')),'activities').order_by('-id')
        for item in query[offset:offset+limit]:
            try:record=row(ctx,item,as_of)
            except (PermissionDenied,ValidationError):continue
            results.append(record)
        # Assignee choices reveal only active staff eligible for this full location/line scope.
        choices=[]
        if ctx.has('crm.manage'):
            for loc in ([get_obj(ctx,Location,location)] if location else Location.objects.filter(business=ctx.business)):
                if not ctx.location_allowed(loc.id):continue
                for m in eligible(ctx,location=loc.id,lines=[]):
                    if m.id not in {r['id'] for r in choices}:choices.append({'id':m.id,'name':m.user.get_full_name() or m.user.username})
        else:choices=[{'id':ctx.membership.id,'name':ctx.user.get_full_name() or ctx.user.username}]
        return response({'results':results,'count':visible,'stage_counts':counts,'next_offset':offset+limit if visible>offset+limit else None,'as_of':as_of,'stages':STAGES,'assignees':choices,'current_member':ctx.membership.id,'basis':'Commercial expected AFN values; no revenue, stock, cash or receivable is recognized by CRM stages or follow-up activities.'})
