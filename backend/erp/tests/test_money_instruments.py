from decimal import Decimal
from uuid import uuid4
import pytest
from django.core.exceptions import PermissionDenied,ValidationError
from django.db import DatabaseError,transaction
from django.contrib.auth import get_user_model
from erp.tests.test_api import environment,client_for
from erp.tests.test_growth import growth_env,open_block
from erp.tests.test_statement_imports import imported
from erp.tests.test_foreign import fx_env
from erp.models import *
from erp.core import Context,execute,balance
from erp.money_instruments import legacy_for,instrument_balance,entries_for


def instrument(ctx,post,wh,kind='BANK',code='BANK-A'):
    payload={'location':wh.location_id,'kind':kind,'code':code,'name':code}
    if kind=='BANK':payload.update(institution='Synthetic bank',account_reference=code)
    result=post('money_instrument',payload)
    return MoneyInstrument.objects.get(pk=result.result['instrument'])


def test_instrument_registration_preserves_legacy_history_and_zero_opening(growth_env):
    ctx,post,wh,*_=growth_env
    old=post('opening_cash',{'location':wh.location_id,'account':'BANK','amount':'1000','reason':'Original reviewed balance.'})
    original=list(old.entries.values('id','account_id','debit','credit','location_id'))
    item=instrument(ctx,post,wh)
    legacy=legacy_for(ctx,wh.location_id,'BANK')
    assert instrument_balance(legacy)==1000 and instrument_balance(item)==0
    assert list(old.entries.values('id','account_id','debit','credit','location_id'))==original
    assert not MoneyInstrumentEntry.objects.filter(entry__document=old).exists()
    assert balance(ctx,'BANK',location=wh.location_id)==1000
    assert not item.source.entries.exists()


@pytest.mark.parametrize('kind',['CASH','BANK'])
def test_separate_pool_transfer_and_overspend_are_atomic(growth_env,kind):
    ctx,post,wh,*_=growth_env
    post('opening_cash',{'location':wh.location_id,'account':kind,'amount':'1000','reason':'Original funds.'})
    item=instrument(ctx,post,wh,kind=kind,code=kind+'-B');legacy=legacy_for(ctx,wh.location_id,kind)
    payload={'from_account':kind,'to_account':kind,'from_location':wh.location_id,'to_location':wh.location_id,'from_instrument':legacy.pk,'to_instrument':item.pk,'amount':'300'}
    doc=post('cash_transfer',payload,'same-location-instrument-transfer')
    assert post('cash_transfer',payload,'same-location-instrument-transfer').pk==doc.pk
    assert instrument_balance(item)==300 and instrument_balance(legacy)==700
    assert balance(ctx,kind,location=wh.location_id)==1000
    assert not doc.entries.filter(account__category='income').exists()
    before=(Document.objects.count(),Entry.objects.count(),MoneyInstrumentEntry.objects.count())
    with pytest.raises(ValidationError):post('expense_post',{'location':wh.location_id,'amount':'301','expense_account':'EXPENSE','cash_account':kind,('cash_instrument' if kind=='CASH' else 'bank_instrument'):item.pk})
    assert before==(Document.objects.count(),Entry.objects.count(),MoneyInstrumentEntry.objects.count())
    assert instrument_balance(item)==300
    with pytest.raises(ValidationError):post('cash_transfer',{**payload,'amount':'1'},'same-location-instrument-transfer')


def test_ambiguous_or_wrong_business_kind_location_selection_rolls_back(growth_env):
    ctx,post,wh,*_=growth_env
    item=instrument(ctx,post,wh,'CASH','TILL-B')
    with pytest.raises(ValidationError):post('opening_cash',{'location':wh.location_id,'amount':'10','reason':'Missing actual instrument.'})
    with pytest.raises(ValidationError):post('opening_cash',{'location':wh.location_id,'account':'BANK','amount':'10','reason':'Wrong kind.','bank_instrument':item.pk})
    other=Location.objects.create(business=ctx.business,name='Other branch',code='OTHER')
    with pytest.raises(ValidationError):post('opening_cash',{'location':other.pk,'amount':'10','reason':'Wrong location.','cash_instrument':item.pk})
    foreign=Business.objects.create(name='Other business',slug='other-money-business')
    foreign_location=Location.objects.create(business=foreign,name='Foreign',code='F')
    alien=MoneyInstrument.objects.create(business=foreign,location=foreign_location,kind='CASH',code='FOREIGN',name='Foreign')
    with pytest.raises(ValidationError):post('opening_cash',{'location':wh.location_id,'amount':'10','reason':'Wrong tenant.','cash_instrument':alien.pk})
    assert not Entry.objects.exists()


def test_sale_and_payment_reversal_keep_original_instrument(growth_env):
    ctx,post,wh,sp,raw,customer,*_=growth_env
    item=instrument(ctx,post,wh,'CASH','SALE-TILL');block=open_block(post,wh,sp)
    sale=post('sale',{'warehouse':wh.pk,'party':customer.pk,'cash_instrument':item.pk,'lines':[{'product':sp.pk,'block':block.pk,'thickness_mm':'22'}],'paid':'500'})
    assert sale.amount==1100 and instrument_balance(item)==500
    assert MoneyInstrumentEntry.objects.get(entry__document=sale).instrument_id==item.pk
    receipt=post('receipt',{'invoice':sale.pk,'amount':'100','cash_instrument':item.pk,'cash_account':'CASH','location':wh.location_id})
    assert instrument_balance(item)==600
    assert MoneyInstrumentEntry.objects.get(entry__document=receipt).instrument_id==item.pk
    post('payment_reverse',{'payment':receipt.pk,'reason':'Reverse wrong original receipt.'})
    assert instrument_balance(item)==500 and instrument_balance(legacy_for(ctx,wh.location_id,'CASH'))==0
    assert balance(ctx,'CASH',location=wh.location_id)==500


@pytest.mark.parametrize('kind',['CASH','BANK'])
@pytest.mark.parametrize('legacy_source',[False,True])
def test_fx_settlement_reversal_retains_original_instrument_even_after_pool_split(fx_env,kind,legacy_source):
    from erp.tests.test_foreign_extensions import invoice,service
    ctx,post,fx,loc,wh,customer,supplier=fx_env
    sale=invoice(post,fx,wh,customer,service(ctx));exposure=ForeignExposure.objects.get(invoice=sale)
    first=None
    if not legacy_source:first=instrument(ctx,post,wh,kind,'FX-A')
    payload={'exposure':exposure.pk,'foreign_amount':'10','location':loc.pk,'cash_account':kind}
    if first:payload['cash_instrument' if kind=='CASH' else 'bank_instrument']=first.pk
    settled=post('fx_settle',fx(payload));original_ids=list(settled.entries.values_list('pk',flat=True))
    if legacy_source:
        instrument(ctx,post,wh,kind,'FX-A');first=legacy_for(ctx,loc,kind)
    other=instrument(ctx,post,wh,kind,'FX-B')
    post('opening_cash',{'location':loc.pk,'account':kind,'amount':'1000','reason':'Independent funds','cash_instrument' if kind=='CASH' else 'bank_instrument':other.pk})
    reverse=post('fx_settlement_reverse',{'settlement':settled.pk,'reason':'Correct original settlement','cash_instrument' if kind=='CASH' else 'bank_instrument':other.pk})
    assert instrument_balance(first)==0 and instrument_balance(other)==1000
    assert MoneyInstrumentEntry.objects.get(entry__document=reverse,entry__account__code=kind).instrument_id==first.pk
    assert list(settled.entries.values_list('pk',flat=True))==original_ids
    assert balance(ctx,'AR',party=customer)==1400


def test_two_drawers_at_one_location_have_separate_custody(growth_env):
    ctx,post,wh,*_=growth_env
    post('opening_cash',{'location':wh.location_id,'amount':'1000','reason':'Legacy float.'})
    item=instrument(ctx,post,wh,'CASH','SECOND-TILL');legacy=legacy_for(ctx,wh.location_id,'CASH')
    post('cash_transfer',{'from_account':'CASH','to_account':'CASH','from_location':wh.location_id,'to_location':wh.location_id,'from_instrument':legacy.pk,'to_instrument':item.pk,'amount':'300'})
    drawers=[]
    for i,pool,value in [(1,legacy,'700'),(2,item,'300')]:
        d=post('cash_drawer',{'location':wh.location_id,'code':f'DRAWER-{i}','name':f'Drawer{i}','cash_instrument':pool.pk,'confirm_location_pool':True})
        drawer=CashDrawer.objects.get(pk=d.result['drawer']);drawers.append(drawer)
        opened=post('cash_shift_open',{'drawer':drawer.pk,'denominations':[{'value':value,'count':'1'}]})
        assert opened.result['opening_amount']==value+'.00'
    paid=post('expense_post',{'location':wh.location_id,'amount':'20','expense_account':'EXPENSE','cash_account':'CASH','cash_instrument':item.pk})
    assert CashShiftEntry.objects.get(entry__document=paid).shift.drawer_id==drawers[1].pk
    assert instrument_balance(item)==280 and instrument_balance(legacy)==700
    count=post('cash_shift_count',{'shift':drawers[1].shifts.get().pk,'denominations':[{'value':'20','count':'14'}],'note':'Actual independent till count.'})
    assert count.result['variance']=='0.00'
    # The counted second till is frozen; first till remains independently usable.
    post('expense_post',{'location':wh.location_id,'amount':'5','expense_account':'EXPENSE','cash_account':'CASH','cash_instrument':legacy.pk})
    with pytest.raises(ValidationError):post('expense_post',{'location':wh.location_id,'amount':'1','expense_account':'EXPENSE','cash_account':'CASH','cash_instrument':item.pk})


def test_bank_matching_and_reconciliation_are_instrument_specific(growth_env):
    ctx,post,wh,*_=growth_env
    first=instrument(ctx,post,wh,code='BANK-A');second=instrument(ctx,post,wh,code='BANK-B')
    a=post('opening_cash',{'location':wh.location_id,'account':'BANK','bank_instrument':first.pk,'amount':'100','reason':'Actual first bank opening.'})
    b=post('opening_cash',{'location':wh.location_id,'account':'BANK','bank_instrument':second.pk,'amount':'100','reason':'Actual second bank opening.'})
    result=imported(post,wh,bank_instrument=first.pk,account_reference='BANK-A')
    statement=StatementImport.objects.get(pk=result.result['statement']);assert statement.instrument_id==first.pk
    from erp.statement_imports import eligible_entries
    assert {e.document_id for e in eligible_entries(ctx,statement)}=={a.pk}
    row=statement.rows.get();wrong=b.entries.get(account__code='BANK')
    with pytest.raises(ValidationError):post('statement_review',{'date':'2026-06-04','row':row.pk,'outcome':'match','entry':wrong.pk,'note':'Wrong physical bank.'})
    entry=a.entries.get(account__code='BANK')
    post('statement_review',{'date':'2026-06-04','row':row.pk,'outcome':'match','entry':entry.pk,'note':'Exact first bank evidence.'})
    reconciled=post('statement_reconcile',{'date':'2026-06-04','statement':statement.pk})
    assert reconciled.result['closing_balance']=='100.00'
    assert balance(ctx,'BANK',location=wh.location_id)==200
    assert instrument_balance(first)==100 and instrument_balance(second)==100
    with pytest.raises(ValidationError):imported(post,wh,bank_instrument=second.pk,account_reference='BANK-A')


def test_original_links_and_dimensions_cannot_be_forged_or_changed(growth_env):
    ctx,post,wh,*_=growth_env;item=instrument(ctx,post,wh)
    doc=post('opening_cash',{'location':wh.location_id,'account':'BANK','bank_instrument':item.pk,'amount':'100','reason':'Actual bank opening.'})
    link=MoneyInstrumentEntry.objects.get(entry__document=doc)
    with pytest.raises(DatabaseError),transaction.atomic():MoneyInstrumentEntry.objects.filter(pk=link.pk).delete()
    with pytest.raises(DatabaseError),transaction.atomic():MoneyInstrument.objects.filter(pk=item.pk).update(location=Location.objects.create(business=ctx.business,name='Wrong',code='WRONG'))
    with pytest.raises(DatabaseError),transaction.atomic():MoneyInstrumentEntry.objects.create(business=ctx.business,instrument=item,entry=doc.entries.get(account__code='EQUITY'))
    with pytest.raises(ValidationError):instrument(ctx,post,wh,code='BANK-A')


def test_instrument_choices_hide_balances_and_bank_identity(growth_env):
    ctx,post,wh,*_=growth_env;item=instrument(ctx,post,wh)
    user=get_user_model().objects.create_user(username='instrument-cashier')
    Membership.objects.create(user=user,business=ctx.business,permissions=['sales.post'],all_locations=False,location_ids=[wh.location_id],product_lines=['sponge'])
    client=client_for(user,ctx.business)
    choices=client.get('/api/money-instruments/?choices=1').json()
    assert any(row['id']==item.pk for row in choices['results'])
    assert all(not {'balance','institution','account_reference'}&row.keys() for row in choices['results'])
    assert client.get('/api/money-instruments/').status_code==403
    assert client.get(f'/api/documents/{item.source_id}/').status_code==403


def test_legacy_statement_and_live_instrument_control_totals_remain_complete(growth_env):
    ctx,post,wh,*_=growth_env
    old=post('opening_cash',{'location':wh.location_id,'account':'BANK','amount':'100','reason':'Original physical bank funds.'})
    statement_doc=imported(post,wh)
    statement=StatementImport.objects.get(pk=statement_doc.result['statement']);assert statement.instrument_id is None
    instrument(ctx,post,wh,code='SECOND-BANK')
    row=statement.rows.get();entry=old.entries.get(account__code='BANK')
    post('statement_review',{'date':'2026-06-04','row':row.pk,'outcome':'match','entry':entry.pk,'note':'Legacy statement retains its real original bank pool.'})
    post('statement_reconcile',{'date':'2026-06-04','statement':statement.pk})
    client=client_for(ctx.user,ctx.business);data=client.get('/api/money-instruments/').json()
    bank=next(row for row in data['controls'] if row['kind']=='BANK' and row['location']==wh.location_id)
    assert bank['ledger_balance']=='100.00' and bank['instrument_total']=='100.00' and bank['difference']=='0.00'
    assert all(row['balance']=='0.00' for row in data['unassigned_location'])
