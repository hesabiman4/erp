"""Independent credit exposure and split-tender conservation on PostgreSQL."""
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4
import pytest
from django.core.exceptions import ValidationError,PermissionDenied
from django.db.models import Sum
from erp.tests.test_api import environment,client_for
from erp.tests.test_growth import growth_env,open_block
from erp.tests.test_money_instruments import instrument
from erp.core import Context,execute,balance,outstanding
from erp.models import Document,Entry,StockMovement,AuditEvent,Party,Business,MoneyInstrumentEntry
from erp.credit_management import exposure
from erp.money_instruments import instrument_balance

def invoice(post,wh,sp,block,customer,**extra):return post('sale',{'warehouse':wh.pk,'party':customer.pk,'lines':[{'product':sp.pk,'block':block.pk,'thickness_mm':'100'}],'paid':'0',**extra})

def test_opening_receivable_counts_and_rejected_sale_is_atomic(growth_env):
    ctx,post,wh,sp,raw,customer,*_=growth_env;block=open_block(post,wh,sp)
    post('opening_receivable',{'party':customer.pk,'location':wh.location_id,'amount':'4000','reason':'Reviewed starting debt'})
    customer.credit_limit='8000';customer.save()
    before=(Document.objects.count(),Entry.objects.count(),StockMovement.objects.count())
    with pytest.raises(ValidationError,match='exception'):invoice(post,wh,sp,block,customer)
    block.refresh_from_db();assert block.remaining_height_mm==1000
    assert before==(Document.objects.count(),Entry.objects.count(),StockMovement.objects.count())
    overridden=invoice(post,wh,sp,block,customer,credit_override_reason='Owner approved specific facility')
    assert outstanding(overridden)==5000 and exposure(ctx,customer)['debt']==9000
    assert AuditEvent.objects.filter(action='sales.credit_override',target=str(overridden.pk)).exists()

def test_credit_hold_overdue_terms_and_historical_snapshots(growth_env):
    ctx,post,wh,sp,raw,customer,*_=growth_env;block=open_block(post,wh,sp)
    customer.payment_terms_days=14;customer.credit_hold=True;customer.save()
    with pytest.raises(ValidationError):invoice(post,wh,sp,block,customer)
    cash=invoice(post,wh,sp,block,customer,paid='5000');assert cash.data['due_date']=='2026-06-15'
    customer.credit_hold=False;customer.payment_terms_days=30;customer.save()
    debt=invoice(post,wh,sp,block,customer);assert debt.data['due_date']=='2026-07-01';cash.refresh_from_db();assert cash.data['due_date']=='2026-06-15'
    customer.block_overdue=True;customer.save()
    with pytest.raises(ValidationError):invoice(post,wh,sp,block,customer)
    post('receipt',{'invoice':debt.pk,'location':wh.location_id,'amount':'5000'})
    next_sale=invoice(post,wh,sp,block,customer);assert outstanding(next_sale)==5000


def test_order_credit_reservation_released_on_conversion_and_cancel(growth_env):
    ctx,post,wh,sp,raw,customer,*_=growth_env;block=open_block(post,wh,sp);customer.credit_limit='6000';customer.save()
    ctx.business.settings={**ctx.business.settings,'credit_management':{'reserve_orders':True}};ctx.business.save()
    order=post('sales_order',{'warehouse':wh.pk,'party':customer.pk,'lines':[{'product':sp.pk,'quantity':'10','unit_price':'500'}]})
    assert exposure(ctx,customer)['orders']==5000
    sale=invoice(post,wh,sp,block,customer,order=order.pk)
    assert exposure(ctx,customer)=={'debt':Decimal('5000.00'),'overdue':Decimal('5000.00'),'orders':Decimal('0.00'),'total':Decimal('5000.00')}
    other=post('sales_order',{'warehouse':wh.pk,'party':customer.pk,'lines':[{'product':sp.pk,'quantity':'2','unit_price':'500'}]})
    assert exposure(ctx,customer)['orders']==1000
    post('order_cancel',{'order':other.pk,'reason':'Customer released balance'})
    assert exposure(ctx,customer)['orders']==0 and balance(ctx,'SALES')==-5000


def test_credit_terms_and_cross_business_summary_require_explicit_authority(growth_env):
    ctx,post,wh,sp,raw,customer,*_=growth_env;c=client_for(ctx.user,ctx.business)
    ctx.membership.permissions=['sales.post','sales.view','sales.credit'];ctx.membership.save()
    assert c.patch(f'/api/catalog/parties/{customer.pk}/',{'credit_limit':'100'},content_type='application/json').status_code==403
    assert c.get(f'/api/credit/?party={customer.pk}').status_code==403
    ctx.membership.permissions+=['sales.credit_manage'];ctx.membership.save()
    saved=c.patch(f'/api/catalog/parties/{customer.pk}/',{'credit_limit':'0','payment_terms_days':7},content_type='application/json');assert saved.status_code==200,saved.content
    assert c.get(f'/api/credit/?party={customer.pk}').json()['limit']=='0.00'
    other=Business.objects.create(name='Hidden',slug='credit-hidden');foreign=Party.objects.create(business=other,name='Hidden debt')
    assert c.get(f'/api/credit/?party={foreign.pk}').status_code==400
    assert c.patch(f'/api/catalog/parties/{customer.pk}/',{'credit_limit':'-1'},content_type='application/json').status_code==400


def test_split_tender_exact_accounts_stock_debt_receipt_and_retry(growth_env):
    ctx,post,wh,sp,raw,customer,*_=growth_env;block=open_block(post,wh,sp);cash=instrument(ctx,post,wh,'CASH','TILL');bank=instrument(ctx,post,wh,'BANK','BANK')
    key=str(uuid4());payload={'warehouse':wh.pk,'party':customer.pk,'lines':[{'product':sp.pk,'block':block.pk,'thickness_mm':'100'}],'paid':'3500','payments':[{'account':'CASH','amount':'2000','instrument':cash.pk},{'account':'BANK','amount':'1500','instrument':bank.pk,'reference':'Deposit slip 42'}]}
    sale=post('sale',payload,key);assert sale.amount==5000 and outstanding(sale)==1500
    assert instrument_balance(cash)==2000 and instrument_balance(bank)==1500
    assert balance(ctx,'SALES')==-5000 and balance(ctx,'COGS')==1000
    block.refresh_from_db();assert block.remaining_height_mm==900
    assert post('sale',payload,key).pk==sale.pk;assert instrument_balance(bank)==1500
    receipt=post('receipt',{'invoice':sale.pk,'location':wh.location_id,'amount':'1500','cash_account':'BANK','bank_instrument':bank.pk})
    assert outstanding(sale)==0 and instrument_balance(bank)==3000 and balance(ctx,'SALES')==-5000
    html=client_for(ctx.user,ctx.business).get(f'/api/documents/{sale.pk}/print/').content.decode();assert 'Bank received' in html and 'Cash received' in html


@pytest.mark.parametrize('parts,paid',[
    ([{'account':'CASH','amount':'1.005'}],'1.01'),
    ([{'account':'CASH','amount':'2000'},{'account':'BANK','amount':'1500'}],'4000'),
    ([{'account':'WRONG','amount':'1'}],'1'),
    ([{'account':'CASH','amount':'-1'}],'-1')])
def test_invalid_split_rolls_back_stock_and_journal(growth_env,parts,paid):
    ctx,post,wh,sp,raw,customer,*_=growth_env;block=open_block(post,wh,sp);before=(Document.objects.count(),Entry.objects.count(),StockMovement.objects.count())
    with pytest.raises(ValidationError):invoice(post,wh,sp,block,customer,paid=paid,payments=parts)
    block.refresh_from_db();assert block.remaining_height_mm==1000 and before==(Document.objects.count(),Entry.objects.count(),StockMovement.objects.count())


def test_bank_only_sale_and_foreign_instrument_rejected(growth_env):
    ctx,post,wh,sp,raw,customer,*_=growth_env;block=open_block(post,wh,sp);bank=instrument(ctx,post,wh)
    sale=invoice(post,wh,sp,block,customer,paid='5000',cash_account='BANK',bank_instrument=bank.pk)
    assert instrument_balance(bank)==5000 and balance(ctx,'CASH')==0
    with pytest.raises(ValidationError):invoice(post,wh,sp,block,customer,paid='1',payments=[{'account':'CASH','amount':'1','instrument':bank.pk}])
