from decimal import Decimal
from uuid import uuid4
import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError,PermissionDenied
from django.db import transaction,DatabaseError
from erp.tests.test_growth import growth_env,open_block
from erp.tests.test_api import environment,client_for
from erp.models import *
from erp.core import execute
from erp.excellence import checks,profitability,TASKS
from erp.customer_notices import send_notices


def test_closing_attestations_invalidate_on_backdated_financial_event_and_gate_close(growth_env):
    ctx,post,wh,sp,raw,customer,supplier=growth_env
    cycle_doc=post('closing_open',{'starts':'2026-05-01','ends':'2026-05-31'})
    cycle=ClosingCycle.objects.get(pk=cycle_doc.result['cycle'])
    for task in TASKS:post('closing_review',{'cycle':cycle.id,'task':task,'accepted':True,'note':'Reviewed source balances; no unresolved exceptions.'})
    assert checks(ctx,cycle)['ready']
    post('stock_opening',{'date':'2026-05-31','warehouse':wh.id,'lines':[{'product':raw.id,'quantity':'10','value':'100'}]})
    assert not checks(ctx,cycle)['ready'] and all(r['stale'] for r in checks(ctx,cycle)['tasks'])
    with pytest.raises(ValidationError):post('period_close',{'through_date':'2026-05-31'})
    with pytest.raises(ValidationError):post('period_close',{'through_date':'2026-05-15'})
    with pytest.raises(ValidationError):post('closing_finish',{'cycle':cycle.id})
    for task in TASKS:post('closing_review',{'cycle':cycle.id,'task':task,'accepted':True,'note':'Re-reviewed after final opening correction.'})
    result=post('closing_finish',{'cycle':cycle.id})
    ctx.business.refresh_from_db();assert str(ctx.business.closed_through)=='2026-05-31'
    assert not Entry.objects.filter(document=result).exists()
    assert result.result['period_document']


def test_closing_evidence_assignee_and_partial_scope(growth_env):
    ctx,post,wh,*_=growth_env
    cycle=post('closing_open',{'starts':'2026-05-01','ends':'2026-05-31'}).result['cycle']
    count=post('cash_count',{'date':'2026-05-31','location':wh.location_id,'counted':'10'})
    with pytest.raises(ValidationError):post('closing_review',{'cycle':cycle,'task':'cash','accepted':True,'evidence':count.id,'note':'Unexplained variance.'})
    user=get_user_model().objects.create_user(username='reviewer');assigned=Membership.objects.create(business=ctx.business,user=user,permissions=['*'],all_locations=True,product_lines=['sponge','adhesive','shared'])
    with pytest.raises(PermissionDenied):post('closing_review',{'cycle':cycle,'task':'cash','assignee':assigned.id,'accepted':True,'note':'Cannot attest for a different person.'})
    ctx.membership.permissions=['accounting.view','cost.view','finance.view'];ctx.membership.save()
    assert client_for(ctx.user,ctx.business).get('/api/excellence/closing/').status_code==403


def test_profitability_reconciles_returns_and_unallocated_shared_costs(growth_env):
    ctx,post,wh,sp,raw,customer,supplier=growth_env
    block=open_block(post,wh,sp)
    sale=post('sale',{'warehouse':wh.id,'party':customer.id,'lines':[{'product':sp.id,'block':block.id,'thickness_mm':'100','sheet_count':'2','unit_price':'200'}]})
    post('sales_return',{'invoice':sale.id,'warehouse':wh.id,'lines':[{'index':0,'sheet_count':'1'}]})
    post('expense_post',{'location':wh.location_id,'supplier':supplier.id,'expense_account':'REPAIRS','line':'shared','amount':'100'})
    from erp.reports import profit_loss
    for group in ['customer','branch','product','order','project']:
        report=profitability(ctx,{'group':group,'to':'2026-06-01'})
        expected=profit_loss(ctx,{'to':'2026-06-01'})['totals']
        assert report['totals']['profit']==Decimal(expected['profit'])==Decimal('900')
        assert sum(r['profit'] for r in report['rows'])==Decimal('900')
    products=profitability(ctx,{'group':'product','to':'2026-06-01'})['rows']
    assert next(r for r in products if r['id'].startswith('p-'))['revenue']==2000
    assert next(r for r in products if r['id']=='unattributed')['other_expenses_net']==100


def portal_setup(ctx,post,sp,customer):
    user=get_user_model().objects.create_user(username='request-customer')
    grant=PortalGrant.objects.create(business=ctx.business,user=user,party=customer)
    listing=post('portal_listing',{'grant':grant.id,'product':sp.id,'profile':'2000x1000'})
    return client_for(user,ctx.business),grant,listing.result['listing']


def test_portal_requests_are_idempotent_nonfinancial_and_review_into_real_order(growth_env):
    ctx,post,wh,sp,raw,customer,*_=growth_env
    portal,grant,listing=portal_setup(ctx,post,sp,customer)
    payload={'kind':'order','lines':[{'listing':listing,'thickness_mm':'22','sheet_count':'3'}],'note':'Please prepare these sheets.'}
    count=Document.objects.count();entries=Entry.objects.count()
    first=portal.post('/api/portal-requests/',payload,content_type='application/json',HTTP_IDEMPOTENCY_KEY='portal-test')
    assert first.status_code==201,first.content
    duplicate=portal.post('/api/portal-requests/',payload,content_type='application/json',HTTP_IDEMPOTENCY_KEY='portal-test')
    assert duplicate.status_code==200 and duplicate.json()['id']==first.json()['id']
    assert Document.objects.count()==count and Entry.objects.count()==entries
    assert portal.post('/api/operations/sale/',{},content_type='application/json',HTTP_IDEMPOTENCY_KEY='forbidden').status_code==403
    result=post('portal_review',{'submission':first.json()['id'],'outcome':'accepted','warehouse':wh.id,'reason':'Confirmed quantity and current rate.','lines':[{'unit_price':'0'}]})
    order=Document.objects.get(pk=result.result['commercial_document'])
    assert order.kind=='sales_order' and order.result['lines'][0]['quantity']=='6.6' and order.party_id==customer.id
    assert not Entry.objects.filter(document=order).exists() and not StockMovement.objects.filter(document=order).exists()
    with pytest.raises(ValidationError):post('portal_review',{'submission':first.json()['id'],'outcome':'accepted','warehouse':wh.id,'reason':'Duplicate approval.','lines':[{'unit_price':'0'}]})
    assert portal.get('/api/portal-requests/').json()['results'][0]['state']=='accepted'


def test_portal_catalog_tenant_scope_changed_payload_and_revocation(growth_env):
    ctx,post,wh,sp,raw,customer,*_=growth_env
    portal,grant,listing=portal_setup(ctx,post,sp,customer)
    bad=portal.post('/api/portal-requests/',{'kind':'order','lines':[{'listing':listing+100,'thickness_mm':'22'}]},content_type='application/json',HTTP_IDEMPOTENCY_KEY='no-other-item')
    assert bad.status_code==403
    data={'kind':'quotation','lines':[{'listing':listing,'thickness_mm':'22'}]}
    assert portal.post('/api/portal-requests/',data,content_type='application/json',HTTP_IDEMPOTENCY_KEY='reuse').status_code==201
    data['note']='Changed request';assert portal.post('/api/portal-requests/',data,content_type='application/json',HTTP_IDEMPOTENCY_KEY='reuse').status_code==400
    post('portal_listing',{'grant':grant.id,'product':sp.id,'profile':'2000x1000','active':False})
    assert portal.get('/api/portal-requests/').json()['listings']==[]
    grant.active=False;grant.save();assert portal.get('/api/portal-requests/').status_code==403


def test_portal_submission_history_and_cross_business_foreign_keys_are_guarded(growth_env):
    ctx,post,wh,sp,raw,customer,*_=growth_env
    portal,grant,listing=portal_setup(ctx,post,sp,customer)
    response=portal.post('/api/portal-requests/',{'kind':'quotation','lines':[{'listing':listing,'thickness_mm':'22'}]},content_type='application/json',HTTP_IDEMPOTENCY_KEY='immutable')
    with pytest.raises(DatabaseError),transaction.atomic():PortalSubmission.objects.filter(pk=response.json()['id']).update(payload={})
    other=Business.objects.create(name='Other',slug='other-request')
    with pytest.raises(DatabaseError),transaction.atomic():PortalListing.objects.create(business=other,grant=grant,product=sp,profile='2000x1000',source=Document.objects.filter(business=ctx.business).first())


def test_customer_notices_require_consent_block_missing_provider_and_preserve_delivery_evidence(growth_env,monkeypatch):
    ctx,post,wh,sp,raw,customer,*_=growth_env
    order=post('sales_order',{'warehouse':wh.id,'party':customer.id,'lines':[{'product':sp.id,'quantity':'10'}]})
    p={'document':order.id,'template':'order_received','channel':'sms','language':'ps-AF','recipient':'+93700000000'}
    with pytest.raises(ValidationError):post('notice_prepare',p)
    original=post('notice_prepare',{**p,'consent_confirmed':True});ident=original.result['notice']
    with pytest.raises(ValidationError):post('notice_prepare',{**p,'consent_confirmed':True})
    monkeypatch.delenv('ERP_MESSAGE_PROVIDER_URL',raising=False);monkeypatch.delenv('ERP_MESSAGE_PROVIDER_TOKEN',raising=False)
    assert send_notices()[0]['state']=='blocked'
    item=CustomerNotice.objects.get(pk=ident);assert item.attempts==0
    post('notice_retry',{'notice':ident,'provider_checked':True,'consent_confirmed':True,'reason':'Reviewed configuration; provider has no accepted message.'})
    class Reply:
        status=202
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,*args):return b'{"message_id":"synthetic-reference"}'
    monkeypatch.setenv('ERP_MESSAGE_PROVIDER_URL','https://messages.example.invalid/send');monkeypatch.setenv('ERP_MESSAGE_PROVIDER_TOKEN','synthetic')
    monkeypatch.setattr('erp.customer_notices.urllib.request.urlopen',lambda *a,**k:Reply())
    assert send_notices()[0]=={'notice':ident,'state':'accepted','delivered':False}
    with pytest.raises(ValidationError):post('notice_status',{'notice':ident,'state':'delivered','provider_reference':'wrong','evidence':'Wrong provider reference.'})
    receipt=post('notice_status',{'notice':ident,'state':'delivered','provider_reference':'synthetic-reference','evidence':'Operator inspected synthetic provider delivery report.'})
    item.refresh_from_db();assert item.state=='delivered' and not Entry.objects.filter(document=receipt).exists()
    assert 'callback' in receipt.result['confirmation_method']


def test_revoked_notice_sender_and_cancelled_order_do_not_send(growth_env,monkeypatch):
    ctx,post,wh,sp,raw,customer,*_=growth_env
    order=post('sales_order',{'warehouse':wh.id,'party':customer.id,'lines':[{'product':sp.id,'quantity':'10'}]})
    post('notice_prepare',{'document':order.id,'template':'order_received','channel':'sms','consent_confirmed':True,'recipient':'+93700000000'})
    post('order_cancel',{'order':order.id,'reason':'Customer cancelled.'})
    def forbidden(*a,**k):raise AssertionError('No external provider call is authorized for this cancelled order.')
    monkeypatch.setattr('erp.customer_notices.urllib.request.urlopen',forbidden)
    assert send_notices()[0]['state']=='blocked'


def test_blocked_notice_cannot_retry_after_replacement_and_project_requires_permission(growth_env,monkeypatch):
    ctx,post,wh,sp,raw,customer,*_=growth_env
    order=post('sales_order',{'warehouse':wh.id,'party':customer.id,'lines':[{'product':sp.id,'quantity':'10'}]})
    payload={'document':order.id,'template':'order_received','channel':'sms','consent_confirmed':True,'recipient':'+93700000000'}
    first=post('notice_prepare',payload)
    monkeypatch.delenv('ERP_MESSAGE_PROVIDER_URL',raising=False);monkeypatch.delenv('ERP_MESSAGE_PROVIDER_TOKEN',raising=False)
    send_notices()
    post('notice_prepare',payload)
    with pytest.raises(ValidationError):post('notice_retry',{'notice':first.result['notice'],'provider_checked':True,'consent_confirmed':True,'reason':'Old attempt must not duplicate new queued notice.'})
    ctx.membership.permissions=['accounting.view','cost.view'];ctx.membership.save()
    with pytest.raises(PermissionDenied):profitability(ctx,{'group':'project'})


def test_notice_generic_documents_keep_original_product_scope(growth_env):
    ctx,post,wh,sp,raw,customer,*_=growth_env
    adhesive=Product.objects.create(business=ctx.business,code='NOTICE-ADH',name='Restricted adhesive',kind='finished',line='adhesive',unit='kg',price='10')
    order=post('sales_order',{'warehouse':wh.id,'party':customer.id,'lines':[{'product':adhesive.id,'quantity':'10'}]})
    prepared=post('notice_prepare',{'document':order.id,'template':'order_received','channel':'manual'})
    ctx.membership.permissions=['messaging.send','documents.view'];ctx.membership.product_lines=['sponge','shared'];ctx.membership.save()
    client=client_for(ctx.user,ctx.business)
    assert client.get(f'/api/documents/{prepared.id}/').status_code==403
    assert client.get(f'/api/documents/{prepared.id}/print/').status_code==403
    assert client.get('/api/excellence/notices/').json()['results']==[]


def test_disabled_authorizing_user_cannot_send_queued_notice(growth_env,monkeypatch):
    ctx,post,wh,sp,raw,customer,*_=growth_env
    order=post('sales_order',{'warehouse':wh.id,'party':customer.id,'lines':[{'product':sp.id,'quantity':'1'}]})
    post('notice_prepare',{'document':order.id,'template':'order_received','channel':'sms','consent_confirmed':True,'recipient':'+93700000000'})
    ctx.user.is_active=False;ctx.user.save(update_fields=['is_active'])
    monkeypatch.setattr('erp.customer_notices.urllib.request.urlopen',lambda *a,**k:pytest.fail('Disabled sender must not contact a provider.'))
    assert send_notices()[0]['state']=='blocked'


def test_product_profitability_respects_selected_line_on_mixed_invoice(growth_env):
    ctx,post,wh,sp,raw,customer,*_=growth_env
    adhesive=Product.objects.create(business=ctx.business,code='MARGIN-ADH',name='Adhesive',kind='finished',line='adhesive',unit='kg',price='200')
    piece=Product.objects.create(business=ctx.business,code='MARGIN-SP',name='Sponge item',kind='finished',line='sponge',unit='each',price='100')
    post('stock_opening',{'warehouse':wh.id,'lines':[{'product':adhesive.id,'quantity':'10','value':'1000'},{'product':piece.id,'quantity':'10','value':'500'}]})
    post('sale',{'warehouse':wh.id,'party':customer.id,'lines':[{'product':piece.id,'quantity':'1'},{'product':adhesive.id,'quantity':'1'}]})
    result=profitability(ctx,{'group':'product','line':'sponge'})
    assert result['totals']['revenue']==100 and result['totals']['profit']==50
    assert len(result['rows'])==1 and result['rows'][0]['label']=='Sponge item' and result['rows'][0]['profit']==50
