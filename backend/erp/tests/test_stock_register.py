from decimal import Decimal
from erp.tests.test_api import environment,client_for
from erp.tests.test_growth import growth_env,open_block
from erp.models import Product,Warehouse,Location,Document,Entry,StockMovement

def test_stock_register_has_global_exact_totals_with_grouped_units_and_page_sort(growth_env):
    ctx,post,wh,sp,raw,*_=growth_env
    products=Product.objects.bulk_create([Product(business=ctx.business,code=f'AD-{i:03}',name=f'Adhesive {i:03}',kind='finished',unit='kg',line='adhesive') for i in range(1,106)])
    post('stock_opening',{'warehouse':wh.pk,'lines':[{'product':p.pk,'quantity':str(i),'value':str(i)} for i,p in enumerate(products,1)]})
    open_block(post,wh,sp,height='100')
    client=client_for(ctx.user,ctx.business);before=(Document.objects.count(),Entry.objects.count(),StockMovement.objects.count())
    result=client.get('/api/stock-register/',{'limit':'5','sort':'-quantity'}).json()
    assert result['count']==106 and result['next_offset']==5 and result['totals']['value']=='15565.000000'
    assert [Decimal(r['quantity']) for r in result['results']]==[105,104,103,102,101]
    assert len(result['quantities'])==106
    cm=[r for r in result['quantities'] if r['product__unit']=='cm'];assert len(cm)==1 and Decimal(cm[0]['quantity'])==10
    second=client.get('/api/stock-register/',{'limit':'5','offset':'5','sort':'-quantity'}).json()
    assert Decimal(second['results'][0]['quantity'])==100 and second['totals']==result['totals']
    found=client.get('/api/stock-register/',{'q':'AD-105'}).json();assert found['count']==1 and found['totals']['value']=='105.000000'
    assert before==(Document.objects.count(),Entry.objects.count(),StockMovement.objects.count())

def test_stock_register_never_leaks_restricted_raw_cost_or_location(growth_env):
    ctx,post,wh,sp,raw,*_=growth_env
    post('stock_opening',{'warehouse':wh.pk,'lines':[{'product':raw.pk,'quantity':'7','value':'4567'}]})
    open_block(post,wh,sp,height='100')
    otherloc=Location.objects.create(business=ctx.business,code='K',name='Kabul')
    other=Warehouse.objects.create(business=ctx.business,location=otherloc,name='Hidden stock')
    open_block(post,other,sp,height='200')
    ctx.membership.permissions=['inventory.view'];ctx.membership.all_locations=False;ctx.membership.location_ids=[wh.location_id];ctx.membership.save()
    client=client_for(ctx.user,ctx.business)
    result=client.get('/api/stock-register/').json()
    assert result['count']==1 and result['totals']['value'] is None
    assert 'value' not in result['results'][0] and 'average_cost' not in result['results'][0]
    assert '4567' not in str(result) and 'Hidden stock' not in str(result)
    assert client.get('/api/stock-register/',{'sort':'value'}).status_code==403
    assert client.get('/api/stock-register/',{'warehouse':other.pk}).status_code==403
    assert client.get('/api/stock-register/',{'sort':'--id'}).status_code==400
    assert client.get('/api/stock-register/',{'availability':'fake'}).status_code==400
    assert client.get('/api/stock-register/',{'limit':1000}).status_code==400
