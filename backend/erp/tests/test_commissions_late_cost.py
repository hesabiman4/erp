from decimal import Decimal
import pytest
from django.core.exceptions import PermissionDenied,ValidationError
from django.db import transaction,DatabaseError
from erp.tests.test_api import environment,client_for
from erp.tests.test_growth import growth_env,open_block
from erp.core import balance,outstanding
from erp.models import Employee,Document,StockPool,StockMovement,Membership,CommissionEarning,CommissionPolicy

def employee_policy(ctx,post,wh):
    employee=Employee.objects.create(business=ctx.business,name='Sales staff',location=wh.location,kind='monthly',rate='10000')
    policy=post('commission_policy',{'employee':employee.id,'rate':'10','effective_from':'2026-01-01','effective_to':'2026-12-31'})
    return employee,policy.result['policy']

def test_commission_collected_net_sales_settles_without_duplicate_revenue_and_rejects_paid_clawback(growth_env):
    ctx,post,wh,sp,raw,customer,*_=growth_env;employee,rule=employee_policy(ctx,post,wh)
    block=open_block(post,wh,sp)
    sale=post('sale',{'warehouse':wh.id,'party':customer.id,'lines':[{'product':sp.id,'block':block.id,'thickness_mm':'100'}],'paid':'2500'})
    earned=post('commission_accrue',{'policy':rule,'invoice':sale.id,'reason':'Approved collected sales'})
    assert earned.amount==Decimal('250')
    assert balance(ctx,'PAYROLL',employee=employee)==Decimal('-250')
    with pytest.raises(ValidationError):post('commission_accrue',{'policy':rule,'invoice':sale.id,'reason':'Duplicate'})
    settlement=post('payroll_settle',{'payroll':earned.id,'amount':'250','location':wh.location_id})
    assert not settlement.entries.filter(account__code='SALES').exists()
    with pytest.raises(ValidationError):post('commission_reverse',{'earning':earned.id,'reason':'Cannot take wages back silently'})
    report=client_for(ctx.user,ctx.business).get(f'/api/reports/employee_statement/?employee={employee.id}').json()
    assert report['totals']['salary_earned']=='250.00' and report['totals']['salary_paid']=='250.00'

def test_commission_returns_reduce_entitlement_unpaid_reversal_and_policy_guards(growth_env):
    ctx,post,wh,sp,raw,customer,*_=growth_env;employee,rule=employee_policy(ctx,post,wh)
    block=open_block(post,wh,sp)
    sale=post('sale',{'warehouse':wh.id,'party':customer.id,'lines':[{'product':sp.id,'block':block.id,'thickness_mm':'100'}],'paid':'5000'})
    earned=post('commission_accrue',{'policy':rule,'invoice':sale.id,'reason':'Approval'})
    post('sales_return',{'invoice':sale.id,'warehouse':wh.id,'reason':'Return full sheet','lines':[{'index':0,'sheet_count':'1'}]})
    preview=client_for(ctx.user,ctx.business).get(f'/api/commissions/?policy={rule}&invoice={sale.id}&date=2026-06-01').json()['calculation']
    assert preview['entitlement']=='0.00' and preview['over_accrued']=='500.00'
    reversed=post('commission_reverse',{'earning':earned.id,'reason':'Unpaid returned sale'})
    assert balance(ctx,'PAYROLL',employee=employee)==0
    with pytest.raises(ValidationError):post('payroll_settle',{'payroll':earned.id,'amount':'1','location':wh.location_id})
    with pytest.raises(ValidationError):post('commission_policy',{'employee':employee.id,'rate':'20','effective_from':'2026-01-01'})
    with pytest.raises(DatabaseError),transaction.atomic():CommissionEarning.objects.filter(source=earned).update(amount='1')
    member=Membership.objects.get(pk=ctx.membership.pk);member.permissions=['payroll.post'];member.save()
    with pytest.raises(PermissionDenied):post('commission_accrue',{'policy':rule,'invoice':sale.id,'reason':'Missing approval'})

def raw_receipt(post,wh,raw,supplier):
    return post('purchase_receive',{'warehouse':wh.id,'supplier':supplier.id,'lines':[{'product':raw.id,'quantity':'100','unit_cost':'10'}]})

def late_bill(post,wh,supplier,receipt,amount='100'):
    return post('late_cost_bill',{'warehouse':wh.id,'supplier':supplier.id,'receipts':[receipt.id],'amount':amount,'supplier_reference':'FREIGHT-1','reason':'Actual freight bill after goods receipt'})

def test_late_cost_real_supplier_bill_onhand_value_only_and_no_double_absorption(growth_env):
    ctx,post,wh,sp,raw,customer,supplier=growth_env;receipt=raw_receipt(post,wh,raw,supplier)
    bill=late_bill(post,wh,supplier,receipt)
    invoice=Document.objects.get(pk=bill.result['invoice'])
    assert invoice.kind=='expense_post' and outstanding(invoice)==100
    assert not bill.entries.exists()
    pool=StockPool.objects.get(business=ctx.business,product=raw,warehouse=wh)
    allocation=post('late_cost_allocate',{'bill':bill.result['late_cost_bill'],'basis':'Freight belongs to goods still on hand','lines':[{'target':'inventory','pool':pool.id,'amount':'100'}]})
    pool.refresh_from_db();assert pool.quantity==100 and pool.value==1100
    assert allocation.movements.get().quantity==0 and allocation.movements.get().value==100
    assert balance(ctx,'COST_CLEARING')==0
    with pytest.raises(ValidationError):post('late_cost_allocate',{'bill':bill.result['late_cost_bill'],'basis':'Duplicate','lines':[{'target':'inventory','pool':pool.id,'amount':'1'}]})
    with pytest.raises(ValidationError):post('production',{'warehouse':wh.id,'inputs':[],'overhead_cost':'100','conversion_sources':[invoice.id],'outputs':[{'product':sp.id,'blocks':[{'length_mm':'2000','width_mm':'1000','height_mm':'100'}]}]})
    post('supplier_payment',{'invoice':invoice.id,'amount':'100','location':wh.location_id})
    assert outstanding(invoice)==0

def test_late_cost_open_wip_flows_into_output_but_cannot_enter_completed_batch(growth_env):
    ctx,post,wh,sp,raw,customer,supplier=growth_env;receipt=raw_receipt(post,wh,raw,supplier);bill=late_bill(post,wh,supplier,receipt)
    batch=post('production_start',{'warehouse':wh.id})
    post('production_consume',{'batch':batch.id,'inputs':[{'product':raw.id,'quantity':'10'}]})
    draft=client_for(ctx.user,ctx.business).post('/api/documents/',{'kind':'late_cost_allocate','data':{'date':'2026-06-01','bill':bill.result['late_cost_bill']}},content_type='application/json').json()
    with pytest.raises(ValidationError):post('late_cost_wip',{'bill':bill.result['late_cost_bill'],'batch':batch.id,'amount':'10','allocation_event':draft['id']})
    post('late_cost_allocate',{'bill':bill.result['late_cost_bill'],'basis':'Freight attributable to mixed open batch','lines':[{'target':'wip','batch':batch.id,'amount':'60'}]})
    complete=post('production_complete',{'batch':batch.id,'warehouse':wh.id,'outputs':[{'product':sp.id,'blocks':[{'length_mm':'2000','width_mm':'1000','height_mm':'100'}]}]})
    assert complete.result['wip_out']=='160.00' and balance(ctx,'WIP')==0
    with pytest.raises(ValidationError):post('late_cost_allocate',{'bill':bill.result['late_cost_bill'],'basis':'After completion','lines':[{'target':'wip','batch':batch.id,'amount':'40'}]})
    with pytest.raises(ValidationError):post('late_cost_wip',{'bill':bill.result['late_cost_bill'],'batch':batch.id,'amount':'1','allocation_event':complete.id})

def test_late_cost_sold_allocation_returns_restore_cost_once(growth_env):
    ctx,post,wh,sp,raw,customer,supplier=growth_env;receipt=raw_receipt(post,wh,raw,supplier)
    made=post('production',{'warehouse':wh.id,'inputs':[{'product':raw.id,'quantity':'10'}],'outputs':[{'product':sp.id,'blocks':[{'length_mm':'2000','width_mm':'1000','height_mm':'100'}]}]})
    sale=post('sale',{'warehouse':wh.id,'party':customer.id,'lines':[{'product':sp.id,'block':made.result['outputs'][0]['blocks'][0],'thickness_mm':'30','sheet_count':'3'}]})
    bill=late_bill(post,wh,supplier,receipt)
    post('late_cost_allocate',{'bill':bill.result['late_cost_bill'],'basis':'These manufactured sheets were already sold','lines':[{'target':'cogs','invoice':sale.id,'index':0,'amount':'100'}]})
    assert balance(ctx,'COGS')==190
    returned=post('sales_return',{'invoice':sale.id,'warehouse':wh.id,'lines':[{'index':0,'sheet_count':'1'} for _ in range(3)]})
    assert [r['value'] for r in returned.result['late_cost_restored']]==['33.33','33.33','33.34']
    assert balance(ctx,'COGS')==0
    pool=StockPool.objects.get(business=ctx.business,product=sp,warehouse=wh);assert pool.quantity==10 and pool.value==200
    with pytest.raises(ValidationError):post('sales_return',{'invoice':sale.id,'warehouse':wh.id,'lines':[{'index':0,'sheet_count':'1'}]})
