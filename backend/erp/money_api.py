from django.core.exceptions import PermissionDenied
from .api import Boundary,response
from .models import MoneyInstrument,Location,Account,Entry
from django.db.models import Sum
from .core import get_obj,balance,money,ZERO
from .money_instruments import whole_pool,instrument_balance


class MoneyInstrumentsAPI(Boundary):
    def get(self,request):
        ctx=self.ctx(request);choices=request.query_params.get('choices')=='1'
        if choices:
            if not any(ctx.has(p) for p in ['finance.post','sales.post','sales.collect','purchases.pay','payroll.post','cash_shifts.manage','cash_shifts.open','finance.statements','finance.reverse','finance.fx','accounting.post','accounting.opening','sales.refund']):raise PermissionDenied('Monetary workflow access is required for instrument choices.')
        else:whole_pool(ctx)
        selected=request.query_params.get('location') or request.headers.get('X-Location-ID')
        if selected:get_obj(ctx,Location,selected)
        query=MoneyInstrument.objects.filter(business=ctx.business,active=True).select_related('location').order_by('location_id','kind','-legacy','id')
        if not ctx.membership.all_locations:query=query.filter(location_id__in=ctx.membership.location_ids)
        if selected:query=query.filter(location_id=selected)
        rows=[]
        for item in query:
            row={'id':item.pk,'location':item.location_id,'kind':item.kind,'code':item.code,'name':item.name,'legacy':item.legacy,'active':item.active}
            if not choices:row.update({'location_name':item.location.name,'institution':item.institution,'account_reference':item.account_reference,'balance':instrument_balance(item)})
            rows.append(row)
        controls=[];unassigned=[]
        if not choices:
            locations=Location.objects.filter(business=ctx.business)
            if not ctx.membership.all_locations:locations=locations.filter(pk__in=ctx.membership.location_ids)
            if selected:locations=locations.filter(pk=selected)
            for location in locations:
                for kind in ('CASH','BANK'):
                    if not Account.objects.filter(business=ctx.business,code=kind).exists():continue
                    instruments=list(query.filter(location=location,kind=kind))
                    total=sum((instrument_balance(i) for i in instruments),ZERO)
                    ledger=money(balance(ctx,kind,location=location))
                    unregistered=ledger if not instruments else ZERO
                    controls.append({'location':location.pk,'kind':kind,'instrument_total':money(total),'unregistered_legacy_balance':unregistered,'ledger_balance':ledger,'difference':money(ledger-total-unregistered)})
            if ctx.membership.all_locations and not selected:
                for kind in ('CASH','BANK'):
                    amounts=Entry.objects.filter(document__business=ctx.business,document__state='posted',account__code=kind,location__isnull=True).aggregate(dr=Sum('debit'),cr=Sum('credit'))
                    unassigned.append({'kind':kind,'balance':money((amounts['dr'] or ZERO)-(amounts['cr'] or ZERO)),'basis':'Original company entries without a physical location; not silently assigned to any instrument.'})
        return response({'controls':controls,'unassigned_location':unassigned,'results':rows,'choices_only':choices,'currency':'AFN','legacy_unregistered_locations':not bool(rows),
            'basis':'Separate AFN physical instruments reconcile to the existing CASH/BANK controls. Legacy unlinked entries remain in their original location pool.'})
