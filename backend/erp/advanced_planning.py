"""Finite daily-capacity planning and measured production analysis.

Schedules are immutable core Documents, not another inventory or wage ledger.
Only the latest posted schedule per work order reserves capacity; source work
orders keep the authoritative lifecycle. Capacity checks use all work at the
center (including hidden demand) but never reveal hidden document details.
"""
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Sum
from .core import D, get_obj, get_product, get_warehouse
from .models import Document, WorkOrder, WorkCenter, JobCard, Block, Location

ZERO = Decimal('0')
STRATEGIES = ('best_fit', 'preserve_remnants', 'oldest_first')


def integer(value, name, lower=0, upper=1000000):
    value = D(value)
    if value != value.to_integral_value() or not lower <= value <= upper:
        raise ValidationError(f'{name} must be a whole number between {lower} and {upper}.')
    return int(value)


def latest_schedules(business):
    result = {}
    for doc in Document.objects.filter(business=business, kind__in=['capacity_schedule', 'capacity_work_order'], state='posted').order_by('-id'):
        ident = doc.result.get('work_order')
        if ident and ident not in result: result[ident] = doc
    return result


def capacity_usage(business, center_id, scheduled_date=None, exclude_work=None):
    """Shared daily capacity function for ordinary and multi-stage planning."""
    schedules = latest_schedules(business)
    works = WorkOrder.objects.filter(business=business).exclude(state='cancelled')
    usage = defaultdict(int)
    for work in works:
        if work.id == exclude_work: continue
        schedule = schedules.get(work.id)
        if schedule:
            for slot in schedule.result.get('slots', []):
                if slot['work_center'] == center_id:
                    usage[date.fromisoformat(slot['date'])] += slot['minutes']
        elif work.work_center_id == center_id:
            usage[work.scheduled_date] += work.planned_minutes
    return usage.get(scheduled_date, 0) if scheduled_date is not None else dict(usage)


def work_for(ctx, identifier):
    from .api import doc_permission
    work = get_obj(ctx, WorkOrder, identifier)
    get_product(ctx, work.product_id); get_warehouse(ctx, work.warehouse_id)
    doc_permission(ctx, work.source)
    if work.order_id:
        doc_permission(ctx, work.order)
        from .operations import _commercial_cancelled
        if _commercial_cancelled(ctx, work.order): raise ValidationError('The source order is closed; new capacity reservations are blocked.')
    return work


def preview_schedule(ctx, p, new_work=None):
    ctx.require('production.plan')
    from .growth import day
    work = new_work or work_for(ctx, p.get('work_order'))
    if work.state != 'planned' or (work.id and (work.job_cards.exists() or work.production_links.exists())):
        raise ValidationError('Only unstarted planned work can be rescheduled.')
    # A start batch has no production link until output; it is still started.
    if work.id and (Document.objects.filter(business=ctx.business, kind='production_start', state='posted', data__work_order=work.id).exists() or Document.objects.filter(business=ctx.business, kind='production_start', state='posted', data__work_order=str(work.id)).exists()):
        raise ValidationError('An existing WIP batch prevents rescheduling this work.')
    start = day(p.get('earliest_date'))
    if start < work.source.date: raise ValidationError('Schedule cannot precede the work-order planning date.')
    stages = p.get('stages')
    if not isinstance(stages, list) or not 1 <= len(stages) <= 20 or not all(isinstance(s, dict) for s in stages):
        raise ValidationError('Enter 1–20 sequential stages.')
    weekdays = p.get('working_weekdays', list(range(7)))
    if not isinstance(weekdays, list) or not weekdays or len(weekdays) > 7:
        raise ValidationError('Choose the actual working weekdays (Monday=0 through Sunday=6).')
    weekdays = set(integer(v, 'Working weekday', 0, 6) for v in weekdays)
    horizon = integer(p.get('horizon_days', 180), 'Planning horizon', 1, 366)
    deadline = start + timedelta(days=horizon - 1)
    transit = integer(p.get('delivery_days', 0), 'Delivery lead days', 0, 365)
    normalized = []; total = 0
    for index, stage in enumerate(stages):
        center = get_obj(ctx, WorkCenter, stage.get('work_center'))
        if not center.active or center.location_id != work.warehouse.location_id:
            raise ValidationError('All stages need active work centers at the production location.')
        name = str(stage.get('name') or '').strip()
        if not name or len(name) > 150: raise ValidationError('Each stage needs a name, maximum 150 characters.')
        minutes = integer(stage.get('minutes'), 'Stage minutes', 1, 144000)
        wait = integer(stage.get('wait_days', 0), 'Wait days before a stage', 0, 365)
        normalized.append((center, name, minutes, wait)); total += minutes
    if total != work.planned_minutes:
        raise ValidationError('Stage minutes must total the existing work order planned minutes; revise the work order explicitly if its estimate is wrong.')
    existing = {center.id: capacity_usage(ctx.business, center.id, exclude_work=work.id) for center, *_ in normalized}
    additions = defaultdict(int); slots = []; cursor = start; summaries = []
    for index, (center, name, minutes, wait) in enumerate(normalized):
        cursor += timedelta(days=wait)
        remaining = minutes; first = None; last = None
        while remaining:
            if cursor > deadline: raise ValidationError('Insufficient capacity inside the reviewed horizon; increase it or revise the work estimate.')
            available = center.daily_minutes - existing[center.id].get(cursor, 0) - additions[(center.id, cursor)] if cursor.weekday() in weekdays else 0
            if available > 0:
                amount = min(available, remaining)
                slots.append({'stage': index, 'name': name, 'work_center': center.id, 'center_name': center.name, 'date': cursor.isoformat(), 'minutes': amount})
                additions[(center.id, cursor)] += amount; remaining -= amount
                first = first or cursor; last = cursor
            if remaining: cursor += timedelta(days=1)
        summaries.append({'index': index, 'name': name, 'work_center': center.id, 'minutes': minutes, 'wait_days': wait, 'start': first.isoformat(), 'finish': last.isoformat()})
        # Daily capacity has no intra-day sequencing: a subsequent stage starts
        # on the next day, even at another center. Never promise unsafe overlap.
        cursor += timedelta(days=1)
    finish = date.fromisoformat(slots[-1]['date'])
    requested = day(p['requested_date']) if p.get('requested_date') else None
    delivery = finish + timedelta(days=transit)
    return {'work_order': work.id, 'number': work.number, 'product': work.product_id, 'warehouse': work.warehouse_id,
            'earliest_date': start.isoformat(), 'finish_date': finish.isoformat(), 'delivery_date': delivery.isoformat(),
            'requested_date': requested.isoformat() if requested else None, 'on_time': delivery <= requested if requested else None,
            'stages': summaries, 'slots': slots, 'working_weekdays': sorted(weekdays), 'planned_minutes': total,
            'delivery_days': transit, 'reserved': False,
            'basis': 'Finite daily center capacity; sequential stages start on successive days. Wait and delivery days are calendar days. No material, staffing or machine-breakdown availability guarantee.'}


def schedule_work(ctx, p, doc):
    from .growth import day
    if day(p.get('earliest_date')) < doc.date: raise ValidationError('New reservations cannot start before their posting date.')
    result = preview_schedule(ctx, p)
    work = work_for(ctx, result['work_order'])
    work.scheduled_date = date.fromisoformat(result['slots'][0]['date'])
    work.save(update_fields=['scheduled_date'])
    doc.reference = work.source; doc.warehouse = work.warehouse; doc.location = work.warehouse.location
    ctx.lines.add(work.product.line)
    return {**result, 'reserved': True, 'stock_posted': False, 'payroll_posted': False}


def new_work_values(ctx, p):
    from .growth import day
    from .api import doc_permission
    warehouse = get_warehouse(ctx, p.get('warehouse')); product = get_product(ctx, p.get('product'))
    if warehouse.kind == 'transit' or product.kind != 'finished': raise ValidationError('Choose a physical production warehouse and finished product.')
    if ctx.business.manufacturing_mode == 'trading': raise ValidationError('Production planning is disabled for this trading business.')
    quantity = D(p.get('planned_quantity'))
    if quantity <= 0 or quantity != quantity.quantize(Decimal('.000001')): raise ValidationError('Planned quantity must be positive with at most six decimal places.')
    if product.unit == 'each' and quantity != quantity.to_integral_value(): raise ValidationError('Counted finished products require whole output quantities.')
    minutes = integer(p.get('planned_minutes'), 'Total planned minutes', 1, 144000)
    order = get_obj(ctx, Document, p['order']) if p.get('order') else None
    source_date = day(p.get('date'))
    if order:
        from .operations import _commercial_cancelled
        doc_permission(ctx, order)
        if order.kind != 'sales_order' or order.state != 'posted' or order.warehouse_id != warehouse.id or order.date > source_date:
            raise ValidationError('Select a posted sales order from this warehouse, dated no later than planning.')
        if _commercial_cancelled(ctx, order): raise ValidationError('The source order is closed.')
    return SimpleNamespace(id=None, number='', product=product, product_id=product.id, warehouse=warehouse, warehouse_id=warehouse.id,
                           planned_quantity=quantity, planned_minutes=minutes, order=order, order_id=order.id if order else None,
                           source=SimpleNamespace(date=source_date), state='planned')


def preview_new_work(ctx, p):
    ctx.require('production.plan')
    work = new_work_values(ctx, p)
    return preview_schedule(ctx, p, work)


def create_scheduled_work(ctx, p, doc):
    from .growth import day
    if day(p.get('earliest_date')) < doc.date: raise ValidationError('New work cannot reserve capacity before its posting date.')
    values = new_work_values(ctx, p); result = preview_schedule(ctx, p, values)
    work = WorkOrder.objects.create(business=ctx.business, number=doc.number, product=values.product, warehouse=values.warehouse,
                                   work_center_id=result['slots'][0]['work_center'], order=values.order, planned_quantity=values.planned_quantity,
                                   scheduled_date=result['slots'][0]['date'], planned_minutes=values.planned_minutes, notes=str(p.get('notes', '')), source=doc)
    doc.reference = values.order; doc.warehouse = values.warehouse; doc.location = values.warehouse.location
    return {**result, 'work_order': work.id, 'number': work.number, 'reserved': True, 'stock_posted': False, 'payroll_posted': False}


def planning_board(ctx, params):
    from .api import doc_permission
    if not (ctx.has('production.view') or ctx.has('production.plan')): ctx.require('production.view')
    selected = get_obj(ctx, Location, params['location']).id if params.get('location') else None
    schedules = latest_schedules(ctx.business); rows = []; centers = []
    for center in WorkCenter.objects.filter(business=ctx.business, active=True).order_by('name'):
        if not ctx.location_allowed(center.location_id) or selected and center.location_id != selected: continue
        centers.append({'id': center.id, 'name': center.name, 'location': center.location_id, 'daily_minutes': center.daily_minutes})
    for work in WorkOrder.objects.filter(business=ctx.business, state__in=['planned', 'in_progress']).select_related('product', 'warehouse__location', 'source', 'order').order_by('scheduled_date', 'id'):
        try:
            get_warehouse(ctx, work.warehouse_id); get_product(ctx, work.product_id); doc_permission(ctx, work.source)
            if work.order_id: doc_permission(ctx, work.order)
        except (ValidationError, PermissionDenied): continue
        if selected and work.warehouse.location_id != selected: continue
        schedule = schedules.get(work.id)
        started = work.job_cards.exists() or work.production_links.exists() or Document.objects.filter(business=ctx.business, kind='production_start', state='posted', data__work_order=work.id).exists() or Document.objects.filter(business=ctx.business, kind='production_start', state='posted', data__work_order=str(work.id)).exists()
        rows.append({'id': work.id, 'number': work.number, 'product_name': work.product.name, 'warehouse_name': work.warehouse.name,
                     'work_center': work.work_center_id, 'planned_minutes': work.planned_minutes, 'planned_quantity': work.planned_quantity,
                     'unit': work.product.unit, 'state': work.state, 'scheduled_date': work.scheduled_date, 'can_schedule': work.state == 'planned' and not started,
                     'schedule': {'id': schedule.id, **schedule.result} if schedule else None})
    return {'results': rows, 'centers': centers, 'basis': 'Published schedules preserve their original slot snapshot; later closure releases future planning capacity without rewriting history.'}


def efficiency(ctx, params):
    """Actual measured inputs/outputs with no physical kg-to-cm inference."""
    from .api import document_scope, doc_permission
    from .growth import day
    ctx.require('production.view')
    loss_limit = D(params['loss_limit_percent']) if params.get('loss_limit_percent') not in (None, '') else None
    if loss_limit is not None and not 0 <= loss_limit <= 100:
        raise ValidationError('Loss review threshold must be between 0 and 100 percent.')
    query = document_scope(ctx).filter(state='posted', kind__in=['production', 'production_bom', 'production_start']).select_related('warehouse', 'location').order_by('-date', '-id')
    if params.get('from'): query = query.filter(date__gte=day(params['from']))
    if params.get('to'): query = query.filter(date__lte=day(params['to']))
    if params.get('location'): query = query.filter(location=get_obj(ctx, Location, params['location']))
    rows = []
    limit = integer(params.get('limit', 100), 'Batch limit', 1, 200)
    for batch in query[:limit]:
        try: doc_permission(ctx, batch)
        except (PermissionDenied, ValidationError): continue
        events = [batch]
        if batch.kind == 'production_start':
            # Do not leak figures from a partially visible staged batch.
            events += list(Document.objects.filter(business=ctx.business, reference=batch, state='posted').order_by('id'))
            try:
                for event in events:
                    get_obj(ctx, Document, event.id)
                    if event.kind not in {'production_consume', 'production_material_return'}: doc_permission(ctx, event)
            except (PermissionDenied, ValidationError): continue
        outputs = []; inputs = defaultdict(lambda: ZERO); costs = ZERO; loss = ZERO; wip = ZERO
        for event in events:
            costs += sum((entry.debit for entry in event.entries.filter(account__code='WIP')), ZERO)
            if event.kind == 'production_material_return': costs -= sum((entry.credit for entry in event.entries.filter(account__code='WIP')), ZERO)
            loss += D(event.result.get('abnormal_loss', '0')); wip += D(event.result.get('wip_in', '0')) - D(event.result.get('wip_out', '0'))
            if ctx.has('consumption.view'):
                sign = -1 if event.kind == 'production_material_return' else 1
                for row in event.result.get('lines' if sign == -1 else 'inputs', []): inputs[row['product']] += sign * D(row['quantity'])
            for row in event.result.get('outputs', []):
                product = get_product(ctx, row['product'])
                pieces = list(Block.objects.filter(business=ctx.business, batch=event, product=product, pk__in=row.get('blocks', [])))
                for block in pieces:
                    outputs.append({'product': product.id, 'product_name': product.name, 'unit': 'cm', 'profile': block.profile,
                                    'quantity': str(block.initial_height_mm / 10), 'block': block.id, 'code': block.code,
                                    'volume_m3': str(block.initial_height_mm * block.length_mm * block.width_mm / Decimal('1000000000'))})
                if not pieces:
                    outputs.append({'product': product.id, 'product_name': product.name, 'unit': product.unit, 'profile': '', 'quantity': row['quantity']})
        trims = []
        output_ids = [row['block'] for row in outputs if row.get('block')]
        for trim in Document.objects.filter(business=ctx.business, state='posted', kind='trim', result__block__in=output_ids):
            try: doc_permission(ctx, trim)
            except (PermissionDenied, ValidationError): continue
            # Heights are comparable only within this one original full face.
            result = trim.result; total = sum((D(result.get(k, 0)) for k in ('main_height_mm', 'top_height_mm', 'bottom_height_mm', 'loss_mm')), ZERO)
            loss_percent = D(result['loss_mm']) / total * 100 if total else None
            trims.append({'number': trim.number, 'block': result['block'], 'main_mm': result['main_height_mm'], 'top_mm': result['top_height_mm'],
                          'bottom_mm': result['bottom_height_mm'], 'loss_mm': result['loss_mm'],
                          'loss_percent': str(loss_percent.quantize(Decimal('.000001'))) if loss_percent is not None else None,
                          'review_loss': loss_percent > loss_limit if loss_limit is not None and loss_percent is not None else None,
                          'main_yield_percent': str((D(result['main_height_mm']) / total * 100).quantize(Decimal('.01'))) if total else None})
        row = {'id': batch.id, 'number': batch.number, 'date': batch.date, 'warehouse_name': batch.warehouse.name if batch.warehouse else '',
               'outputs': outputs, 'trims': trims, 'completed': bool(outputs), 'formula_required': False,
               'flagged_losses': sum(1 for trim in trims if trim['review_loss']) if loss_limit is not None else None}
        if ctx.has('consumption.view'):
            row['inputs'] = [{'product': identifier, 'product_name': get_product(ctx, identifier).name,
                              'quantity': str(quantity), 'unit': get_product(ctx, identifier).unit} for identifier, quantity in inputs.items()]
        if ctx.has('cost.view'): row.update(total_cost=str(costs), abnormal_loss=str(loss), wip_remaining=str(wip))
        rows.append(row)
    return {'results': rows, 'limit': limit, 'loss_limit_percent': str(loss_limit) if loss_limit is not None else None,
            'basis': 'Actual batch quantities, initial measured output and original trim events. Optional trim-loss threshold marks evidence for review only and posts no expense. Compare like grades/footprints/units; kg input is never treated as cm output. No formula or theoretical yield is inferred.'}


def cutting_alternatives(ctx, p):
    from .order_cutting import preview
    rows = []
    for strategy in STRATEGIES:
        try: rows.append({'strategy': strategy, 'feasible': True, **preview(ctx, {**p, 'strategy': strategy})})
        except ValidationError as exc: rows.append({'strategy': strategy, 'feasible': False, 'reason': ' '.join(exc.messages)})
    return {'alternatives': rows, 'basis': 'Three deterministic heuristics. No global optimum is claimed. Posting recomputes current availability; another operator may reserve stock meanwhile.'}


OPERATIONS = {'capacity_schedule': ('production.plan', schedule_work), 'capacity_work_order': ('production.plan', create_scheduled_work)}


from .api import Boundary, response

class PlanningAPI(Boundary):
    def get(self, request, section):
        params = dict(request.query_params.items())
        if request.headers.get('X-Location-ID'): params['location'] = request.headers['X-Location-ID']
        if section == 'board': return response(planning_board(self.ctx(request), params))
        if section == 'efficiency': return response(efficiency(self.ctx(request), params))
        if section == 'demand':
            from .demand_planning import suggestion
            return response(suggestion(self.ctx(request), params))
        raise ValidationError('Unknown planning section.')

    def post(self, request, section):
        ctx = self.ctx(request)
        if not isinstance(request.data, dict): raise ValidationError('Send a planning object with explicitly reviewed fields.')
        if section == 'preview': return response(preview_schedule(ctx, request.data))
        if section == 'new-preview': return response(preview_new_work(ctx, request.data))
        if section == 'cutting': return response(cutting_alternatives(ctx, request.data))
        raise ValidationError('Use a supported planning preview; reservations use the operation posting endpoint.')
