"""Scoped purchasing review, assigned counting and scale evidence endpoints."""
from django.core.exceptions import PermissionDenied, ValidationError
from .api import Boundary, response, can
from .core import get_obj, get_product, get_warehouse
from .models import Document, Membership, Product, Block, StockPool, Warehouse
from .procurement_models import SupplierClaim, CycleCountSession, WeighingDevice, WeightMeasurement
from .procurement import receipt_match, visible_claim, visible_count, source_document


class ProcurementAPI(Boundary):
    def get(self, request, section):
        ctx = self.ctx(request)
        location = request.headers.get('X-Location-ID')
        if location:
            try: location = int(location)
            except ValueError: raise ValidationError('Invalid selected location.')
            if not ctx.location_allowed(location): raise PermissionDenied('Location is outside your assignment.')
        try:
            offset = max(0, int(request.query_params.get('offset', 0)))
            limit = min(200, max(1, int(request.query_params.get('limit', 100))))
        except ValueError: raise ValidationError('Use integer pagination.')
        result = []
        if section in {'matches', 'sources'}:
            if not can(ctx, 'purchases.view', 'purchases.post', 'purchases.claim', 'purchases.approve'): raise PermissionDenied('Purchasing review is restricted.')
            query = Document.objects.filter(business=ctx.business, state='posted', kind__in=['purchase_receive'] if section == 'matches' else ['purchase_order', 'purchase_receive', 'purchase_return']).select_related('party').order_by('-pk')
            if location: query = query.filter(location_id=location)
            if request.query_params.get('id'): query = query.filter(pk=request.query_params['id'])
            for item in query:
                try:
                    source_document(ctx, item.pk, [item.kind])
                    if section == 'matches': row = receipt_match(ctx, item)
                    else:
                        safe = [{key: line[key] for key in ['index', 'product', 'product_name', 'quantity'] if key in line} for line in item.result.get('lines', [])]
                        row = {'id': item.pk, 'number': item.number, 'date': item.date, 'kind': item.kind, 'supplier': item.party_id, 'supplier_name': item.party.name if item.party_id else '', 'lines': safe}
                    result.append(row)
                except (PermissionDenied, ValidationError): continue
        elif section == 'claims':
            if not can(ctx, 'purchases.view', 'purchases.claim', 'purchases.approve'): raise PermissionDenied('Supplier claims are restricted.')
            for item in SupplierClaim.objects.filter(business=ctx.business).select_related('document', 'product', 'supplier', 'source').order_by('-pk'):
                try: visible_claim(ctx, item.pk)
                except (PermissionDenied, ValidationError): continue
                if location and item.document.location_id != location: continue
                resolution = getattr(item, 'resolution', None)
                result.append({'id': item.pk, 'number': item.source.number, 'date': item.source.date, 'supplier_name': item.supplier.name, 'document': item.document_id, 'document_number': item.document.number, 'product_name': item.product.name, 'quantity': item.quantity, 'unit': item.product.unit, 'reason': item.reason, 'description': item.description, 'state': item.state, 'resolution': {'outcome': resolution.outcome, 'note': resolution.note, 'financial_document': resolution.financial_document_id} if resolution else None})
        elif section == 'counts':
            if not can(ctx, 'inventory.count_record', 'inventory.count_manage', 'inventory.count_review'): raise PermissionDenied('Counting access is restricted.')
            for item in CycleCountSession.objects.filter(business=ctx.business).select_related('assignee__user', 'warehouse', 'source', 'observation').order_by('-pk'):
                try: visible_count(ctx, item.pk)
                except (PermissionDenied, ValidationError): continue
                if location and item.warehouse.location_id != location: continue
                row = {'id': item.pk, 'number': item.source.number, 'warehouse': item.warehouse_id, 'warehouse_name': item.warehouse.name, 'assignee': item.assignee_id, 'assignee_name': item.assignee.user.get_full_name() or item.assignee.user.username, 'mine': item.assignee.user_id == ctx.user.pk, 'due_date': item.due_date, 'targets': item.targets, 'instructions': item.instructions, 'state': item.state, 'blind': True}
                if ctx.has('inventory.count_review') and item.observation_id:
                    row['observation'] = item.observation_id
                    row['lines'] = [{key: line[key] for key in ['index', 'product', 'product_name', 'unit', 'block', 'expected_quantity', 'counted_quantity', 'variance']} for line in item.observation.result['lines']]
                    row['adjustment'] = item.adjustment_id
                result.append(row)
        elif section == 'assignment-options':
            ctx.require('inventory.count_manage')
            warehouses = Warehouse.objects.filter(business=ctx.business).exclude(kind='transit')
            targets = []
            for warehouse in warehouses:
                try: get_warehouse(ctx, warehouse.pk)
                except PermissionDenied: continue
                if location and warehouse.location_id != location: continue
                for pool in StockPool.objects.filter(business=ctx.business, warehouse=warehouse).exclude(product__unit='cm').select_related('product'):
                    try: get_product(ctx, pool.product_id)
                    except PermissionDenied: continue
                    targets.append({'key': f'pool:{pool.pk}', 'warehouse': warehouse.pk, 'product': pool.product_id, 'product_name': pool.product.name, 'code': pool.product.code, 'unit': pool.product.unit})
                for block in Block.objects.filter(business=ctx.business, warehouse=warehouse).exclude(status='in_transit').select_related('product'):
                    try: get_product(ctx, block.product_id)
                    except PermissionDenied: continue
                    targets.append({'key': f'block:{block.pk}', 'warehouse': warehouse.pk, 'product': block.product_id, 'product_name': block.product.name, 'block': block.pk, 'code': block.code, 'unit': 'cm'})
            members = []
            for member in Membership.objects.filter(business=ctx.business, active=True).select_related('user'):
                if not any(x in member.permissions for x in ['*', 'inventory.*', 'inventory.count_record']): continue
                members.append({'id': member.pk, 'name': member.user.get_full_name() or member.user.username, 'all_locations': member.all_locations, 'location_ids': member.location_ids})
            return response({'targets': targets, 'assignees': members})
        elif section in {'devices', 'measurements'}:
            if not can(ctx, 'inventory.measure', 'inventory.scale_manage', 'purchases.post'): raise PermissionDenied('Measured-weight evidence is restricted.')
            if section == 'devices':
                for device in WeighingDevice.objects.filter(business=ctx.business).select_related('warehouse'):
                    try: get_warehouse(ctx, device.warehouse_id)
                    except PermissionDenied: continue
                    if location and device.warehouse.location_id != location: continue
                    calibration = device.calibrations.select_related('source').order_by('-source__date', '-pk').first()
                    result.append({'id': device.pk, 'code': device.code, 'name': device.name, 'warehouse': device.warehouse_id, 'warehouse_name': device.warehouse.name, 'capacity_kg': device.capacity_kg, 'calibration': {'date': calibration.source.date, 'next_due': calibration.next_due, 'reference': calibration.reference, 'note': calibration.note} if calibration else None})
            else:
                used = {str(line['measurement']) for receipt in Document.objects.filter(business=ctx.business, state='posted', kind='purchase_receive') for line in receipt.data.get('lines', []) if line.get('measurement')}
                for measurement in WeightMeasurement.objects.filter(business=ctx.business).select_related('product', 'device__warehouse', 'source').order_by('-pk'):
                    try: get_product(ctx, measurement.product_id); get_warehouse(ctx, measurement.device.warehouse_id)
                    except PermissionDenied: continue
                    if location and measurement.device.warehouse.location_id != location: continue
                    result.append({'id': measurement.pk, 'number': measurement.source.number, 'date': measurement.source.date, 'device': measurement.device.code, 'warehouse': measurement.device.warehouse_id, 'product': measurement.product_id, 'product_name': measurement.product.name, 'gross_kg': measurement.gross_kg, 'tare_kg': measurement.tare_kg, 'net_kg': measurement.net_kg, 'container_count': measurement.container_count, 'received': str(measurement.pk) in used})
        else: raise ValidationError('Unknown procurement/counting resource.')
        return response({'results': result[offset:offset+limit], 'count': len(result), 'next_offset': offset+limit if len(result)>offset+limit else None})
