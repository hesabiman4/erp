from datetime import date
from decimal import Decimal
from uuid import uuid4
import pytest
from django.core.exceptions import PermissionDenied,ValidationError
from django.db import DatabaseError,transaction
from erp.tests.test_growth import growth_env
from erp.tests.test_api import environment,client_for
from erp.core import Context,execute
from erp.models import Business,Location,Warehouse,Product,Party,Document,Entry,StockMovement
from erp.sourcing_models import SourcingRequest,SupplierOffer,SourcingAward
from erp.sourcing_api import comparison


def request(post,wh,product,**extra):
    return post('rfq_create',{'warehouse':wh.id,'desired_date':'2026-06-03','lines':[{'product':product.id,'quantity':'10'}],**extra})


def offer(post,rfq,supplier,reference='QUOTE-1',price='10',**extra):
    return post('rfq_offer',{'request':rfq.result['request'],'supplier':supplier.id,'reference':reference,'valid_through':'2026-06-10','lead_days':'2','payment_terms':'Payment after receipt; 15 calendar days','freight_estimate':'20','lines':[{'index':0,'unit_cost':price}],**extra})


def test_comparison_shows_original_prices_freight_terms_and_lead_time_then_awards_once(growth_env):
    ctx,post,wh,sp,raw,customer,supplier=growth_env
    rfq=request(post,wh,raw);a=offer(post,rfq,supplier)
    other=Party.objects.create(business=ctx.business,name='Other supplier',kind='supplier')
    b=offer(post,rfq,other,reference='COMPETING',price='11',freight_estimate='0',lead_days='5')
    result=comparison(ctx,SourcingRequest.objects.get(pk=rfq.result['request']),date(2026,6,1))
    assert [r['id'] for r in result['rows']]==[b.result['offer'],a.result['offer']]
    assert result['rows'][0]['comparison_total']==110 and not result['rows'][0]['meets_desired_date']
    assert result['rows'][1]['comparison_total']==120 and result['rows'][1]['meets_desired_date']
    assert result['rows'][0]['payment_terms']=='Payment after receipt; 15 calendar days'
    before=Entry.objects.count(),StockMovement.objects.count()
    payload={'offer':a.result['offer'],'reason':'Reviewed: choose the faster supplier to meet the production receipt date.'}
    awarded=post('rfq_award',payload,'rfq-award-once')
    order=Document.objects.get(pk=awarded.result['purchase_order'])
    assert order.kind=='purchase_order' and order.amount==100 and order.party_id==supplier.id
    assert order.result['lines'][0]['quantity']=='10' and order.result['lines'][0]['unit_cost']=='10'
    assert 'estimated_freight' not in order.data and order.data['expected_date']=='2026-06-03'
    assert awarded.result['freight_estimate']=='20.00'
    assert before==(Entry.objects.count(),StockMovement.objects.count())
    assert post('rfq_award',payload,'rfq-award-once').id==awarded.id
    with pytest.raises(ValidationError):post('rfq_award',payload)
    assert SourcingAward.objects.filter(request_id=rfq.result['request']).count()==1
    with pytest.raises(ValidationError):offer(post,rfq,other,reference='AFTER-AWARD')


def test_sponge_request_uses_actual_footprint_and_cm_without_label_weight_conversion(growth_env):
    ctx,post,wh,sp,raw,customer,supplier=growth_env
    rfq=request(post,wh,sp,lines=[{'product':sp.id,'quantity':'6.6','length_mm':'2000','width_mm':'1000'}])
    assert rfq.result['lines'][0]['quantity']=='6.6' and rfq.result['lines'][0]['unit']=='cm'
    assert rfq.result['lines'][0]['profile']=='2000.000x1000.000'
    quoted=offer(post,rfq,supplier,price='500',freight_estimate='0')
    assert quoted.result['merchandise_total']=='3300.00'
    awarded=post('rfq_award',{'offer':quoted.result['offer'],'reason':'Reviewed compatible full-face order.'})
    order=Document.objects.get(pk=awarded.result['purchase_order'])
    assert order.result['lines'][0]['quantity']=='6.6' and order.result['lines'][0]['profile']=='2000.000x1000.000'
    with pytest.raises(ValidationError):request(post,wh,sp)


def test_expired_offer_partial_prices_foreign_currency_and_missing_reason_reject(growth_env):
    ctx,post,wh,sp,raw,customer,supplier=growth_env
    rfq=request(post,wh,raw)
    with pytest.raises(ValidationError):offer(post,rfq,supplier,lines=[])
    with pytest.raises(ValidationError):offer(post,rfq,supplier,offer_currency='USD')
    with pytest.raises(ValidationError):offer(post,rfq,supplier,price='-1')
    quoted=offer(post,rfq,supplier,valid_through='2026-06-02')
    count=Document.objects.count()
    with pytest.raises(ValidationError):post('rfq_award',{'date':'2026-06-03','offer':quoted.result['offer'],'reason':'The expired price cannot be awarded.'})
    with pytest.raises(ValidationError):post('rfq_award',{'offer':quoted.result['offer'],'reason':''})
    assert Document.objects.count()==count and not SourcingAward.objects.exists()


def test_cancellation_preserves_supplier_offers_and_blocks_further_conversion(growth_env):
    ctx,post,wh,sp,raw,customer,supplier=growth_env
    rfq=request(post,wh,raw);quoted=offer(post,rfq,supplier)
    closed=post('rfq_close',{'request':rfq.result['request'],'reason':'Purchase is no longer required; preserve original evidence.'})
    request_record=SourcingRequest.objects.get(pk=rfq.result['request'])
    assert request_record.state=='cancelled' and request_record.closed_by_id==closed.id
    assert SupplierOffer.objects.filter(request=request_record).count()==1
    with pytest.raises(ValidationError):post('rfq_award',{'offer':quoted.result['offer'],'reason':'Closed request cannot be ordered.'})
    with pytest.raises(ValidationError):offer(post,rfq,supplier,reference='AFTER-CLOSE')
    assert comparison(ctx,request_record,date(2026,6,1))['rows'][0]['id']==quoted.result['offer']


def test_cost_scope_and_raw_material_scope_apply_to_direct_documents_print_and_comparison(growth_env):
    ctx,post,wh,sp,raw,customer,supplier=growth_env
    rfq=request(post,wh,raw);quoted=offer(post,rfq,supplier)
    awarded=post('rfq_award',{'offer':quoted.result['offer'],'reason':'Reviewed source scope remains on generated purchase order.'})
    client=client_for(ctx.user,ctx.business)
    ctx.membership.permissions=['purchases.view','inventory.raw'];ctx.membership.save()
    assert client.get('/api/sourcing/requests/').status_code==200
    assert client.get('/api/sourcing/comparison/',{'request':rfq.result['request']}).status_code==403
    assert client.get(f'/api/documents/{quoted.id}/').status_code==403
    assert client.get(f'/api/documents/{quoted.id}/print/').status_code==403
    ctx.membership.permissions=['purchases.view','cost.view'];ctx.membership.save()
    assert client.get(f'/api/documents/{awarded.result["purchase_order"]}/').status_code==403
    assert client.get(f'/api/documents/{awarded.result["purchase_order"]}/print/').status_code==403
    assert client.get('/api/sourcing/requests/').json()['results']==[]
    assert client.get(f'/api/documents/{rfq.id}/').status_code==403
    assert client.get(f'/api/documents/{quoted.id}/print/').status_code==403


def test_cross_business_location_and_line_references_fail_without_partial_result_leaks(growth_env):
    ctx,post,wh,sp,raw,customer,supplier=growth_env
    other=Business.objects.create(name='Other business',slug='private-sourcing')
    loc=Location.objects.create(business=other,code='O',name='Other location')
    foreign_wh=Warehouse.objects.create(business=other,location=loc,name='Other warehouse')
    with pytest.raises(ValidationError):request(post,foreign_wh,raw)
    adhesive=Product.objects.create(business=ctx.business,code='SOURCING-ADH',name='Adhesive',unit='kg',kind='finished',line='adhesive')
    rfq=request(post,wh,raw,lines=[{'product':raw.id,'quantity':'10'},{'product':adhesive.id,'quantity':'5'}])
    ctx.membership.product_lines=['sponge'];ctx.membership.permissions=['purchases.view','cost.view','inventory.raw'];ctx.membership.save()
    client=client_for(ctx.user,ctx.business)
    assert client.get('/api/sourcing/requests/').json()['results']==[]
    assert client.get(f'/api/documents/{rfq.id}/').status_code==403
    ctx.membership.all_locations=False;ctx.membership.location_ids=[];ctx.membership.save()
    assert client.get('/api/sourcing/requests/').json()['results']==[]


def test_offer_and_request_history_are_immutable_and_tenant_guarded(growth_env):
    ctx,post,wh,sp,raw,customer,supplier=growth_env
    rfq=request(post,wh,raw);quoted=offer(post,rfq,supplier)
    with pytest.raises(DatabaseError),transaction.atomic():SupplierOffer.objects.filter(pk=quoted.result['offer']).update(merchandise_total='1')
    with pytest.raises(DatabaseError),transaction.atomic():SourcingRequest.objects.filter(pk=rfq.result['request']).update(lines=[])
    other=Business.objects.create(name='Wrong business',slug='wrong-offer')
    with pytest.raises(DatabaseError),transaction.atomic():SupplierOffer.objects.create(business=other,request_id=rfq.result['request'],supplier=supplier,reference='CROSS',valid_through=date(2026,6,10),lead_days=1,payment_terms='cash',lines=[],freight_estimate='0',merchandise_total='1',comparison_total='1',source=quoted)
