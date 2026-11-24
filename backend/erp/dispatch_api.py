"""Read-only scoped transport/quality workspaces; mutations use core operations."""
from django.core.exceptions import PermissionDenied, ValidationError
from .api import Boundary, response, can, serialize_model
from .core import get_obj, get_product, get_warehouse
from .models import Block, Document
from .dispatch_models import TransportVehicle, TransportDriver, DeliveryTrip, DeliveryLoad, DeliveryAcknowledgement, CustomerQualityClaim, RecallCampaign
from .dispatch import visible_trip, visible_claim, load_totals, recall_basis, source_document


def proof_rows(ctx, source_ids):
    from .models import Attachment
    return [{'id': item.pk, 'filename': item.filename, 'document': item.document_id} for item in Attachment.objects.filter(business=ctx.business, document_id__in=source_ids).order_by('pk')]


def trip_row(ctx, trip):
    visible_trip(ctx, trip.pk)
    result = {'id': trip.pk, 'number': trip.source.number, 'warehouse': trip.warehouse_id, 'warehouse_name': trip.warehouse.name, 'vehicle': trip.vehicle_id, 'plate': trip.vehicle.plate, 'driver': trip.driver_id, 'driver_name': trip.driver.name, 'scheduled_date': trip.scheduled_date, 'destination': trip.destination, 'notes': trip.notes, 'state': trip.state, 'source': trip.source_id, 'loads': [], 'attachments': proof_rows(ctx, [trip.source_id])}
    for load in trip.loads.select_related('product', 'document'):
        accepted, disputed, remaining, unresolved = load_totals(load)
        acknowledgements = []
        for ack in load.acknowledgements.select_related('source').order_by('pk'):
            resolution = getattr(ack, 'resolution', None)
            acknowledgements.append({'id': ack.pk, 'source': ack.source_id, 'date': ack.source.date, 'accepted': ack.accepted, 'disputed': ack.disputed, 'recipient': ack.recipient, 'note': ack.note, 'attachments': proof_rows(ctx, [ack.source_id]), 'proof_ids': ack.attachments, 'resolution': {'id': resolution.pk, 'outcome': resolution.outcome, 'note': resolution.note, 'financial_document': resolution.financial_document_id} if resolution else None})
        result['loads'].append({'id': load.pk, 'document': load.document_id, 'number': load.document.number, 'kind': load.document.kind, 'index': load.line_index, 'product': load.product_id, 'product_name': load.product.name, 'unit': load.product.unit, 'quantity': load.quantity, 'accepted': accepted, 'disputed': disputed, 'remaining': remaining, 'unresolved': unresolved, 'acknowledgements': acknowledgements})
    return result


def claim_row(ctx, claim):
    visible_claim(ctx, claim.pk)
    row = {'id': claim.pk, 'number': claim.source.number, 'source': claim.source_id, 'invoice': claim.invoice_id, 'invoice_number': claim.invoice.number, 'customer': claim.invoice.party.name if claim.invoice.party_id else '', 'index': claim.line_index, 'product': claim.product_id, 'product_name': claim.product.name, 'unit': claim.product.unit, 'block': claim.block_id, 'block_code': claim.block.code if claim.block_id else '', 'batch': claim.batch_id, 'quantity': claim.quantity, 'reason': claim.reason, 'description': claim.description, 'state': claim.state, 'disposition': claim.disposition, 'date': claim.source.date, 'events': [], 'attachments': proof_rows(ctx, [claim.source_id])}
    for event in claim.events.select_related('source').order_by('pk'):
        row['events'].append({'id': event.pk, 'kind': event.kind, 'note': event.note, 'date': event.source.date, 'source': event.source_id, 'inspection': event.inspection_id, 'return_document': event.financial_document_id, 'replacement': event.replacement_id, 'proof_ids': event.attachments, 'attachments': proof_rows(ctx, [event.source_id])})
    return row


def recall_row(ctx, campaign):
    # Recall actions are business-wide. Do not reveal a scoped user's incomplete
    # list as if it represented the campaign's entire affected population.
    if not ctx.membership.all_locations:
        raise PermissionDenied('Complete location scope is required for a recall campaign view.')
    if campaign.lot_id:
        get_product(ctx, campaign.lot.product_id)
    if campaign.batch_id:
        get_obj(ctx, Document, campaign.batch_id)
    _, blocks, products = recall_basis(ctx, campaign.lot, campaign.batch)
    for block in Block.objects.filter(business=ctx.business, pk__in=blocks):
        get_product(ctx, block.product_id)
    for product in products: get_product(ctx, product)
    sales = []
    if ctx.has('sales.view') or ctx.has('quality.recall_customers'):
        for invoice in Document.objects.filter(business=ctx.business, kind='sale', state='posted').select_related('party'):
            if any(line.get('block') in blocks or line.get('product') in products for line in invoice.result.get('lines', [])):
                try: get_obj(ctx, Document, invoice.pk)
                except (PermissionDenied, ValidationError): continue
                sales.append({'invoice': invoice.pk, 'number': invoice.number, 'date': invoice.date, 'customer': invoice.party.name if invoice.party_id else '', 'phone': invoice.party.phone if invoice.party_id else '', 'basis': 'recorded_block' if any(line.get('block') in blocks for line in invoice.result.get('lines', [])) else 'conservative_product_scope'})
    return {'id': campaign.pk, 'source': campaign.source_id, 'number': campaign.source.number, 'date': campaign.source.date, 'lot': campaign.lot_id, 'lot_code': campaign.lot.code if campaign.lot_id else '', 'batch': campaign.batch_id, 'batch_number': campaign.batch.number if campaign.batch_id else '', 'reason': campaign.reason, 'state': campaign.state, 'blocks': [{'id': hold.block_id, 'code': hold.block.code, 'warehouse': hold.block.warehouse_id, 'status': hold.block.status, 'prior_status': hold.prior_status, 'released': bool(hold.released_by_id)} for hold in campaign.block_holds.select_related('block')], 'pooled_products': list(products), 'customer_actions': sales, 'scope_note': 'Only recorded lineage is traced. Pooled kg/count products are conservatively held; legacy untracked inputs are not represented as exact traceability.'}


class DispatchAPI(Boundary):
    def get(self, request, section):
        ctx = self.ctx(request)
        if section == 'sources':
            kinds = set()
            if can(ctx, 'delivery.post', 'quality.claim', 'quality.approve'):
                kinds.add('sale')
            if can(ctx, 'delivery.post'):
                kinds.add('transfer_dispatch')
            if can(ctx, 'delivery.approve', 'quality.approve'):
                kinds.update(['sales_return', 'transfer_resolve'])
            if can(ctx, 'quality.recall'):
                kinds.update(['production', 'production_complete', 'production_start', 'production_bom'])
            if not kinds: raise PermissionDenied('Source-document lookup requires delivery or quality-case authority.')
            query = Document.objects.filter(business=ctx.business, state='posted', kind__in=kinds).select_related('party').order_by('-pk')
            if request.query_params.get('q'):
                from django.db.models import Q
                search = str(request.query_params['q'])[:150]
                query = query.filter(Q(number__icontains=search) | Q(party__name__icontains=search))
            location = request.headers.get('X-Location-ID')
            if location:
                try: query = query.filter(location_id=int(location))
                except ValueError: raise ValidationError('Invalid location.')
            result = []
            for document in query:
                try:
                    source_document(ctx, document.pk, kinds)
                except (PermissionDenied, ValidationError):
                    continue
                safe_lines = []
                for line in document.result.get('lines', []):
                    safe_lines.append({key: line[key] for key in ['index', 'product', 'product_name', 'quantity', 'unit', 'profile', 'block'] if key in line})
                result.append({'id': document.pk, 'number': document.number, 'kind': document.kind, 'date': document.date, 'warehouse': document.warehouse_id, 'party': document.party_id, 'party_name': document.party.name if document.party_id else '', 'reference': document.reference_id, 'result': {'lines': safe_lines}})
                if len(result) >= 100: break
            return response({'results': result, 'limit': 100, 'scope': 'Authorized transport/quality source references and quantities; no invoice values or confidential inputs.'})
        try:
            limit = max(1, min(200, int(request.query_params.get('limit', '100'))))
            offset = max(0, int(request.query_params.get('offset', '0')))
        except ValueError:
            raise ValidationError('Use integer pagination.')
        location = request.headers.get('X-Location-ID')
        if location:
            try: location = int(location)
            except ValueError: raise ValidationError('Invalid selected location.')
            if not ctx.location_allowed(location): raise PermissionDenied('Location is outside your assignment.')
        models = {'vehicles': TransportVehicle, 'drivers': TransportDriver, 'trips': DeliveryTrip, 'claims': CustomerQualityClaim, 'recalls': RecallCampaign}
        if section not in models:
            raise ValidationError('Unknown delivery/quality resource.')
        permissions = ['quality.view', 'quality.claim', 'quality.approve'] if section == 'claims' else ['quality.recall', 'quality.view'] if section == 'recalls' else ['delivery.view', 'delivery.post', 'delivery.confirm', 'delivery.manage']
        if not can(ctx, *permissions): raise PermissionDenied('This transport/quality resource is restricted.')
        query = models[section].objects.filter(business=ctx.business).order_by('-pk')
        if request.query_params.get('id'): query = query.filter(pk=request.query_params['id'])
        rows = []
        for item in query:
            try:
                if section == 'trips':
                    if location and item.warehouse.location_id != location: continue
                    row = trip_row(ctx, item)
                elif section == 'claims':
                    if location and item.invoice.location_id != location: continue
                    row = claim_row(ctx, item)
                elif section == 'recalls':
                    row = recall_row(ctx, item)
                else:
                    get_obj(ctx, type(item), item.pk)
                    if location and item.location_id != location: continue
                    row = serialize_model(item)
                rows.append(row)
            except (PermissionDenied, ValidationError):
                continue
        return response({'results': rows[offset:offset + limit], 'count': len(rows), 'next_offset': offset + limit if len(rows) > offset + limit else None})
