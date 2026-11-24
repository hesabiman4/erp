from decimal import Decimal
from uuid import uuid4
import pytest
from django.core.exceptions import ValidationError,PermissionDenied
from django.db import DatabaseError,transaction
from django.db.models import Sum
from erp.tests.test_foreign import fx_env
from erp.tests.test_api import environment,client_for
from erp.models import Product,Document,Entry,Allocation,ForeignExposure,ForeignWallet,ForeignMovement,ForeignWalletMovement,StockPool,Business,Party,Location
from erp.foreign_models import ForeignDeposit,ForeignDepositMovement
from erp.foreign import exposure_balance,wallet_balance,reconcile
from erp.foreign_extensions import deposit_balance
from erp.core import balance,outstanding,Context,execute,journal


def service(ctx):
    return Product.objects.create(business=ctx.business,code='FX-SERVICE',name='Delivered service',unit='each',kind='service',line='sponge',price='100')


def invoice(post,fx,wh,customer,product,price='2',qty='10'):
    return post('fx_sale',fx({'warehouse':wh.id,'party':customer.id,'foreign_currency':'USD','lines':[{'product':product.id,'quantity':qty,'foreign_unit_price':price}]}))


def test_integrated_foreign_sale_records_contract_once_and_conserves_line_rounding(fx_env):
    ctx,post,fx,loc,wh,customer,supplier=fx_env
    item=service(ctx)
    payload=fx({'warehouse':wh.id,'party':customer.id,'foreign_currency':'USD','rate':'70.12345678','lines':[{'product':item.id,'quantity':'3','foreign_unit_price':'1.11'},{'product':item.id,'quantity':'2','foreign_unit_price':'2.22'}]})
    sale=post('fx_sale',payload,'fx-invoice-once')
    assert sale.kind=='sale' and sale.amount==Decimal('544.86')
    assert post('fx_sale',payload,'fx-invoice-once').id==sale.id
    exposure=ForeignExposure.objects.get(invoice=sale)
    assert exposure.foreign_amount==Decimal('7.77')
    assert exposure_balance(exposure)==(Decimal('7.77'),Decimal('544.86'))
    assert balance(ctx,'SALES')==Decimal('-544.86')
    assert sum((Decimal(row['functional_amount']) for row in sale.result['foreign_snapshot']['lines']),Decimal(0))==sale.amount
    assert Document.objects.filter(kind='sale').count()==1


def test_integrated_foreign_purchase_receives_and_bills_once(fx_env):
    ctx,post,fx,loc,wh,customer,supplier=fx_env
    raw=Product.objects.create(business=ctx.business,code='FXRAW',name='Material',unit='kg',kind='raw',line='shared')
    bill=post('fx_purchase',fx({'warehouse':wh.id,'supplier':supplier.id,'supplier_reference':'USD-EXAMPLE-1','foreign_currency':'USD','lines':[{'product':raw.id,'quantity':'10','foreign_unit_cost':'2'}]}))
    assert bill.kind=='purchase_bill' and bill.amount==1400
    assert bill.reference.kind=='purchase_receive'
    assert StockPool.objects.get(product=raw,warehouse=wh).quantity==10
    assert balance(ctx,'RAW')==1400 and balance(ctx,'AP',party=supplier)==-1400 and balance(ctx,'GRNI')==0
    assert exposure_balance(ForeignExposure.objects.get(invoice=bill))==(Decimal(20),Decimal(1400))


def test_foreign_purchase_normalized_duplicate_reference_rolls_back_nested_receipt(fx_env):
    ctx,post,fx,loc,wh,customer,supplier=fx_env
    raw=Product.objects.create(business=ctx.business,code='DUPFX',name='Material',unit='kg',kind='raw',line='shared')
    payload=fx({'warehouse':wh.id,'supplier':supplier.id,'supplier_reference':'USD-۱۲۳','foreign_currency':'USD','lines':[{'product':raw.id,'quantity':'10','foreign_unit_cost':'2'}]})
    post('fx_purchase',payload)
    before=(Document.objects.count(),Entry.objects.count(),StockPool.objects.get(product=raw,warehouse=wh).quantity)
    with pytest.raises(ValidationError):post('fx_purchase',{**payload,'supplier_reference':'usd 123'})
    assert before==(Document.objects.count(),Entry.objects.count(),StockPool.objects.get(product=raw,warehouse=wh).quantity)


def test_refundable_deposit_revalues_allocates_and_refunds_exact_foreign_balance(fx_env):
    ctx,post,fx,loc,wh,customer,supplier=fx_env
    sale=invoice(post,fx,wh,customer,service(ctx));exposure=ForeignExposure.objects.get(invoice=sale)
    deposited=post('fx_deposit',fx({'party':customer.id,'side':'customer','classification':'refundable_monetary','location':loc.id,'foreign_currency':'USD','foreign_amount':'30'}))
    deposit=ForeignDeposit.objects.get(source=deposited)
    post('fx_deposit_revalue',fx({'deposit':deposit.id,'rate':'72','date':'2026-06-30'}))
    assert deposit_balance(deposit)==(Decimal(30),Decimal(2160))
    allocated=post('fx_deposit_allocate',{'deposit':deposit.id,'exposure':exposure.id,'foreign_amount':'20','date':'2026-07-01'})
    assert allocated.result['cash_changed'] is False
    assert exposure_balance(exposure)==(Decimal(0),Decimal(0)) and deposit_balance(deposit)==(Decimal(10),Decimal(720))
    assert balance(ctx,'FX_CUSTOMER_DEPOSITS',party=customer)==-720
    refunded=post('fx_refund',fx({'deposit':deposit.id,'foreign_amount':'10','rate':'73','date':'2026-07-02','location':loc.id,'reason':'Customer requested unused refundable credit'}))
    assert deposit_balance(deposit)==(Decimal(0),Decimal(0)) and refunded.result['exchange_gain']=='-10.00'
    assert reconcile(ctx)['difference']=='0.00'
    with pytest.raises(ValidationError):post('fx_refund',fx({'deposit':deposit.id,'foreign_amount':'0.01','date':'2026-07-02','reason':'Already exhausted'}))


def test_deposit_requires_explicit_monetary_classification_and_matching_party(fx_env):
    ctx,post,fx,loc,wh,customer,supplier=fx_env
    with pytest.raises(ValidationError):post('fx_deposit',fx({'party':customer.id,'side':'customer','classification':'goods_advance','location':loc.id,'foreign_currency':'USD','foreign_amount':'10'}))
    sale=invoice(post,fx,wh,customer,service(ctx));exposure=ForeignExposure.objects.get(invoice=sale)
    other=Party.objects.create(business=ctx.business,kind='customer',name='Other customer')
    deposit=post('fx_deposit',fx({'party':other.id,'side':'customer','classification':'refundable_monetary','location':loc.id,'foreign_currency':'USD','foreign_amount':'10'}))
    with pytest.raises(ValidationError):post('fx_deposit_allocate',{'deposit':deposit.result['deposit'],'exposure':exposure.id,'foreign_amount':'10'})
    assert exposure_balance(exposure)[0]==20


def test_latest_foreign_settlement_reversal_preserves_original_and_reopens_carrying_balance(fx_env):
    ctx,post,fx,loc,wh,customer,supplier=fx_env
    sale=invoice(post,fx,wh,customer,service(ctx));exposure=ForeignExposure.objects.get(invoice=sale)
    post('fx_revalue',fx({'date':'2026-06-30','target_type':'invoice','target':exposure.id,'rate':'72'}))
    settled=post('fx_settle',fx({'exposure':exposure.id,'foreign_amount':'10','rate':'73','date':'2026-07-01'}))
    ids=list(settled.entries.values_list('id',flat=True));original_allocation=settled.allocations.get().amount
    reverse=post('fx_settlement_reverse',{'settlement':settled.id,'date':'2026-07-02','reason':'Incorrect receipt'})
    assert exposure_balance(exposure)==(Decimal(20),Decimal(1440))
    assert balance(ctx,'AR',party=customer)==1440 and balance(ctx,'CASH')==0
    assert list(settled.entries.values_list('id',flat=True))==ids
    assert reverse.allocations.get().amount==-original_allocation
    with pytest.raises(ValidationError):post('fx_settlement_reverse',{'settlement':settled.id,'date':'2026-07-02','reason':'Duplicate'})


def test_reversal_rejects_later_invoice_or_wallet_movements(fx_env):
    ctx,post,fx,loc,wh,customer,supplier=fx_env
    sale=invoice(post,fx,wh,customer,service(ctx));exposure=ForeignExposure.objects.get(invoice=sale)
    wallet_doc=post('fx_wallet',{'name':'Invoice USD wallet','location':loc.id,'foreign_currency':'USD','kind':'cash'})
    wallet=ForeignWallet.objects.get(pk=wallet_doc.result['wallet'])
    settled=post('fx_settle',fx({'exposure':exposure.id,'foreign_amount':'10','wallet':wallet.id}))
    post('fx_revalue',fx({'date':'2026-06-30','target_type':'wallet','target':wallet.id,'rate':'72'}))
    with pytest.raises(ValidationError):post('fx_settlement_reverse',{'settlement':settled.id,'date':'2026-07-01','reason':'Later wallet valuation'})
    assert wallet_balance(wallet)==(Decimal(10),Decimal(720))


def test_foreign_sales_return_releases_revalued_debt_and_paid_return_creates_refundable_credit(fx_env):
    ctx,post,fx,loc,wh,customer,supplier=fx_env
    product=Product.objects.create(business=ctx.business,code='FXADH',name='Adhesive',unit='kg',kind='finished',line='adhesive',price='140')
    post('stock_opening',{'warehouse':wh.id,'lines':[{'product':product.id,'quantity':'10','value':'1000'}]})
    sale=invoice(post,fx,wh,customer,product);exposure=ForeignExposure.objects.get(invoice=sale)
    post('fx_revalue',fx({'date':'2026-06-30','target_type':'invoice','target':exposure.id,'rate':'72'}))
    returned=post('fx_return',fx({'exposure':exposure.id,'lines':[{'index':0,'quantity':'2'}],'date':'2026-07-01','rate':'73','reason':'Inspected return'}))
    assert returned.kind=='sales_return' and returned.result['foreign_credit']=='4.00'
    assert exposure_balance(exposure)==(Decimal(16),Decimal(1152))
    assert balance(ctx,'SALES')==-1120 and balance(ctx,'COGS')==800
    post('fx_settle',fx({'exposure':exposure.id,'foreign_amount':'16','rate':'73','date':'2026-07-02'}))
    paid_return=post('fx_return',fx({'exposure':exposure.id,'lines':[{'index':0,'quantity':'8'}],'date':'2026-07-03','rate':'74','reason':'Remaining goods returned'}))
    credit=ForeignDeposit.objects.get(source=paid_return)
    assert deposit_balance(credit)==(Decimal(16),Decimal(1184))
    assert exposure_balance(exposure)==(Decimal(0),Decimal(0))
    pool=StockPool.objects.get(product=product,warehouse=wh)
    assert pool.quantity==10 and pool.value==1000 and balance(ctx,'COGS')==0 and balance(ctx,'SALES')==0
    assert reconcile(ctx)['difference']=='0.00'


def test_foreign_supplier_return_conserves_inventory_payable_and_refundable_supplier_credit(fx_env):
    ctx,post,fx,loc,wh,customer,supplier=fx_env
    raw=Product.objects.create(business=ctx.business,code='RFX',name='Material',unit='kg',kind='raw',line='shared')
    bill=post('fx_purchase',fx({'warehouse':wh.id,'supplier':supplier.id,'foreign_currency':'USD','lines':[{'product':raw.id,'quantity':'10','foreign_unit_cost':'2'}]}));exposure=ForeignExposure.objects.get(invoice=bill)
    post('fx_settle',fx({'exposure':exposure.id,'foreign_amount':'20','rate':'71','date':'2026-06-02'}))
    returned=post('fx_return',fx({'exposure':exposure.id,'lines':[{'index':0,'quantity':'2'}],'date':'2026-06-03','rate':'72','reason':'Rejected material returned'}))
    deposit=ForeignDeposit.objects.get(source=returned)
    assert deposit_balance(deposit)==(Decimal(4),Decimal(288))
    assert StockPool.objects.get(product=raw).quantity==8 and balance(ctx,'RAW')==1120
    assert balance(ctx,'AP',party=supplier)==0 and balance(ctx,'FX_SUPPLIER_DEPOSITS',party=supplier)==288


def test_foreign_price_credit_and_database_deposit_history_guards(fx_env):
    ctx,post,fx,loc,wh,customer,supplier=fx_env
    sale=invoice(post,fx,wh,customer,service(ctx));exposure=ForeignExposure.objects.get(invoice=sale)
    post('fx_credit',fx({'exposure':exposure.id,'foreign_amount':'2','line':'sponge','reason':'Approved price concession'}))
    assert exposure_balance(exposure)==(Decimal(18),Decimal(1260))
    assert balance(ctx,'SALES')==-1260
    with pytest.raises(ValidationError):post('fx_credit',fx({'exposure':exposure.id,'foreign_amount':'19','line':'sponge','reason':'Exceeds original'}))
    created=post('fx_deposit',fx({'party':customer.id,'side':'customer','classification':'refundable_monetary','location':loc.id,'foreign_currency':'USD','foreign_amount':'2'}))
    deposit=ForeignDeposit.objects.get(source=created)
    with pytest.raises(DatabaseError),transaction.atomic():ForeignDeposit.objects.filter(pk=deposit.id).update(base_value=999)
    post('fx_deposit_revalue',fx({'deposit':deposit.id,'rate':'71','date':'2026-06-30'}))
    with pytest.raises(DatabaseError),transaction.atomic():ForeignDepositMovement.objects.filter(deposit=deposit).delete()


def test_foreign_deposits_scope_and_unsupported_tax_roll_back(fx_env):
    ctx,post,fx,loc,wh,customer,supplier=fx_env
    before=Document.objects.count()
    with pytest.raises(ValidationError):invoice(post,lambda p:fx({**p,'tax_rule':999}),wh,customer,service(ctx))
    assert Document.objects.count()==before
    created=post('fx_deposit',fx({'party':customer.id,'side':'customer','classification':'refundable_monetary','location':loc.id,'foreign_currency':'USD','foreign_amount':'2'}))
    ctx.membership.permissions=['sales.view'];ctx.membership.save()
    client=client_for(ctx.user,ctx.business)
    assert client.get('/api/foreign/extensions/').status_code==403
    with pytest.raises(PermissionDenied):post('fx_refund',fx({'deposit':created.result['deposit'],'foreign_amount':'1','reason':'Unauthorized'}))


def test_database_rejects_forged_negative_foreign_allocations(fx_env):
    ctx,post,fx,loc,wh,customer,supplier=fx_env
    sale=invoice(post,fx,wh,customer,service(ctx));item=ForeignExposure.objects.get(invoice=sale)
    source=post('fx_settle',fx({'exposure':item.id,'foreign_amount':'10'}))
    original=source.allocations.get()
    def forged(reference,amount_value,mirror_journal=False):
        key=uuid4().hex
        doc=Document.objects.create(business=ctx.business,kind='fx_settlement_reverse',number='FORGED-'+key,date=source.date,reference=reference,created_by=ctx.user,idempotency_key=key,request_hash=key)
        if mirror_journal:
            journal(ctx,doc,[{'account':entry.account.code,'debit':entry.credit,'credit':entry.debit,'location':entry.location,'party':entry.party,'line':entry.line} for entry in source.entries.select_related('account','location','party')])
        Allocation.objects.create(document=doc,invoice=sale,amount=amount_value)
    # Wrong source kind, a partial negative, and a journal-only forgery without
    # the compensating exposure movement must all fail at PostgreSQL itself.
    with pytest.raises(DatabaseError),transaction.atomic():forged(sale,-original.amount,True)
    with pytest.raises(DatabaseError),transaction.atomic():forged(source,Decimal('-1'),True)
    with pytest.raises(DatabaseError),transaction.atomic():forged(source,-original.amount,True)
    assert exposure_balance(item)==(Decimal(10),Decimal(700))
    assert source.allocations.get().amount==original.amount


def test_reversal_journal_guard_compares_duplicate_rows_as_a_multiset(fx_env):
    ctx,post,fx,loc,wh,customer,supplier=fx_env
    first=post('opening_receivable',{'party':customer.id,'location':loc.id,'amount':'100'})
    second=post('opening_receivable',{'party':customer.id,'location':loc.id,'amount':'100'})
    receipt=post('receipt',{'party':customer.id,'location':loc.id,'amount':'200','allocations':[{'invoice':first.id,'amount':'100'},{'invoice':second.id,'amount':'100'}]})
    key=uuid4().hex
    wrong=Document.objects.create(business=ctx.business,kind='payment_reverse',number='WRONG-MULTISET-'+key,date=receipt.date,reference=receipt,created_by=ctx.user,idempotency_key=key,request_hash=key)
    # The original has two identical AR credits. Matching one AR debit twice is
    # insufficient: an unrelated expense debit cannot replace the second row.
    journal(ctx,wrong,[{'account':'AR','debit':'100','location':loc,'party':customer},{'account':'EXPENSE','debit':'100','location':loc},{'account':'CASH','credit':'200','location':loc}])
    with pytest.raises(DatabaseError),transaction.atomic():Allocation.objects.create(document=wrong,invoice=first,amount='-100')
