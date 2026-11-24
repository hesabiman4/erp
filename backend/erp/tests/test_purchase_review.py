from decimal import Decimal
from uuid import uuid4
import pytest
from erp.tests.test_api import environment,client_for
from erp.tests.test_growth import growth_env
from erp.core import Context,balance,outstanding
from erp.models import Document,Entry,StockMovement,Product,Business,Membership
from erp.purchase_review import review

def fixture_purchase(ctx,post,wh,raw,supplier):
    order=post('purchase_order',{'warehouse':wh.pk,'supplier':supplier.pk,'expected_date':'2026-06-02','lines':[{'product':raw.pk,'quantity':'10','unit_cost':'100'}]})
    receipt=post('purchase_receive',{'warehouse':wh.pk,'supplier':supplier.pk,'order':order.pk,'lines':[{'product':raw.pk,'quantity':'8','unit_cost':'110','order_index':0}]})
    bill=post('purchase_bill',{'receipt':receipt.pk,'supplier_reference':'TRAIN-001','lines':[{'index':0,'quantity':'3'}]})
    return order,receipt,bill

def test_purchase_review_reconciles_receipt_remainders_billed_returns_and_payables(growth_env):
    ctx,post,wh,sp,raw,customer,supplier=growth_env;order,receipt,bill=fixture_purchase(ctx,post,wh,raw,supplier)
    post('purchase_return',{'receipt':receipt.pk,'bill':bill.pk,'reason':'Actual billed return','lines':[{'index':0,'quantity':'1'}]})
    post('purchase_return',{'receipt':receipt.pk,'reason':'Actual unbilled return','lines':[{'index':0,'quantity':'2'}]})
    claim=post('supplier_claim',{'document':receipt.pk,'index':0,'quantity':'1','reason':'quality','description':'Documented quality evidence'})
    before=(Document.objects.count(),Entry.objects.count(),StockMovement.objects.count())
    result=review(ctx,{})
    assert result['counts']=={'undelivered':1,'unbilled':1,'price_review':1,'unpaid':1,'claim':1}
    assert result['unpaid_total']==220
    assert next(r for r in result['results'] if r['kind']=='undelivered')['lines'][0]['remaining']==2
    assert next(r for r in result['results'] if r['kind']=='unbilled')['lines'][0]['remaining']==3
    assert next(r for r in result['results'] if r['kind']=='price_review')['lines'][0]['difference']=='10'
    assert before==(Document.objects.count(),Entry.objects.count(),StockMovement.objects.count())
    client=client_for(ctx.user,ctx.business)
    billable=client.get(f'/api/receipts/{receipt.pk}/billable/').json()
    assert Decimal(billable['lines'][0]['remaining_quantity'])==3 and billable['supplier']==supplier.pk
    before_stock=StockMovement.objects.count();key=str(uuid4());payload={'receipt':receipt.pk,'supplier_reference':'TRAIN-002','lines':[{'index':0,'quantity':'3'}]}
    new_bill=post('purchase_bill',payload,key);assert post('purchase_bill',payload,key).pk==new_bill.pk
    assert StockMovement.objects.count()==before_stock and balance(ctx,'GRNI')==0 and balance(ctx,'AP')==-550
    assert 'unbilled' not in review(ctx,{})['counts']

def test_purchase_review_hides_restricted_link_totals_and_price_details(growth_env):
    ctx,post,wh,sp,raw,customer,supplier=growth_env
    finished=Product.objects.create(business=ctx.business,code='AD',name='Finished adhesive',kind='finished',line='adhesive',unit='kg')
    order=post('purchase_order',{'warehouse':wh.pk,'supplier':supplier.pk,'lines':[{'product':raw.pk,'quantity':'10','unit_cost':'999'},{'product':finished.pk,'quantity':'2','unit_cost':'5'}]})
    post('purchase_receive',{'warehouse':wh.pk,'supplier':supplier.pk,'order':order.pk,'lines':[{'product':raw.pk,'quantity':'1','unit_cost':'999','order_index':0}]})
    post('purchase_receive',{'warehouse':wh.pk,'supplier':supplier.pk,'order':order.pk,'lines':[{'product':finished.pk,'quantity':'1','unit_cost':'5','order_index':1}]})
    ctx.membership.permissions=['purchases.view','documents.all_lines'];ctx.membership.save()
    result=review(Context(ctx.user,ctx.business),{})
    assert result['counts']=={'restricted_links':1} and result['unpaid_total']==0
    assert '999' not in str(result) and all(r['lines']==[] for r in result['results'])

def test_review_pagination_search_and_filters_cover_all_matches(growth_env):
    ctx,post,wh,sp,raw,customer,supplier=growth_env
    for i in range(4):post('purchase_order',{'warehouse':wh.pk,'supplier':supplier.pk,'lines':[{'product':raw.pk,'quantity':str(i+1),'unit_cost':'100'}]})
    result=review(ctx,{'limit':'2'});assert result['count']==4 and result['next_offset']==2 and len(result['results'])==2
    second=review(ctx,{'limit':'2','offset':'2'});assert second['count']==4 and second['next_offset'] is None
    assert review(ctx,{'q':second['results'][0]['number']})['count']==1
    assert review(ctx,{'kind':'unpaid'})['count']==0
    assert review(ctx,{'q':'not a supplier'})['count']==0

def test_purchasing_review_and_billable_enforce_action_and_tenant_boundaries(growth_env):
    ctx,post,wh,sp,raw,customer,supplier=growth_env;order,receipt,bill=fixture_purchase(ctx,post,wh,raw,supplier)
    client=client_for(ctx.user,ctx.business)
    for params in [{'kind':'secret'},{'limit':201},{'offset':-1},{'q':'x'*101}]:assert client.get('/api/purchase-review/',params).status_code==400
    ctx.membership.permissions=['purchases.view','inventory.raw'];ctx.membership.save()
    assert client.get('/api/purchase-review/').status_code==200
    assert client.get(f'/api/receipts/{receipt.pk}/billable/').status_code==403
    ctx.membership.permissions=['sales.view'];ctx.membership.save();assert client.get('/api/purchase-review/').status_code==403
    other=Business.objects.create(name='Hidden furniture',slug='purchase-review-private');Membership.objects.create(user=ctx.user,business=other,permissions=['*'],all_locations=True)
    foreign=client_for(ctx.user,other)
    assert foreign.get('/api/purchase-review/').json()['count']==0
    assert foreign.get(f'/api/receipts/{receipt.pk}/billable/').status_code==400
