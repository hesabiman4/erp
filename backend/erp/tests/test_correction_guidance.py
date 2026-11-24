from decimal import Decimal
from erp.tests.test_api import environment,client_for
from erp.tests.test_growth import growth_env,open_block
from erp.models import Document,Entry,StockMovement,Block,Business,Membership
from erp.core import outstanding,balance

def guide(ctx,doc,**params):return client_for(ctx.user,ctx.business).get(f'/api/documents/{doc.pk}/correction/',params)

def test_guidance_reads_real_return_remainder_and_preserves_original_postings(growth_env):
    ctx,post,wh,sp,raw,customer,*_=growth_env;block=open_block(post,wh,sp)
    sale=post('sale',{'warehouse':wh.pk,'party':customer.pk,'lines':[{'product':sp.pk,'block':block.pk,'thickness_mm':'100'}],'paid':'3500'})
    before=(Document.objects.count(),Entry.objects.count(),StockMovement.objects.count())
    response=guide(ctx,sale);assert response.status_code==200,response.content
    plan=response.json();assert not plan['posting_performed']
    assert plan['options'][0]['action']=='sale_return' and plan['options'][0]['initial']=={'invoice':sale.pk}
    assert Decimal(plan['returns']['lines'][0]['remaining_sheets'])==1
    assert before==(Document.objects.count(),Entry.objects.count(),StockMovement.objects.count())
    returned=post('sales_return',{'invoice':sale.pk,'reason':'Customer returned physical sheet','lines':[{'index':0,'sheet_count':'1'}]})
    block.refresh_from_db();assert block.remaining_height_mm==900
    child=Block.objects.get(parent=block);assert child.initial_height_mm==100 and child.status=='inspection'
    after=guide(ctx,sale).json();assert Decimal(after['returns']['lines'][0]['remaining_quantity'])==0
    assert any(r['id']==returned.pk for r in after['related'])
    credit=guide(ctx,returned).json();refund=next(o for o in credit['options'] if o['action']=='customer_refund')
    assert refund['initial']['amount']=='3500.00'
    post('customer_refund',{**refund['initial'],'reason':'Return unused customer credit'})
    assert guide(ctx,returned).json()['options']==[]
    sale.refresh_from_db();assert sale.state=='posted' and sale.amount==5000 and outstanding(sale)==0
    assert balance(ctx,'SALES')==0 and balance(ctx,'COGS')==0

def test_purchase_guidance_separates_unbilled_receipts_from_particular_bills(growth_env):
    ctx,post,wh,sp,raw,customer,supplier=growth_env
    receipt=post('purchase_receive',{'warehouse':wh.pk,'supplier':supplier.pk,'lines':[{'product':raw.pk,'quantity':'10','unit_cost':'100'}]})
    bill=post('purchase_bill',{'receipt':receipt.pk,'lines':[{'index':0,'quantity':'4'}]})
    original=guide(ctx,receipt).json();assert Decimal(original['returns']['lines'][0]['remaining_quantity'])==6
    billed=guide(ctx,receipt,bill=bill.pk).json();assert Decimal(billed['returns']['lines'][0]['remaining_quantity'])==4
    linked=guide(ctx,bill).json();assert linked['options'][0]['initial']=={'receipt':receipt.pk,'bill':bill.pk}
    post('purchase_return',{'receipt':receipt.pk,'bill':bill.pk,'reason':'Supplier accepted return','lines':[{'index':0,'quantity':'2'}]})
    assert Decimal(guide(ctx,receipt,bill=bill.pk).json()['returns']['lines'][0]['remaining_quantity'])==2
    assert Decimal(guide(ctx,receipt).json()['returns']['lines'][0]['remaining_quantity'])==6
    assert outstanding(bill)==200

def test_payment_reversal_guidance_uses_original_and_duplicate_protection(growth_env):
    ctx,post,wh,sp,raw,customer,*_=growth_env
    invoice=post('opening_receivable',{'location':wh.location_id,'party':customer.pk,'amount':'500','reason':'Reviewed opening'})
    receipt=post('receipt',{'location':wh.location_id,'invoice':invoice.pk,'amount':'300'})
    selected=next(o for o in guide(ctx,receipt).json()['options'] if o['action']=='payment_reverse')
    reversed_doc=post('payment_reverse',{**selected['initial'],'reason':'Wrong receipt confirmed'})
    assert outstanding(invoice)==500 and balance(ctx,'CASH')==0
    again=guide(ctx,receipt).json();assert not any(o['action']=='payment_reverse' for o in again['options'])
    assert any(d['id']==reversed_doc.pk for d in again['related'])

def test_guidance_enforces_business_location_and_action_permissions(growth_env):
    ctx,post,wh,sp,raw,customer,*_=growth_env;block=open_block(post,wh,sp)
    sale=post('sale',{'warehouse':wh.pk,'party':customer.pk,'lines':[{'product':sp.pk,'block':block.pk,'thickness_mm':'20'}],'paid':'0'})
    ctx.membership.permissions=['sales.view'];ctx.membership.save()
    view=guide(ctx,sale).json();assert view['options']==[] and view['returns'] is None
    assert 'cost' not in view['document']['result']['lines'][0]
    foreign=Business.objects.create(name='Furniture private',slug='correction-private')
    Membership.objects.create(user=ctx.user,business=foreign,permissions=['*'],all_locations=True)
    client=client_for(ctx.user,foreign)
    assert client.get(f'/api/documents/{sale.pk}/correction/').status_code==400
    ctx.membership.permissions=['inventory.view'];ctx.membership.save()
    assert guide(ctx,sale).status_code==403

def test_ordinary_expense_is_not_given_an_unsafe_universal_reversal(growth_env):
    ctx,post,wh,*_=growth_env
    post('opening_cash',{'location':wh.location_id,'amount':'100','reason':'Reviewed cash'})
    expense=post('expense_post',{'location':wh.location_id,'amount':'20','expense_account':'EXPENSE','notes':'Review evidence'})
    before=Entry.objects.count();assert guide(ctx,expense).json()['options']==[];assert Entry.objects.count()==before
