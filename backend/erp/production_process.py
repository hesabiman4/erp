"""Actual batch process projection; moving a UI card never mutates a ledger."""
from decimal import Decimal
from django.core.exceptions import PermissionDenied,ValidationError
from .api import Boundary,response,document_scope,doc_permission
from .core import get_obj
from .models import Document,Block,Location


def process_board(ctx,params):
    if not any(ctx.has(p) for p in ['production.view','production.post','production.plan']):raise PermissionDenied('Production process access is restricted.')
    try:before=int(params['before']) if params.get('before') else None
    except (TypeError,ValueError):raise ValidationError('Use a numeric batch cursor.')
    if before is not None and before<=0:raise ValidationError('Use a positive batch cursor.')
    query=document_scope(ctx).filter(state='posted',kind__in=['production_start','production','production_bom'])
    if params.get('location'):query=query.filter(location=get_obj(ctx,Location,params['location']))
    if before:query=query.filter(pk__lt=before)
    sources=list(query.order_by('-id')[:61]);results=[]
    for batch in sources[:60]:
        try:doc_permission(ctx,batch)
        except (PermissionDenied,ValidationError):continue
        events=list(Document.objects.filter(business=ctx.business,reference=batch,state='posted',kind__in=['production_consume','production_material_return','production_complete']).select_related('location','warehouse'))
        # A mixed-line batch is an indivisible operational record. Do not expose
        # its whole totals by silently dropping a restricted output or input.
        lines=set(batch.product_lines)
        for e in events:lines.update(e.product_lines)
        if not ctx.has('documents.all_lines') and not lines.issubset(set(ctx.membership.product_lines)):continue
        wip=sum((Decimal(str(e.result.get('wip_in','0')))-Decimal(str(e.result.get('wip_out','0'))) for e in events),Decimal('0'))
        complete=[e for e in events if e.kind=='production_complete']
        outputs=[batch.pk] if batch.kind!='production_start' else [e.pk for e in complete]
        pieces=[]
        for block in Block.objects.filter(business=ctx.business,batch_id__in=outputs).select_related('product','warehouse'):
            if not ctx.location_allowed(block.warehouse.location_id) or not ctx.line_allowed(block.product.line):continue
            pieces.append({'id':block.pk,'code':block.code,'product':block.product_id,'product_name':block.product.name,'status':block.status,
                'length_mm':block.length_mm,'width_mm':block.width_mm,'remaining_height_mm':block.remaining_height_mm,
                'reserved_height_mm':block.reserved_height_mm,'warehouse':block.warehouse_id})
        held=[b for b in pieces if b['status'] in ['curing','inspection']]
        if batch.kind=='production_start' and not complete and wip<=0:stage='materials';next_action='production_consume';initial={'batch':batch.pk}
        elif batch.kind=='production_start' and wip>0:stage='output';next_action='production_complete';initial={'batch':batch.pk,'warehouse':batch.warehouse_id}
        elif held:stage='quality';next_action='quality_release';initial={'block':held[0]['id']} if len(held)==1 else {}
        else:stage='ready';next_action=None;initial={}
        row={'id':batch.pk,'number':batch.number,'date':batch.date,'warehouse':batch.warehouse_id,'warehouse_name':batch.warehouse.name if batch.warehouse else '',
            'stage':stage,'has_completion':bool(complete) or batch.kind!='production_start','can_consume':batch.kind=='production_start' and not complete,
            'next_action':next_action,'initial':initial,'blocks':pieces,'held_blocks':len(held),'has_remaining_wip':wip>0,
            'output_documents':[{'id':e.pk,'number':e.number} for e in complete]}
        if ctx.has('cost.view'):row['wip_remaining']=wip
        results.append(row)
    return {'results':results,'next_cursor':sources[59].pk if len(sources)>60 else None,'page_size':60,
        'basis':'Stages derive from original posted consumption, output and physical block status. Dragging only opens a reviewed existing operation; it never posts or saves a cosmetic stage.'}


class ProductionProcessAPI(Boundary):
    def get(self,request):
        params=dict(request.query_params.items())
        if request.headers.get('X-Location-ID'):params['location']=request.headers['X-Location-ID']
        return response(process_board(self.ctx(request),params))
