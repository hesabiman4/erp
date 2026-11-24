"""Purchasing assurance and warehouse evidence; never a second stock ledger."""
import unicodedata
from datetime import date
from decimal import Decimal
from django.core.exceptions import PermissionDenied, ValidationError
from .core import D, get_obj, get_product, get_warehouse, execute, money
from .models import Document, Membership, Party, Block, Product, StockPool
from .operations import posted, positive, _commercial_index
from .procurement_models import SupplierClaim, SupplierClaimResolution, CycleCountSession, WeighingDevice, ScaleCalibration, WeightMeasurement

ZERO = Decimal('0')


def source_document(ctx, identifier, kinds):
    from .api import doc_permission
    source = posted(ctx, identifier, kinds)
    doc_permission(ctx, source)
    return source


def normalize_reference(value):
    # Supplier papers often mix Persian/Arabic digits, spaces and hyphens.
    # Normalize those differences without changing the saved original text.
    value = unicodedata.normalize('NFKC', str(value)).casefold()
    return ''.join(str(unicodedata.digit(c)) if c.isdigit() else c for c in value if c.isalnum())


def duplicate_reference(ctx, supplier, reference):
    normalized = normalize_reference(reference)
    if not normalized:
        return None
    for document in Document.objects.filter(business=ctx.business, party=supplier, state='posted', kind__in=['purchase_bill', 'expense_post', 'asset_acquire']):
        original = document.data.get('supplier_reference', '')
        if original and normalize_reference(original) == normalized:
            return document
    return None


def receipt_match(ctx, receipt):
    """Compare source quantities and prices without silently changing valuation."""
    receipt = source_document(ctx, receipt.pk, ['purchase_receive'])
    order = source_document(ctx, receipt.result['order'], ['purchase_order']) if receipt.result.get('order') else None
    bills = list(Document.objects.filter(business=ctx.business, reference=receipt, state='posted', kind='purchase_bill'))
    returns = list(Document.objects.filter(business=ctx.business, state='posted', kind='purchase_return', result__receipt=receipt.pk))
    for document in bills + returns:
        source_document(ctx, document.pk, [document.kind])
    order_receipts=list(Document.objects.filter(business=ctx.business,state='posted',kind='purchase_receive',result__order=order.pk)) if order else []
    for document in order_receipts:source_document(ctx,document.pk,['purchase_receive'])
    lines = []
    for line in receipt.result.get('lines', []):
        product = get_product(ctx, line['product'])
        ordered = order.result['lines'][int(line.get('order_index', line['index']))] if order else None
        billed = sum((D(x['quantity']) for doc in bills for x in doc.result.get('lines', []) if x['index'] == line['index']), ZERO)
        returned = sum((D(x['quantity']) for doc in returns for x in doc.result.get('lines', []) if x['index'] == line['index']), ZERO)
        order_qty = D(ordered['quantity']) if ordered else None
        received_order = sum((D(x['quantity']) for doc in order_receipts for x in doc.result.get('lines', []) if x.get('order_index') == line.get('order_index')), ZERO) if order else None
        row = {'index': line['index'], 'product': product.pk, 'product_name': product.name, 'unit': product.unit, 'received': line['quantity'], 'billed': str(billed), 'returned': str(returned), 'ordered': str(order_qty) if order else None, 'order_received_total': str(received_order) if order else None, 'order_outstanding': str(max(ZERO, order_qty - received_order)) if order else None, 'flags': []}
        if not order: row['flags'].append('no_purchase_order')
        if order and received_order < order_qty: row['flags'].append('order_partially_received')
        if billed < D(line['quantity']) - returned: row['flags'].append('unbilled_goods')
        if ctx.has('cost.view'):
            actual_price = D(receipt.data['lines'][int(line['index'])].get('unit_cost', receipt.data['lines'][int(line['index'])].get('price', '0')))
            row.update({'received_unit_cost': line['unit_cost'], 'receipt_base_unit_cost': str(actual_price), 'receipt_cost': line['cost']})
            if order:
                row['ordered_unit_price'] = ordered['unit_cost']
                row['unit_price_variance'] = str(actual_price - D(ordered['unit_cost']))
                if actual_price != D(ordered['unit_cost']): row['flags'].append('purchase_price_difference')
        lines.append(row)
    result = {'id': receipt.pk, 'number': receipt.number, 'date': receipt.date, 'supplier': receipt.party_id, 'supplier_name': receipt.party.name if receipt.party_id else '', 'warehouse': receipt.warehouse_id, 'order': order.pk if order else None, 'order_number': order.number if order else '', 'lines': lines, 'bills': [{'id': doc.pk, 'number': doc.number, 'supplier_reference': doc.data.get('supplier_reference', '')} for doc in bills], 'note': 'Posted bills clear actual receipt carrying values. Price differences require the supported reviewed cost workflow; matching does not revalue stock.'}
    return result


def supplier_claim(ctx, payload, doc):
    source = source_document(ctx, payload['document'], ['purchase_receive', 'purchase_order'])
    if not source.party_id: raise ValidationError('A supplier-linked purchase document is required.')
    index = _commercial_index(payload['index'])
    lines = source.result.get('lines', [])
    if index < 0 or index >= len(lines): raise ValidationError('Select a valid purchase item.')
    original = lines[index]
    product = get_product(ctx, original['product'])
    qty = positive(payload['quantity'])
    if qty != qty.quantize(Decimal('.000001')): raise ValidationError('Claim quantity supports six decimal places.')
    reason = str(payload.get('reason', ''))
    description = str(payload.get('description', '')).strip()
    if reason not in {'shortage', 'damage', 'quality', 'price', 'other'} or not description: raise ValidationError('Select the claim reason and describe the evidence.')
    if source.kind == 'purchase_order' and reason != 'shortage': raise ValidationError('An order-only claim is for undelivered shortage; received goods use the receipt.')
    maximum = D(original['quantity'])
    if source.kind == 'purchase_order':
        fulfilled = sum((D(line['quantity']) for received in Document.objects.filter(business=ctx.business, state='posted', kind='purchase_receive', result__order=source.pk) for line in received.result.get('lines', []) if line.get('order_index') == index), ZERO)
        maximum -= fulfilled
    claimed = sum((item.quantity for item in SupplierClaim.objects.filter(business=ctx.business, document=source, line_index=index).exclude(state='cancelled')), ZERO)
    if qty + claimed > maximum: raise ValidationError('Claim exceeds the original unclaimed received/undelivered quantity.')
    claim = SupplierClaim.objects.create(business=ctx.business, supplier=source.party, document=source, line_index=index, product=product, quantity=qty, reason=reason, description=description, source=doc)
    doc.reference, doc.party, doc.location, doc.warehouse = source, source.party, source.location, source.warehouse
    return {'claim': claim.pk, 'document': source.pk, 'product': product.pk, 'quantity': str(qty), 'reason': reason, 'description': description, 'state': 'open', 'posting_effect': 'none'}


def visible_claim(ctx, identifier):
    claim = get_obj(ctx, SupplierClaim, identifier)
    source_document(ctx, claim.document_id, ['purchase_receive', 'purchase_order'])
    get_product(ctx, claim.product_id)
    return claim


def supplier_claim_resolve(ctx, payload, doc):
    claim = visible_claim(ctx, payload['claim'])
    if claim.state != 'open': raise ValidationError('This supplier claim is already resolved.')
    note = str(payload.get('note', '')).strip()
    outcome = str(payload.get('outcome', ''))
    if not note or outcome not in {'returned_credit', 'replacement_received', 'accepted_no_credit', 'rejected', 'cancelled'}: raise ValidationError('Select the resolution and record the agreed outcome.')
    actual = None
    if outcome == 'returned_credit':
        if claim.document.kind != 'purchase_receive': raise ValidationError('A supplier return must belong to received goods.')
        actual = source_document(ctx, payload.get('financial_document'), ['purchase_return'])
        qty = sum((D(line['quantity']) for line in actual.result.get('lines', []) if line.get('index') == claim.line_index and line.get('product') == claim.product_id), ZERO)
        if actual.result.get('receipt') != claim.document_id or actual.party_id != claim.supplier_id or qty != claim.quantity: raise ValidationError('Link a posted supplier return for exactly this claimed receipt item and quantity.')
    elif outcome == 'replacement_received':
        actual = source_document(ctx, payload.get('financial_document'), ['purchase_receive'])
        qty = sum((D(line['quantity']) for line in actual.result.get('lines', []) if line.get('product') == claim.product_id), ZERO)
        if actual.pk == claim.document_id or actual.party_id != claim.supplier_id or qty != claim.quantity: raise ValidationError('Link a separate posted receipt for exactly this supplier, item and quantity. Its financial treatment remains in that receipt.')
    elif payload.get('financial_document'): raise ValidationError('Only a real returned-credit or replacement resolution links a posted document.')
    if actual and actual.date > doc.date: raise ValidationError('Resolution cannot precede its actual supporting event.')
    SupplierClaimResolution.objects.create(business=ctx.business, claim=claim, outcome=outcome, financial_document=actual, note=note, source=doc)
    claim.state = 'cancelled' if outcome == 'cancelled' else 'resolved'; claim.save(update_fields=['state'])
    doc.reference, doc.party, doc.location, doc.warehouse = claim.source, claim.supplier, claim.document.location, claim.document.warehouse
    return {'claim': claim.pk, 'outcome': outcome, 'financial_document': actual.pk if actual else None, 'note': note, 'posting_effect': 'none'}


def visible_count(ctx, identifier, reviewer=False):
    session = get_obj(ctx, CycleCountSession, identifier)
    get_warehouse(ctx, session.warehouse_id)
    for target in session.targets: get_product(ctx, target['product'])
    if reviewer: ctx.require('inventory.count_review')
    elif session.assignee_id != ctx.membership.pk and not (ctx.has('inventory.count_manage') or ctx.has('inventory.count_review')): raise PermissionDenied('This count is assigned to a different employee.')
    return session


def cycle_count_assign(ctx, payload, doc):
    warehouse = get_warehouse(ctx, payload['warehouse'])
    if warehouse.kind == 'transit': raise ValidationError('Assign a physical store count, not an in-transit count.')
    member = get_obj(ctx, Membership, payload['assignee'])
    if not member.active or not any(permission in member.permissions for permission in ['*', 'inventory.*', 'inventory.count_record']): raise ValidationError('The assigned active employee needs inventory.count_record permission.')
    if not member.all_locations and warehouse.location_id not in member.location_ids: raise ValidationError('The counter is not assigned to this location.')
    due = date.fromisoformat(str(payload['due_date']))
    if due < doc.date: raise ValidationError('Count due date cannot precede assignment.')
    targets, seen = [], set()
    for item in payload.get('lines', []):
        product = get_product(ctx, item['product'])
        if product.kind == 'service' or product.line not in member.product_lines: raise ValidationError('Select countable items assigned to the counter product-line scope.')
        if product.kind == 'raw' and not any(p in member.permissions for p in ['*', 'inventory.*', 'inventory.raw', 'consumption.*', 'consumption.view']): raise ValidationError('The counter needs raw inventory authority for material counts.')
        block = get_obj(ctx, Block, item['block']) if product.unit == 'cm' else None
        if block and (block.product_id != product.pk or block.warehouse_id != warehouse.pk or block.status == 'in_transit'): raise ValidationError('Count an identified matching physical block in the chosen warehouse.')
        key = (product.pk, block.pk if block else None)
        if key in seen: raise ValidationError('Each physical block or product pool can appear only once.')
        seen.add(key); targets.append({'product': product.pk, 'product_name': product.name, 'unit': product.unit, 'block': block.pk if block else None, 'code': block.code if block else product.code})
    if not targets: raise ValidationError('Select at least one item or scan a block to count.')
    session = CycleCountSession.objects.create(business=ctx.business, warehouse=warehouse, assignee=member, due_date=due, targets=targets, instructions=str(payload.get('instructions', '')), source=doc)
    doc.warehouse, doc.location = warehouse, warehouse.location
    return {'session': session.pk, 'targets': targets, 'assignee': member.pk, 'due_date': due.isoformat(), 'state': 'assigned', 'blind': True, 'posting_effect': 'none'}


def cycle_count_record(ctx, payload, doc):
    session = visible_count(ctx, payload['session'])
    if session.assignee_id != ctx.membership.pk: raise PermissionDenied('Only the assigned counter records the observation; a reviewer creates a new assignment for a recount.')
    if session.state != 'assigned': raise ValidationError('This session was already observed or closed; assign a new count for a recount.')
    lines = payload.get('lines', [])
    if len(lines) != len(session.targets): raise ValidationError('Record every assigned target exactly once.')
    values = []
    for index, target in enumerate(session.targets):
        line = lines[index]
        if str(line.get('product')) != str(target['product']) or str(line.get('block') or '') != str(target.get('block') or ''): raise ValidationError('Observed rows must match assigned products and blocks in the assigned order.')
        values.append({**line, 'product': target['product'], **({'block': target['block']} if target['block'] else {})})
    # The canonical observation handler runs inside this action's core.execute
    # transaction. Counters do not need standalone inventory.count permission,
    # which would let them query book quantities through arbitrary observations.
    from .corrections import stock_count
    snapshot = stock_count(ctx, {'warehouse': session.warehouse_id, 'lines': values, 'notes': str(payload.get('notes', ''))}, doc)
    session.observation, session.state = doc, 'observed'; session.save(update_fields=['observation', 'state'])
    doc.reference, doc.warehouse, doc.location = session.source, session.warehouse, session.warehouse.location
    return {**snapshot, 'session': session.pk, 'state': 'observed', 'posting_effect': 'none', 'message': 'Observation recorded. A separate reviewer checks differences; expected quantities remain hidden from the counter.'}


def cycle_count_review(ctx, payload, doc):
    session = visible_count(ctx, payload['session'], reviewer=True)
    if session.state != 'observed': raise ValidationError('Review an observed session exactly once.')
    if doc.date < session.observation.date: raise ValidationError('A review cannot precede its physical observation date.')
    if session.assignee.user_id == ctx.user.pk and not ctx.has('inventory.count_self_review'): raise PermissionDenied('A different authorized reviewer must approve this count. inventory.count_self_review is a separate explicit small-team exception.')
    note = str(payload.get('reason', '')).strip()
    if not note: raise ValidationError('Record the review evidence and variance reason.')
    outcome = payload.get('outcome', 'adjust')
    if outcome not in {'adjust', 'recount', 'accept_no_difference'}: raise ValidationError('Choose adjustment, recount or no-difference acceptance.')
    has_variance = any(D(line['variance']) for line in session.observation.result['lines'])
    adjustment = None
    if outcome == 'adjust':
        if not has_variance: raise ValidationError('This observation has no variance; accept it without a stock posting.')
        previous = getattr(ctx, 'cycle_review_session', None)
        ctx.cycle_review_session = session.pk
        try:
            adjustment = execute(ctx, 'stock_count_adjust', {'date': doc.date.isoformat(), 'count': session.observation_id, 'reason': note, 'values': payload.get('values', {}), 'lot_allocations': payload.get('lot_allocations', [])}, f'cycle-adjust-{doc.pk}')
        finally:
            ctx.cycle_review_session = previous
    elif outcome == 'accept_no_difference':
        if has_variance: raise ValidationError('A difference cannot be accepted as no variance. Recount or post a reviewed adjustment.')
        from .corrections import pool_snapshot
        for line in session.observation.result['lines']:
            current = StockPool.objects.get(pk=line['pool_snapshot']['pool'], business=ctx.business)
            if pool_snapshot(current) != line['pool_snapshot']: raise ValidationError('Stock changed after observation; request a recount instead of accepting stale evidence.')
            if line.get('block'):
                block = get_obj(ctx, Block, line['block'])
                snapshot = line['block_snapshot']
                if block.remaining_height_mm != D(snapshot['height_mm']) or block.reserved_height_mm != D(snapshot['reserved_height_mm']) or block.status != snapshot['status']: raise ValidationError('Block condition changed after observation; request a recount.')
    session.adjustment, session.reviewed_by, session.state = adjustment, doc, 'recount' if outcome == 'recount' else 'closed'; session.save(update_fields=['adjustment', 'reviewed_by', 'state'])
    doc.reference, doc.warehouse, doc.location = session.source, session.warehouse, session.warehouse.location
    return {'session': session.pk, 'state': session.state, 'outcome': outcome, 'adjustment': adjustment.pk if adjustment else None, 'posting_effect': 'linked_stock_count_adjust' if adjustment else 'none', 'reason': note}


def weighing_device(ctx, payload, doc):
    warehouse = get_warehouse(ctx, payload['warehouse'])
    if warehouse.kind == 'transit': raise ValidationError('Register scales at a physical warehouse.')
    code, name = str(payload.get('code', '')).strip(), str(payload.get('name', '')).strip()
    if not code or len(code) > 60 or not name or len(name)>150: raise ValidationError('Enter a unique scale code (up to 60 characters) and name (up to 150).')
    capacity = positive(payload['capacity_kg'])
    if capacity != capacity.quantize(Decimal('.000001')): raise ValidationError('Scale capacity supports six decimal kilograms.')
    device = WeighingDevice.objects.create(business=ctx.business, warehouse=warehouse, code=code, name=name, capacity_kg=capacity, source=doc)
    doc.warehouse, doc.location = warehouse, warehouse.location
    return {'device': device.pk, 'code': code, 'capacity_kg': str(capacity), 'integration': 'operator_confirmed_manual_entry', 'posting_effect': 'none'}


def scale_calibrate(ctx, payload, doc):
    device = get_obj(ctx, WeighingDevice, payload['device']); get_warehouse(ctx, device.warehouse_id)
    due = date.fromisoformat(str(payload['next_due']))
    reference, note = str(payload.get('reference', '')).strip(), str(payload.get('note', '')).strip()
    if due <= doc.date or not reference or not note: raise ValidationError('Record calibration evidence and a future due date; the software does not certify calibration.')
    if device.calibrations.filter(source__date__gt=doc.date).exists(): raise ValidationError('A calibration cannot precede a later recorded calibration.')
    calibration = ScaleCalibration.objects.create(business=ctx.business, device=device, next_due=due, reference=reference, note=note, source=doc)
    doc.reference, doc.warehouse, doc.location = device.source, device.warehouse, device.warehouse.location
    return {'calibration': calibration.pk, 'device': device.pk, 'next_due': due.isoformat(), 'reference': reference, 'posting_effect': 'none'}


def weight_measure(ctx, payload, doc):
    device = get_obj(ctx, WeighingDevice, payload['device']); get_warehouse(ctx, device.warehouse_id)
    product = get_product(ctx, payload['product'])
    if product.unit != 'kg' or product.kind == 'service': raise ValidationError('Measured scale quantity is net kilograms; grade labels and centimetres cannot be weighed into stock.')
    calibration = device.calibrations.filter(source__date__lte=doc.date).order_by('-source__date', '-pk').first()
    if not calibration or calibration.next_due < doc.date: raise ValidationError('A current documented calibration is required before confirming weight.')
    gross, tare = D(payload['gross_kg']), D(payload['tare_kg'])
    count = _commercial_index(payload.get('container_count', 1))
    if gross <= 0 or tare < 0 or tare >= gross or gross > device.capacity_kg or count < 1 or count > 1000000: raise ValidationError('Gross must exceed total tare and be within scale capacity; container count must be between 1 and 1,000,000.')
    if any(x != x.quantize(Decimal('.000001')) for x in [gross, tare]): raise ValidationError('Weights support at most six decimal kilograms.')
    if payload.get('confirmed') is not True: raise ValidationError('The operator must confirm the actual gross and total tare readings.')
    measurement = WeightMeasurement.objects.create(business=ctx.business, device=device, calibration=calibration, product=product, gross_kg=gross, tare_kg=tare, net_kg=gross-tare, container_count=count, note=str(payload.get('note', '')), source=doc)
    doc.reference, doc.warehouse, doc.location = calibration.source, device.warehouse, device.warehouse.location
    return {'measurement': measurement.pk, 'product': product.pk, 'gross_kg': str(gross), 'total_tare_kg': str(tare), 'net_kg': str(gross-tare), 'container_count': count, 'confirmed_by': ctx.user.pk, 'posting_effect': 'none', 'integration': 'operator_confirmed_manual_entry'}


def measured_receive(ctx, payload, doc):
    measurement = get_obj(ctx, WeightMeasurement, payload['measurement'])
    get_product(ctx, measurement.product_id); get_warehouse(ctx, measurement.device.warehouse_id)
    if measurement.source.date > doc.date: raise ValidationError('Goods cannot be received before their measurement date.')
    supplier = get_obj(ctx, Party, payload['supplier'])
    line = {'product': measurement.product_id, 'quantity': str(measurement.net_kg), 'unit_cost': str(payload['unit_cost']), 'measurement': measurement.pk}
    if payload.get('lot'): line['lot'] = payload['lot']
    if measurement.product.kind == 'raw' and ctx.business.settings.get('lot_tracking') and not payload.get('lot') and not payload.get('lot_allocations'): raise ValidationError('Strict raw-material tracking requires selecting the actual incoming material lot for this measured receipt.')
    receipt = execute(ctx, 'purchase_receive', {'date': doc.date.isoformat(), 'warehouse': measurement.device.warehouse_id, 'supplier': supplier.pk, 'lines': [line], 'lot_allocations': payload.get('lot_allocations', [])}, f'measured-receipt-{doc.pk}')
    doc.reference, doc.warehouse, doc.location, doc.party, doc.amount = receipt, receipt.warehouse, receipt.location, receipt.party, receipt.amount
    return {'measurement': measurement.pk, 'receipt': receipt.pk, 'receipt_number': receipt.number, 'net_kg': str(measurement.net_kg), 'posting_effect': 'linked_purchase_receive_once'}


def document_guard(ctx, doc):
    """Called by every generic document/print/download authorization path."""
    if doc.kind in {'stock_count', 'stock_count_adjust'}:
        for line in doc.result.get('lines', []):
            if line.get('product'): get_product(ctx, line['product'])
        count_id = doc.pk if doc.kind == 'stock_count' else doc.reference_id
        session = CycleCountSession.objects.filter(business=ctx.business, observation_id=count_id).first()
        if session:
            visible_count(ctx, session.pk, reviewer=True)
    if doc.kind.startswith('cycle_count_') and doc.state == 'posted':
        session_id = doc.result.get('session')
        if session_id: visible_count(ctx, session_id)
    if doc.kind.startswith('supplier_claim') and doc.state == 'posted':
        if doc.result.get('claim'): visible_claim(ctx, doc.result['claim'])
    if doc.kind == 'weight_measure' and doc.state == 'posted':
        get_product(ctx, doc.result['product'])
    if doc.kind == 'measured_receive' and doc.state == 'posted':
        source_document(ctx, doc.result['receipt'], ['purchase_receive'])


def public_result(ctx, doc, value):
    if doc.kind != 'cycle_count_record' or ctx.has('inventory.count_review'): return value
    hidden = {'expected_quantity', 'variance', 'pool_snapshot', 'block_snapshot'}
    def prune(item):
        if isinstance(item, dict): return {key: prune(val) for key, val in item.items() if key not in hidden}
        if isinstance(item, list): return [prune(val) for val in item]
        return item
    return prune(value)


def enrich_registry(operations):
    """Normalized duplicate checking complements the existing quantity locks."""
    result = dict(operations)
    for action in ['purchase_bill', 'expense_post', 'asset_acquire', 'fx_purchase']:
        if action not in result: continue
        permission, original = result[action]
        def guarded(ctx, payload, doc, handler=original, name=action):
            if payload.get('supplier_reference'):
                reference=str(payload['supplier_reference'])
                if len(reference)>150 or not normalize_reference(reference):raise ValidationError('Use a supplier reference containing letters or digits, within 150 characters.')
                supplier = None
                if name == 'purchase_bill':
                    receipt = source_document(ctx, payload['receipt'], ['purchase_receive'])
                    supplier = receipt.party or get_obj(ctx, Party, payload.get('supplier'))
                elif payload.get('supplier') or (name=='fx_purchase' and payload.get('party')): supplier = get_obj(ctx, Party, payload.get('supplier') or payload.get('party'))
                if supplier and duplicate_reference(ctx, supplier, payload['supplier_reference']): raise ValidationError('This supplier invoice reference already exists after normalizing digits, letter case and separators. Review the existing bill instead of posting a duplicate.')
            return handler(ctx, payload, doc)
        result[action] = (permission, guarded)
    if 'purchase_receive' in result:
        permission, receipt_handler = result['purchase_receive']
        def measured_guard(ctx, payload, doc):
            seen = set()
            for line in payload.get('lines', []):
                if not line.get('measurement'): continue
                measurement = get_obj(ctx, WeightMeasurement, line['measurement'])
                get_product(ctx, measurement.product_id); get_warehouse(ctx, measurement.device.warehouse_id)
                if measurement.pk in seen or str(line.get('product')) != str(measurement.product_id) or str(payload.get('warehouse')) != str(measurement.device.warehouse_id) or D(line.get('quantity')) != measurement.net_kg or measurement.source.date > doc.date: raise ValidationError('Measured receiving requires the original product, warehouse, date and exact net kilograms, once per reading.')
                seen.add(measurement.pk)
                for prior in Document.objects.filter(business=ctx.business, state='posted', kind='purchase_receive'):
                    if any(str(old.get('measurement')) == str(measurement.pk) for old in prior.data.get('lines', [])): raise ValidationError('This weight measurement already received goods; record a new physical measurement for another receipt.')
            return receipt_handler(ctx, payload, doc)
        result['purchase_receive'] = (permission, measured_guard)
    if 'stock_count_adjust' in result:
        permission, adjustment_handler = result['stock_count_adjust']
        def cycle_adjust_guard(ctx, payload, doc):
            session = CycleCountSession.objects.filter(business=ctx.business, observation_id=payload.get('count')).first()
            if session:
                visible_count(ctx, session.pk, reviewer=True)
                if getattr(ctx, 'cycle_review_session', None) != session.pk: raise ValidationError('Review the assigned count through cycle_count_review; a direct adjustment cannot bypass its reviewer and close controls.')
            return adjustment_handler(ctx, payload, doc)
        result['stock_count_adjust'] = (permission, cycle_adjust_guard)
    return result


OPERATIONS = {
    'supplier_claim': ('purchases.claim', supplier_claim),
    'supplier_claim_resolve': ('purchases.approve', supplier_claim_resolve),
    'cycle_count_assign': ('inventory.count_manage', cycle_count_assign),
    'cycle_count_record': ('inventory.count_record', cycle_count_record),
    'cycle_count_review': ('inventory.count_review', cycle_count_review),
    'weighing_device': ('inventory.scale_manage', weighing_device),
    'scale_calibrate': ('inventory.scale_manage', scale_calibrate),
    'weight_measure': ('inventory.measure', weight_measure),
    'measured_receive': ('purchases.post', measured_receive),
}
