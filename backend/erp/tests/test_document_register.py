"""Whole-result register acceptance on actual PostgreSQL postings."""
import pytest
from erp.tests.test_api import environment,client_for
from erp.tests.test_growth import growth_env
from erp.models import Document,Entry,StockMovement,Business,Location,Product,Membership

def get(ctx,**params):
    return client_for(ctx.user,ctx.business).get('/api/document-register/',params)

def test_whole_result_sort_filter_balance_and_totals_are_not_page_local(growth_env):
    ctx,post,wh,sp,raw,customer,*_=growth_env
    invoices=[post('opening_receivable',{'party':customer.pk,'location':wh.location_id,'amount':str(i),'reason':'Verified synthetic opening'}) for i in range(1,106)]
    post('receipt',{'invoice':invoices[-1].pk,'location':wh.location_id,'amount':'105'})
    post('receipt',{'invoice':invoices[-2].pk,'location':wh.location_id,'amount':'4'})
    before=(Document.objects.count(),Entry.objects.count(),StockMovement.objects.count())
    response=get(ctx,kind='opening_receivable',limit='5',sort='-amount')
    assert response.status_code==200,response.content
    result=response.json();assert result['count']==105 and result['next_offset']==5
    assert result['totals']=={'amount':'5565.00','balance':'5456.00'}
    assert [r['amount'] for r in result['results']]==['105.00','104.00','103.00','102.00','101.00']
    second=get(ctx,kind='opening_receivable',limit=5,offset=5,sort='-amount').json()
    assert second['results'][0]['amount']=='100.00' and second['totals']==result['totals']
    paid=get(ctx,kind='opening_receivable',payment='paid').json()
    assert paid['count']==1 and paid['totals']=={'amount':'105.00','balance':'0.00'}
    partial=get(ctx,kind='opening_receivable',payment='partial').json()
    assert partial['count']==1 and partial['results'][0]['id']==invoices[-2].pk and partial['totals']['balance']=='100.00'
    overdue=get(ctx,kind='opening_receivable',payment='overdue').json()
    assert overdue['count']==104 and overdue['totals']['balance']=='5456.00'
    assert get(ctx,kind='opening_receivable',q=invoices[0].number).json()['count']==1
    assert get(ctx,kind='opening_receivable',**{'from':'2026-06-02'}).json()['totals']['amount']=='0'
    assert before==(Document.objects.count(),Entry.objects.count(),StockMovement.objects.count())

def test_hidden_documents_do_not_leak_through_count_sort_or_totals(growth_env):
    ctx,post,wh,sp,raw,customer,supplier=growth_env
    post('purchase_receive',{'warehouse':wh.pk,'supplier':supplier.pk,'lines':[{'product':raw.pk,'quantity':'10','unit_cost':'999'}]})
    finished=Product.objects.create(business=ctx.business,code='AD',name='Adhesive',kind='finished',line='adhesive',unit='kg')
    visible=post('purchase_receive',{'warehouse':wh.pk,'supplier':supplier.pk,'lines':[{'product':finished.pk,'quantity':'2','unit_cost':'3'}]})
    ctx.membership.permissions=['purchases.view'];ctx.membership.save()
    result=get(ctx,kind='purchase_receive',sort='-amount').json()
    assert result['count']==1 and result['totals']['amount']=='6.00' and result['results'][0]['id']==visible.pk
    assert '9990' not in str(result)
    ctx.membership.permissions=['inventory.view'];ctx.membership.save()
    assert get(ctx,kind='purchase_receive').status_code==403

def test_cost_redaction_and_business_location_product_scopes(growth_env):
    ctx,post,wh,sp,raw,customer,*_=growth_env
    post('stock_opening',{'warehouse':wh.pk,'lines':[{'product':sp.pk,'value':'12345','blocks':[{'length_mm':'2000','width_mm':'1000','height_mm':'100'}]}]})
    ctx.membership.permissions=['inventory.view'];ctx.membership.save()
    hidden=get(ctx,kind='stock_opening',sort='amount').json()
    assert hidden['count']==1 and hidden['totals']['amount'] is None and hidden['results'][0]['amount'] is None
    assert '12345' not in str(hidden)
    ctx.membership.permissions=['*'];ctx.membership.save()
    other=Location.objects.create(business=ctx.business,code='K',name='Kabul')
    post('opening_receivable',{'party':customer.pk,'location':other.pk,'amount':'400','reason':'Kabul debt'})
    post('opening_receivable',{'party':customer.pk,'location':wh.location_id,'amount':'200','reason':'Herat debt'})
    foreign=Business.objects.create(name='Private furniture',slug='register-foreign')
    foreign_location=Location.objects.create(business=foreign,code='F',name='Hidden')
    Membership.objects.create(user=ctx.user,business=foreign,permissions=['*'],all_locations=True)
    assert get(ctx,kind='opening_receivable',location=foreign_location.pk).status_code==400
    ctx.membership.all_locations=False;ctx.membership.location_ids=[wh.location_id];ctx.membership.save()
    scoped=get(ctx,kind='opening_receivable').json()
    assert scoped['count']==1 and scoped['totals']['amount']=='200.00'
    assert get(ctx,kind='opening_receivable',location=other.pk).status_code==403
    ctx.membership.permissions=['inventory.view'];ctx.membership.product_lines=['adhesive'];ctx.membership.save()
    assert get(ctx,kind='stock_opening').json()['count']==0

@pytest.mark.parametrize('params',[{'sort':'data__password'},{'sort':'--id'},{'payment':'secret'},{'from':'2026-02-30'},{'from':'2026-06-02','to':'2026-06-01'},{'limit':'201'},{'offset':'-1'},{'q':'x'*101},{'kind':'missing'}])
def test_register_rejects_invalid_controls(growth_env,params):
    ctx,*_=growth_env
    response=get(ctx,**{'kind':'sale',**params});assert response.status_code==400,response.content
