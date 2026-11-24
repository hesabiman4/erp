from django.core.exceptions import PermissionDenied, ValidationError
from .api import Boundary, response, can, doc_permission
from .core import get_obj, get_product, get_warehouse
from .models import Document, StockPool
from .jobs_models import CostingProject, SubcontractJob
from .jobs import project_for, actuals, ALLOWED_PROJECT_DOCUMENTS, posted


def project_row(ctx, project):
    project_for(ctx, project.pk)
    result = {'id': project.pk, 'code': project.code, 'name': project.name, 'customer': project.customer_id, 'customer_name': project.customer.name, 'location': project.location_id, 'description': project.description, 'due_date': project.due_date, 'state': project.state, 'source': project.source_id, 'documents': [], 'estimates': [], 'bom_plans': [], 'financials_restricted': True}
    restricted = False
    for link in project.document_links.select_related('document'):
        try:
            document = get_obj(ctx, Document, link.document_id)
            doc_permission(ctx,document)
        except (PermissionDenied, ValidationError): restricted = True; continue
        if document.kind.startswith('payroll') and not ctx.has('payroll.view'):
            restricted = True; continue
        result['documents'].append({'id': document.pk, 'number': document.number, 'kind': document.kind, 'date': document.date, 'note': link.note})
    if ctx.has('cost.view'):
        for estimate in project.estimates.select_related('source').order_by('-pk'):
            if not set(estimate.source.product_lines).issubset(set(ctx.membership.product_lines)): continue
            result['estimates'].append({'id': estimate.pk, 'date': estimate.source.date, 'lines': estimate.lines, 'estimated_cost': estimate.estimated_cost, 'estimated_revenue': estimate.estimated_revenue, 'note': estimate.note})
    if ctx.has('bom.view') and ctx.has('consumption.view') and ctx.business.manufacturing_mode == 'bom':
        for plan in project.bom_plans.select_related('source'):
            if set(plan.source.product_lines).issubset(set(ctx.membership.product_lines)):
                result['bom_plans'].append({'id': plan.pk, 'quantity': plan.quantity, 'snapshot': plan.snapshot, 'date': plan.source.date})
    if ctx.has('accounting.view') and ctx.has('cost.view') and not restricted:
        result['actuals'] = actuals(ctx, project)
        result['financials_restricted'] = False
    result['partial_scope'] = restricted
    return result


class JobsAPI(Boundary):
    def get(self, request, section):
        ctx = self.ctx(request)
        if not can(ctx, 'jobs.view', 'jobs.manage', 'jobs.plan'):
            raise PermissionDenied('Project/job costing access is restricted.')
        location = request.headers.get('X-Location-ID')
        try:
            location = int(location) if location else None
            limit = max(1, min(100, int(request.query_params.get('limit', '100'))))
            offset = max(0, int(request.query_params.get('offset', '0')))
        except ValueError: raise ValidationError('Use integer pagination/location.')
        if location and not ctx.location_allowed(location): raise PermissionDenied('Restricted location.')
        result = []
        if section == 'sources':
            query = Document.objects.filter(business=ctx.business, state='posted', kind__in=ALLOWED_PROJECT_DOCUMENTS).order_by('-pk')
            if request.query_params.get('q'): query = query.filter(number__icontains=str(request.query_params['q'])[:150])
            if location: query = query.filter(location_id=location)
            for document in query:
                try: posted(ctx, document.pk)
                except (PermissionDenied, ValidationError): continue
                # Source lookup intentionally omits all amounts/ingredients.
                result.append({'id': document.pk, 'number': document.number, 'kind': document.kind, 'date': document.date, 'warehouse': document.warehouse_id, 'party': document.party_id, 'project': getattr(getattr(document, 'costing_project_link', None), 'project_id', None)})
                if len(result) >= 100: break
            return response({'results': result, 'limit': 100})
        if section == 'projects':
            query = CostingProject.objects.filter(business=ctx.business).select_related('customer').order_by('-pk')
            if request.query_params.get('id'): query = query.filter(pk=request.query_params['id'])
            for project in query:
                if location and project.location_id != location: continue
                try: result.append(project_row(ctx, project))
                except (PermissionDenied, ValidationError): continue
        elif section == 'subcontracts':
            for order in SubcontractJob.objects.filter(business=ctx.business).select_related('project', 'supplier', 'product', 'warehouse').order_by('-pk'):
                try:
                    project_for(ctx, order.project_id); get_warehouse(ctx, order.warehouse_id); get_product(ctx, order.product_id)
                    if location and order.warehouse.location_id != location: continue
                    events = []
                    for event in order.events.select_related('document'):
                        posted(ctx, event.document_id)
                        events.append({'id': event.pk, 'kind': event.kind, 'document': event.document_id, 'number': event.document.number, 'quantity': event.quantity, 'processing_bill': event.processing_bill_id, 'note': event.note})
                    result.append({'id': order.pk, 'project': order.project_id, 'project_code': order.project.code, 'supplier': order.supplier_id, 'supplier_name': order.supplier.name, 'warehouse': order.warehouse_id, 'warehouse_name': order.warehouse.name, 'product': order.product_id, 'product_name': order.product.name, 'unit': order.product.unit, 'planned_quantity': order.planned_quantity, 'instructions': order.instructions, 'state': order.state, 'events': events, 'owned_stock_note': 'Vendor warehouse quantities remain company-owned. Leftover material is never erased by closing this job.'})
                except (PermissionDenied, ValidationError): continue
        else: raise ValidationError('Unknown job costing resource.')
        return response({'results': result[offset:offset + limit], 'count': len(result), 'next_offset': offset + limit if len(result) > offset + limit else None})
