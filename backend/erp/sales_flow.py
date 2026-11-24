"""Read-only, permission-scoped commercial progression from immutable documents."""
from decimal import Decimal
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from .models import Document, Allocation
from .core import D, outstanding


def commercial_flow(ctx, document):
    if document.kind=='quotation' and document.state in {'draft','cancelled'}:
        from .api import doc_permission
        related=[];closure=None
        for item in Document.objects.filter(business=ctx.business,kind='order_cancel',state='posted',reference=document).order_by('id'):
            try:doc_permission(ctx,item)
            except (PermissionDenied,ValidationError):continue
            related.append({'id':item.id,'number':item.number,'kind':item.kind,'date':item.date.isoformat(),'state':item.state})
            closure={'number':item.number,'date':item.date.isoformat(),'reason':item.result.get('reason','')}
        cancelled=document.state=='cancelled'
        return {'status':'cancelled' if cancelled else 'draft','cancelled':cancelled,'closure':closure,'can_continue':False,'can_cancel':not cancelled,'lines':[],'related':related}
    if document.state != 'posted' or document.kind not in {'quotation', 'sales_order', 'sale', 'receipt'}:
        return None
    # Import at call time to share the exact document visibility boundary.
    from .api import doc_permission
    visible = []
    restricted_progress = False
    def permitted(item):
        try:
            doc_permission(ctx, item)
            return True
        except (PermissionDenied, ValidationError):
            return False
    def add(item):
        if item.id == document.id or any(row['id'] == item.id for row in visible):
            return
        if not permitted(item):
            return
        visible.append({'id': item.id, 'number': item.number, 'kind': item.kind, 'date': item.date.isoformat(), 'state': item.state})
    related = Document.objects.filter(business=ctx.business, state='posted').select_related('party', 'warehouse', 'location', 'employee', 'reference')
    source = document.reference if document.reference_id else None
    if source:
        add(source)
    rows = []
    cancellation_ids = [document.id]
    if document.kind == 'sales_order' and source and source.kind == 'quotation':
        cancellation_ids.append(source.id)
    cancellations = list(related.filter(kind='order_cancel', reference_id__in=cancellation_ids))
    for item in cancellations:
        # Legacy cancellation documents did not always inherit product scopes.
        if item.reference_id and not permitted(item.reference):
            restricted_progress = True
        elif permitted(item):
            add(item)
    cancelled = bool(cancellations)
    if document.kind in {'quotation', 'sales_order'}:
        kind = 'sales_order' if document.kind == 'quotation' else 'sale'
        children = list(related.filter(reference=document, kind=kind) if kind == 'sales_order' else related.filter(kind='sale', result__order=document.id))
        # Older versions permitted quote conversion into another warehouse. Never
        # disclose that hidden child's quantities through a source summary.
        restricted_progress = restricted_progress or any(not permitted(child) for child in children)
        for child in children:
            add(child)
        for index, original in enumerate(document.result.get('lines', [])):
            key = 'quotation_index' if document.kind == 'quotation' else 'order_index'
            used = sum((D(line['quantity']) for child in children for line in child.result.get('lines', []) if line.get(key, line.get('index')) == index), Decimal('0'))
            remaining = max(D(original['quantity']) - used, Decimal('0'))
            rows.append({**original, 'index': index, 'processed_quantity': str(used), 'remaining_quantity': str(remaining)})
        remaining = sum((D(row['remaining_quantity']) for row in rows), Decimal('0'))
        used = sum((D(row['processed_quantity']) for row in rows), Decimal('0'))
        status = 'cancelled' if cancelled else ('ordered' if document.kind == 'quotation' else 'fulfilled') if remaining == 0 else 'partial' if used else 'open'
        can_continue = not cancelled and remaining > 0
        if document.kind == 'quotation':
            invoices = related.filter(kind='sale', result__order__in=[child.id for child in children])
            for invoice in invoices:
                add(invoice)
    else:
        status = ('unpaid' if outstanding(document) == document.amount else 'partial') if document.kind == 'sale' and outstanding(document) > 0 else 'paid'
        can_continue = document.kind == 'sale' and outstanding(document) > 0
    if document.kind == 'sale':
        for allocation in Allocation.objects.filter(invoice=document).select_related('document'):
            add(allocation.document)
    elif document.kind == 'receipt':
        for allocation in Allocation.objects.filter(document=document).select_related('invoice'):
            add(allocation.invoice)
    visible_ids={row['id'] for row in visible}
    closure=next(({'number':item.number,'date':item.date.isoformat(),'reason':item.result.get('reason','')} for item in reversed(cancellations) if item.id in visible_ids),None)
    if restricted_progress and document.kind in {'quotation','sales_order'}:
        return {'status':'restricted','restricted_progress':True,'cancelled':False,'closure':None,'can_continue':False,'lines':[],'related':sorted(visible,key=lambda row:(row['date'],row['id'])),'can_cancel':False}
    return {'status': status, 'cancelled': cancelled, 'closure': closure, 'can_continue': can_continue, 'lines': rows, 'related': sorted(visible, key=lambda row: (row['date'], row['id'])), 'can_cancel': document.kind in {'quotation', 'sales_order'} and not cancelled}
