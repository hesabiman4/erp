"""Dedicated job costing, optional nested BOM planning, and owned subcontract WIP.

Project association never posts money or stock. Subcontract events validate and
link actual existing transfer, production, and supplier-bill documents. They do
not simulate receipts or duplicate the original core accounting operations.
"""
from decimal import Decimal
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Sum
from .core import D, get_obj, get_product, get_warehouse, money
from .models import BOM, Document, Entry, Party, StockMovement
from .jobs_models import CostingProject, ProjectEstimate, ProjectDocument, ProjectBOMPlan, SubcontractJob, SubcontractEvent

ZERO = Decimal('0')


def fail(message): raise ValidationError(message)


def text(p, name, limit=4000):
    value = str(p.get(name) or '').strip()
    if not value or len(value) > limit: fail(f'{name} is required, maximum {limit} characters.')
    return value


def nonnegative(value):
    value = D(value)
    if value < 0: fail('Negative quantities/costs are not permitted.')
    return value


def project_for(ctx, identifier, writable=False):
    project = get_obj(ctx, CostingProject, identifier)
    if writable and project.state != 'open': fail('The project is closed; its historical estimates and documents remain available.')
    return project


def posted(ctx, identifier, kinds=None):
    document = get_obj(ctx, Document, identifier)
    from .api import doc_permission
    doc_permission(ctx,document)
    if document.state != 'posted' or kinds and document.kind not in kinds:
        fail('Select a compatible actual posted document.')
    if document.kind.startswith('payroll'):
        ctx.require('payroll.view')
    ctx.lines.update(document.product_lines)
    return document


def project_create(ctx, p, doc):
    from .models import Location
    location = get_obj(ctx, Location, p['location'])
    customer = get_obj(ctx, Party, p['customer'])
    if customer.kind != 'customer': fail('A job/project needs its actual customer account.')
    from .growth import day
    due = day(p['due_date']) if p.get('due_date') else None
    project = CostingProject(business=ctx.business, location=location, customer=customer, code=text(p, 'code', 50), name=text(p, 'name', 200), description=str(p.get('description', ''))[:4000], due_date=due, source=doc)
    project.full_clean(); project.save()
    doc.location, doc.party = location, customer
    return {'project': project.pk, 'state': project.state, 'financial_posting': False}


def project_estimate(ctx, p, doc):
    ctx.require('cost.view')
    project = project_for(ctx, p['project'], True)
    lines, total = [], ZERO
    for line in p.get('lines', []):
        category = line.get('category')
        if category not in {'materials', 'labor', 'overhead', 'subcontract', 'other'}:
            fail('Estimate categories are materials, labor, overhead, subcontract, or other.')
        amount = nonnegative(line['quantity']); rate = nonnegative(line['unit_cost'])
        if amount <= 0: fail('Estimate quantities must be positive.')
        value = money(amount * rate)
        product = get_product(ctx, line['product']) if line.get('product') else None
        lines.append({'category': category, 'description': text(line, 'description', 200), 'product': product.pk if product else None, 'quantity': str(amount), 'unit_cost': str(rate), 'cost': str(value)})
        total += value
    if not lines: fail('Provide at least one estimate line.')
    revenue = money(nonnegative(p.get('estimated_revenue', '0')))
    estimate = ProjectEstimate(business=ctx.business, project=project, lines=lines, estimated_cost=total, estimated_revenue=revenue, note=str(p.get('note', ''))[:4000], source=doc)
    estimate.full_clean(); estimate.save()
    doc.reference, doc.location, doc.party = project.source, project.location, project.customer
    return {'project': project.pk, 'estimate': estimate.pk, 'estimated_cost': str(total), 'estimated_revenue': str(revenue), 'financial_posting': False, 'version': project.estimates.count()}


ALLOWED_PROJECT_DOCUMENTS = {'quotation', 'sales_order', 'sale', 'sales_return', 'purchase_order', 'purchase_receive', 'purchase_bill', 'purchase_return', 'expense_post', 'payroll_accrue', 'production_start', 'production_consume', 'production_complete', 'production', 'production_bom', 'production_material_return', 'material_issue', 'material_return', 'transfer_dispatch', 'transfer_receive', 'transfer_resolve', 'inventory_write_down', 'inventory_write_down_reverse'}


def associate(ctx, project, document, source, note=''):
    if document.kind not in ALLOWED_PROJECT_DOCUMENTS: fail('This document is not an eligible dedicated job-cost document.')
    existing = ProjectDocument.objects.filter(document=document).first()
    if existing:
        if existing.project_id != project.pk: fail('The whole document already belongs to another job. Split mixed-job documents in the original workflow.')
        return existing
    if document.kind in {'sale', 'quotation', 'sales_order', 'sales_return'} and document.party_id != project.customer_id:
        fail('Customer documents must belong to this project\'s customer.')
    if document.reference_id:
        parent = ProjectDocument.objects.filter(document_id=document.reference_id).first()
        if parent and parent.project_id != project.pk:
            fail('A linked correction/receipt cannot be assigned to a different project than its source.')
    for child in ProjectDocument.objects.filter(document__reference=document):
        if child.project_id != project.pk: fail('A linked child is already assigned to another project.')
    link = ProjectDocument(business=ctx.business, project=project, document=document, source=source, note=note)
    link.full_clean(); link.save()
    return link


def project_link(ctx, p, doc):
    project = project_for(ctx, p['project'], True)
    original = posted(ctx, p['document'], ALLOWED_PROJECT_DOCUMENTS)
    if ProjectDocument.objects.filter(document=original).exists(): fail('This document already has a dedicated job association.')
    link = associate(ctx, project, original, doc, text(p, 'note'))
    doc.reference, doc.location, doc.party = original, project.location, project.customer
    return {'project': project.pk, 'link': link.pk, 'document': original.pk, 'financial_posting': False, 'stock_deducted': False}


def explode_bom(ctx, bom, amount, trail=(), depth=0, counter=None):
    if ctx.business.manufacturing_mode != 'bom': fail('Nested BOM planning is disabled for actual-consumption/trading businesses.')
    ctx.require('bom.view')
    if not bom.approved: fail('Every nested BOM version must be approved.')
    if bom.pk in trail: fail('A cycle was found in the nested BOM graph.')
    if depth > 15: fail('Nested BOM planning supports at most 16 levels.')
    counter = counter if counter is not None else [0]
    product = get_product(ctx, bom.product_id)
    denominator = D(bom.output_quantity)
    if denominator <= 0 or amount <= 0: fail('BOM output and planned quantities must be positive.')
    nodes, leaves = [], {}
    for component in bom.components:
        counter[0] += 1
        if counter[0] > 1000: fail('Nested BOM planning supports at most 1,000 component nodes.')
        item = get_product(ctx, component['product'])
        required = D(component['quantity']) * amount / denominator
        if required <= 0: fail('BOM component quantities must be positive.')
        if component.get('bom'):
            child = get_obj(ctx, BOM, component['bom'])
            if child.product_id != item.pk: fail('A nested BOM must produce the selected component product.')
            expanded = explode_bom(ctx, child, required, (*trail, bom.pk), depth + 1, counter)
            nodes.append(expanded)
            for leaf in expanded['leaves']:
                leaves[leaf['product']] = leaves.get(leaf['product'], ZERO) + D(leaf['quantity'])
        else:
            leaves[item.pk] = leaves.get(item.pk, ZERO) + required
    if not bom.components: fail('An approved planning BOM must contain components.')
    return {'bom': bom.pk, 'version': bom.version, 'product': product.pk, 'quantity': str(amount), 'children': nodes, 'leaves': [{'product': identifier, 'quantity': str(value)} for identifier, value in sorted(leaves.items())]}


def project_bom_plan(ctx, p, doc):
    project = project_for(ctx, p['project'], True)
    bom = get_obj(ctx, BOM, p['bom'])
    amount = D(p['quantity'])
    if amount != amount.quantize(Decimal('.000001')): fail('Planned output quantity supports six decimal places.')
    snapshot = explode_bom(ctx, bom, amount)
    plan = ProjectBOMPlan(business=ctx.business, project=project, bom=bom, quantity=amount, snapshot=snapshot, source=doc)
    plan.full_clean(); plan.save()
    doc.reference, doc.location, doc.party = project.source, project.location, project.customer
    # Recipes stay in a separately authorized planning resource, rather than in
    # a normal project/document response visible to ordinary sales staff.
    return {'project': project.pk, 'plan': plan.pk, 'expected_only': True, 'stock_deducted': False, 'financial_posting': False}


def validate_nested_bom(ctx, bom):
    """Validate a newly saved draft/root; nested versions must be approved."""
    approved = bom.approved
    try:
        bom.approved = True
        explode_bom(ctx, bom, D(bom.output_quantity))
    finally:
        bom.approved = approved


def subcontract_create(ctx, p, doc):
    project = project_for(ctx, p['project'], True)
    supplier = get_obj(ctx, Party, p['supplier'])
    warehouse = get_warehouse(ctx, p['warehouse'])
    product = get_product(ctx, p['product'])
    if supplier.kind != 'supplier' or warehouse.kind == 'transit' or product.kind not in {'finished', 'trim'}:
        fail('Use a supplier, a dedicated company-owned vendor-stock warehouse, and a manufactured output item.')
    amount = D(p['quantity'])
    if amount <= 0 or amount != amount.quantize(Decimal('.000001')) or product.unit == 'each' and amount != amount.to_integral_value():
        fail('Enter a valid planned output quantity in the product\'s stock unit.')
    order = SubcontractJob(business=ctx.business, project=project, supplier=supplier, warehouse=warehouse, product=product, planned_quantity=amount, instructions=text(p, 'instructions'), source=doc)
    order.full_clean(); order.save()
    doc.reference, doc.location, doc.warehouse, doc.party = project.source, warehouse.location, warehouse, supplier
    return {'subcontract': order.pk, 'project': project.pk, 'owned_vendor_stock': True, 'financial_posting': False}


def subcontract_for(ctx, identifier):
    order = get_obj(ctx, SubcontractJob, identifier)
    project_for(ctx, order.project_id, True)
    get_product(ctx, order.product_id); get_warehouse(ctx, order.warehouse_id)
    if order.state != 'open': fail('This subcontract job is already closed.')
    return order


def subcontract_link(ctx, p, doc):
    order = subcontract_for(ctx, p['subcontract'])
    kind = p.get('kind')
    kinds = {'send': {'transfer_dispatch'}, 'vendor_receipt': {'transfer_receive'}, 'production': {'production', 'production_bom'}, 'finished_receipt': {'transfer_receive'}}
    if kind not in kinds: fail('Choose send, vendor_receipt, production, or finished_receipt.')
    original = posted(ctx, p['document'], kinds[kind])
    if SubcontractEvent.objects.filter(document=original).exists(): fail('This operational source is already linked to a subcontract event.')
    amount, bill = ZERO, None
    if kind == 'send':
        if original.result.get('destination') != order.warehouse_id: fail('The dispatch destination must be this job\'s company-owned vendor warehouse.')
    elif kind == 'vendor_receipt':
        if original.warehouse_id != order.warehouse_id or not order.events.filter(kind='send', document_id=original.reference_id).exists():
            fail('The vendor receipt must acknowledge a linked material dispatch into the owned vendor warehouse.')
    elif kind == 'production':
        if original.warehouse_id != order.warehouse_id: fail('Subcontract production must consume and receive output at the owned vendor warehouse.')
        if not order.events.filter(kind='vendor_receipt').exists(): fail('Acknowledge the actual material dispatch into vendor stock first.')
        if any(int(line.get('warehouse', order.warehouse_id)) != order.warehouse_id for line in original.result.get('inputs', [])):
            fail('Subcontract actual materials must come from this owned vendor-stock warehouse.')
        amount = sum((D(output['quantity']) for output in original.result.get('outputs', []) if int(output['product']) == order.product_id), ZERO)
        if amount <= 0: fail('The real production batch does not produce this subcontract item.')
        bill = posted(ctx, p.get('processing_bill'), {'expense_post'})
        if bill.party_id != order.supplier_id or bill.data.get('expense_account') != 'COST_CLEARING' or bill.data.get('production_cost') is not True:
            fail('Use the same supplier\'s actual production-processing bill debiting COST_CLEARING.')
        allocations = [entry for entry in original.data.get('conversion_allocations', []) if entry['document'] == bill.pk]
        if not allocations or sum((D(entry['amount']) for entry in allocations), ZERO) <= 0:
            fail('The production batch must actually absorb this processing bill through the core conversion-source workflow.')
        produced = order.events.filter(kind='production').aggregate(total=Sum('quantity'))['total'] or ZERO
        if produced + amount > order.planned_quantity: fail('Recorded production exceeds the subcontract planned output.')
        associate(ctx, order.project, bill, doc, 'Actual subcontract processing bill')
    else:
        dispatch = original.reference
        if not dispatch or dispatch.kind != 'transfer_dispatch' or dispatch.warehouse_id != order.warehouse_id or original.warehouse_id == order.warehouse_id:
            fail('Finished receipt must follow a real dispatch out of the owned vendor warehouse to a different company warehouse.')
        indexes = {line['index'] for line in dispatch.result.get('lines', []) if int(line['product']) == order.product_id}
        amount = sum((D(line['quantity']) for line in original.result.get('lines', []) if line['index'] in indexes), ZERO)
        produced = order.events.filter(kind='production').aggregate(total=Sum('quantity'))['total'] or ZERO
        received = order.events.filter(kind='finished_receipt').aggregate(total=Sum('quantity'))['total'] or ZERO
        if amount <= 0 or amount + received > produced: fail('Finished receipts cannot exceed this job\'s actual produced output.')
        associate(ctx, order.project, dispatch, doc, 'Owned finished goods returning from subcontractor')
    event = SubcontractEvent(business=ctx.business, subcontract=order, kind=kind, document=original, processing_bill=bill, quantity=amount, note=text(p, 'note'), source=doc)
    event.full_clean(); event.save()
    associate(ctx, order.project, original, doc, event.note)
    doc.reference, doc.location, doc.warehouse, doc.party = original, order.warehouse.location, order.warehouse, order.supplier
    return {'subcontract': order.pk, 'event': event.pk, 'linked_document': original.pk, 'quantity': str(amount), 'kind': kind, 'financial_posting': False, 'stock_deducted': False}


def subcontract_close(ctx, p, doc):
    order = subcontract_for(ctx, p['subcontract'])
    produced = order.events.filter(kind='production').aggregate(total=Sum('quantity'))['total'] or ZERO
    received = order.events.filter(kind='finished_receipt').aggregate(total=Sum('quantity'))['total'] or ZERO
    if produced != order.planned_quantity or received != produced:
        fail('Close only after the planned output was actually produced and all finished output was received back.')
    reason = text(p, 'note')
    order.state, order.closed_by = 'completed', doc; order.save(update_fields=['state', 'closed_by'])
    doc.reference, doc.location, doc.warehouse, doc.party = order.source, order.warehouse.location, order.warehouse, order.supplier
    return {'subcontract': order.pk, 'state': order.state, 'note': reason, 'remaining_vendor_materials_preserved': True, 'financial_posting': False}


def project_close(ctx, p, doc):
    project = project_for(ctx, p['project'], True)
    if project.subcontracts.exclude(state='completed').exists(): fail('Complete open subcontract jobs before closing the project.')
    reason = text(p, 'note')
    project.state, project.closed_by = 'completed', doc; project.save(update_fields=['state', 'closed_by'])
    doc.reference, doc.location, doc.party = project.source, project.location, project.customer
    return {'project': project.pk, 'state': project.state, 'note': reason, 'financial_posting': False, 'remaining_balances_preserved': True}


def actuals(ctx, project):
    ctx.require('accounting.view'); ctx.require('cost.view')
    documents = []
    for link in project.document_links.select_related('document'):
        original = get_obj(ctx, Document, link.document_id)
        from .api import doc_permission
        doc_permission(ctx,original)
        if original.kind.startswith('payroll'): ctx.require('payroll.view')
        # A partial project financial total is misleading and can leak hidden
        # location/product activity. Deny the full financial panel if any source
        # is outside the viewer's scope, instead of silently filtering its cost.
        documents.append(original.pk)
    entries = Entry.objects.filter(document_id__in=documents, document__state='posted').select_related('account')
    revenue = sum((entry.credit - entry.debit for entry in entries if entry.account.category == 'income'), ZERO)
    costs = sum((entry.debit - entry.credit for entry in entries if entry.account.category == 'expense'), ZERO)
    cogs = sum((entry.debit - entry.credit for entry in entries if entry.account.code == 'COGS'), ZERO)
    wip = sum((entry.debit - entry.credit for entry in entries if entry.account.code == 'WIP'), ZERO)
    clearing = sum((entry.debit - entry.credit for entry in entries if entry.account.code in {'COST_CLEARING', 'LABOR_CLEARING'}), ZERO)
    material_consumed = -sum((move.value for move in StockMovement.objects.filter(document_id__in=documents, pool__product__kind='raw', document__kind__in=['production', 'production_bom', 'production_consume', 'production_material_return'])), ZERO)
    return {'revenue': str(money(revenue)), 'recognized_cost': str(money(costs)), 'cogs': str(money(cogs)), 'profit': str(money(revenue - costs)), 'wip_balance': str(money(wip)), 'unabsorbed_conversion': str(money(clearing)), 'material_consumption_analysis': str(money(material_consumed)), 'basis': 'Actual income/expense ledger entries of uniquely tagged whole documents. Capitalized material, WIP and conversion clearing are displayed separately and are not expensed twice. Untagged documents are excluded.'}


OPERATIONS = {
    'job_project': ('jobs.manage', project_create),
    'job_estimate': ('jobs.plan', project_estimate),
    'job_document': ('jobs.manage', project_link),
    'job_bom_plan': ('jobs.plan', project_bom_plan),
    'job_subcontract': ('jobs.manage', subcontract_create),
    'job_subcontract_link': ('jobs.manage', subcontract_link),
    'job_subcontract_close': ('jobs.manage', subcontract_close),
    'job_close': ('jobs.manage', project_close),
}
