from decimal import Decimal
from django.core.exceptions import PermissionDenied,ValidationError
import pytest
from erp.tests.test_api import environment,client_for
from erp.tests.test_growth import growth_env,open_block
from erp.core import Context,balance
from erp.models import Block,Document,Entry,StockMovement,Product,Location,Warehouse,Business,Membership
from erp.order_readiness import readiness

def order(post,wh,sp,customer,quantity,**extra):
    return post('sales_order',{'warehouse':wh.pk,'party':customer.pk,'lines':[{'product':sp.pk,'quantity':quantity,'unit_price':'500','length_mm':'2000','width_mm':'1000'}],**extra})

def test_fragments_never_join_and_preview_does_not_reserve_or_post(growth_env):
    ctx,post,wh,sp,raw,customer,*_=growth_env
    for i in range(10):open_block(post,wh,sp,height='100')
    source=order(post,wh,sp,customer,'22')
    before=(Document.objects.count(),Entry.objects.count(),StockMovement.objects.count())
    no_details=readiness(ctx,source.pk,{})
    assert no_details['lines'][0]['status']=='needs_cut_details' and not no_details['ready_now']
    checked=readiness(ctx,source.pk,{'thickness_0':'220'})
    assert not checked['ready_now'] and checked['lines'][0]['shortage']==22 and checked['lines'][0]['available']==0
    assert not checked['reserved'] and before==(Document.objects.count(),Entry.objects.count(),StockMovement.objects.count())
    assert all(b.remaining_height_mm==100 and b.reserved_height_mm==0 for b in Block.objects.filter(business=ctx.business))

def test_shared_block_preview_budget_loss_and_quality_are_rechecked(growth_env):
    ctx,post,wh,sp,raw,customer,*_=growth_env;block=open_block(post,wh,sp,height='120')
    source=order(post,wh,sp,customer,'12')
    ready=readiness(ctx,source.pk,{'thickness_0':'60'});assert ready['ready_now'] and ready['lines'][0]['available']==12
    loss=readiness(ctx,source.pk,{'thickness_0':'60','loss_0':'1'});assert not loss['ready_now'] and loss['lines'][0]['available']==6 and loss['lines'][0]['shortage']==6
    ctx.business.settings={**ctx.business.settings,'require_inspection':True};ctx.business.save()
    assert readiness(ctx,source.pk,{'thickness_0':'60'})['lines'][0]['available']==0
    ctx.business.settings={**ctx.business.settings,'require_inspection':False};ctx.business.save()
    duplicate=post('sales_order',{'warehouse':wh.pk,'party':customer.pk,'lines':[{'product':sp.pk,'quantity':'8','unit_price':'500','length_mm':'2000','width_mm':'1000'},{'product':sp.pk,'quantity':'8','unit_price':'500','length_mm':'2000','width_mm':'1000'}]})
    result=readiness(ctx,duplicate.pk,{'thickness_0':'80','thickness_1':'80'})
    assert not result['ready_now'] and [r['available'] for r in result['lines']]==[8,0]
    assert result['lines'][1]['shortage']==8

def test_identified_held_sheets_for_this_order_are_not_lost_or_double_counted(growth_env):
    ctx,post,wh,sp,raw,customer,*_=growth_env;block=open_block(post,wh,sp,height='100')
    source=order(post,wh,sp,customer,'4.4')
    plan=post('cut_plan',{'warehouse':wh.pk,'product':sp.pk,'profile':block.profile,'lines':[{'order':source.pk,'order_index':0,'thickness_mm':'22','sheet_count':2}]})
    post('cut_execute',{'plan':plan.result['plan']})
    ready=readiness(ctx,source.pk,{'thickness_0':'22'})
    assert ready['ready_now'] and ready['lines'][0]['available']==Decimal('4.4')
    assert len(ready['lines'][0]['allocations'])==2 and all(a['held_for_this_order'] for a in ready['lines'][0]['allocations'])
    assert Block.objects.filter(parent=block,reserved_height_mm=22).count()==2

def test_weight_stock_is_budgeted_across_order_lines_and_closed_orders_are_not_ready(growth_env):
    ctx,post,wh,sp,raw,customer,*_=growth_env
    ad=Product.objects.create(business=ctx.business,code='READY-AD',name='Adhesive',kind='finished',line='adhesive',unit='kg',price='10')
    post('stock_opening',{'warehouse':wh.pk,'lines':[{'product':ad.pk,'quantity':'10','value':'100'}]})
    source=post('sales_order',{'warehouse':wh.pk,'party':customer.pk,'lines':[{'product':ad.pk,'quantity':'7','unit_price':'10'},{'product':ad.pk,'quantity':'7','unit_price':'10'}]})
    checked=readiness(ctx,source.pk,{})
    assert [r['available'] for r in checked['lines']]==[7,3] and checked['lines'][1]['shortage']==4
    post('order_cancel',{'order':source.pk,'reason':'Customer cancelled remainder'})
    assert readiness(ctx,source.pk,{})['closed'] and not readiness(ctx,source.pk,{})['ready_now']

def test_promises_keep_history_without_accounting_or_stock_effect_and_require_authority(growth_env):
    ctx,post,wh,sp,raw,customer,*_=growth_env;source=order(post,wh,sp,customer,'10')
    before=(Entry.objects.count(),StockMovement.objects.count())
    a=post('order_promise',{'order':source.pk,'promised_date':'2026-06-05','reason':'Customer agreed','basis':'Reviewed manufacturing schedule and quality release'})
    b=post('order_promise',{'order':source.pk,'promised_date':'2026-06-07','reason':'Customer accepted revised date','basis':'Reviewed transport schedule'})
    checked=readiness(ctx,source.pk,{})
    assert [p['document'] for p in checked['promises']]==[b.pk,a.pk]
    assert before==(Entry.objects.count(),StockMovement.objects.count()) and balance(ctx,'SALES')==0
    with pytest.raises(ValidationError):post('order_promise',{'order':source.pk,'promised_date':'2026-05-31','reason':'x','basis':'y'})
    with pytest.raises(ValidationError):post('order_promise',{'order':source.pk,'promised_date':'2026-06-09','reason':'x'})
    ctx.membership.permissions=['sales.view','inventory.view'];ctx.membership.save()
    with pytest.raises(PermissionDenied):post('order_promise',{'order':source.pk,'promised_date':'2026-06-09','reason':'x','basis':'y'})

def test_readiness_respects_business_locations_product_scopes_and_valid_geometry(growth_env):
    ctx,post,wh,sp,raw,customer,*_=growth_env;source=order(post,wh,sp,customer,'10');c=client_for(ctx.user,ctx.business)
    assert c.get(f'/api/orders/{source.pk}/readiness/',{'thickness_0':'-1'}).status_code==400
    assert c.get(f'/api/orders/{source.pk}/readiness/',{'thickness_0':'10','loss_0':'-1'}).status_code==400
    other=Business.objects.create(name='Furniture private',slug='readiness-private');Membership.objects.create(user=ctx.user,business=other,permissions=['*'],all_locations=True)
    assert client_for(ctx.user,other).get(f'/api/orders/{source.pk}/readiness/').status_code==400
    ctx.membership.permissions=['sales.view'];ctx.membership.save();assert c.get(f'/api/orders/{source.pk}/readiness/').status_code==403
    ctx.membership.permissions=['sales.view','inventory.view'];ctx.membership.product_lines=['adhesive'];ctx.membership.save()
    assert c.get(f'/api/orders/{source.pk}/readiness/').status_code==403

def test_transit_and_inactive_products_cannot_be_advertised_as_ready(growth_env):
    ctx,post,wh,sp,raw,customer,*_=growth_env;open_block(post,wh,sp)
    source=order(post,wh,sp,customer,'10')
    sp.active=False;sp.save(update_fields=['active'])
    assert readiness(ctx,source.pk,{'thickness_0':'100'})['lines'][0]['status']=='inactive_product'
    wh.kind='transit';wh.save(update_fields=['kind'])
    with pytest.raises(ValidationError,match='physical warehouse'):readiness(ctx,source.pk,{'thickness_0':'100'})
