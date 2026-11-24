"""Transport evidence, customer quality cases, and defensive recall holds.

These operations never issue inventory, recognize revenue, or create credits.
Actual returns/replacements remain separately authorized existing ERP documents.
"""
from decimal import Decimal
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q, Sum
from .core import D, get_obj, get_product, get_warehouse
from .models import Attachment, Block, Document, LotMovement, MaterialLot, QualityInspection
from .dispatch_models import (
    TransportVehicle, TransportDriver, DeliveryTrip, DeliveryLoad,
    DeliveryAcknowledgement, DeliveryDisputeResolution, CustomerQualityClaim,
    QualityClaimEvent, RecallCampaign, RecallBlockHold, RecallProductHold,
)

ZERO = Decimal('0')


def fail(message):
    raise ValidationError(message)


def text(payload, name, maximum=1000):
    result = str(payload.get(name) or '').strip()
    if not result or len(result) > maximum:
        fail(f'{name} is required and must be no longer than {maximum} characters.')
    return result


def quantity(value, product):
    result = D(value)
    if result < 0 or result != result.quantize(Decimal('.000001')):
        fail('Use a nonnegative exact quantity with at most six decimal places.')
    if product.unit == 'each' and result != result.to_integral_value():
        fail('Piece quantities must be whole numbers.')
    return result


def source_document(ctx, identifier, kinds):
    document = get_obj(ctx, Document, identifier)
    if document.state != 'posted' or document.kind not in kinds:
        fail('Select a compatible posted source document.')
    for line in document.result.get('lines', []):
        if line.get('product'):
            get_product(ctx, line['product'])
    return document


def evidence(ctx, ids, allowed):
    if not isinstance(ids, list) or len(ids) > 30:
        fail('Evidence must contain at most 30 private attachment IDs.')
    result = []
    for identifier in ids:
        item = get_obj(ctx, Attachment, identifier)
        if item.pk in result or item.document_id not in allowed:
            fail('Evidence must be unique and attached to this case or one of its linked source documents.')
        get_obj(ctx, Document, item.document_id)
        result.append(item.pk)
    return result


def visible_trip(ctx, identifier):
    trip = get_obj(ctx, DeliveryTrip, identifier)
    get_warehouse(ctx, trip.warehouse_id)
    for load in trip.loads.select_related('document', 'product'):
        source_document(ctx, load.document_id, {'sale', 'transfer_dispatch'})
        get_product(ctx, load.product_id)
    return trip


def vehicle_create(ctx, p, doc):
    warehouse = get_warehouse(ctx, p['warehouse'])
    vehicle = TransportVehicle(business=ctx.business, location=warehouse.location, plate=text(p, 'plate', 50), description=str(p.get('description', ''))[:200], capacity_note=str(p.get('capacity_note', ''))[:150], source=doc)
    vehicle.full_clean(); vehicle.save()
    doc.location, doc.warehouse = warehouse.location, warehouse
    return {'vehicle': vehicle.pk, 'plate': vehicle.plate, 'financial_effect': False}


def driver_create(ctx, p, doc):
    warehouse = get_warehouse(ctx, p['warehouse'])
    driver = TransportDriver(business=ctx.business, location=warehouse.location, name=text(p, 'name', 200), phone=str(p.get('phone', ''))[:50], source=doc)
    driver.full_clean(); driver.save()
    doc.location, doc.warehouse = warehouse.location, warehouse
    return {'driver': driver.pk, 'name': driver.name, 'financial_effect': False}


def trip_create(ctx, p, doc):
    warehouse = get_warehouse(ctx, p['warehouse'])
    vehicle = get_obj(ctx, TransportVehicle, p['vehicle'])
    driver = get_obj(ctx, TransportDriver, p['driver'])
    if warehouse.kind == 'transit' or not vehicle.active or not driver.active:
        fail('Select a physical source warehouse and active vehicle/driver.')
    if vehicle.location_id != warehouse.location_id or driver.location_id != warehouse.location_id:
        fail('Vehicle, driver, and loading warehouse must belong to the same location.')
    from .growth import day
    scheduled = day(p.get('scheduled_date') or doc.date)
    if scheduled < doc.date:
        fail('Trip planning cannot schedule a departure before its document date.')
    trip = DeliveryTrip(business=ctx.business, warehouse=warehouse, vehicle=vehicle, driver=driver, scheduled_date=scheduled, destination=text(p, 'destination', 250), notes=str(p.get('notes', ''))[:4000], source=doc)
    trip.full_clean(); trip.save()
    doc.location, doc.warehouse = warehouse.location, warehouse
    return {'trip': trip.pk, 'state': trip.state, 'stock_deducted': False, 'revenue_posted': False}


def trip_load(ctx, p, doc):
    trip = visible_trip(ctx, p['trip'])
    if trip.state != 'planned':
        fail('Load documents before departure; a departed trip cannot be silently edited.')
    result = []
    for requested in p.get('lines', []):
        original = source_document(ctx, requested['document'], {'sale', 'transfer_dispatch'})
        if original.warehouse_id != trip.warehouse_id:
            fail('Only documents fulfilled/dispatched from this loading warehouse can be loaded.')
        if original.date > doc.date:
            fail('A load cannot precede its posted invoice/transfer.')
        index = int(requested['index'])
        lines = original.result.get('lines', [])
        if index < 0 or index >= len(lines):
            fail('Invalid source line index.')
        line = lines[index]
        product = get_product(ctx, line['product'])
        if product.kind == 'service':
            fail('Services cannot be loaded onto a vehicle.')
        amount = quantity(requested['quantity'], product)
        used = DeliveryLoad.objects.filter(business=ctx.business, document=original, line_index=index).exclude(trip__state='cancelled').aggregate(total=Sum('quantity'))['total'] or ZERO
        returned = sum((D(item['quantity']) for credit in Document.objects.filter(business=ctx.business, reference=original, kind='sales_return', state='posted') for item in credit.result.get('lines', []) if int(item.get('index', -1)) == index), ZERO) if original.kind == 'sale' else ZERO
        if amount <= 0 or used + amount > D(line['quantity']) - returned:
            fail('Loaded quantities exceed the unduplicated delivered/dispatched source quantity.')
        # A legacy whole-invoice confirmation is already complete evidence; do
        # not create a second competing customer-delivery confirmation.
        from .models import DeliveryConfirmation
        if original.kind == 'sale' and DeliveryConfirmation.objects.filter(invoice=original).exists():
            fail('This invoice already has a complete legacy delivery confirmation.')
        load = DeliveryLoad(business=ctx.business, trip=trip, document=original, line_index=index, product=product, quantity=amount, source=doc)
        load.full_clean(); load.save()
        result.append({'load': load.pk, 'document': original.pk, 'number': original.number, 'index': index, 'product': product.pk, 'quantity': str(amount), 'unit': product.unit})
    if not result:
        fail('Select at least one invoice/transfer line to load.')
    doc.reference, doc.location, doc.warehouse = trip.source, trip.warehouse.location, trip.warehouse
    return {'trip': trip.pk, 'lines': result, 'stock_deducted': False, 'revenue_posted': False}


def trip_depart(ctx, p, doc):
    trip = visible_trip(ctx, p['trip'])
    if trip.state != 'planned' or not trip.loads.exists():
        fail('Only a planned trip with loaded documents can depart.')
    if DeliveryTrip.objects.filter(business=ctx.business, state='in_transit').filter(Q(vehicle=trip.vehicle) | Q(driver=trip.driver)).exclude(pk=trip.pk).exists():
        fail('This vehicle or driver is already assigned to another active trip.')
    trip.state, trip.dispatched_by = 'in_transit', doc
    trip.save(update_fields=['state', 'dispatched_by'])
    doc.reference, doc.location, doc.warehouse = trip.source, trip.warehouse.location, trip.warehouse
    return {'trip': trip.pk, 'state': trip.state, 'stock_deducted': False, 'revenue_posted': False}


def load_totals(load):
    totals = load.acknowledgements.aggregate(accepted=Sum('accepted'), disputed=Sum('disputed'))
    accepted, disputed = totals['accepted'] or ZERO, totals['disputed'] or ZERO
    unresolved = sum((row.disputed for row in load.acknowledgements.filter(disputed__gt=0, resolution__isnull=True)), ZERO)
    return accepted, disputed, load.quantity - accepted - disputed, unresolved


def delivery_acknowledge(ctx, p, doc):
    load = get_obj(ctx, DeliveryLoad, p['load'])
    trip = visible_trip(ctx, load.trip_id)
    if trip.state != 'in_transit':
        fail('Acknowledge only a departed, open trip.')
    product = get_product(ctx, load.product_id)
    accepted = quantity(p.get('accepted', '0'), product)
    disputed = quantity(p.get('disputed', '0'), product)
    remaining = load_totals(load)[2]
    if accepted + disputed <= 0 or accepted + disputed > remaining:
        fail('Accepted plus disputed quantity must be positive and cannot exceed the unacknowledged load.')
    if disputed and not str(p.get('note', '')).strip():
        fail('Disputed delivery quantities require an explanation.')
    allowed = {load.document_id, load.source_id, trip.source_id}
    proof = evidence(ctx, p.get('attachments', []), allowed)
    ack = DeliveryAcknowledgement(business=ctx.business, load=load, accepted=accepted, disputed=disputed, recipient=text(p, 'recipient', 200), note=str(p.get('note', ''))[:4000], attachments=proof, source=doc)
    ack.full_clean(); ack.save()
    doc.reference, doc.location, doc.warehouse = load.document, trip.warehouse.location, trip.warehouse
    return {'acknowledgement': ack.pk, 'trip': trip.pk, 'load': load.pk, 'accepted': str(accepted), 'disputed': str(disputed), 'unacknowledged': str(remaining - accepted - disputed), 'stock_deducted': False, 'revenue_posted': False, 'proof_attachments': proof}


def dispute_resolve(ctx, p, doc):
    ack = get_obj(ctx, DeliveryAcknowledgement, p['acknowledgement'])
    trip = visible_trip(ctx, ack.load.trip_id)
    if ack.disputed <= 0 or DeliveryDisputeResolution.objects.filter(acknowledgement=ack).exists():
        fail('Select an unresolved delivery discrepancy; it can be resolved only once.')
    outcome = p.get('outcome')
    if outcome not in {'accepted_after_review', 'linked_return', 'linked_transfer_resolution'}:
        fail('Choose an accepted review or an existing linked return/transfer resolution.')
    linked = None
    if outcome != 'accepted_after_review':
        kinds = {'sales_return'} if outcome == 'linked_return' else {'transfer_resolve'}
        linked = source_document(ctx, p.get('financial_document'), kinds)
        source = ack.load.document
        if outcome == 'linked_return' and (linked.reference_id != source.pk or linked.party_id != source.party_id):
            fail('The return must reference this load\'s original customer invoice.')
        if outcome == 'linked_transfer_resolution' and linked.reference_id != source.pk:
            fail('The transfer discrepancy must reference the original dispatch.')
        matching = sum((D(row['quantity']) for row in linked.result.get('lines', []) if int(row.get('index', -1)) == ack.load.line_index), ZERO)
        already = DeliveryDisputeResolution.objects.filter(business=ctx.business, financial_document=linked, acknowledgement__load__line_index=ack.load.line_index).aggregate(total=Sum('acknowledgement__disputed'))['total'] or ZERO
        if matching < ack.disputed + already:
            fail('The linked resolution does not cover the unallocated disputed source-line quantity.')
    resolution = DeliveryDisputeResolution(business=ctx.business, acknowledgement=ack, outcome=outcome, note=text(p, 'note', 4000), financial_document=linked, source=doc)
    resolution.full_clean(); resolution.save()
    doc.reference, doc.location, doc.warehouse = ack.source, trip.warehouse.location, trip.warehouse
    return {'resolution': resolution.pk, 'trip': trip.pk, 'outcome': outcome, 'financial_document': linked.pk if linked else None, 'financial_posting': False}


def trip_close(ctx, p, doc):
    trip = visible_trip(ctx, p['trip'])
    if trip.state != 'in_transit' or any(load_totals(load)[2] or load_totals(load)[3] for load in trip.loads.all()):
        fail('Close only an active trip with every quantity acknowledged and every dispute resolved.')
    trip.state, trip.closed_by = 'completed', doc
    trip.save(update_fields=['state', 'closed_by'])
    doc.reference, doc.location, doc.warehouse = trip.source, trip.warehouse.location, trip.warehouse
    return {'trip': trip.pk, 'state': trip.state, 'stock_deducted': False, 'revenue_posted': False}


def trip_cancel(ctx, p, doc):
    trip = visible_trip(ctx, p['trip'])
    if trip.state != 'planned':
        fail('Only an un-departed trip can be cancelled; resolve an active trip through acknowledgements.')
    reason = text(p, 'reason', 4000)
    trip.state, trip.closed_by = 'cancelled', doc
    trip.save(update_fields=['state', 'closed_by'])
    doc.reference, doc.location, doc.warehouse = trip.source, trip.warehouse.location, trip.warehouse
    return {'trip': trip.pk, 'state': trip.state, 'reason': reason, 'stock_deducted': False}


def visible_claim(ctx, identifier):
    claim = get_obj(ctx, CustomerQualityClaim, identifier)
    source_document(ctx, claim.invoice_id, {'sale'})
    get_product(ctx, claim.product_id)
    return claim


def claim_open(ctx, p, doc):
    invoice = source_document(ctx, p['invoice'], {'sale'})
    index = int(p['index']); lines = invoice.result.get('lines', [])
    if index < 0 or index >= len(lines):
        fail('Choose the affected original invoice line.')
    line = lines[index]; product = get_product(ctx, line['product'])
    amount = quantity(p['quantity'], product)
    used = CustomerQualityClaim.objects.filter(business=ctx.business, invoice=invoice, line_index=index).exclude(state='rejected').aggregate(total=Sum('quantity'))['total'] or ZERO
    if amount <= 0 or used + amount > D(line['quantity']):
        fail('Claimed quantity exceeds the original quantity not already covered by another claim.')
    reason = p.get('reason')
    if reason not in {'dimension', 'appearance', 'hardness', 'damage', 'adhesion', 'other'}:
        fail('Choose a quality complaint reason.')
    block = None
    if line.get('block'):
        # The block may now be located at a different branch. Its original sale
        # gives permitted traceability without granting that branch's stock view.
        block = Block.objects.filter(business=ctx.business, pk=line['block'], product=product).first()
    if p.get('block') and (not block or str(block.pk) != str(p['block'])):
        fail('The selected block is not the block identified on this invoice line.')
    batch = block.batch if block else None
    if p.get('batch'):
        requested = source_document(ctx, p['batch'], {'production', 'production_complete', 'production_bom'})
        if batch and requested.pk != batch.pk:
            fail('The selected production batch does not match the sold block.')
        if not batch:
            # Weight-pool products cannot claim precise batch lineage without a
            # recorded allocation; do not fabricate an adhesive batch link.
            fail('This sale does not record an identifiable production batch; leave the batch unlinked.')
    claim = CustomerQualityClaim(business=ctx.business, invoice=invoice, line_index=index, product=product, block=block, batch=batch, quantity=amount, reason=reason, description=text(p, 'description', 4000), source=doc)
    claim.full_clean(); claim.save()
    proof = evidence(ctx, p.get('attachments', []), {invoice.pk})
    event = QualityClaimEvent(business=ctx.business, claim=claim, kind='opened', note=claim.description, attachments=proof, source=doc)
    event.full_clean(); event.save()
    doc.reference, doc.location, doc.warehouse, doc.party = invoice, invoice.location, invoice.warehouse, invoice.party
    return {'claim': claim.pk, 'invoice': invoice.pk, 'state': claim.state, 'block': block.pk if block else None, 'batch': batch.pk if batch else None, 'financial_posting': False, 'stock_deducted': False}


def claim_review(ctx, p, doc):
    claim = visible_claim(ctx, p['claim'])
    if claim.state != 'open':
        fail('Only an open claim can receive an inspection decision.')
    disposition = p.get('disposition')
    if disposition not in {'return', 'replacement', 'repair', 'no_action', 'rejected'}:
        fail('Choose a documented claim disposition.')
    inspection = get_obj(ctx, QualityInspection, p['inspection']) if p.get('inspection') else None
    if inspection and (inspection.template.product_id != claim.product_id or (claim.block_id and inspection.block_id != claim.block_id) or (claim.batch_id and not inspection.block_id and inspection.batch_id != claim.batch_id)):
        fail('The inspection must concern this claim\'s product and actual block/batch.')
    allowed = {claim.invoice_id, claim.source_id} | set(claim.events.values_list('source_id', flat=True))
    proof = evidence(ctx, p.get('attachments', []), allowed)
    event = QualityClaimEvent(business=ctx.business, claim=claim, kind='reviewed', note=text(p, 'note', 4000), inspection=inspection, attachments=proof, source=doc)
    event.full_clean(); event.save()
    claim.disposition = disposition
    claim.state = 'rejected' if disposition == 'rejected' else 'reviewed'
    claim.save(update_fields=['disposition', 'state'])
    doc.reference, doc.location, doc.warehouse, doc.party = claim.source, claim.invoice.location, claim.invoice.warehouse, claim.invoice.party
    return {'claim': claim.pk, 'state': claim.state, 'disposition': disposition, 'financial_posting': False}


def claim_close(ctx, p, doc):
    claim = visible_claim(ctx, p['claim'])
    if claim.state != 'reviewed':
        fail('Close only an inspected/reviewed claim; rejected and closed cases cannot be closed again.')
    returned = source_document(ctx, p['return_document'], {'sales_return'}) if p.get('return_document') else None
    replacement = source_document(ctx, p['replacement'], {'sale'}) if p.get('replacement') else None
    if claim.disposition in {'return', 'replacement'} and not returned:
        fail('This disposition requires the separately posted original-invoice return/credit document.')
    if claim.disposition == 'replacement' and not replacement:
        fail('Link the separately authorized replacement sale/delivery; this case does not issue stock.')
    if returned:
        if returned.reference_id != claim.invoice_id or returned.party_id != claim.invoice.party_id:
            fail('The financial return must reference the original invoice/customer.')
        matching = sum((D(line['quantity']) for line in returned.result.get('lines', []) if int(line.get('index', -1)) == claim.line_index), ZERO)
        used = QualityClaimEvent.objects.filter(business=ctx.business, financial_document=returned, kind='closed', claim__line_index=claim.line_index).aggregate(total=Sum('claim__quantity'))['total'] or ZERO
        if matching < used + claim.quantity:
            fail('The financial return does not cover the unallocated claimed quantity.')
    if replacement:
        if replacement.pk == claim.invoice_id or replacement.party_id != claim.invoice.party_id:
            fail('Replacement must be a different posted sale to the same customer.')
        matching = sum((D(line['quantity']) for line in replacement.result.get('lines', []) if int(line.get('product', -1)) == claim.product_id), ZERO)
        used = QualityClaimEvent.objects.filter(business=ctx.business, replacement=replacement, kind='closed', claim__product_id=claim.product_id).aggregate(total=Sum('claim__quantity'))['total'] or ZERO
        if matching < used + claim.quantity:
            fail('Replacement quantities do not cover the claims already linked plus this claim.')
    allowed = {claim.invoice_id, claim.source_id} | set(claim.events.values_list('source_id', flat=True))
    if returned: allowed.add(returned.pk)
    if replacement: allowed.add(replacement.pk)
    proof = evidence(ctx, p.get('attachments', []), allowed)
    event = QualityClaimEvent(business=ctx.business, claim=claim, kind='closed', note=text(p, 'note', 4000), financial_document=returned, replacement=replacement, attachments=proof, source=doc)
    event.full_clean(); event.save()
    claim.state = 'closed'; claim.save(update_fields=['state'])
    doc.reference, doc.location, doc.warehouse, doc.party = claim.source, claim.invoice.location, claim.invoice.warehouse, claim.invoice.party
    return {'claim': claim.pk, 'state': 'closed', 'return_document': returned.pk if returned else None, 'replacement': replacement.pk if replacement else None, 'financial_posting': False, 'stock_deducted': False}


def recall_basis(ctx, lot=None, batch=None):
    documents = set()
    if lot:
        get_product(ctx, lot.product_id)
        documents |= set(LotMovement.objects.filter(business=ctx.business, lot=lot).values_list('document_id', flat=True))
        batches = Document.objects.filter(business=ctx.business, pk__in=documents, kind='production_consume').values_list('reference_id', flat=True)
        documents |= set(Document.objects.filter(business=ctx.business, reference_id__in=batches, kind='production_complete', state='posted').values_list('pk', flat=True))
    if batch:
        documents.add(batch.pk)
        if batch.kind == 'production_start':
            documents |= set(Document.objects.filter(business=ctx.business, reference=batch, kind='production_complete', state='posted').values_list('pk', flat=True))
    blocks = set(Block.objects.filter(business=ctx.business, batch_id__in=documents).values_list('pk', flat=True))
    frontier = set(blocks)
    while frontier:
        frontier = set(Block.objects.filter(business=ctx.business, parent_id__in=frontier).values_list('pk', flat=True)) - blocks
        blocks |= frontier
    products = set()
    # Kg/count outputs are pooled. Hold their entire product conservatively;
    # never claim that an untracked weight balance identifies one batch exactly.
    for document in Document.objects.filter(business=ctx.business, pk__in=documents, kind__in=['production', 'production_complete', 'production_bom']):
        for output in document.result.get('outputs', []):
            product = get_product(ctx, output['product'])
            if product.unit != 'cm': products.add(product.pk)
    return documents, blocks, products


def complete_recall_scope(ctx):
    ctx.require('quality.recall')
    if not ctx.membership.all_locations:
        raise PermissionDenied('A business-wide recall requires complete location access.')


def recall_open(ctx, p, doc):
    complete_recall_scope(ctx)
    if bool(p.get('lot')) == bool(p.get('batch')):
        fail('Select exactly one material lot or production batch as the recall basis.')
    lot = get_obj(ctx, MaterialLot, p['lot']) if p.get('lot') else None
    batch = source_document(ctx, p['batch'], {'production', 'production_bom', 'production_start', 'production_complete'}) if p.get('batch') else None
    documents, block_ids, product_ids = recall_basis(ctx, lot, batch)
    for original in Document.objects.filter(business=ctx.business, pk__in=documents):
        if not set(original.product_lines).issubset(set(ctx.membership.product_lines)):
            raise PermissionDenied('Recall requires access to every affected product line.')
    blocks = list(Block.objects.filter(business=ctx.business, pk__in=block_ids).select_related('product'))
    for block in blocks: get_product(ctx, block.product_id)
    campaign = RecallCampaign(business=ctx.business, lot=lot, batch=batch, reason=text(p, 'reason', 4000), source=doc)
    campaign.full_clean(); campaign.save()
    if lot:
        lot.state = 'held'; lot.save(update_fields=['state'])
    for block in blocks:
        hold = RecallBlockHold(business=ctx.business, campaign=campaign, block=block, prior_status=block.status, source=doc)
        hold.full_clean(); hold.save()
        if block.status in {'ready', 'reserved'}:
            block.status = 'inspection'; block.save(update_fields=['status'])
    for product_id in product_ids:
        get_product(ctx, product_id)
        RecallProductHold.objects.create(business=ctx.business, campaign=campaign, product_id=product_id, source=doc)
    doc.reference = batch
    return {'campaign': campaign.pk, 'lot': lot.pk if lot else None, 'batch': batch.pk if batch else None, 'held_blocks': sorted(block_ids), 'conservatively_held_products': sorted(product_ids), 'scope': 'Recorded lot/batch lineage only; pooled kg/count outputs are held at whole-product scope. Legacy untracked input use is not claimed to be traced.', 'stock_deducted': False, 'financial_posting': False}


def recall_close(ctx, p, doc):
    complete_recall_scope(ctx)
    campaign = get_obj(ctx, RecallCampaign, p['campaign'])
    if campaign.state != 'open': fail('This recall campaign is already closed.')
    text(p, 'reason', 4000)
    for hold in campaign.block_holds.select_related('block'):
        get_product(ctx, hold.block.product_id)
        hold.released_by = doc; hold.save(update_fields=['released_by'])
    for hold in campaign.product_holds.select_related('product'):
        get_product(ctx, hold.product_id)
        hold.released_by = doc; hold.save(update_fields=['released_by'])
    campaign.state, campaign.closed_by = 'closed', doc
    campaign.save(update_fields=['state', 'closed_by'])
    # Never restore ready automatically: an inspection/curing/damage hold may
    # predate or follow this recall. Separate quality release remains required.
    doc.reference = campaign.source
    return {'campaign': campaign.pk, 'state': 'closed', 'quality_release_required': True, 'financial_posting': False, 'stock_deducted': False}


def guard_active_recall(ctx, action, p):
    recalled_lots = set(RecallCampaign.objects.filter(business=ctx.business, state='open', lot__isnull=False).values_list('lot_id', flat=True))
    if action == 'lot_status' and p.get('state') == 'released' and p.get('lot') and int(p['lot']) in recalled_lots:
        fail('An active recall holds this material lot; close/review the recall before release.')
    declared = [p, *p.get('lines', []), *p.get('inputs', []), *p.get('lot_allocations', [])]
    if any(row.get('lot') and int(row['lot']) in recalled_lots for row in declared):
        fail('An active recall holds this material lot.')
    held_products = set(RecallProductHold.objects.filter(business=ctx.business, released_by__isnull=True).values_list('product_id', flat=True))
    held_blocks = set(RecallBlockHold.objects.filter(business=ctx.business, released_by__isnull=True).values_list('block_id', flat=True))
    if not held_products and not held_blocks: return
    rows = list(p.get('lines', [])) + list(p.get('inputs', []))
    if p.get('block') or p.get('product'): rows.append(p)
    for row in rows:
        if row.get('product') and int(row['product']) in held_products:
            fail('An active recall holds this pooled product. Close/review the recall before issuing it.')
        if row.get('block'):
            block = get_obj(ctx, Block, row['block'])
            if block.pk in held_blocks or block.product_id in held_products:
                fail('An active recall holds this block; quality release or stock movement cannot bypass it.')
    if action in {'transfer_receive', 'transfer_resolve'} and p.get('transfer'):
        transfer = get_obj(ctx, Document, p['transfer'])
        if any(row.get('block') in held_blocks or row.get('product') in held_products for row in transfer.result.get('lines', [])):
            fail('Receive/resolve this recalled transfer under a separately reviewed quality process; ordinary receipt is held.')
    if action == 'stock_count_adjust' and p.get('count'):
        count = get_obj(ctx, Document, p['count'])
        if any(row.get('block') in held_blocks or row.get('product') in held_products for row in count.result.get('lines', [])):
            fail('Recalled stock cannot be adjusted through a normal count before quality review.')
    if action == 'production_complete' and p.get('batch'):
        if RecallCampaign.objects.filter(business=ctx.business, batch_id=p['batch'], state='open').exists():
            fail('This production batch is under recall and cannot be completed normally.')


def enrich_registry(registry):
    guarded = {'sale', 'fx_sale', 'cut', 'trim', 'reserve', 'quality_release', 'lot_status', 'transfer_dispatch', 'transfer_receive', 'transfer_resolve', 'material_issue', 'material_return', 'production', 'production_bom', 'production_consume', 'production_complete', 'stock_adjust', 'stock_count_adjust'}
    for action in guarded & registry.keys():
        permission, handler = registry[action]
        def wrapped(ctx, p, doc, action=action, handler=handler):
            guard_active_recall(ctx, action, p)
            return handler(ctx, p, doc)
        registry[action] = permission, wrapped
    if 'delivery_confirm' in registry:
        permission, handler = registry['delivery_confirm']
        def confirm(ctx, p, doc):
            if DeliveryLoad.objects.filter(business=ctx.business, document_id=p.get('invoice')).exclude(trip__state='cancelled').exists():
                fail('Use trip acknowledgements for this loaded invoice; a whole-invoice confirmation would duplicate evidence.')
            return handler(ctx, p, doc)
        registry['delivery_confirm'] = permission, confirm
    return registry


OPERATIONS = {
    'transport_vehicle': ('delivery.manage', vehicle_create),
    'transport_driver': ('delivery.manage', driver_create),
    'delivery_trip': ('delivery.post', trip_create),
    'delivery_load': ('delivery.post', trip_load),
    'delivery_depart': ('delivery.post', trip_depart),
    'delivery_acknowledge': ('delivery.confirm', delivery_acknowledge),
    'delivery_dispute_resolve': ('delivery.approve', dispute_resolve),
    'delivery_close': ('delivery.post', trip_close),
    'delivery_cancel': ('delivery.post', trip_cancel),
    'quality_claim': ('quality.claim', claim_open),
    'quality_claim_review': ('quality.approve', claim_review),
    'quality_claim_close': ('quality.approve', claim_close),
    'quality_recall': ('quality.recall', recall_open),
    'quality_recall_close': ('quality.recall', recall_close),
}
