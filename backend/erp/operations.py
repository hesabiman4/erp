"""Transactional inventory, manufacturing, and fulfillment domain handlers.

The public entry point is core.execute. Handlers deliberately do not commit, number
documents, or swallow errors: the outer posting boundary locks the business and
rolls back the document, stock ledger, and journals together.
"""
from .party_profiles import snapshot as party_snapshot
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.exceptions import PermissionDenied
from django.db.models import Q

from .models import Allocation, Block, BOM, Document, Party, Product, TaxRule, Warehouse
from .core import (
    D, money, get_obj, get_product, get_warehouse, pool_for, profile_for,
    stock_in, stock_out, journal, outstanding,
)

ZERO = Decimal("0")


def positive(value, label="quantity"):
    value = D(value)
    if value <= 0:
        raise ValidationError(f"{label} must be greater than zero.")
    return value


def nonnegative(value, label="amount"):
    value = D(value)
    if value < 0:
        raise ValidationError(f"{label} cannot be negative.")
    return value


def geometry(value, label="dimension"):
    value = positive(value, label)
    if value != value.quantize(Decimal(".001")):
        raise ValidationError(f"{label} supports at most three decimal mm places.")
    return value


def geometry_zero(value, label="dimension"):
    value = nonnegative(value, label)
    if value != value.quantize(Decimal(".001")):
        raise ValidationError(f"{label} supports at most three decimal mm places.")
    return value


def sheet_thickness(item):
    """Accept explicitly labeled entry units, preserving exact server arithmetic."""
    if "thickness_mm" in item:
        thickness = geometry(item["thickness_mm"], "sheet thickness")
        if "thickness_cm" in item and thickness != D(item["thickness_cm"]) * 10:
            raise ValidationError("The mm and cm thickness values disagree.")
        return thickness
    if "thickness_cm" in item:
        return geometry(D(item["thickness_cm"]) * 10, "sheet thickness")
    unit = item.get("thickness_unit", "mm")
    if unit not in ("mm", "cm"):
        raise ValidationError("Sheet thickness unit must be mm or cm.")
    return geometry(D(item["thickness"]) * (10 if unit == "cm" else 1), "sheet thickness")


def inventory_account(product, warehouse=None):
    if warehouse and warehouse.kind == "transit":
        return "TRANSIT"
    return "RAW" if product.kind == "raw" else "TRIM" if product.kind in ("trim", "scrap") else "FG"


def entry(code, debit=ZERO, credit=ZERO, **dimensions):
    return {"account": code, "debit": money(debit), "credit": money(credit), **dimensions}


def dims(product, warehouse, **extra):
    return {"line": product.line, "warehouse": warehouse.id, "location": warehouse.location_id, **extra}


def posted(ctx, identifier, kinds=None):
    source = get_obj(ctx, Document, identifier)
    if source.state != "posted" or (kinds and source.kind not in kinds):
        raise ValidationError("The referenced document is not a compatible posted document.")
    return source


def party_for(ctx, payload, kind="customer"):
    identifier = payload.get("party") or payload.get("supplier")
    if identifier:
        party = get_obj(ctx, Party, identifier)
        if party.kind != kind:
            raise ValidationError(f"A {kind} account is required.")
        return party
    if kind == "customer":
        # Each unidentified walk-in debt retains an invoice-linked party identity.
        return Party.objects.create(
            business=ctx.business, kind="customer",
            name=payload.get("customer_name") or "مشتری گذری / Walk-in",
            phone=payload.get("phone", ""), address=payload.get("address", ""),
            notes=payload.get("notes", ""),
        )
    raise ValidationError("A supplier account is required.")


def block_for(ctx, identifier, warehouse=None, ready=False):
    block = get_obj(ctx, Block, identifier)
    if warehouse and block.warehouse_id != warehouse.id:
        raise ValidationError("The block is not in the selected warehouse.")
    if ready and block.status not in ("ready", "reserved"):
        raise ValidationError("This block is held, exhausted, or not available for sale.")
    return block


def make_block(ctx, doc, product, warehouse, spec, parent=None, suffix=""):
    length = geometry(spec["length_mm"], "length")
    width = geometry(spec["width_mm"], "width")
    height = geometry(spec.get("height_mm", spec.get("remaining_height_mm")), "height")
    profile = profile_for(length, width)
    status = spec.get("status", "ready")
    if status not in ("ready", "curing", "inspection", "damaged", "in_transit"):
        raise ValidationError("Invalid initial block status.")
    block = Block.objects.create(
        business=ctx.business, product=product, warehouse=warehouse,
        batch=doc if doc.kind.startswith("production") else (parent.batch if parent else doc),
        parent=parent, code=spec.get("code") or f"{doc.number}-{suffix or Block.objects.filter(business=ctx.business).count() + 1}",
        length_mm=length, width_mm=width, initial_height_mm=height,
        remaining_height_mm=height, reserved_height_mm=ZERO, status=status, profile=profile,
    )
    return block


def _planned_outputs(ctx, payload):
    outputs = payload.get("outputs") or []
    if not outputs:
        raise ValidationError("At least one measured production output is required.")
    planned = []
    for i, output in enumerate(outputs):
        product = get_product(ctx, output["product"])
        if product.kind not in ("finished", "trim", "scrap"):
            raise ValidationError("Production outputs must be finished goods, trim, or recoverable scrap.")
        ctx.lines.add(product.line)
        if product.unit == "cm":
            blocks = output.get("blocks") or []
            if not blocks:
                raise ValidationError("Sponge output requires the measured dimensions of each physical block.")
            qty = sum((geometry(b["height_mm"], "height") / 10 for b in blocks), ZERO)
            if "quantity" in output and D(output["quantity"]) != qty:
                raise ValidationError("Output cm must equal the sum of measured block heights.")
            for b in blocks:
                geometry(b["length_mm"], "length")
                geometry(b["width_mm"], "width")
        else:
            qty = positive(output["quantity"])
            blocks = []
            if product.unit == "each" and qty != qty.to_integral_value():
                raise ValidationError("Piece counts must be whole numbers.")
        planned.append({"product": product, "quantity": qty, "blocks": blocks, "source": output, "index": i})
    return planned


def _output_costs(planned, total):
    total = money(total)
    if any("cost" in p["source"] for p in planned):
        if not all("cost" in p["source"] for p in planned):
            raise ValidationError("Provide a carrying cost for every output, or allocation weights for every output.")
        values = [money(nonnegative(p["source"]["cost"], "output cost")) for p in planned]
        if sum(values, ZERO) != total:
            raise ValidationError("Output costs plus approved loss must exactly equal the batch cost.")
        return values
    if len(planned) == 1:
        return [total]
    if not all("allocation_weight" in p["source"] for p in planned):
        raise ValidationError("Multiple outputs require explicit carrying costs or approved allocation weights.")
    weights = [positive(p["source"]["allocation_weight"], "allocation weight") for p in planned]
    allocated, remainder = [], total
    for i, weight in enumerate(weights):
        value = remainder if i == len(weights) - 1 else money(total * weight / sum(weights, ZERO))
        allocated.append(value)
        remainder -= value
    return allocated


def _receive_outputs(ctx, doc, warehouse, planned, total):
    values = _output_costs(planned, total)
    result, journals = [], []
    for item, value in zip(planned, values):
        product, qty = item["product"], item["quantity"]
        block_ids = []
        if product.unit == "cm":
            # Across unlike footprints, allocate this output's value by measured
            # volume, not merely the sum of incomparable heights.
            weights = [D(b["height_mm"]) * D(b["length_mm"]) * D(b["width_mm"]) for b in item["blocks"]]
            remainder = value
            for j, (spec, weight) in enumerate(zip(item["blocks"], weights)):
                block = make_block(ctx, doc, product, warehouse, spec, suffix=f"{item['index']+1}-{j+1}")
                part = remainder if j == len(weights) - 1 else money(value * weight / sum(weights, ZERO))
                stock_in(ctx, doc, product, warehouse, block.remaining_height_mm / 10, part, block.profile)
                remainder -= part
                block_ids.append(block.id)
        else:
            stock_in(ctx, doc, product, warehouse, qty, value)
        journals.append(entry(inventory_account(product), debit=value, **dims(product, warehouse)))
        result.append({"product": product.id, "product_name": product.name, "quantity": str(qty), "cost": str(value), "blocks": block_ids})
    return result, journals


def _consume_inputs(ctx, doc, payload, default_warehouse):
    total, output, journals = ZERO, [], []
    for item in payload.get("inputs", []):
        product = get_product(ctx, item["product"])
        ctx.lines.add(product.line)
        warehouse = get_warehouse(ctx, item.get("warehouse", default_warehouse.id))
        if warehouse.kind == "transit" or product.unit == "cm" or product.kind == "service":
            raise ValidationError("Consume measured materials from available stores/floor stock; dimensioned block rework needs an explicit conversion.")
        qty = positive(item["quantity"])
        cost = stock_out(ctx, doc, product, warehouse, qty)
        total += cost
        output.append({"product": product.id, "warehouse": warehouse.id, "quantity": str(qty), "cost": str(cost)})
        journals.append(entry(inventory_account(product), credit=cost, **dims(product, warehouse)))
    labour = money(nonnegative(payload.get("labor_cost", "0"), "labor cost"))
    overhead = money(nonnegative(payload.get("overhead_cost", "0"), "overhead cost"))
    conversion = labour + overhead
    if conversion:
        ctx.require("production.cost")
        sources = payload.get("conversion_sources", [])
        allocations, source_total = [], ZERO
        for requested in sources:
            identifier = requested.get("document") if isinstance(requested, dict) else requested
            source = posted(ctx, identifier, ["payroll_accrue", "expense_post"])
            if source.date > doc.date:
                raise ValidationError("Production cannot absorb a cost source from a future date.")
            eligible = list(source.entries.filter(account__code__in=["LABOR_CLEARING", "COST_CLEARING"], debit__gt=0).select_related("account"))
            source_value = sum((line.debit for line in eligible), ZERO)
            previous = sum((D(allocation["amount"]) for previous_doc in Document.objects.filter(business=ctx.business, state="posted", kind__in=["production", "production_bom", "production_consume"]) for allocation in previous_doc.data.get("conversion_allocations", []) if allocation["document"] == source.id), ZERO)
            previous += sum((D(allocation["amount"]) for allocation in allocations if allocation["document"] == source.id), ZERO)
            available = source_value - previous
            from .late_cost import prior_allocated
            available -= prior_allocated(source.id)
            value = money(positive(requested.get("amount", available) if isinstance(requested, dict) else available, "source allocation"))
            if value > available:
                raise ValidationError("The source does not have sufficient unabsorbed eligible production costs.")
            # Supported source events post a single clearing debit; source cost
            # already exists and is reclassified, never expensed a second time.
            if len({line.account.code for line in eligible}) != 1:
                raise ValidationError("The source must identify one eligible production clearing account.")
            journals.append(entry(eligible[0].account.code, credit=value, location=default_warehouse.location_id, employee=source.employee_id))
            allocations.append({"document": source.id, "amount": str(value), "account": eligible[0].account.code})
            source_total += value
        if sources:
            if source_total != conversion:
                raise ValidationError("Linked source allocations must exactly equal labor plus overhead.")
            doc.data = {**doc.data, "conversion_allocations": allocations}
        else:
            raise ValidationError("Nonzero conversion costs require linked posted eligible payroll/production-expense sources.")
        total += conversion
    if total:
        journals.append(entry("WIP", debit=total, location=default_warehouse.location_id))
    return money(total), output, journals


def _bom_requirements(ctx, payload):
    if ctx.business.manufacturing_mode == "trading":
        raise ValidationError("Manufacturing is disabled for this business; configure its manufacturing mode first.")
    if not payload.get("bom"):
        if ctx.business.manufacturing_mode == "bom":
            raise ValidationError("Select an approved BOM version for BOM-assisted production.")
        return None
    if ctx.business.manufacturing_mode != "bom":
        raise ValidationError("BOM-assisted production is disabled for this business.")
    bom = get_obj(ctx, BOM, payload["bom"])
    get_product(ctx, bom.product_id)
    if not bom.approved:
        raise ValidationError("Only approved BOM versions can be used.")
    planned_qty = positive(payload.get("planned_quantity", bom.output_quantity))
    denominator = positive(bom.output_quantity, "BOM output quantity")
    expected = []
    for line in bom.components:
        component = get_product(ctx, line["product"])
        expected.append({"product": component.id, "quantity": str(positive(line["quantity"], "BOM component quantity") * planned_qty / denominator)})
    if payload.get("outputs") and not any(int(output["product"]) == bom.product_id for output in payload["outputs"]):
        raise ValidationError("The selected BOM product must be included in the actual production outputs.")
    return {"bom": bom.id, "product": bom.product_id, "version": bom.version, "planned_quantity": str(planned_qty), "expected": expected}


def production_start(ctx, payload, doc):
    warehouse = get_warehouse(ctx, payload["warehouse"])
    doc.warehouse, doc.location = warehouse, warehouse.location
    if payload.get("work_order"):
        from .growth import before_production
        before_production(ctx, payload, doc)
    requirements = _bom_requirements(ctx, payload)
    return {"warehouse": warehouse.id, "wip_in": "0.00", "wip_out": "0.00", "bom": requirements, "status": "open"}


def production_consume(ctx, payload, doc):
    batch = posted(ctx, payload["batch"], ["production_start"])
    if Document.objects.filter(reference=batch, kind="production_complete", state="posted").exists():
        raise ValidationError("Costs must be finalized before output completion; late cost replay is not supported.")
    warehouse = get_warehouse(ctx, payload.get("warehouse", batch.warehouse_id))
    doc.reference, doc.warehouse, doc.location = batch, warehouse, warehouse.location
    if batch.data.get("work_order"):
        from .growth import before_production
        before_production(ctx, {**payload, "work_order": batch.data["work_order"]}, doc)
    total, inputs, journals = _consume_inputs(ctx, doc, payload, warehouse)
    if not total and not inputs:
        raise ValidationError("Record actual consumption or eligible conversion costs.")
    journal(ctx, doc, journals)
    return {"batch": batch.id, "inputs": inputs, "wip_in": str(total), "wip_out": "0.00"}


def _finish_production(ctx, payload, doc, warehouse, available):
    planned = _planned_outputs(ctx, payload)
    if len(planned) > 1:
        ctx.require("production.cost")
    loss = money(nonnegative(payload.get("abnormal_loss", "0"), "abnormal loss"))
    allocated = money(nonnegative(payload.get("allocated_cost", available), "allocated batch cost"))
    if allocated > available or loss > allocated:
        raise ValidationError("Completion or abnormal loss exceeds available batch WIP.")
    outputs, journals = _receive_outputs(ctx, doc, warehouse, planned, allocated - loss)
    if loss:
        journals.append(entry("WASTE", debit=loss, location=warehouse.location_id))
    journals.append(entry("WIP", credit=allocated, location=warehouse.location_id))
    return outputs, journals, allocated, loss


def production_complete(ctx, payload, doc):
    batch = posted(ctx, payload["batch"], ["production_start"])
    warehouse = get_warehouse(ctx, payload.get("warehouse", batch.warehouse_id))
    children = Document.objects.filter(reference=batch, state="posted")
    available = sum((D(c.result.get("wip_in", "0")) - D(c.result.get("wip_out", "0")) for c in children), ZERO)
    if available <= 0:
        raise ValidationError("The production batch has no remaining costed WIP.")
    doc.reference, doc.warehouse, doc.location = batch, warehouse, warehouse.location
    outputs, journals, allocated, loss = _finish_production(ctx, payload, doc, warehouse, available)
    journal(ctx, doc, journals)
    return {"batch": batch.id, "outputs": outputs, "wip_in": "0.00", "wip_out": str(allocated), "wip_remaining": str(available - allocated), "abnormal_loss": str(loss)}


def production(ctx, payload, doc):
    warehouse = get_warehouse(ctx, payload["warehouse"])
    doc.warehouse, doc.location = warehouse, warehouse.location
    requirements = _bom_requirements(ctx, payload)
    total, inputs, journals = _consume_inputs(ctx, doc, payload, warehouse)
    if total <= 0:
        raise ValidationError("A completed batch requires actual costed inputs or conversion costs.")
    outputs, finish_journals, allocated, loss = _finish_production(ctx, payload, doc, warehouse, total)
    if allocated != total:
        raise ValidationError("One-shot production must allocate all batch cost; use staged production for WIP.")
    journal(ctx, doc, journals + finish_journals)
    return {"inputs": inputs, "outputs": outputs, "total_cost": str(total), "wip_in": str(total), "wip_out": str(allocated), "abnormal_loss": str(loss), "bom": requirements}


def trim(ctx, payload, doc):
    block = block_for(ctx, payload["block"])
    product, warehouse = get_product(ctx, block.product_id), get_warehouse(ctx, block.warehouse_id)
    ctx.lines.add(product.line)
    if block.status not in ("curing", "inspection", "ready") or block.reserved_height_mm:
        raise ValidationError("Release block reservations and quality holds before trimming.")
    main = geometry(payload["main_height_mm"], "main height")
    top = geometry_zero(payload.get("top_height_mm", "0"), "top height")
    bottom = geometry_zero(payload.get("bottom_height_mm", "0"), "bottom height")
    loss = geometry_zero(payload.get("loss_mm", "0"), "loss")
    if main + top + bottom + loss != block.remaining_height_mm:
        raise ValidationError("Main, top, bottom, and loss heights must reconcile to the measured source block.")
    if top + bottom and not payload.get("outputs"):
        raise ValidationError("Record saleable/recoverable trim outputs rather than discarding their identity.")
    doc.warehouse, doc.location = warehouse, warehouse.location
    cost = stock_out(ctx, doc, product, warehouse, block.remaining_height_mm / 10, block.profile)
    trim_outputs = _planned_outputs(ctx, {"outputs": payload["outputs"]}) if payload.get("outputs") else []
    abnormal = money(nonnegative(payload.get("abnormal_loss_cost", "0")))
    if abnormal > cost:
        raise ValidationError("Loss cost exceeds source carrying value.")
    trim_values = [money(nonnegative(p["source"].get("cost", "0"))) for p in trim_outputs]
    main_cost = money(payload.get("main_cost", cost - sum(trim_values, ZERO) - abnormal))
    if main_cost < 0 or main_cost + sum(trim_values, ZERO) + abnormal != cost:
        raise ValidationError("Main block, trim carrying values, and abnormal loss must conserve source cost.")
    stock_in(ctx, doc, product, warehouse, main / 10, main_cost, block.profile)
    block.remaining_height_mm = main
    block.status = "ready"
    block.save(update_fields=["remaining_height_mm", "status"])
    outputs, journals = [], []
    if trim_outputs:
        outputs, journals = _receive_outputs(ctx, doc, warehouse, trim_outputs, sum(trim_values, ZERO))
    journals += [entry(inventory_account(product), credit=cost, **dims(product, warehouse)), entry(inventory_account(product), debit=main_cost, **dims(product, warehouse))]
    if abnormal:
        journals.append(entry("WASTE", debit=abnormal, **dims(product, warehouse)))
    journal(ctx, doc, journals)
    return {"block": block.id, "main_height_mm": str(main), "top_height_mm": str(top), "bottom_height_mm": str(bottom), "loss_mm": str(loss), "outputs": outputs, "cost": str(cost), "main_cost": str(main_cost), "abnormal_loss": str(abnormal)}


def reserve(ctx, payload, doc):
    results = []
    for item in payload.get("lines", []):
        block = block_for(ctx, item["block"], ready=True)
        get_product(ctx, block.product_id)
        count = positive(item.get("sheet_count", "1"), "sheet count")
        if count != count.to_integral_value():
            raise ValidationError("Sheet count must be a whole number.")
        loss = geometry_zero(item.get("cutting_loss_mm", "0"))
        if item.get("loss_policy", "per_operation") == "per_cut":
            loss *= count
        height = sheet_thickness(item) * count + loss
        if height > block.remaining_height_mm - block.reserved_height_mm:
            raise ValidationError("Insufficient unreserved height in the selected block.")
        block.reserved_height_mm += height
        block.save(update_fields=["reserved_height_mm"])
        results.append({"block": block.id, "height_mm": str(height)})
    if not results:
        raise ValidationError("Select blocks to reserve.")
    return {"lines": results}


def _release_reservation(ctx, reservation, doc):
    reservation = posted(ctx, reservation, ["reserve"])
    if Document.objects.filter(reference=reservation, state="posted", kind__in=["reservation_release", "sale", "cut"]).exists():
        raise ValidationError("This reservation has already been released or fulfilled.")
    for line in reservation.result["lines"]:
        block = block_for(ctx, line["block"])
        height = D(line["height_mm"])
        if block.reserved_height_mm < height:
            raise ValidationError("Reservation ledger is inconsistent.")
        block.reserved_height_mm -= height
        block.save(update_fields=["reserved_height_mm"])
    doc.reference = reservation


def reservation_release(ctx, payload, doc):
    _release_reservation(ctx, payload["reservation"], doc)
    return {"released": True}


def _cut_source(ctx, doc, item, warehouse):
    if item.get("partial_width_mm") or item.get("partial_length_mm"):
        raise ValidationError("Partial-footprint cuts are not implemented; use a full-face thickness cut.")
    block = block_for(ctx, item["block"], warehouse, ready=True)
    product = get_product(ctx, item.get("product", block.product_id))
    if product.id != block.product_id or product.unit != "cm":
        raise ValidationError("The selected block must match this sponge product.")
    ctx.lines.add(product.line)
    thickness = sheet_thickness(item)
    count = positive(item.get("sheet_count", "1"), "sheet count")
    if count != count.to_integral_value() or count > 10000:
        raise ValidationError("Sheet count must be a whole number of at most 10,000.")
    loss = geometry_zero(item.get("cutting_loss_mm", "0"), "cutting loss")
    if item.get("loss_policy", "per_operation") == "per_cut":
        loss *= count
    elif item.get("loss_policy", "per_operation") != "per_operation":
        raise ValidationError("Loss policy must be per_cut or per_operation.")
    consumed = count * thickness + loss
    if consumed > block.remaining_height_mm - block.reserved_height_mm:
        raise ValidationError("The selected physical block has insufficient available height; remnants cannot be joined.")
    cost = stock_out(ctx, doc, product, warehouse, consumed / 10, block.profile)
    block.remaining_height_mm -= consumed
    if block.remaining_height_mm == 0:
        block.status = "exhausted"
    block.save(update_fields=["remaining_height_mm", "status"])
    return block, product, thickness, int(count), loss, money(cost)


def cut(ctx, payload, doc):
    warehouse = get_warehouse(ctx, payload["warehouse"])
    doc.warehouse, doc.location = warehouse, warehouse.location
    if payload.get("reservation"):
        _release_reservation(ctx, payload["reservation"], doc)
    block, product, thickness, count, loss, cost = _cut_source(ctx, doc, payload, warehouse)
    ids = []
    remaining_cost = cost
    for i in range(count):
        child = make_block(ctx, doc, product, warehouse, {"length_mm": block.length_mm, "width_mm": block.width_mm, "height_mm": thickness}, parent=block, suffix=str(i + 1))
        portion = remaining_cost if i == count - 1 else money(cost / count)
        stock_in(ctx, doc, product, warehouse, thickness / 10, portion, block.profile)
        remaining_cost -= portion
        ids.append(child.id)
    # Normal cutting loss is absorbed into the retained sheet inventory; no
    # revenue or total inventory-value change occurs until fulfillment.
    return {"source_block": block.id, "blocks": ids, "billable_cm": str(thickness * count / 10), "loss_mm": str(loss), "cost": str(cost)}


def sale(ctx, payload, doc):
    from .order_cutting import bind_sale
    payload=bind_sale(ctx,payload,doc)
    warehouse = get_warehouse(ctx, payload["warehouse"])
    if warehouse.kind == "transit":
        raise ValidationError("Goods in transit cannot be sold.")
    doc.warehouse, doc.location = warehouse, warehouse.location
    customer = party_for(ctx, payload)
    doc.party = customer
    if payload.get("reservation"):
        _release_reservation(ctx, payload["reservation"], doc)
    results, journals, net = [], [], ZERO
    for index, item in enumerate(payload.get("lines", [])):
        allowance_before = sum((d.amount for d in Document.objects.filter(business=ctx.business, kind="inventory_allowance_release", data__issue_document=doc.pk)), ZERO)
        product = get_product(ctx, item["product"])
        ctx.lines.add(product.line)
        source_block, thickness, count, loss = None, ZERO, 0, ZERO
        if product.unit == "cm":
            source_block, product, thickness, count, loss, cost = _cut_source(ctx, doc, item, warehouse)
            qty = thickness * count / 10
            profile = source_block.profile
        elif product.kind == "service":
            qty, cost, profile = positive(item["quantity"]), ZERO, ""
        else:
            qty = positive(item["quantity"])
            if product.unit == "each" and qty != qty.to_integral_value():
                raise ValidationError("Piece counts must be whole numbers.")
            cost = stock_out(ctx, doc, product, warehouse, qty)
            profile = ""
        price = nonnegative(item.get("unit_price", product.price), "unit price")
        if price == 0:
            if not item.get("free_issue") or not item.get("reason"):
                raise ValidationError("A zero-price line needs an explicit authorized free_issue and reason.")
            ctx.require("sales.price")
        price_basis='catalog_match';price_reference=None
        if price != product.price:
            from .models import CustomerPrice
            agreement=CustomerPrice.objects.filter(business=ctx.business,party=customer,product=product,profile=profile,effective_from__lte=doc.date,unit_price=price).filter(Q(effective_to__isnull=True)|Q(effective_to__gte=doc.date)).order_by('-effective_from','-pk').first()
            agreed=agreement is not None
            price_basis='agreement_match' if agreed else 'authorized_override'
            price_reference=agreement.pk if agreement else None
            if not agreed and payload.get("order"):
                agreed_order = posted(ctx, payload["order"], ["sales_order"])
                source_index = _commercial_index(item.get("order_index", index))
                source_lines = agreed_order.result.get("lines", [])
                if 0 <= source_index < len(source_lines):
                    source_line = source_lines[source_index]
                    agreed = source_line["product"] == product.id and price == D(source_line["unit_price"])
                    if agreed:price_basis='order_match';price_reference=agreed_order.pk
            if not agreed:ctx.require("sales.price")
        discount = money(nonnegative(item.get("discount", "0"), "discount"))
        if discount:
            ctx.require("sales.discount")
        gross = money(qty * price)
        if discount > gross:
            raise ValidationError("Line discount cannot exceed the line value.")
        amount = gross - discount
        net += amount
        journals.append(entry("SALES", credit=amount, **dims(product, warehouse, party=customer.id)))
        if cost:
            journals += [entry("COGS", debit=cost, **dims(product, warehouse)), entry(inventory_account(product), credit=cost, **dims(product, warehouse))]
        allowance_after = sum((d.amount for d in Document.objects.filter(business=ctx.business, kind="inventory_allowance_release", data__issue_document=doc.pk)), ZERO)
        results.append({"index": index, "product": product.id, "product_name": product.name, "line": product.line, "quantity": str(qty), "unit_price": str(price), "price_basis":price_basis,"price_reference":price_reference,"catalog_price_snapshot":str(product.price), "discount": str(discount), "amount": str(amount), "cost": str(cost), "allowance_released": str(allowance_after - allowance_before), "block": source_block.id if source_block else None, "profile": profile, "thickness_mm": str(thickness), "sheet_count": count, "loss_mm": str(loss), "length_mm": str(source_block.length_mm) if source_block else None, "width_mm": str(source_block.width_mm) if source_block else None})
    if not results:
        raise ValidationError("An invoice requires at least one delivered line.")
    tax = ZERO
    tax_snapshot = None
    if payload.get("tax_rule"):
        rule = get_obj(ctx, TaxRule, payload["tax_rule"])
        if doc.date < rule.effective_from or (rule.effective_to and doc.date > rule.effective_to):
            raise ValidationError("The tax rule is not effective on this invoice date.")
        tax = money(net * rule.rate / 100)
        tax_snapshot = {"name": rule.name, "rate": str(rule.rate), "amount": str(tax), "account_code": rule.account_code}
        journals.append(entry(rule.account_code, credit=tax, location=warehouse.location_id, party=customer.id))
    total = money(net + tax)
    doc.amount = total
    journals.append(entry("AR", debit=total, location=warehouse.location_id, party=customer.id))
    from .sale_payments import sale_payments
    tenders,paid = sale_payments(ctx,payload,warehouse.location_id)
    applied = min(paid, total)
    deposit = paid - applied
    if total > applied:
        ctx.require("sales.credit")
    from .credit_management import enforce,apply_terms,policy,release_for_order
    order = _fulfill_order(ctx, payload, doc, results, "sales_order")
    apply_terms(customer,payload,doc)
    enforce(ctx,customer,total-applied,payload,doc,release=release_for_order(ctx,order,results) if policy(ctx.business) else ZERO)
    if paid:
        for tender in tenders:
            journals.append(entry(tender["account"],debit=tender["amount"],location=warehouse.location_id,party=customer.id,instrument=tender["instrument"]))
        journals.append(entry("AR", credit=applied, location=warehouse.location_id, party=customer.id))
        if deposit:
            journals.append(entry("DEPOSITS", credit=deposit, location=warehouse.location_id, party=customer.id))
        if applied:
            Allocation.objects.create(document=doc, invoice=doc, amount=applied)
    journal(ctx, doc, journals)
    return {"lines": results, "subtotal": str(net), "tax": tax_snapshot, "total": str(total), "payments": tenders, "paid": str(applied), "outstanding": str(total - applied), "deposit_amount": str(deposit), "deposit_side": "customer", "party": customer.id, "customer_snapshot": party_snapshot(customer), "order": order, "recognition": "delivered_counter_sale"}


def sales_return(ctx, payload, doc):
    invoice = posted(ctx, payload["invoice"], ["sale"])
    warehouse = get_warehouse(ctx, payload.get("warehouse", invoice.warehouse_id))
    doc.reference, doc.party, doc.warehouse, doc.location = invoice, invoice.party, warehouse, warehouse.location
    prior = Document.objects.filter(reference=invoice, kind="sales_return", state="posted")
    lines, journals, net, total_cost = [], [], ZERO, ZERO
    for request_position, requested in enumerate(payload.get("lines", [])):
        index = int(requested["index"])
        if index < 0 or index >= len(invoice.result["lines"]):
            raise ValidationError("Invalid original invoice line.")
        original = invoice.result["lines"][index]
        product = get_product(ctx, original["product"])
        ctx.lines.add(product.line)
        returned = sum((D(x["quantity"]) for d in prior for x in d.result.get("lines", []) if x["index"] == index), ZERO)
        returned += sum((D(x["quantity"]) for x in lines if x["index"] == index), ZERO)
        original_qty = D(original["quantity"])
        if product.unit == "cm":
            count = positive(requested.get("sheet_count", "1"), "returned sheet count")
            if count != count.to_integral_value():
                raise ValidationError("Returned sheet count must be whole.")
            qty = D(original["thickness_mm"]) * count / 10
        else:
            count = 0
            qty = positive(requested["quantity"])
        if qty + returned > original_qty:
            raise ValidationError("The return exceeds the quantity originally delivered and not already returned.")
        # Last return absorbs rounding residual to restore precisely the original
        # issued carrying amount, never the selling/refund price.
        prior_cost = sum((D(x["cost"]) for d in prior for x in d.result.get("lines", []) if x["index"] == index), ZERO)
        prior_cost += sum((D(x["cost"]) for x in lines if x["index"] == index), ZERO)
        cost = D(original["cost"]) - prior_cost if qty + returned == original_qty else money(D(original["cost"]) * qty / original_qty)
        prior_amount = sum((D(x["amount"]) for d in prior for x in d.result.get("lines", []) if x["index"] == index), ZERO)
        prior_amount += sum((D(x["amount"]) for x in lines if x["index"] == index), ZERO)
        amount = D(original["amount"]) - prior_amount if qty + returned == original_qty else money(D(original["amount"]) * qty / original_qty)
        block_ids = []
        if product.unit == "cm":
            parent = block_for(ctx, original["block"])
            rem = cost
            for i in range(int(count)):
                child = make_block(ctx, doc, product, warehouse, {"length_mm": original["length_mm"], "width_mm": original["width_mm"], "height_mm": original["thickness_mm"], "status": "inspection"}, parent=parent, suffix=f"{index}-{request_position}-{i}")
                value = rem if i == int(count) - 1 else money(cost / count)
                stock_in(ctx, doc, product, warehouse, child.remaining_height_mm / 10, value, child.profile)
                rem -= value
                block_ids.append(child.id)
        elif product.kind != "service":
            stock_in(ctx, doc, product, warehouse, qty, cost)
        allowance_restored = ZERO
        if D(original.get("allowance_released", "0")):
            from .finance import restore_inventory_allowance
            allowance_restored = restore_inventory_allowance(ctx, doc, invoice, original, qty, returned)
        if cost:
            journals += [entry(inventory_account(product), debit=cost, **dims(product, warehouse)), entry("COGS", credit=cost, **dims(product, warehouse))]
        journals.append(entry("SALES", debit=amount, **dims(product, warehouse, party=invoice.party_id)))
        net += amount
        total_cost += cost
        lines.append({"index": index, "product": product.id, "quantity": str(qty), "amount": str(amount), "cost": str(cost), "allowance_restored": str(allowance_restored), "blocks": block_ids})
    if not lines:
        raise ValidationError("Select at least one original invoice line to return.")
    tax = ZERO
    if invoice.result.get("tax"):
        previously_returned_net = sum((sum((D(line["amount"]) for line in returned_doc.result.get("lines", [])), ZERO) for returned_doc in prior), ZERO)
        if previously_returned_net + net == D(invoice.result["subtotal"]):
            tax = D(invoice.result["tax"]["amount"]) - sum((D(returned_doc.result.get("tax", "0")) for returned_doc in prior), ZERO)
        else:
            tax = money(net * D(invoice.result["tax"]["rate"]) / 100)
        journals.append(entry(invoice.result["tax"].get("account_code", "TAX"), debit=tax, location=warehouse.location_id))
    credit = money(net + tax)
    applied = min(credit, outstanding(invoice))
    deposit = credit - applied
    if applied:
        journals.append(entry("AR", credit=applied, party=invoice.party_id, location=warehouse.location_id))
        Allocation.objects.create(document=doc, invoice=invoice, amount=applied)
    if deposit:
        journals.append(entry("DEPOSITS", credit=deposit, party=invoice.party_id, location=warehouse.location_id))
    doc.amount = credit
    journal(ctx, doc, journals)
    return {"invoice": invoice.id, "lines": lines, "subtotal": str(net), "tax": str(tax), "total": str(credit), "cost": str(total_cost), "allocated": str(applied), "deposit_amount": str(deposit), "deposit_side": "customer"}


def quality_release(ctx, payload, doc):
    block = block_for(ctx, payload["block"])
    get_product(ctx, block.product_id)
    if block.status not in ("inspection", "curing"):
        raise ValidationError("Only inspection/curing stock can be released.")
    if not payload.get("reason"):
        raise ValidationError("Record the inspection/release result.")
    block.status = "ready"
    block.save(update_fields=["status"])
    return {"block": block.id, "status": "ready"}


def purchase_receive(ctx, payload, doc):
    warehouse = get_warehouse(ctx, payload["warehouse"])
    if warehouse.kind == "transit":
        raise ValidationError("Purchase receipts require a physical store warehouse.")
    doc.warehouse, doc.location = warehouse, warehouse.location
    if payload.get("supplier") or payload.get("party"):
        doc.party = party_for(ctx, payload, "supplier")
    lines, journals, total = [], [], ZERO
    requested = payload.get("lines", [])
    if not requested:
        raise ValidationError("A receipt requires at least one stock item.")
    base_values = [money(positive(x["quantity"]) * nonnegative(x.get("unit_cost", x.get("price", "0")), "unit cost")) for x in requested]
    landed = money(nonnegative(payload.get("landed_cost", "0")))
    if landed and not sum(base_values, ZERO):
        raise ValidationError("Landed cost allocation requires a nonzero purchase value.")
    remaining_landed = landed
    for index, (item, base) in enumerate(zip(requested, base_values)):
        product = get_product(ctx, item["product"])
        ctx.lines.add(product.line)
        qty = positive(item["quantity"])
        allocation = remaining_landed if index == len(requested) - 1 else money(landed * base / sum(base_values, ZERO)) if landed else ZERO
        remaining_landed -= allocation
        value = base + allocation
        if product.unit == "cm":
            blocks = item.get("blocks") or []
            planned = _planned_outputs(ctx, {"outputs": [{"product": product.id, "quantity": str(qty), "blocks": blocks}]})
            _, output_entries = _receive_outputs(ctx, doc, warehouse, planned, value)
            journals.extend(output_entries)
        elif product.kind == "service":
            raise ValidationError("Use an expense/supplier bill for a service; it is not stock.")
        else:
            stock_in(ctx, doc, product, warehouse, qty, value)
            journals.append(entry(inventory_account(product), debit=value, **dims(product, warehouse)))
        total += value
        lines.append({"index": index, "product": product.id, "product_name": product.name, "quantity": str(qty), "cost": str(value), "unit_cost": str(value / qty), "billed_quantity": "0"})
    journals.append(entry("GRNI", credit=total, location=warehouse.location_id, party=doc.party_id))
    doc.amount = money(total)
    order = _fulfill_order(ctx, payload, doc, lines, "purchase_order")
    journal(ctx, doc, journals)
    return {"lines": lines, "total": str(total), "landed_cost": str(landed), "clearing": "GRNI", "order": order, "supplier_snapshot": party_snapshot(doc.party) if doc.party else None}


def purchase_bill(ctx, payload, doc):
    receipt = posted(ctx, payload["receipt"], ["purchase_receive"])
    supplier = get_obj(ctx, Party, receipt.party_id) if receipt.party_id else party_for(ctx, payload, "supplier")
    if supplier.kind != "supplier":
        raise ValidationError("Supplier account required.")
    reference = str(payload.get("supplier_reference", "")).strip()
    if reference and Document.objects.filter(business=ctx.business, party=supplier, kind="purchase_bill", state="posted", data__supplier_reference=reference).exists():
        raise ValidationError("This supplier invoice reference has already been posted.")
    doc.reference, doc.party, doc.warehouse, doc.location = receipt, supplier, receipt.warehouse, receipt.location
    from .credit_management import apply_terms
    apply_terms(supplier,payload,doc)
    prior = Document.objects.filter(reference=receipt, kind="purchase_bill", state="posted")
    requested = payload.get("lines") or [{"index": line["index"], "quantity": line["quantity"]} for line in receipt.result["lines"]]
    results, total = [], ZERO
    for item in requested:
        index = int(item["index"])
        if index < 0 or index >= len(receipt.result["lines"]):
            raise ValidationError("Invalid receipt line.")
        original = receipt.result["lines"][index]
        product = get_product(ctx, original["product"])
        qty = positive(item["quantity"])
        billed = sum((D(x["quantity"]) for d in prior for x in d.result.get("lines", []) if x["index"] == index), ZERO)
        billed += sum((D(x["quantity"]) for x in results if x["index"] == index), ZERO)
        unbilled_returns = sum((D(x["quantity"]) for d in Document.objects.filter(business=ctx.business, kind="purchase_return", state="posted", result__receipt=receipt.id, result__bill=None) for x in d.result.get("lines", []) if x["index"] == index), ZERO)
        if billed + qty + unbilled_returns > D(original["quantity"]):
            raise ValidationError("Billing exceeds received unbilled quantity.")
        if "unit_cost" in item and D(item["unit_cost"]) != D(original["unit_cost"]):
            raise ValidationError("Late price changes require controlled valuation adjustment, which is not enabled.")
        prior_value = sum((D(x["cost"]) for d in prior for x in d.result.get("lines", []) if x["index"] == index), ZERO)
        prior_value += sum((D(x["cost"]) for x in results if x["index"] == index), ZERO)
        return_value = sum((D(x["credit"]) for returned_doc in Document.objects.filter(business=ctx.business, kind="purchase_return", state="posted", result__receipt=receipt.id, result__bill=None) for x in returned_doc.result.get("lines", []) if x["index"] == index), ZERO)
        value = D(original["cost"]) - prior_value - return_value if billed + qty + unbilled_returns == D(original["quantity"]) else money(D(original["unit_cost"]) * qty)
        total += value
        results.append({"index": index, "product": product.id, "quantity": str(qty), "cost": str(value)})
    doc.amount = money(total)
    journal(ctx, doc, [entry("GRNI", debit=total, location=receipt.location_id, party=supplier.id), entry("AP", credit=total, location=receipt.location_id, party=supplier.id)])
    return {"receipt": receipt.id, "lines": results, "total": str(total), "outstanding": str(total), "supplier_snapshot": party_snapshot(supplier)}


def stock_opening(ctx, payload, doc):
    warehouse = get_warehouse(ctx, payload["warehouse"])
    doc.warehouse, doc.location = warehouse, warehouse.location
    results, journals, total = [], [], ZERO
    for index, item in enumerate(payload.get("lines", [])):
        product = get_product(ctx, item["product"])
        ctx.lines.add(product.line)
        value = money(nonnegative(item.get("value", "0")))
        if product.unit == "cm":
            plans = _planned_outputs(ctx, {"outputs": [{"product": product.id, "blocks": item.get("blocks", [])}]})
            output, parts = _receive_outputs(ctx, doc, warehouse, plans, value)
            results.extend(output)
            journals.extend(parts)
        else:
            qty = positive(item["quantity"])
            stock_in(ctx, doc, product, warehouse, qty, value)
            journals.append(entry(inventory_account(product), debit=value, **dims(product, warehouse)))
            results.append({"product": product.id, "quantity": str(qty), "cost": str(value)})
        total += value
    if not results:
        raise ValidationError("Enter opening stock lines.")
    journals.append(entry("EQUITY", credit=total, location=warehouse.location_id))
    journal(ctx, doc, journals)
    return {"lines": results, "total": str(total)}


def stock_adjust(ctx, payload, doc):
    if not payload.get("reason"):
        raise ValidationError("An approved stock adjustment requires a reason.")
    warehouse = get_warehouse(ctx, payload["warehouse"])
    product = get_product(ctx, payload["product"])
    ctx.lines.add(product.line)
    qty = D(payload["quantity"])
    if qty == 0:
        raise ValidationError("Quantity adjustment must be nonzero.")
    profile = ""
    if product.unit == "cm":
        geometry_zero(abs(qty) * 10, "height adjustment")
        block = block_for(ctx, payload["block"], warehouse)
        if block.product_id != product.id or block.remaining_height_mm + qty * 10 < block.reserved_height_mm:
            raise ValidationError("Adjustment would violate this block's product or reserved height.")
        profile = block.profile
        block.remaining_height_mm += qty * 10
        if block.remaining_height_mm < 0:
            raise ValidationError("Block height cannot become negative.")
        block.status = "ready" if block.remaining_height_mm else "exhausted"
        block.save(update_fields=["remaining_height_mm", "status"])
    if qty > 0:
        value = money(nonnegative(payload["value"]))
        stock_in(ctx, doc, product, warehouse, qty, value, profile)
        journals = [entry(inventory_account(product), debit=value, **dims(product, warehouse)), entry("EXPENSE", credit=value, **dims(product, warehouse))]
    else:
        value = stock_out(ctx, doc, product, warehouse, -qty, profile)
        journals = [entry("WASTE", debit=value, **dims(product, warehouse)), entry(inventory_account(product), credit=value, **dims(product, warehouse))]
    doc.warehouse, doc.location = warehouse, warehouse.location
    journal(ctx, doc, journals)
    return {"product": product.id, "quantity": str(qty), "cost": str(value), "reason": payload["reason"]}


def transfer_dispatch(ctx, payload, doc):
    source = get_warehouse(ctx, payload["warehouse"])
    destination = get_warehouse(ctx, payload["destination"])
    if source.id == destination.id or source.kind == "transit" or destination.kind == "transit":
        raise ValidationError("Select different physical source and destination warehouses.")
    # Transit is assigned to the receiving location so its storekeeper can
    # acknowledge incoming goods without gaining access to the sender's books.
    transit, _ = Warehouse.objects.get_or_create(business=ctx.business, location=destination.location, name_en="Inventory in transit", kind="transit",defaults={'name':'موجودی در مسیر','name_fa':'موجودی در مسیر'})
    doc.warehouse, doc.location = source, source.location
    results, journals = [], []
    for index, item in enumerate(payload.get("lines", [])):
        product = get_product(ctx, item["product"])
        ctx.lines.add(product.line)
        profile, block = "", None
        if product.unit == "cm":
            block = block_for(ctx, item["block"], source, ready=True)
            if block.product_id != product.id or block.reserved_height_mm:
                raise ValidationError("The block must match and be free of reservations.")
            qty = block.remaining_height_mm / 10
            if "quantity" in item and D(item["quantity"]) != qty:
                raise ValidationError("Transfer an entire remaining block/piece; cut a child sheet first for partial transfers.")
            profile = block.profile
        else:
            qty = positive(item["quantity"])
        value = stock_out(ctx, doc, product, source, qty, profile)
        stock_in(ctx, doc, product, transit, qty, value, profile)
        if block:
            block.warehouse, block.status = transit, "in_transit"
            block.save(update_fields=["warehouse", "status"])
        journals += [entry("TRANSIT", debit=value, **dims(product, transit)), entry(inventory_account(product), credit=value, **dims(product, source))]
        results.append({"index": index, "product": product.id, "quantity": str(qty), "cost": str(value), "profile": profile, "block": block.id if block else None})
    if not results:
        raise ValidationError("Select stock to dispatch.")
    charge = money(nonnegative(payload.get("internal_charge", "0")))
    doc.amount = charge
    journal(ctx, doc, journals)
    return {"lines": results, "source": source.id, "destination": destination.id, "transit": transit.id, "internal_charge": str(charge), "status": "in_transit"}


def _transfer_resolved(transfer, index):
    return sum((D(line["quantity"]) for d in Document.objects.filter(reference=transfer, kind__in=["transfer_receive", "transfer_resolve"], state="posted") for line in d.result.get("lines", []) if line["index"] == index), ZERO)


def _transfer_process(ctx, payload, doc, resolution="receive"):
    try:
        transfer = Document.objects.get(business=ctx.business, pk=int(payload["transfer"]), kind="transfer_dispatch", state="posted")
    except (Document.DoesNotExist, ValueError, TypeError):
        raise ValidationError("Invalid posted transfer for this business.")
    # A receiver is authorized through the destination, not the sender's
    # location-scoped document getter. Every referenced product is checked below.
    target_id = transfer.result["source"] if resolution == "return" else transfer.result["destination"]
    target = get_warehouse(ctx, payload.get("warehouse", target_id))
    if target.id != target_id:
        raise ValidationError("The receipt/return warehouse does not match the transfer.")
    for line in transfer.result.get("lines", []):
        get_product(ctx, line["product"])
    transit = get_warehouse(ctx, transfer.result["transit"])
    doc.reference, doc.warehouse, doc.location = transfer, target, target.location
    requested = payload.get("lines")
    if not requested:
        requested = [{"index": x["index"], "quantity": str(D(x["quantity"]) - _transfer_resolved(transfer, x["index"]))} for x in transfer.result["lines"] if D(x["quantity"]) > _transfer_resolved(transfer, x["index"])]
    results, journals = [], []
    for item in requested:
        index = int(item["index"])
        if index < 0 or index >= len(transfer.result["lines"]):
            raise ValidationError("Invalid dispatched line.")
        original = transfer.result["lines"][index]
        product = get_product(ctx, original["product"])
        qty = positive(item["quantity"])
        resolved = _transfer_resolved(transfer, index) + sum((D(x["quantity"]) for x in results if x["index"] == index), ZERO)
        if qty + resolved > D(original["quantity"]):
            raise ValidationError("Receipt/resolution exceeds dispatched outstanding stock.")
        if original.get("block") and qty != D(original["quantity"]):
            raise ValidationError("A physical block/piece must be acknowledged in full; receive other blocks separately.")
        # Transit is a frozen shipment layer. If several shipments share a pool,
        # remove this shipment's actual carrying amount, not a blended markup.
        prior_value = sum((D(x["cost"]) for d in Document.objects.filter(reference=transfer, kind__in=["transfer_receive", "transfer_resolve"], state="posted") for x in d.result.get("lines", []) if x["index"] == index), ZERO)
        prior_value += sum((D(x["cost"]) for x in results if x["index"] == index), ZERO)
        value = D(original["cost"]) - prior_value if qty + resolved == D(original["quantity"]) else money(D(original["cost"]) * qty / D(original["quantity"]))
        pool = pool_for(ctx, product, transit, original.get("profile", ""))
        if pool.last_date and doc.date < pool.last_date:
            raise ValidationError("Backdated transit valuation is not supported.")
        if pool.quantity < qty or pool.value < value:
            raise ValidationError("Transit stock/value no longer reconciles with this dispatch.")
        # Reverse a frozen transfer layer using the shared ledger API: stock_out
        # has optional fixed values in newer cores; use a compensating in/out
        # value adjustment only when necessary via explicit movement below.
        from .models import StockMovement
        pool.quantity -= qty
        pool.value -= value
        pool.last_date = doc.date
        pool.save(update_fields=["quantity", "value", "last_date"])
        StockMovement.objects.create(document=doc, pool=pool, quantity=-qty, value=-value)
        if resolution in ("receive", "return"):
            stock_in(ctx, doc, product, target, qty, value, original.get("profile", ""))
            journals.append(entry(inventory_account(product), debit=value, **dims(product, target)))
        else:
            journals.append(entry("WASTE", debit=value, **dims(product, target)))
        journals.append(entry("TRANSIT", credit=value, **dims(product, transit)))
        if original.get("block"):
            block = block_for(ctx, original["block"], transit)
            block.warehouse = target
            block.status = "ready" if resolution in ("receive", "return") else "damaged"
            if resolution not in ("receive", "return"):
                block.remaining_height_mm = ZERO
            block.save(update_fields=["warehouse", "status", "remaining_height_mm"])
        results.append({"index": index, "product": product.id, "quantity": str(qty), "cost": str(value), "resolution": resolution})
    if not results:
        raise ValidationError("This transfer has no outstanding quantities to receive/resolve.")
    journal(ctx, doc, journals)
    remaining = sum((D(x["quantity"]) - _transfer_resolved(transfer, x["index"]) - sum((D(r["quantity"]) for r in results if r["index"] == x["index"]), ZERO) for x in transfer.result["lines"]), ZERO)
    return {"transfer": transfer.id, "lines": results, "remaining_quantity": str(remaining), "status": "received" if remaining == 0 else "partially_received"}


def transfer_receive(ctx, payload, doc):
    return _transfer_process(ctx, payload, doc)


def transfer_resolve(ctx, payload, doc):
    resolution = payload.get("resolution")
    if resolution not in ("return", "damage", "shortage") or not payload.get("reason"):
        raise ValidationError("Choose return, damage, or shortage and record the discrepancy reason.")
    return _transfer_process(ctx, payload, doc, resolution)


def material_move(ctx, payload, doc):
    source = get_warehouse(ctx, payload["warehouse"])
    target = get_warehouse(ctx, payload["destination"])
    if source.location_id != target.location_id or source.id == target.id:
        raise ValidationError("Use dispatch/receipt for inter-location movements; floor issues/returns stay within one location.")
    if doc.kind == "material_issue" and (target.kind != "floor" or source.kind == "transit"):
        raise ValidationError("Material issue destination must be the production floor.")
    if doc.kind == "material_return" and (source.kind != "floor" or target.kind == "transit"):
        raise ValidationError("Unused-material returns must leave the production floor for a store.")
    doc.warehouse, doc.location = source, source.location
    results, journals = [], []
    for item in payload.get("lines", []):
        product = get_product(ctx, item["product"])
        if product.unit == "cm" or product.kind == "service":
            raise ValidationError("Floor material moves accept measured material stock, not dimensioned blocks or services.")
        qty = positive(item["quantity"])
        value = stock_out(ctx, doc, product, source, qty)
        stock_in(ctx, doc, product, target, qty, value)
        journals += [entry(inventory_account(product), debit=value, **dims(product, target)), entry(inventory_account(product), credit=value, **dims(product, source))]
        results.append({"product": product.id, "quantity": str(qty), "cost": str(value)})
    if not results:
        raise ValidationError("Enter material quantities to move.")
    journal(ctx, doc, journals)
    return {"source": source.id, "destination": target.id, "lines": results, "consumed": False}


def production_material_return(ctx, payload, doc):
    consumption = posted(ctx, payload["consumption"], ["production_consume"])
    batch = consumption.reference
    if not batch or Document.objects.filter(reference=batch, kind="production_complete", state="posted").exists():
        raise ValidationError("Return WIP material before completion/cost finalization.")
    warehouse = get_warehouse(ctx, payload.get("warehouse", consumption.warehouse_id))
    doc.reference, doc.warehouse, doc.location = batch, warehouse, warehouse.location
    prior = Document.objects.filter(business=ctx.business, kind="production_material_return", state="posted", result__consumption=consumption.id)
    results, journals, total = [], [], ZERO
    for requested in payload.get("lines", []):
        index = int(requested["index"])
        if index < 0 or index >= len(consumption.result["inputs"]):
            raise ValidationError("Invalid actual-consumption input line.")
        original = consumption.result["inputs"][index]
        product = get_product(ctx, original["product"])
        qty = positive(requested["quantity"])
        returned = sum((D(x["quantity"]) for d in prior for x in d.result.get("lines", []) if x["index"] == index), ZERO)
        returned += sum((D(x["quantity"]) for x in results if x["index"] == index), ZERO)
        if qty + returned > D(original["quantity"]):
            raise ValidationError("WIP return exceeds actual unreturned material consumption.")
        previous_value = sum((D(x["cost"]) for returned_doc in prior for x in returned_doc.result.get("lines", []) if x["index"] == index), ZERO)
        previous_value += sum((D(x["cost"]) for x in results if x["index"] == index), ZERO)
        value = D(original["cost"]) - previous_value if qty + returned == D(original["quantity"]) else money(D(original["cost"]) * qty / D(original["quantity"]))
        stock_in(ctx, doc, product, warehouse, qty, value)
        journals += [entry(inventory_account(product), debit=value, **dims(product, warehouse)), entry("WIP", credit=value, location=warehouse.location_id)]
        total += value
        results.append({"index": index, "product": product.id, "quantity": str(qty), "cost": str(value)})
    if not results:
        raise ValidationError("Select actual material consumption to reverse into stock.")
    journal(ctx, doc, journals)
    return {"batch": batch.id, "consumption": consumption.id, "lines": results, "wip_in": "0.00", "wip_out": str(total)}


def purchase_return(ctx, payload, doc):
    receipt = posted(ctx, payload["receipt"], ["purchase_receive"])
    bill = posted(ctx, payload["bill"], ["purchase_bill"]) if payload.get("bill") else None
    if bill and bill.reference_id != receipt.id:
        raise ValidationError("The supplier bill does not belong to this receipt.")
    warehouse = get_warehouse(ctx, payload.get("warehouse", receipt.warehouse_id))
    doc.reference, doc.party, doc.warehouse, doc.location = bill or receipt, (bill.party if bill else receipt.party), warehouse, warehouse.location
    prior = Document.objects.filter(business=ctx.business, kind="purchase_return", state="posted", result__receipt=receipt.id)
    results, journals, credit = [], [], ZERO
    for requested in payload.get("lines", []):
        index = int(requested["index"])
        if index < 0 or index >= len(receipt.result["lines"]):
            raise ValidationError("Invalid received item line.")
        original = receipt.result["lines"][index]
        product = get_product(ctx, original["product"])
        qty = positive(requested["quantity"])
        returned = sum((D(x["quantity"]) for d in prior for x in d.result.get("lines", []) if x["index"] == index), ZERO)
        returned += sum((D(x["quantity"]) for x in results if x["index"] == index), ZERO)
        if qty + returned > D(original["quantity"]):
            raise ValidationError("Return exceeds original unreturned receipt quantity.")
        billed = sum((D(x["quantity"]) for d in Document.objects.filter(reference=receipt, kind="purchase_bill", state="posted") for x in d.result.get("lines", []) if x["index"] == index), ZERO)
        if bill:
            bill_qty = sum((D(x["quantity"]) for x in bill.result["lines"] if x["index"] == index), ZERO)
            bill_returned = sum((D(x["quantity"]) for d in prior.filter(reference=bill) for x in d.result.get("lines", []) if x["index"] == index), ZERO)
            bill_returned += sum((D(x["quantity"]) for x in results if x["index"] == index), ZERO)
            if qty + bill_returned > bill_qty:
                raise ValidationError("Supplier credit quantity exceeds this bill's quantity.")
        else:
            unbilled_returned = sum((D(x["quantity"]) for d in prior.filter(result__bill=None) for x in d.result.get("lines", []) if x["index"] == index), ZERO)
            unbilled_returned += sum((D(x["quantity"]) for x in results if x["index"] == index), ZERO)
            if qty + unbilled_returned + billed > D(original["quantity"]):
                raise ValidationError("Billed goods need a return linked to their supplier bill.")
        profile = ""
        if product.unit == "cm":
            block = block_for(ctx, requested["block"], warehouse, ready=True)
            if block.product_id != product.id or block.reserved_height_mm or block.remaining_height_mm / 10 != qty:
                raise ValidationError("Return an identified entire unreserved block/piece.")
            profile = block.profile
            block.remaining_height_mm, block.status = ZERO, "exhausted"
            block.save(update_fields=["remaining_height_mm", "status"])
        carrying = stock_out(ctx, doc, product, warehouse, qty, profile)
        previous_credit = sum((D(x["credit"]) for d in prior for x in d.result.get("lines", []) if x["index"] == index), ZERO)
        previous_credit += sum((D(x["credit"]) for x in results if x["index"] == index), ZERO)
        value = D(original["cost"]) - previous_credit if qty + returned == D(original["quantity"]) else money(D(original["unit_cost"]) * qty)
        credit += value
        journals.append(entry(inventory_account(product), credit=carrying, **dims(product, warehouse)))
        difference = carrying - value
        if difference:
            journals.append(entry("EXPENSE", debit=max(difference, ZERO), credit=max(-difference, ZERO), **dims(product, warehouse)))
        results.append({"index": index, "product": product.id, "quantity": str(qty), "cost": str(carrying), "credit": str(value)})
    if not results:
        raise ValidationError("Select received items to return.")
    deposit = ZERO
    if bill:
        allocated = min(credit, outstanding(bill))
        deposit = credit - allocated
        if allocated:
            journals.append(entry("AP", debit=allocated, party=bill.party_id, location=warehouse.location_id))
            Allocation.objects.create(document=doc, invoice=bill, amount=allocated)
        if deposit:
            journals.append(entry("SUPPLIER_DEPOSITS", debit=deposit, party=bill.party_id, location=warehouse.location_id))
    else:
        journals.append(entry("GRNI", debit=credit, party=receipt.party_id, location=warehouse.location_id))
    doc.amount = credit
    journal(ctx, doc, journals)
    return {"receipt": receipt.id, "bill": bill.id if bill else None, "lines": results, "total": str(credit), "deposit_amount": str(deposit), "deposit_side": "supplier"}


def internal_charge_total(transfer):
    adjustments=Document.objects.filter(business=transfer.business,reference=transfer,kind='internal_charge_adjust',state='posted')
    return money(D(transfer.result.get('internal_charge','0'))+sum((D(d.result['charge_delta']) for d in adjustments),ZERO))


def internal_charge_adjust(ctx,payload,doc):
    transfer=posted(ctx,payload['transfer'],['transfer_dispatch'])
    if not str(payload.get('reason','')).strip(): raise ValidationError('An internal charge adjustment requires an approved reason.')
    delta=money(D(payload['amount']))
    if not delta: raise ValidationError('Enter a nonzero signed adjustment amount.')
    before=internal_charge_total(transfer)
    settled=sum((d.amount for d in Document.objects.filter(reference=transfer,kind='internal_settlement',state='posted')),ZERO)
    if before+delta<settled: raise ValidationError('A reduction cannot exceed the unpaid internal charge. Review settled cash separately.')
    doc.reference=transfer;doc.location=transfer.location;doc.warehouse=transfer.warehouse;doc.product_lines=transfer.product_lines;ctx.lines.update(transfer.product_lines);doc.amount=abs(delta)
    return {'transfer':transfer.pk,'charge_delta':str(delta),'internal_charge':str(before+delta),'remaining_internal_charge':str(before+delta-settled),'managerial_only':True}


def internal_settlement(ctx, payload, doc):
    transfer = posted(ctx, payload["transfer"], ["transfer_dispatch"])
    charge = internal_charge_total(transfer)
    settled = sum((d.amount for d in Document.objects.filter(reference=transfer, kind="internal_settlement", state="posted")), ZERO)
    amount = money(positive(payload["amount"]))
    if settled + amount > charge:
        raise ValidationError("Internal settlement exceeds this managerial branch charge.")
    source = get_warehouse(ctx, transfer.result["destination"])
    target = get_warehouse(ctx, transfer.result["source"])
    account_from, account_to = payload.get("source_account", "CASH"), payload.get("destination_account", "CASH")
    if account_from not in ("CASH", "BANK") or account_to not in ("CASH", "BANK"):
        raise ValidationError("Internal settlement uses company cash/bank accounts only.")
    from .core import balance
    if balance(ctx, account_from, location=source.location_id) < amount:
        raise ValidationError("The paying branch has insufficient recorded cash/bank funds.")
    doc.reference, doc.location, doc.amount = transfer, source.location, amount
    journal(ctx, doc, [entry(account_to, debit=amount, location=target.location_id), entry(account_from, credit=amount, location=source.location_id)])
    return {"transfer": transfer.id, "amount": str(amount), "remaining_internal_charge": str(charge - settled - amount), "managerial_only": True}


def commercial_order(ctx, payload, doc):
    purchasing = doc.kind == "purchase_order"
    warehouse = get_warehouse(ctx, payload["warehouse"])
    doc.warehouse, doc.location = warehouse, warehouse.location
    party = party_for(ctx, payload, "supplier" if purchasing else "customer")
    doc.party = party
    results, total = [], ZERO
    for index, item in enumerate(payload.get("lines", [])):
        product = get_product(ctx, item["product"])
        qty = sheet_thickness(item) * positive(item.get("sheet_count", "1")) / 10 if product.unit == "cm" and any(k in item for k in ("thickness_mm", "thickness_cm", "thickness")) else positive(item["quantity"])
        if product.unit == "each" and qty != qty.to_integral_value():
            raise ValidationError("Piece counts must be whole numbers.")
        price = nonnegative(item.get("unit_cost", "0") if purchasing else item.get("unit_price", product.price), "unit price")
        if not purchasing and price != product.price and not (doc.kind == "sales_order" and payload.get("quotation")):
            ctx.require("sales.price")
        profile = ""
        if product.unit == "cm" and item.get("length_mm") and item.get("width_mm"):
            profile = profile_for(geometry(item["length_mm"]), geometry(item["width_mm"]))
        value = money(qty * price)
        results.append({"index": index, "product": product.id, "product_name": product.name, "quantity": str(qty), "unit": product.unit, "profile": profile, "length_mm": str(geometry(item["length_mm"])) if profile else None, "width_mm": str(geometry(item["width_mm"])) if profile else None, "unit_cost" if purchasing else "unit_price": str(price), "amount": str(value), "fulfilled_quantity": "0"})
        total += value
    if not results:
        raise ValidationError("An order/quotation needs at least one item.")
    if payload.get("quotation"):
        if doc.kind != "sales_order":
            raise ValidationError("Only a sales order can convert a quotation.")
        quotation = posted(ctx, payload["quotation"], ["quotation"])
        if quotation.party_id != party.id or quotation.warehouse_id != warehouse.id:
            raise ValidationError("The sales order must use the quotation's customer and warehouse.")
        if _commercial_cancelled(ctx, quotation):
            raise ValidationError("This quotation is cancelled; create a new quotation for new work.")
        previous = Document.objects.filter(business=ctx.business, reference=quotation, kind="sales_order", state="posted")
        processed = []
        for index, line in enumerate(results):
            quote_index = _commercial_index(payload["lines"][index].get("quotation_index", index))
            if quote_index < 0 or quote_index >= len(quotation.result["lines"]):
                raise ValidationError("Invalid quotation item reference.")
            expected = quotation.result["lines"][quote_index]
            if expected["product"] != line["product"] or (expected.get("profile") and expected["profile"] != line["profile"]):
                raise ValidationError("The product and sheet footprint must match the quotation line.")
            if D(line["unit_price"]) != D(expected["unit_price"]) and D(line["unit_price"]) != get_product(ctx, line["product"]).price:
                ctx.require("sales.price")
            converted = sum((D(item["quantity"]) for prior in previous for item in prior.result.get("lines", []) if item.get("quotation_index", item.get("index")) == quote_index), ZERO)
            converted += sum((D(item["quantity"]) for item in processed if item["quotation_index"] == quote_index), ZERO)
            if converted + D(line["quantity"]) > D(expected["quantity"]):
                raise ValidationError("Conversion exceeds the quotation's remaining quantity.")
            line["quotation_index"] = quote_index
            processed.append(line)
        doc.reference = quotation
    doc.amount = money(total)
    if not purchasing:
        from .credit_management import apply_terms,enforce,policy
        apply_terms(party,payload,doc)
        if doc.kind=='sales_order' and policy(ctx.business):enforce(ctx,party,doc.amount,payload,doc)
    return {"lines": results, "total": str(total), "party": party.id, "party_snapshot": party_snapshot(party), "recognition": "none_until_delivered", "status": "open"}


def _commercial_index(value):
    try:
        parsed = D(value)
    except ValidationError:
        raise ValidationError("Invalid commercial source line index.")
    if parsed != parsed.to_integral_value():
        raise ValidationError("A source line index must be a whole number.")
    return int(parsed)


def _commercial_cancelled(ctx, order):
    """A quote closure also stops the undelivered portion of its child orders."""
    ids = [order.id]
    if order.kind == "sales_order" and order.reference_id and order.reference.kind == "quotation":
        ids.append(order.reference_id)
    return Document.objects.filter(business=ctx.business, reference_id__in=ids, kind="order_cancel", state="posted").exists()


def _fulfill_order(ctx, payload, doc, actual_lines, order_kind):
    if not payload.get("order"):
        return None
    order = posted(ctx, payload["order"], [order_kind])
    if order.date > doc.date:
        raise ValidationError("An order cannot be fulfilled before its document date.")
    if order.party_id != doc.party_id or order.warehouse_id != doc.warehouse_id:
        raise ValidationError("Order party and warehouse must match the fulfillment.")
    if _commercial_cancelled(ctx, order):
        raise ValidationError("The remaining quantity of this order has been cancelled.")
    event_kind = "purchase_receive" if order_kind == "purchase_order" else "sale"
    previous = Document.objects.filter(business=ctx.business, kind=event_kind, state="posted", result__order=order.id)
    processed = []
    for index, line in enumerate(actual_lines):
        order_index = _commercial_index(payload["lines"][index].get("order_index", index))
        if order_index < 0 or order_index >= len(order.result["lines"]):
            raise ValidationError("Invalid order item reference.")
        expected = order.result["lines"][order_index]
        if expected["product"] != line["product"] or (expected.get("profile") and expected["profile"] != line.get("profile", "")):
            raise ValidationError("Delivered/received item and footprint must match the order line.")
        fulfilled = sum((D(item["quantity"]) for previous_doc in previous for item in previous_doc.result.get("lines", []) if item.get("order_index") == order_index), ZERO)
        fulfilled += sum((D(item["quantity"]) for item in processed if item["order_index"] == order_index), ZERO)
        if fulfilled + D(line["quantity"]) > D(expected["quantity"]):
            raise ValidationError("Fulfillment exceeds this order's remaining quantity.")
        if order_kind == 'sales_order':
            from .order_cutting import reserved_quantity
            if fulfilled + D(line['quantity']) + reserved_quantity(ctx,order.id,order_index) > D(expected['quantity']):
                raise ValidationError('This sales-order quantity is reserved for a cutting plan or held sheets. Sell those identified sheets or release their demand first.')
        line["order_index"] = order_index
        processed.append(line)
    if doc.reference_id is None:
        doc.reference = order
    return order.id


def order_cancel(ctx, payload, doc):
    order = get_obj(ctx, Document, payload["order"])
    draft_quotation = order.kind == "quotation" and order.state == "draft"
    if order.kind not in {"purchase_order", "sales_order", "quotation"} or (order.state != "posted" and not draft_quotation):
        raise ValidationError("Choose a posted order/quotation or an open draft quotation.")
    if order.date > doc.date:
        raise ValidationError("Cancellation cannot precede the quotation/order date.")
    ctx.require("purchases.post" if order.kind == "purchase_order" else "sales.post")
    reason = payload.get("reason", "")
    reason = reason.strip() if isinstance(reason, str) else ""
    if not reason or len(reason) > 1000 or Document.objects.filter(business=ctx.business, reference=order, kind="order_cancel", state="posted").exists():
        raise ValidationError("Record a cancellation reason; the remaining order can only be cancelled once.")
    orders = list(Document.objects.filter(business=ctx.business, reference=order, kind="sales_order", state="posted")) if order.kind == "quotation" else [order]
    for linked in orders:
        get_obj(ctx, Document, linked.id)
    linked_ids = [linked.id for linked in orders]
    events = Document.objects.filter(business=ctx.business, state="posted").filter(Q(pk__in=linked_ids) | Q(kind="sale", result__order__in=linked_ids) | Q(kind="purchase_receive", result__order=order.id))
    if events.filter(date__gt=doc.date).exists():
        raise ValidationError("Cancellation cannot precede activity already posted against this quotation/order.")
    doc.reference, doc.party, doc.warehouse, doc.location = order, order.party, order.warehouse, order.location
    ctx.lines.update(order.product_lines)
    if draft_quotation:
        order.state = "cancelled"
        order.save(update_fields=["state"])
        from .models import AuditEvent
        AuditEvent.objects.create(business=ctx.business,user=ctx.user,action='draft.cancel',target=str(order.id),details={'cancellation_document':doc.id,'reason':reason})
    return {"order": order.id, "status": "remaining_cancelled", "reason": reason, "draft_quotation_closed": draft_quotation, "linked_orders_stopped": bool(linked_ids) if order.kind == "quotation" else False, "prior_fulfillments_preserved": True, "accounting_effect": "none; posted invoices and receipts remain valid"}


MANUFACTURING_REPORTS = {"production_batches", "production_waste", "stock_movements", "block_history", "transfer_status"}


def manufacturing_report(ctx, name, params=None):
    """Read-only operational reports with the same scope as posting services."""
    params = params or {}
    if name not in MANUFACTURING_REPORTS:
        raise ValidationError("Unknown manufacturing report.")
    module = "production" if name.startswith("production_") else "transfers" if name == "transfer_status" else "inventory"
    if not any(ctx.has(p) for p in (f"{module}.view", f"{module}.post", "reports.view", "accounting.view")):
        raise PermissionDenied("This operational report is restricted.")
    qs = Document.objects.filter(business=ctx.business, state="posted").select_related("party", "warehouse", "location")
    if not ctx.membership.all_locations:
        scope = Q(location_id__in=ctx.membership.location_ids)
        if name == "transfer_status":
            destinations = list(Warehouse.objects.filter(business=ctx.business, location_id__in=ctx.membership.location_ids, kind__in=["store", "floor"]).values_list("id", flat=True))
            for destination in destinations:
                scope |= Q(kind="transfer_dispatch", result__destination=destination)
        qs = qs.filter(scope)
    from datetime import date
    for key, lookup in (("from", "date__gte"), ("to", "date__lte")):
        if params.get(key):
            try:
                effective = date.fromisoformat(params[key])
            except (ValueError, TypeError):
                raise ValidationError("Report dates use YYYY-MM-DD.")
            qs = qs.filter(**{lookup: effective})
    if params.get("warehouse"):
        warehouse = get_warehouse(ctx, params["warehouse"])
        qs = qs.filter(Q(warehouse=warehouse) | Q(kind="transfer_dispatch", result__destination=warehouse.id)) if name == "transfer_status" else qs.filter(warehouse=warehouse)
    def visible(doc):
        return set(doc.product_lines).issubset(set(ctx.membership.product_lines)) or ctx.has("documents.all_lines")
    def row(doc):
        return {"id": doc.id, "number": doc.number, "date": doc.date.isoformat(), "kind": doc.kind, "warehouse": doc.warehouse_id, "location": doc.location_id}
    def cost_fields(data):
        return data if ctx.has("cost.view") else {k: v for k, v in data.items() if k not in ("cost", "total_cost", "abnormal_loss", "wip_in", "wip_out", "wip_remaining", "value")}
    rows = []
    if name == "production_batches":
        for doc in qs.filter(kind__in=["production", "production_bom", "production_start", "production_consume", "production_complete", "production_material_return"]).order_by("-id")[:1000]:
            if not visible(doc):
                continue
            item = row(doc)
            item.update(cost_fields({key: doc.result[key] for key in ("total_cost", "wip_in", "wip_out", "wip_remaining", "abnormal_loss") if key in doc.result}))
            item["outputs"] = [cost_fields({key: value for key, value in output.items() if key in ("product", "quantity", "blocks", "cost")}) for output in doc.result.get("outputs", [])]
            if ctx.has("consumption.view"):
                item["inputs"] = [cost_fields(line) for line in doc.result.get("inputs", [])]
                if doc.result.get("bom"):
                    item["bom"] = doc.result["bom"]
            rows.append(item)
    elif name == "production_waste":
        for doc in qs.filter(kind__in=["production", "production_bom", "production_complete", "trim", "sale", "cut", "transfer_resolve", "stock_adjust"]).order_by("-id")[:2000]:
            if not visible(doc):
                continue
            result = doc.result
            loss_mm = D(result.get("loss_mm", "0")) + sum((D(line.get("loss_mm", "0")) for line in result.get("lines", [])), ZERO)
            abnormal = D(result.get("abnormal_loss", "0"))
            resolved = [line for line in result.get("lines", []) if line.get("resolution") in ("damage", "shortage")]
            negative_adjust = doc.kind == "stock_adjust" and D(result.get("quantity", "0")) < 0
            if loss_mm or abnormal or resolved or negative_adjust:
                item = row(doc)
                item.update(cost_fields({"loss_mm": str(loss_mm), "abnormal_loss": str(abnormal)}))
                item["reason"] = doc.data.get("reason", "")
                item["resolved_stock"] = [cost_fields(line) for line in resolved]
                if negative_adjust:
                    item["product"], item["quantity"] = result["product"], result["quantity"]
                    if ctx.has("cost.view"):
                        item["cost"] = result.get("cost", "0")
                rows.append(item)
    elif name == "stock_movements":
        from .models import StockMovement
        movements = StockMovement.objects.filter(document__in=qs, pool__product__line__in=ctx.membership.product_lines).select_related("document", "pool__product", "pool__warehouse").order_by("-id")
        if not (ctx.has("consumption.view") or ctx.has("inventory.raw")):
            movements = movements.exclude(pool__product__kind="raw")
        if params.get("product"):
            product = get_product(ctx, params["product"])
            if product.kind == "raw" and not (ctx.has("consumption.view") or ctx.has("inventory.raw")):
                raise PermissionDenied("Raw-material movements are restricted.")
            movements = movements.filter(pool__product=product)
        for movement in movements[:2000]:
            if not visible(movement.document):
                continue
            item = row(movement.document)
            item.update({"product": movement.pool.product_id, "product_name": movement.pool.product.name, "warehouse": movement.pool.warehouse_id, "profile": movement.pool.profile, "unit": movement.pool.product.unit, "quantity": str(movement.quantity)})
            if ctx.has("cost.view"):
                item["value"] = str(movement.value)
            rows.append(item)
    elif name == "block_history":
        if not params.get("block"):
            raise ValidationError("Select a physical block/piece for its history.")
        block = block_for(ctx, params["block"])
        get_product(ctx, block.product_id)
        for doc in qs.order_by("id")[:5000]:
            if not visible(doc):
                continue
            referenced = doc.pk == block.batch_id or doc.data.get("block") == block.pk or doc.result.get("source_block") == block.pk
            referenced = referenced or any(line.get("block") == block.pk or block.pk in line.get("blocks", []) for line in doc.result.get("lines", []) + doc.result.get("outputs", []))
            if referenced:
                rows.append(row(doc))
        return {"report": name, "block": {"id": block.pk, "code": block.code, "parent": block.parent_id, "batch": block.batch_id, "product": block.product_id, "warehouse": block.warehouse_id, "profile": block.profile, "initial_height_mm": str(block.initial_height_mm), "remaining_height_mm": str(block.remaining_height_mm), "reserved_height_mm": str(block.reserved_height_mm), "status": block.status}, "rows": rows, "limit": 5000}
    else:
        for transfer in qs.filter(kind="transfer_dispatch").order_by("-id")[:1000]:
            if not visible(transfer):
                continue
            item = row(transfer)
            item.update({"source": transfer.result["source"], "destination": transfer.result["destination"], "transit": transfer.result["transit"], "lines": []})
            for line in transfer.result["lines"]:
                resolved = _transfer_resolved(transfer, line["index"])
                item["lines"].append(cost_fields({**line, "resolved_quantity": str(resolved), "outstanding_quantity": str(D(line["quantity"]) - resolved)}))
            item["status"] = "resolved" if all(D(line["outstanding_quantity"]) == 0 for line in item["lines"]) else "in_transit"
            if ctx.has("transfers.settle") or ctx.has("finance.view"):
                settled = sum((d.amount for d in Document.objects.filter(reference=transfer, kind="internal_settlement", state="posted")), ZERO)
                item["internal_charge"] = str(internal_charge_total(transfer))
                item["internal_outstanding"] = str(D(item["internal_charge"]) - settled)
            rows.append(item)
    return {"report": name, "rows": rows, "count": len(rows), "limit": 2000, "currency": ctx.business.currency}


OPERATIONS = {
    'internal_charge_adjust':('transfers.adjust',internal_charge_adjust),
    "production": ("production.post", production),
    "production_start": ("production.post", production_start),
    "production_consume": ("production.post", production_consume),
    "production_complete": ("production.post", production_complete),
    "production_bom": ("production.post", production),
    "production_material_return": ("production.post", production_material_return),
    "trim": ("production.post", trim),
    "quality_release": ("production.post", quality_release),
    "reserve": ("sales.post", reserve),
    "reservation_release": ("sales.post", reservation_release),
    "cut": ("inventory.post", cut),
    "sale": ("sales.post", sale),
    "sales_return": ("sales.refund", sales_return),
    "purchase_receive": ("purchases.post", purchase_receive),
    "purchase_bill": ("purchases.post", purchase_bill),
    "purchase_return": ("purchases.post", purchase_return),
    "purchase_order": ("purchases.post", commercial_order),
    "sales_order": ("sales.post", commercial_order),
    "quotation": ("sales.post", commercial_order),
    "order_cancel": ("documents.cancel", order_cancel),
    "material_issue": ("inventory.post", material_move),
    "material_return": ("inventory.post", material_move),
    "stock_opening": ("inventory.adjust", stock_opening),
    "stock_adjust": ("inventory.adjust", stock_adjust),
    "transfer_dispatch": ("transfers.post", transfer_dispatch),
    "transfer_receive": ("transfers.post", transfer_receive),
    "transfer_resolve": ("transfers.post", transfer_resolve),
    "internal_settlement": ("transfers.settle", internal_settlement),
}
