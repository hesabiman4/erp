from datetime import date
from decimal import Decimal
from uuid import uuid4
import pytest
from django.core.exceptions import ValidationError,PermissionDenied
from django.db import DatabaseError,transaction
from erp.tests.test_api import environment,client_for
from erp.models import *
from erp.core import Context,execute,outstanding,balance
from erp.foreign import exposure_balance,wallet_balance,reconcile
from erp.reports import report

@pytest.fixture
def fx_env(environment):
 user,business,member,loc,warehouse,product=environment
 ctx=Context(user,business);customer=Party.objects.create(business=business,kind='customer',name='USD customer');supplier=Party.objects.create(business=business,kind='supplier',name='USD supplier')
 def post(action,payload,key=None):return execute(ctx,action,{'date':'2026-06-01',**payload},key or str(uuid4()))
 def fx(payload):return {'rate':'70','rate_reference':'Approved saraf quote',**payload}
 return ctx,post,fx,loc,warehouse,customer,supplier

def test_customer_foreign_revaluation_partial_settlements_and_historical_aging(fx_env):
 ctx,post,fx,loc,wh,customer,supplier=fx_env
 invoice=post('opening_receivable',{'location':loc.id,'party':customer.id,'amount':'7000','reason':'Foreign opening invoice'})
 registered=post('fx_register',fx({'invoice':invoice.id,'foreign_currency':'USD','foreign_amount':'100'}));exposure=ForeignExposure.objects.get(pk=registered.result['exposure'])
 assert outstanding(invoice)==7000
 with pytest.raises(ValidationError):post('receipt',{'location':loc.id,'invoice':invoice.id,'amount':'100'})
 with pytest.raises(ValidationError):post('fx_settle',fx({'exposure':exposure.id,'foreign_amount':'101'}))
 post('fx_revalue',fx({'date':'2026-06-30','target_type':'invoice','target':exposure.id,'rate':'72'}))
 assert outstanding(invoice)==7200
 before=report(ctx,'receivables',{'to':'2026-06-01'});after=report(ctx,'receivables',{'to':'2026-06-30'})
 assert Decimal(before['totals']['outstanding'])==7000 and Decimal(after['totals']['outstanding'])==7200
 paid=post('fx_settle',fx({'date':'2026-07-01','exposure':exposure.id,'foreign_amount':'40','rate':'73','location':loc.id}))
 assert Decimal(paid.result['functional_cash'])==2920 and Decimal(paid.result['carrying_released'])==2880 and Decimal(paid.result['exchange_gain'])==40
 assert outstanding(invoice)==4320 and exposure_balance(exposure)[0]==60
 post('fx_settle',fx({'date':'2026-07-02','exposure':exposure.id,'foreign_amount':'60','rate':'71','location':loc.id}))
 assert outstanding(invoice)==0 and balance(ctx,'AR',party=customer)==0
 assert balance(ctx,'FX_GAIN')==-240 and balance(ctx,'FX_LOSS')==60
 assert Allocation.objects.filter(invoice=invoice).aggregate(v=__import__('django.db.models',fromlist=['Sum']).Sum('amount'))['v']==7000
 assert report(ctx,'balance_sheet',{})['totals']['difference']=='0.00'
 assert report(ctx,'cash_flow',{})['totals']['difference']=='0.00'
 with pytest.raises(DatabaseError),transaction.atomic():ForeignMovement.objects.filter(exposure=exposure).update(base_value=0)

def test_wallet_exchanges_revaluation_and_remittance_conserve_functional_value(fx_env):
 ctx,post,fx,loc,wh,customer,supplier=fx_env
 wallet_doc=post('fx_wallet',{'name':'Herat USD','location':loc.id,'foreign_currency':'USD','kind':'cash'});wallet=ForeignWallet.objects.get(pk=wallet_doc.result['wallet'])
 post('fx_opening',fx({'wallet':wallet.id,'foreign_amount':'100','reason':'Verified USD cash count'}))
 post('fx_exchange',fx({'wallet':wallet.id,'foreign_amount':'50','direction':'sell','rate':'72','fee':'10'}))
 assert wallet_balance(wallet)==(Decimal(50),Decimal(3500))
 assert reconcile(ctx)['difference']=='0.00'
 post('fx_revalue',fx({'date':'2026-06-30','target_type':'wallet','target':wallet.id,'rate':'71'}))
 assert wallet_balance(wallet)==(Decimal(50),Decimal(3550))
 kabul=Location.objects.create(business=ctx.business,name='Kabul',code='K');target_doc=post('fx_wallet',{'name':'Kabul USD bank','location':kabul.id,'foreign_currency':'USD','kind':'bank'});target=ForeignWallet.objects.get(pk=target_doc.result['wallet'])
 transfer=post('fx_remit_dispatch',{'date':'2026-07-01','source_wallet':wallet.id,'destination_wallet':target.id,'foreign_amount':'20','reference':'Saraf reference 55','fee':'5'})
 assert wallet_balance(wallet)==(Decimal(30),Decimal(2130)) and wallet_balance(target)==(Decimal(0),Decimal(0))
 assert reconcile(ctx)['difference']=='0.00'
 post('fx_revalue',fx({'date':'2026-07-02','target_type':'remittance','target':transfer.result['remittance'],'rate':'73'}))
 post('fx_remit_receive',{'date':'2026-07-03','remittance':transfer.result['remittance']})
 assert wallet_balance(target)==(Decimal(20),Decimal(1460))
 assert reconcile(ctx)['difference']=='0.00'
 with pytest.raises(ValidationError):post('fx_remit_receive',{'date':'2026-07-03','remittance':transfer.result['remittance']})
 assert balance(ctx,'SALES')==0 and balance(ctx,'FX_TRANSIT')==0
 cash=report(ctx,'cash_flow',{})['totals'];assert cash['difference']=='0.00';assert Decimal(cash['exchange_effect'])==190 and Decimal(cash['operating'])==-15
 assert report(ctx,'balance_sheet',{})['totals']['difference']=='0.00'

def test_supplier_foreign_settlement_and_currency_scope(fx_env):
 ctx,post,fx,loc,wh,customer,supplier=fx_env
 invoice=post('opening_payable',{'location':loc.id,'party':supplier.id,'amount':'7000','reason':'Verified USD payable'})
 registered=post('fx_register',fx({'invoice':invoice.id,'foreign_currency':'USD','foreign_amount':'100'}))
 result=post('fx_settle',fx({'exposure':registered.result['exposure'],'foreign_amount':'100','rate':'72'}))
 assert Decimal(result.result['exchange_gain'])==-200 and outstanding(invoice)==0 and balance(ctx,'AP',party=supplier)==0
 with pytest.raises(ValidationError):post('fx_register',fx({'invoice':invoice.id,'foreign_currency':'EUR','foreign_amount':'100'}))
 ctx.membership.permissions=['sales.view'];ctx.membership.save()
 client=client_for(ctx.user,ctx.business);assert client.get('/api/growth/fx_wallets/').status_code==403
 with pytest.raises(PermissionDenied):post('fx_rate',{'foreign_currency':'USD','rate':'70','reference':'Unauthorized quote'})

def test_exchange_rate_snapshot_and_unmatched_invoice_rejected(fx_env):
 ctx,post,fx,loc,wh,customer,*_=fx_env
 quote=post('fx_rate',{'foreign_currency':'PKR','rate':'0.25','reference':'Approved source'})
 invoice=post('opening_receivable',{'location':loc.id,'party':customer.id,'amount':'250','reason':'Verified balance'})
 with pytest.raises(ValidationError):post('fx_register',{'invoice':invoice.id,'foreign_currency':'PKR','foreign_amount':'999','rate_record':quote.result['rate_record']})
 assert not ForeignExposure.objects.exists()
 post('fx_register',{'invoice':invoice.id,'foreign_currency':'PKR','foreign_amount':'1000','rate_record':quote.result['rate_record']})
 with pytest.raises(DatabaseError),transaction.atomic():ExchangeRate.objects.filter(pk=quote.result['rate_record']).update(rate=999)

def test_foreign_settlement_approval_covers_carrying_value_not_only_cash(fx_env):
 ctx,post,fx,loc,wh,customer,*_=fx_env
 invoice=post('opening_receivable',{'location':loc.id,'party':customer.id,'amount':'7000','reason':'Verified opening'})
 registered=post('fx_register',fx({'invoice':invoice.id,'foreign_currency':'USD','foreign_amount':'100'}))
 ctx.membership.permissions=['finance.fx','finance.fx_rate','sales.collect'];ctx.membership.approval_limit=5000;ctx.membership.save()
 with pytest.raises(PermissionDenied):post('fx_settle',fx({'exposure':registered.result['exposure'],'foreign_amount':'100','rate':'30'}))
 assert outstanding(invoice)==7000 and not ForeignMovement.objects.exists()
