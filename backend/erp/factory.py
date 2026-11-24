"""Permission-scoped shop-floor read model over posted production records."""
from decimal import Decimal
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Sum
from .api import Boundary, response, doc_permission
from .core import get_obj, get_product, get_warehouse
from .models import Document, WorkOrder, WorkProduction, JobCard, Location
from .growth import produced


def board(ctx, params):
    if not any(ctx.has(p) for p in ('production.view', 'production.post', 'production.plan')):
        raise PermissionDenied('Factory access is restricted.')
    location = params.get('location')
    if location:
        location = get_obj(ctx, Location, location).id
    rows = []
    for work in WorkOrder.objects.filter(business=ctx.business, state__in=['planned', 'in_progress']).select_related('product', 'warehouse__location', 'work_center', 'order').order_by('scheduled_date', 'id'):
        try:
            get_warehouse(ctx, work.warehouse_id); get_product(ctx, work.product_id)
            doc_permission(ctx, work.source)
            if work.order_id: doc_permission(ctx, work.order)
        except (PermissionDenied, ValidationError):
            continue
        if location and work.warehouse.location_id != location: continue
        batches = []
        for batch in Document.objects.filter(business=ctx.business, kind='production_start', state='posted', data__work_order=str(work.id)).order_by('id'):
            # JSON identifiers can be integers or form strings.
            batches.append(batch)
        for batch in Document.objects.filter(business=ctx.business, kind='production_start', state='posted', data__work_order=work.id).order_by('id'):
            if batch.pk not in {b.pk for b in batches}: batches.append(batch)
        projected = []
        for batch in batches:
            try: doc_permission(ctx, batch)
            except (PermissionDenied, ValidationError): continue
            events = Document.objects.filter(business=ctx.business, reference=batch, state='posted')
            value = Decimal('0')
            for event in events:
                value += Decimal(str(event.result.get('wip_in', '0'))) - Decimal(str(event.result.get('wip_out', '0')))
            completed = events.filter(kind='production_complete').exists()
            item = {'id': batch.id, 'number': batch.number, 'date': batch.date, 'has_completion': completed, 'can_consume': not completed, 'can_complete': value > 0}
            if ctx.has('cost.view'): item['wip_remaining'] = value
            projected.append(item)
        from .operations import _commercial_cancelled
        closed = bool(work.order_id and _commercial_cancelled(ctx, work.order))
        actual = produced(work)
        rows.append({'id': work.id, 'number': work.number, 'product': work.product_id, 'product_name': work.product.name, 'unit': work.product.unit,
                     'warehouse': work.warehouse_id, 'warehouse_name': work.warehouse.name, 'location': work.warehouse.location_id,
                     'center_name': work.work_center.name, 'scheduled_date': work.scheduled_date, 'state': work.state,
                     'planned_quantity': work.planned_quantity, 'actual_quantity': actual, 'planned_minutes': work.planned_minutes,
                     'actual_minutes': JobCard.objects.filter(business=ctx.business, work_order=work).aggregate(v=Sum('minutes'))['v'] or 0,
                     'source_closed': closed, 'batches': projected})
    return {'results': rows, 'count': len(rows), 'basis': 'Posted output and actual job-card time; planning does not post wages or revenue.'}


class FactoryAPI(Boundary):
    def get(self, request):
        params = dict(request.query_params.items())
        if request.headers.get('X-Location-ID'): params['location'] = request.headers['X-Location-ID']
        return response(board(self.ctx(request), params))
