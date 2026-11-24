from django.core.exceptions import PermissionDenied,ValidationError
from .api import Boundary,response,doc_permission
from .core import Context,get_obj,balance,money
from .models import CashDrawer,CashShift,Membership,Location
from .cashier_shifts import drawer_for,shift_for,custody_scope,expected,current_receiver,drawer_balance,drawer_instrument


def eligible(ctx,location=None):
    records=[]
    for member in Membership.objects.filter(business=ctx.business,active=True,user__is_active=True).select_related('user'):
        candidate=Context(member.user,ctx.business,member)
        if not candidate.has('cash_shifts.open'):continue
        if location:
            try:custody_scope(candidate,location)
            except PermissionDenied:continue
        records.append({'id':member.id,'name':member.user.get_full_name() or member.user.username})
    return records


def shift_row(ctx,shift):
    count=shift.counts.order_by('-id').first()
    handover=getattr(shift,'cashhandover',None)
    return {'id':shift.id,'number':shift.source.number,'drawer':shift.drawer_id,'drawer_name':shift.drawer.name,'location':shift.drawer.location_id,
        'cashier':shift.cashier_id,'cashier_name':shift.cashier.user.get_full_name() or shift.cashier.user.username,
        'mine':shift.cashier_id==ctx.membership.id,'date':shift.source.date,'state':shift.state,'opening_amount':shift.opening_amount,
        'expected':expected(shift),'opening_denominations':shift.opening_denominations,
        'count':{'id':count.id,'expected':count.expected,'counted':count.counted,'variance':count.variance,'denominations':count.denominations,'note':count.note,'date':count.source.date} if count else None,
        'review':shift.reviewed_by_id,'handover':handover.id if handover else None,'handover_receiver':current_receiver(handover)[0] if handover else None,'handover_accepted':bool(handover and handover.accepted_by_id)}


class CashierAPI(Boundary):
    def get(self,request):
        ctx=self.ctx(request)
        if not any(ctx.has(p) for p in ['cash_shifts.view','cash_shifts.open','cash_shifts.manage','cash_shifts.review','cash_shifts.handover']):raise PermissionDenied('Cash custody is restricted.')
        location=request.query_params.get('location') or request.headers.get('X-Location-ID')
        if location:location=get_obj(ctx,Location,location).id
        if request.query_params.get('shift'):
            shift=shift_for(ctx,request.query_params['shift']);data=shift_row(ctx,shift)
            try:offset=int(request.query_params.get('offset',0))
            except (TypeError,ValueError):raise ValidationError('Use a nonnegative movement offset.')
            if offset<0:raise ValidationError('Use a nonnegative movement offset.')
            links=shift.cash_entries.filter(entry__document__state='posted').select_related('entry__document').order_by('id');moves=[]
            for link in links[offset:offset+100]:
                entry=link.entry;doc=entry.document
                try:doc_permission(ctx,doc);visible=True
                except (PermissionDenied,ValidationError):visible=False
                moves.append({'id':link.id,'date':doc.date,'number':doc.number if visible else None,'document':doc.id if visible else None,
                    'restricted_source':not visible,'received':entry.debit,'paid':entry.credit,'cash_change':entry.debit-entry.credit,
                    'reason':link.reason if visible else ''})
            data.update({'movements':moves,'movement_count':links.count(),'next_offset':offset+100 if links.count()>offset+100 else None,'receivers':eligible(ctx,shift.drawer.location_id)})
            return response(data)
        drawers=[];shifts=[]
        for drawer in CashDrawer.objects.filter(business=ctx.business).select_related('location'):
            try:drawer_for(ctx,drawer.id)
            except (PermissionDenied,ValidationError):continue
            if location and drawer.location_id!=location:continue
            active=drawer.shifts.filter(state__in=['open','counted']).first()
            visible=not active or active.cashier_id==ctx.membership.pk or ctx.has('cash_shifts.manage') or ctx.has('cash_shifts.review')
            drawers.append({'id':drawer.id,'name':drawer.name,'code':drawer.code,'location':drawer.location_id,'location_name':drawer.location.name,
                'managed':bool(drawer.activated_by_id),'active_shift':active.id if active and visible else None,'occupied':bool(active),
                'instrument':getattr(drawer_instrument(drawer),'pk',None),'recorded_cash':drawer_balance(ctx,drawer) if visible else None})
        for shift in CashShift.objects.filter(business=ctx.business).select_related('drawer__location','cashier__user','source').order_by('-id'):
            try:shift_for(ctx,shift.id)
            except (PermissionDenied,ValidationError):continue
            if location and shift.drawer.location_id!=location:continue
            shifts.append(shift_row(ctx,shift))
            if len(shifts)>=100:break
        return response({'drawers':drawers,'results':shifts,'current_member':ctx.membership.id,
            'basis':'Each drawer accounts for its selected physical AFN cash instrument. Opening, counting and handover do not move cash or post income. Reviewed actual discrepancies use separate recorded expense/other income, never automatic employee debt.'})
