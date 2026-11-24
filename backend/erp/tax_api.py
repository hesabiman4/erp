"""Business-scoped immutable tax rule administration and nonposting preview."""
from django.core.exceptions import ValidationError
from .api import Boundary,response
from .tax_models import TaxSchedule
from .taxation import change,calculate,read_permission,snapshot,schedule_for


def offset_for(request):
    try:value=int(request.query_params.get('offset',0))
    except (ValueError,TypeError):raise ValidationError('Select a valid tax history offset.')
    if not 0<=value<=10_000_000:raise ValidationError('Select a valid tax history offset.')
    return value


class TaxSchedulesAPI(Boundary):
    def get(self,request,pk=None):
        ctx=self.ctx(request);read_permission(ctx)
        if pk is not None:
            rule=schedule_for(ctx,pk);offset=offset_for(request)
            events=rule.changes.select_related('actor').order_by('-pk');count=events.count()
            return response({'rule':snapshot(rule),'history_total':count,'offset':offset,
                'next_offset':offset+50 if offset+50<count else None,
                'history':[{'id':event.pk,'operation':event.operation,'actor':event.actor.get_full_name() or event.actor.username,
                    'reason':event.reason,'before':event.before,'after':event.after,'at':event.at} for event in events[offset:offset+50]],
                'financial_posting':False})
        query=TaxSchedule.objects.filter(business=ctx.business).order_by('-effective_from','-pk')
        kind=request.query_params.get('tax_type')
        if kind:
            if kind not in dict(TaxSchedule.TAX_TYPES):raise ValidationError('Select a valid tax schedule type.')
            query=query.filter(tax_type=kind)
        offset=offset_for(request)
        count=query.count()
        return response({'results':[snapshot(rule) for rule in query[offset:offset+100]],'count':count,'offset':offset,
            'next_offset':offset+100 if offset+100<count else None,
            'unconfirmed_count':TaxSchedule.objects.filter(business=ctx.business,requires_confirmation=True).count(),
            'automatic_posting_enabled':False,'financial_posting':False})

    def post(self,request,pk=None):
        ctx=self.ctx(request)
        if not isinstance(request.data,dict):raise ValidationError('Select a valid tax schedule action.')
        operation=request.data.get('action')
        if operation=='preview':
            read_permission(ctx)
            if pk is None or set(request.data)-{'action','amount'}:raise ValidationError('Select a valid tax schedule action.')
            rule=schedule_for(ctx,pk)
            # Explicitly nonposting and visibly unconfirmed previews support review.
            return response(calculate(rule,request.data.get('amount'),require_confirmed=False))
        if (operation=='create')!=(pk is None) or operation not in {'create','confirm','revoke'}:
            raise ValidationError('Select a valid tax schedule action.')
        result=change(ctx,operation,{k:v for k,v in request.data.items() if k!='action'},request.headers.get('Idempotency-Key'),pk)
        return response({'rule':result,'financial_posting':False},status=201 if operation=='create' else 200)
