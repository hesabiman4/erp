from decimal import Decimal
import pytest
from erp.tests.test_api import environment,client_for
from erp.tests.test_growth import growth_env,open_block
from erp.core import Context,balance
from erp.models import Party,Product,Business,Membership,Document,Entry,StockMovement

def test_profile_contacts_groups_and_duplicate_advice_are_isolated_and_nonposting(growth_env):
    ctx,post,wh,sp,raw,customer,supplier=growth_env;c=client_for(ctx.user,ctx.business)
    before=(Document.objects.count(),Entry.objects.count(),StockMovement.objects.count())
    saved=c.patch(f'/api/catalog/parties/{customer.pk}/',{'name':'شركة  علی','phone':'۰۷۰۰ ۱۲۳ ۴۵۶','group_name':'Furniture makers','registration_number':'SYNTHETIC','delivery_address':'Training delivery gate','contacts':[{'name':'Ahmad','role':'Purchasing','phone':'0700111000','email':'training@example.test'}]},content_type='application/json')
    assert saved.status_code==200,saved.content
    assert saved.json()['contacts'][0]['role']=='Purchasing'
    result=c.post('/api/party-tools/duplicates/',{'kind':'customer','name':'شرکة علی','phone':'0700123456'},content_type='application/json').json()
    assert result['count']==1 and 'same_phone' in result['results'][0]['reasons']
    assert not result['automatic_merge']
    assert c.post('/api/party-tools/duplicates/',{'kind':'customer','name':saved.json()['name'],'exclude':customer.pk},content_type='application/json').json()['count']==0
    other=Business.objects.create(name='Hidden',slug='profile-hidden');Party.objects.create(business=other,name='Hidden contact',phone='0700123456',group_name='Secret')
    assert c.get('/api/party-tools/groups/?kind=customer').json()['groups']==['Furniture makers']
    assert 'Hidden' not in str(result)
    profile=c.get(f'/api/reports/customer_statement/?party={customer.pk}').json()['party']
    assert profile['delivery_address']=='Training delivery gate' and profile['contacts'][0]['name']=='Ahmad'
    assert before==(Document.objects.count(),Entry.objects.count(),StockMovement.objects.count())

@pytest.mark.parametrize('contacts',[{},[{'name':''}],[{'name':'A','private':'bad'}],[{'name':'A','phone':12}],[{'name':'A','email':'wrong'}],[{'name':'a'}]*21])
def test_invalid_contacts_fail_without_updating_profile(growth_env,contacts):
    ctx,*rest=growth_env;customer=rest[4];c=client_for(ctx.user,ctx.business)
    r=c.patch(f'/api/catalog/parties/{customer.pk}/',{'name':'Must roll back','contacts':contacts},content_type='application/json')
    assert r.status_code==400,r.content
    customer.refresh_from_db();assert customer.name=='Customer' and customer.contacts==[]

def test_supplier_terms_are_separate_authority_and_freeze_on_bills(growth_env):
    ctx,post,wh,sp,raw,customer,supplier=growth_env;c=client_for(ctx.user,ctx.business)
    ctx.membership.permissions=['purchases.post','purchases.view'];ctx.membership.save()
    assert c.patch(f'/api/catalog/parties/{supplier.pk}/',{'payment_terms_days':30},content_type='application/json').status_code==403
    assert c.patch(f'/api/catalog/parties/{customer.pk}/',{'phone':'0700000123'},content_type='application/json').status_code==403
    ctx.membership.permissions+=['purchases.terms_manage'];ctx.membership.save()
    assert c.patch(f'/api/catalog/parties/{supplier.pk}/',{'payment_terms_days':30},content_type='application/json').status_code==200
    assert c.patch(f'/api/catalog/parties/{supplier.pk}/',{'credit_limit':'100'},content_type='application/json').status_code==400
    ctx.membership.permissions=['*'];ctx.membership.save()
    receipt=post('purchase_receive',{'warehouse':wh.pk,'supplier':supplier.pk,'lines':[{'product':raw.pk,'quantity':'10','unit_cost':'100'}]})
    bill=post('purchase_bill',{'receipt':receipt.pk})
    assert bill.data['due_date']=='2026-07-01' and bill.data['payment_terms_days_snapshot']==30
    supplier.payment_terms_days=7;supplier.save();bill.refresh_from_db();assert bill.data['due_date']=='2026-07-01'
    assert balance(ctx,'AP')==-1000
    assert c.patch(f'/api/catalog/parties/{supplier.pk}/',{'kind':'customer'},content_type='application/json').status_code==400

def test_pricing_explanation_uses_footprint_effective_date_and_posted_snapshot(growth_env):
    ctx,post,wh,sp,raw,customer,supplier=growth_env;c=client_for(ctx.user,ctx.business);block=open_block(post,wh,sp)
    agreement=post('customer_price',{'party':customer.pk,'product':sp.pk,'profile':block.profile,'unit_price':'450','effective_from':'2026-06-01','effective_to':'2026-06-30'})
    hint=c.get('/api/party-tools/pricing/',{'party':customer.pk,'product':sp.pk,'block':block.pk,'date':'2026-06-01','price':'450'}).json()
    assert hint['basis']=='agreement_match' and hint['agreement']['id']==agreement.result['customer_price']
    assert c.get('/api/party-tools/pricing/',{'party':customer.pk,'product':sp.pk,'block':block.pk,'date':'2026-07-01'}).json()['agreement'] is None
    sale=post('sale',{'warehouse':wh.pk,'party':customer.pk,'lines':[{'product':sp.pk,'block':block.pk,'thickness_mm':'10','unit_price':'450'}],'paid':'0'})
    assert sale.result['lines'][0]['price_basis']=='agreement_match' and sale.result['lines'][0]['price_reference']==agreement.result['customer_price']
    assert Decimal(sale.result['lines'][0]['catalog_price_snapshot'])==500
    assert sale.result['customer_snapshot']['delivery_address']==''
    customer.delivery_address='New address';customer.name='Changed later';customer.save();sale.refresh_from_db()
    assert sale.result['customer_snapshot']['name']=='Customer' and sale.result['customer_snapshot']['delivery_address']==''
    ctx.membership.permissions=['sales.view'];ctx.membership.save()
    public=c.get('/api/catalog/parties/').json();assert 'credit_limit' not in next(p for p in public if p['id']==customer.pk)
    assert c.get('/api/party-tools/groups/?kind=supplier').status_code==403
    assert c.get('/api/party-tools/pricing/',{'party':supplier.pk,'product':sp.pk}).status_code==400
