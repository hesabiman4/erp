from datetime import timedelta
from decimal import Decimal
import pytest
from django.core.exceptions import PermissionDenied,ValidationError
from django.utils import timezone
from erp.tests.test_api import environment,client_for
from erp.tests.test_growth import growth_env,open_block
from erp.core import profile_for
from erp.models import Product,Document,Entry,StockMovement,Location,Warehouse
from erp.demand_planning import suggestion


def params(wh,product,**extra):return {'warehouse':wh.pk,'product':product.pk,'to':'2026-06-07','lookback_days':7,'lead_days':0,'cover_days':7,'safety_quantity':0,'rounding_quantity':1,**extra}


def test_actual_net_sales_returns_backlog_and_rounding_without_writes(growth_env):
    ctx,post,wh,sp,raw,customer,*_=growth_env
    ad=Product.objects.create(business=ctx.business,code='PLAN-AD',name='Planning adhesive',kind='finished',unit='kg',line='adhesive',price='100')
    post('stock_opening',{'warehouse':wh.pk,'lines':[{'product':ad.pk,'quantity':'100','value':'1000'}]})
    sale=post('sale',{'warehouse':wh.pk,'party':customer.pk,'lines':[{'product':ad.pk,'quantity':'40'}],'paid':'0'})
    post('sales_return',{'invoice':sale.pk,'lines':[{'index':0,'quantity':'10'}]})
    post('sales_order',{'warehouse':wh.pk,'party':customer.pk,'lines':[{'product':ad.pk,'quantity':'90','unit_price':'100'}]})
    before=(Document.objects.count(),Entry.objects.count(),StockMovement.objects.count())
    result=suggestion(ctx,params(wh,ad,safety_quantity='2',rounding_quantity='5'))
    assert result['sold_quantity']==40 and result['returned_quantity']==10 and result['net_quantity']==30
    assert result['projected_quantity']==30 and result['open_order_quantity']==90 and result['ready_quantity']==70
    assert result['suggested_quantity']==25  # ceil((max(30,90)+2-70)/5)*5
    assert not result['formula_inferred'] and not result['financial_posting'] and result['snapshot_only']
    assert before==(Document.objects.count(),Entry.objects.count(),StockMovement.objects.count())


def test_sponge_uses_billed_height_not_kerf_and_keeps_footprints_and_holds(growth_env):
    ctx,post,wh,sp,raw,customer,*_=growth_env;block=open_block(post,wh,sp,'100')
    sale=post('sale',{'warehouse':wh.pk,'party':customer.pk,'lines':[{'product':sp.pk,'block':block.pk,'thickness_mm':'22','cutting_loss_mm':'2'}],'paid':'0'})
    post('sales_return',{'invoice':sale.pk,'lines':[{'index':0,'sheet_count':1}]})
    post('stock_opening',{'warehouse':wh.pk,'lines':[{'product':sp.pk,'value':'100','blocks':[{'length_mm':'1000','width_mm':'1000','height_mm':'100'}]}]})
    result=suggestion(ctx,params(wh,sp,length_mm=2000,width_mm=1000))
    assert result['sold_quantity']==Decimal('2.2') and result['returned_quantity']==Decimal('2.2')
    assert result['ready_quantity']==Decimal('7.6')  # returned sheet is under inspection
    assert result['profile']==profile_for(2000,1000)
    other=suggestion(ctx,params(wh,sp,length_mm=1000,width_mm=1000));assert other['sold_quantity']==0 and other['ready_quantity']==10
    ctx.business.settings={**ctx.business.settings,'require_inspection':True};ctx.business.save()
    assert suggestion(ctx,params(wh,sp,length_mm=2000,width_mm=1000))['ready_quantity']==0


def test_assumed_capacity_uses_actual_bookings_and_never_reserves(growth_env):
    ctx,post,wh,sp,raw,customer,*_=growth_env
    ad=Product.objects.create(business=ctx.business,code='CAP-AD',name='Capacity adhesive',kind='finished',unit='kg',line='adhesive',price='100')
    post('sales_order',{'warehouse':wh.pk,'party':customer.pk,'lines':[{'product':ad.pk,'quantity':'20','unit_price':'100'}]})
    center=post('work_center',{'name':'Actual center','location':wh.location_id,'daily_minutes':100}).result['work_center']
    post('work_order',{'work_center':center,'warehouse':wh.pk,'product':ad.pk,'planned_quantity':'2','planned_minutes':40,'scheduled_date':timezone.localdate().isoformat()})
    before=(Document.objects.count(),Entry.objects.count(),StockMovement.objects.count())
    result=suggestion(ctx,params(wh,ad,cover_days=1,work_center=center,minutes_per_unit=4))
    assert result['capacity']['free_minutes']==60 and result['capacity']['needed_minutes']==80 and result['capacity']['shortage_minutes']==20
    assert not result['capacity']['reserved'] and before==(Document.objects.count(),Entry.objects.count(),StockMovement.objects.count())


def test_generic_reservations_excluded_but_live_order_cut_reservations_count_once(growth_env):
    ctx,post,wh,sp,raw,customer,*_=growth_env;block=open_block(post,wh,sp,'100')
    post('reserve',{'warehouse':wh.pk,'lines':[{'block':block.pk,'thickness_mm':'20'}]})
    order=post('sales_order',{'warehouse':wh.pk,'party':customer.pk,'lines':[{'product':sp.pk,'quantity':'10','unit_price':'500','length_mm':2000,'width_mm':1000}]})
    p=params(wh,sp,length_mm=2000,width_mm=1000)
    result=suggestion(ctx,p);assert result['ready_quantity']==8 and result['suggested_quantity']==2 and result['assigned_reserved_quantity']==0
    plan=post('cut_plan',{'warehouse':wh.pk,'product':sp.pk,'profile':block.profile,'lines':[{'order':order.pk,'order_index':0,'thickness_mm':'20','sheet_count':2}]})
    planned=suggestion(ctx,p);assert planned['ready_quantity']==8 and planned['assigned_reserved_quantity']==4
    post('cut_execute',{'plan':plan.result['plan']})
    cut=suggestion(ctx,p);assert cut['ready_quantity']==8 and cut['assigned_reserved_quantity']==4 and cut['suggested_quantity']==2


def test_tenant_location_permission_and_mixed_line_records_cannot_understate_demand(growth_env):
    ctx,post,wh,sp,raw,customer,*_=growth_env;open_block(post,wh,sp)
    ad=Product.objects.create(business=ctx.business,code='SECRET-AD',name='Restricted product',kind='finished',unit='kg',line='adhesive',price='1')
    post('sales_order',{'warehouse':wh.pk,'party':customer.pk,'lines':[{'product':sp.pk,'quantity':'1','unit_price':'1','length_mm':2000,'width_mm':1000},{'product':ad.pk,'quantity':'1','unit_price':'1'}]})
    ctx.membership.permissions=['production.plan','sales.view','inventory.view'];ctx.membership.product_lines=['sponge'];ctx.membership.save()
    with pytest.raises(PermissionDenied,match='restricted related records'):suggestion(ctx,params(wh,sp,length_mm=2000,width_mm=1000))
    client=client_for(ctx.user,ctx.business);assert client.get('/api/planning/demand/',params(wh,sp,length_mm=2000,width_mm=1000)).status_code==403
    ctx.membership.permissions=['sales.view'];ctx.membership.save()
    with pytest.raises(PermissionDenied):suggestion(ctx,params(wh,sp,length_mm=2000,width_mm=1000))


@pytest.mark.parametrize('change',[{'lookback_days':0},{'lookback_days':367},{'cover_days':0},{'lead_days':365,'cover_days':2},{'safety_quantity':-1},{'rounding_quantity':0},{'to':(timezone.localdate()+timedelta(days=1)).isoformat()},{'length_mm':'2000.0001'}])
def test_invalid_assumptions_rejected(growth_env,change):
    ctx,post,wh,sp,*_=growth_env
    with pytest.raises(ValidationError):suggestion(ctx,params(wh,sp,**{'length_mm':2000,'width_mm':1000,**change}))
