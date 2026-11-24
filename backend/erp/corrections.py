"""Physical stock-count evidence and separately authorized reconciliation.

Counting never changes quantities or journals. Applying a count is a distinct
posting that rejects stale observations instead of silently replacing new stock
movements. Financial corrections continue to use supported linked return,
credit, refund, and valuation workflows rather than an unsafe generic reversal.
"""
from decimal import Decimal

from django.core.exceptions import ValidationError

from .core import D, get_product, get_warehouse, journal, money, pool_for, stock_in, stock_out
from .models import Block, Document, StockMovement
from .operations import block_for, dims, entry, geometry_zero, inventory_account, posted


ZERO = Decimal("0")
QUANTITY = Decimal(".000001")


def counted_quantity(product, value):
    quantity = D(value)
    if quantity < 0 or quantity != quantity.quantize(QUANTITY):
        raise ValidationError("Counted quantity must be nonnegative with at most six decimal places.")
    if product.unit == "each" and quantity != quantity.to_integral_value():
        raise ValidationError("Counted pieces must be whole numbers.")
    return quantity


def pool_snapshot(pool):
    latest = StockMovement.objects.filter(pool=pool).order_by("-id").values_list("id", flat=True).first()
    return {"pool": pool.id, "quantity": str(pool.quantity), "value": str(pool.value), "last_movement": latest, "last_date": pool.last_date.isoformat() if pool.last_date else None}


def stock_count(ctx, payload, doc):
    warehouse = get_warehouse(ctx, payload["warehouse"])
    if warehouse.kind == "transit":
        raise ValidationError("Count physical stores/floor stock; resolve in-transit discrepancies through the transfer.")
    doc.warehouse, doc.location = warehouse, warehouse.location
    lines, seen = [], set()
    for index, source in enumerate(payload.get("lines", [])):
        product = get_product(ctx, source["product"])
        if product.kind == "service":
            raise ValidationError("Services cannot be physically counted.")
        profile, block, block_snapshot = "", None, None
        if product.unit == "cm":
            block = block_for(ctx, source["block"], warehouse)
            if block.product_id != product.pk or block.status == "in_transit":
                raise ValidationError("Count an identified local block matching the product.")
            measured = geometry_zero(source["counted_height_mm"], "counted height")
            if measured < block.reserved_height_mm:
                raise ValidationError("Resolve reservations before counting less than their committed height.")
            profile = block.profile
            expected, counted = block.remaining_height_mm / 10, measured / 10
            block_snapshot = {"height_mm": str(block.remaining_height_mm), "reserved_height_mm": str(block.reserved_height_mm), "status": block.status}
            key = ("block", block.pk)
        else:
            key = ("pool", product.pk)
            counted = counted_quantity(product, source["counted_quantity"])
            expected = None
        if key in seen:
            raise ValidationError("Each product pool or physical block can appear only once in a count.")
        seen.add(key)
        pool = pool_for(ctx, product, warehouse, profile)
        if pool.last_date and pool.last_date > doc.date:
            raise ValidationError("A physical count cannot backdate before later stock movements.")
        if expected is None:
            expected = pool.quantity
        lines.append({"index": index, "product": product.pk, "product_name": product.name, "unit": product.unit, "profile": profile, "block": block.pk if block else None, "expected_quantity": str(expected), "counted_quantity": str(counted), "variance": str(counted - expected), "pool_snapshot": pool_snapshot(pool), "block_snapshot": block_snapshot})
    if not lines:
        raise ValidationError("Enter at least one physically counted item or block.")
    return {"warehouse": warehouse.pk, "lines": lines, "status": "observed", "posting_effect": "none", "notes": str(payload.get("notes", ""))}


def stock_count_adjust(ctx, payload, doc):
    count = posted(ctx, payload["count"], ["stock_count", "cycle_count_record"])
    if not str(payload.get("reason", "")).strip():
        raise ValidationError("Count reconciliation requires an approved variance reason.")
    if Document.objects.filter(business=ctx.business, kind="stock_count_adjust", reference=count, state="posted").exists():
        raise ValidationError("This count has already been reconciled. Record a new observation for later changes.")
    warehouse = get_warehouse(ctx, count.warehouse_id)
    doc.reference, doc.warehouse, doc.location = count, warehouse, warehouse.location
    requested_values = payload.get("values", {})
    if not isinstance(requested_values, dict):
        raise ValidationError("Surplus cost values must map count-line indexes to monetary values.")
    verified = []
    # Validate every observation before mutating the first pool. Multiple block
    # lines can share one financial pool without invalidating their own count.
    for line in count.result["lines"]:
        product = get_product(ctx, line["product"])
        pool = pool_for(ctx, product, warehouse, line["profile"])
        current = pool_snapshot(pool)
        observed = line["pool_snapshot"]
        if any(current[key] != observed[key] for key in ("pool", "last_movement", "last_date")) or D(current["quantity"]) != D(observed["quantity"]) or D(current["value"]) != D(observed["value"]):
            raise ValidationError("Stock changed after this count. Recount affected items before reconciliation.")
        block = None
        if line["block"]:
            block = block_for(ctx, line["block"], warehouse)
            snapshot = line["block_snapshot"]
            if block.product_id != product.pk or block.profile != line["profile"] or block.remaining_height_mm != D(snapshot["height_mm"]) or block.reserved_height_mm != D(snapshot["reserved_height_mm"]) or block.status != snapshot["status"]:
                raise ValidationError("Block geometry, reservation, or condition changed after counting. Recount it.")
        verified.append((line, product, pool, block))
    results, journals, approval_value = [], [], ZERO
    for line, product, observed_pool, block in verified:
        variance = D(line["variance"])
        value, signed_value = ZERO, ZERO
        if variance:
            if variance > 0:
                supplied = requested_values.get(str(line["index"]), requested_values.get(line["index"]))
                if supplied is None:
                    if observed_pool.quantity <= 0:
                        raise ValidationError("A surplus in an empty pool requires an explicit approved carrying value.")
                    value = money(D(line["pool_snapshot"]["value"]) * variance / D(line["pool_snapshot"]["quantity"]))
                else:
                    value = money(D(supplied))
                    if value < 0:
                        raise ValidationError("Approved surplus carrying value cannot be negative.")
                stock_in(ctx, doc, product, warehouse, variance, value, line["profile"])
                journals += [entry(inventory_account(product), debit=value, **dims(product, warehouse)), entry("EXPENSE", credit=value, **dims(product, warehouse))]
                signed_value = value
            else:
                if str(line["index"]) in requested_values or line["index"] in requested_values:
                    raise ValidationError("Shortage cost uses the current moving average and cannot be overridden.")
                value = stock_out(ctx, doc, product, warehouse, -variance, line["profile"])
                journals += [entry("WASTE", debit=value, **dims(product, warehouse)), entry(inventory_account(product), credit=value, **dims(product, warehouse))]
                signed_value = -value
            if block:
                height = D(line["counted_quantity"]) * 10
                block.remaining_height_mm = height
                if height == 0:
                    block.status = "exhausted"
                elif block.status in ("exhausted", "damaged"):
                    block.status = "inspection"
                # Counting does not release curing/inspection stock or clear any
                # reservation; a separate quality/reservation action does that.
                block.save(update_fields=["remaining_height_mm", "status"])
            approval_value += value
        results.append({"index": line["index"], "product": product.pk, "product_name": product.name, "block": line["block"], "quantity": str(variance), "counted_quantity": line["counted_quantity"], "cost": str(value), "value": str(signed_value)})
    if not any(D(line["quantity"]) for line in results):
        raise ValidationError("This count has no variance requiring an adjustment.")
    doc.amount = money(approval_value)
    journal(ctx, doc, journals)
    return {"count": count.pk, "warehouse": warehouse.pk, "lines": results, "total": str(approval_value), "reason": str(payload["reason"]), "status": "reconciled"}


OPERATIONS = {
    "stock_count": ("inventory.count", stock_count),
    "stock_count_adjust": ("inventory.adjust", stock_count_adjust),
}
