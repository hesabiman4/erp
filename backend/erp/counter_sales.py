"""Scoped counter-sale read models; ordinary sale remains the posting authority."""
import json
import re
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, Sum
from .core import D, get_obj, get_product, get_warehouse
from .models import Business, Block, Document, StockPool, AuditEvent, RecallBlockHold, RecallProductHold, ForeignExposure


DEFAULT_THICKNESSES = ['10', '20', '22', '30', '50']


def shortcuts(ctx):
    raw = ctx.business.settings.get('counter_sales_thickness_mm', DEFAULT_THICKNESSES)
    if not isinstance(raw, list) or len(raw) > 12:
        raise ValidationError('Counter thickness configuration must contain at most 12 values.')
    values = []
    for item in raw:
        value = D(item)
        if value <= 0 or value > 10000 or value != value.quantize(D('.001')):
            raise ValidationError('Thickness shortcuts require positive millimetres with at most three decimal places.')
        text = format(value.normalize(), 'f')
        if text in values: raise ValidationError('Thickness shortcuts must be unique.')
        values.append(text)
    return values


@transaction.atomic
def configure(ctx, payload):
    ctx.require('settings.manage')
    business = Business.objects.select_for_update().get(pk=ctx.business.pk)
    previous = business.settings.get('counter_sales_thickness_mm', DEFAULT_THICKNESSES)
    business.settings = {**business.settings, 'counter_sales_thickness_mm': payload.get('thickness_mm')}
    ctx.business = business
    values = shortcuts(ctx)
    business.settings['counter_sales_thickness_mm'] = values
    business.save(update_fields=['settings'])
    AuditEvent.objects.create(business=business, user=ctx.user, action='counter.thickness_shortcuts', details={'before': previous, 'after': values})
    return {'thickness_mm': values, 'financial_posting': False}


def availability(ctx, params):
    ctx.require('sales.post')
    warehouse = get_warehouse(ctx, params.get('warehouse'))
    if warehouse.kind == 'transit': raise ValidationError('Goods in transit cannot be sold.')
    product = get_product(ctx, params.get('product'))
    if not product.active or product.kind == 'raw': raise ValidationError('Select an active saleable product.')
    try: offset = int(params.get('offset', 0))
    except (TypeError, ValueError): raise ValidationError('Use a nonnegative availability offset.')
    if offset < 0 or offset > 1000000: raise ValidationError('Availability offset is outside the supported range.')
    held = RecallProductHold.objects.filter(business=ctx.business, product=product, released_by__isnull=True).exists()
    result = {'product': product.id, 'warehouse': warehouse.id, 'unit': product.unit, 'price': product.price,
              'held': held, 'thickness_mm': shortcuts(ctx), 'blocks': [], 'available_quantity': '0',
              'inspection_required': bool(ctx.business.settings.get('require_inspection')),
              'inspection_verified_by_preview': False,
              'count': 0, 'next_offset': None, 'basis': 'Current unreserved stock; revalidated atomically when the ordinary sale posts.'}
    if held: return result
    if product.kind == 'service':
        result['available_quantity'] = None
        return result
    if product.unit != 'cm':
        if params.get('code'):raise ValidationError('A block label requires the matching sponge product and warehouse.')
        result['available_quantity'] = StockPool.objects.filter(business=ctx.business, warehouse=warehouse, product=product, profile='').aggregate(total=Sum('quantity'))['total'] or D('0')
        return result
    blocks = Block.objects.filter(business=ctx.business, warehouse=warehouse, product=product,
                                  status__in=['ready', 'reserved'], remaining_height_mm__gt=F('reserved_height_mm'))
    blocks = blocks.exclude(pk__in=RecallBlockHold.objects.filter(business=ctx.business, released_by__isnull=True).values('block_id'))
    if params.get('code'):
        code = str(params['code']).strip()
        if len(code) > 300: raise ValidationError('Block search is too long.')
        scanned = None
        if code.startswith('{'):
            try: label = json.loads(code)
            except (TypeError, ValueError): raise ValidationError('Unrecognized block QR content.')
            if not isinstance(label, dict) or label.get('type') != 'erp-block' or type(label.get('version')) is not int or label.get('version') != 1 or type(label.get('business')) is not int or label.get('business') != ctx.business.id:
                raise ValidationError('Block QR belongs to another business or an unsupported format.')
            scanned = get_obj(ctx, Block, label.get('block'))
            if label.get('code') != scanned.code: raise ValidationError('Block QR identity does not match its current code.')
        elif '/api/blocks/' in code:
            match = re.search(r'/api/blocks/(\d+)/label/(?:\?.*)?$', code)
            if not match: raise ValidationError('Unrecognized block label reference.')
            scanned = get_obj(ctx, Block, match.group(1))
        if scanned:
            get_product(ctx, scanned.product_id)
            if scanned.warehouse_id != warehouse.id or scanned.product_id != product.id:
                raise ValidationError('Scanned block does not match the selected product and warehouse.')
            blocks = blocks.filter(pk=scanned.id)
        else:
            if len(code) > 80: raise ValidationError('Block-code search is too long.')
            blocks = blocks.filter(code__icontains=code)
    if params.get('profile'): blocks = blocks.filter(profile=str(params['profile'])[:100])
    if params.get('thickness_mm'):
        thickness = D(params['thickness_mm']); count = D(params.get('sheet_count', '1')); loss = D(params.get('cutting_loss_mm', '0'))
        if thickness <= 0 or count <= 0 or count != count.to_integral_value() or count > 10000 or loss < 0:
            raise ValidationError('Use positive thickness, whole sheet count and nonnegative total loss.')
        blocks = blocks.filter(remaining_height_mm__gte=F('reserved_height_mm') + thickness * count + loss)
    result['count'] = blocks.count()
    result['blocks'] = [{'id': block.id, 'code': block.code, 'profile': block.profile, 'length_mm': block.length_mm,
                         'width_mm': block.width_mm, 'remaining_height_mm': block.remaining_height_mm,
                         'reserved_height_mm': block.reserved_height_mm, 'available_height_mm': block.remaining_height_mm - block.reserved_height_mm}
                        for block in blocks.order_by('remaining_height_mm', 'id')[offset:offset + 50]]
    result['next_offset'] = offset + 50 if offset + 50 < result['count'] else None
    # Never aggregate unlike footprints into an interchangeable cm quantity.
    result['available_quantity'] = None
    return result


def repeat_sale(ctx, identifier):
    from .api import doc_permission
    ctx.require('sales.post'); ctx.require('sales.view')
    source = get_obj(ctx, Document, identifier); doc_permission(ctx, source)
    if source.kind != 'sale' or source.state != 'posted': raise ValidationError('Select an original posted sale to repeat.')
    if ForeignExposure.objects.filter(business=ctx.business,invoice=source).exists() or source.result.get('foreign') or source.data.get('foreign_currency') or source.data.get('currency') not in (None, '', 'AFN'):
        raise ValidationError('Repeat foreign-priced sales through the full reviewed foreign invoice workflow.')
    warehouse = get_warehouse(ctx, source.warehouse_id)
    lines = []
    for item in source.result.get('lines', []):
        product = get_product(ctx, item['product'])
        if not product.active or product.kind == 'raw': raise ValidationError('A previous product is no longer saleable.')
        lines.append({'product': product.id, 'product_name': product.name, 'unit': product.unit, 'unit_price': product.price,
                      'thickness_mm': item.get('thickness_mm', '') if product.unit == 'cm' else '',
                      'sheet_count': item.get('sheet_count', 1) if product.unit == 'cm' else 1,
                      'quantity': item.get('quantity', ''), 'source_profile': item.get('profile', ''),
                      'block': '', 'cutting_loss_mm': '0'})
    if not lines or len(lines) > 100: raise ValidationError('This sale has no supported repeatable lines.')
    return {'source': source.id, 'number': source.number, 'warehouse': warehouse.id, 'party': source.party_id,
            'lines': lines, 'paid': '0', 'order': None,
            'basis': 'Customer and requested quantities copied only. Select current physical stock, review current prices, tax and actual payment. Original sale is unchanged.'}
