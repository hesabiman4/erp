"""The exact A05/A14 accounting example, from purchase to branch receipt."""
from decimal import Decimal
import pytest
from .test_api import environment
from erp.models import Product, Party, Employee, Location, Warehouse, Block, StockPool, BOM
from erp.core import Context, execute, balance, outstanding, profile_for
from erp.reports import report

def test_exact_9000_cm_manufacturing_accounting_cycle(environment):
    user,business,membership,factory,store,sponge=environment
    sponge.price=Decimal('100');sponge.save()
    raw=Product.objects.create(business=business,code='ACTUAL-TDI',name='Actual material',unit='kg',kind='raw',line='shared')
    trim=Product.objects.create(business=business,code='TOP-45',name='سربلوک 45',unit='each',kind='trim',line='sponge',price='100')
    supplier=Party.objects.create(business=business,name='Synthetic supplier',kind='supplier')
    worker=Employee.objects.create(business=business,name='Production employee',location=factory,kind='monthly',rate='30000')
    kabul=Location.objects.create(business=business,name='Kabul',code='KABUL')
    branch=Warehouse.objects.create(business=business,location=kabul,name='Kabul store')
    counter=iter(range(100))
    def post(action,payload):
        return execute(Context(user,business),action,{'date':'2026-04-30',**payload},f'exact-cycle-{next(counter)}')
    post('opening_cash',{'location':factory.pk,'amount':'20000','reason':'Reviewed synthetic opening'})
    receipt=post('purchase_receive',{'warehouse':store.pk,'supplier':supplier.pk,'lines':[{'product':raw.pk,'quantity':'1600','unit_cost':'100'}]})
    bill=post('purchase_bill',{'receipt':receipt.pk,'supplier_reference':'EXAMPLE-01'})
    labor=post('payroll_accrue',{'employee':worker.pk,'period':'2026-04','expense_account':'LABOR_CLEARING','line':'sponge'})
    overhead=post('expense_post',{'location':factory.pk,'amount':'10000','expense_account':'COST_CLEARING','production_cost':True,'cash_account':'CASH','description':'Eligible conversion overhead','line':'sponge'})
    batch=post('production',{'warehouse':store.pk,'inputs':[{'product':raw.pk,'quantity':'1600'}],'labor_cost':'30000','overhead_cost':'10000','conversion_sources':[labor.pk,overhead.pk],'outputs':[{'product':sponge.pk,'cost':'180000','blocks':[{'length_mm':'2000','width_mm':'1000','height_mm':'1000'} for _ in range(90)]},{'product':trim.pk,'quantity':'200','cost':'20000'}]})
    assert not BOM.objects.filter(business=business).exists()
    assert batch.result['total_cost']=='200000.00'
    profile=profile_for('2000','1000')
    pool=StockPool.objects.get(business=business,product=sponge,warehouse=store,profile=profile)
    assert pool.quantity==Decimal('9000') and pool.value==Decimal('180000')
    assert balance(Context(user,business),'WIP')==0
    assert balance(Context(user,business),'LABOR_CLEARING')==0
    assert balance(Context(user,business),'COST_CLEARING')==0
    block=Block.objects.filter(batch=batch).order_by('pk').first()
    invoice=post('sale',{'warehouse':store.pk,'customer_name':'Walk-in example','phone':'0700000000','lines':[{'product':sponge.pk,'block':block.pk,'thickness_cm':'50','sheet_count':1}],'paid':'3500'})
    pool.refresh_from_db()
    assert pool.quantity==Decimal('8950') and pool.value==Decimal('179000')
    assert invoice.amount==Decimal('5000') and outstanding(invoice)==Decimal('1500')
    assert balance(Context(user,business),'SALES')==Decimal('-5000')
    assert balance(Context(user,business),'COGS')==Decimal('1000')
    post('receipt',{'location':factory.pk,'invoice':invoice.pk,'amount':'1500','cash_account':'CASH'})
    assert outstanding(invoice)==0
    full_block=Block.objects.filter(batch=batch,remaining_height_mm=1000).order_by('pk').first()
    transfer=post('transfer_dispatch',{'warehouse':store.pk,'destination':branch.pk,'internal_charge':'3000','lines':[{'product':sponge.pk,'block':full_block.pk,'quantity':'100'}]})
    assert balance(Context(user,business),'TRANSIT')==Decimal('2000')
    post('transfer_receive',{'transfer':transfer.pk})
    assert balance(Context(user,business),'TRANSIT')==0
    assert balance(Context(user,business),'SALES')==Decimal('-5000')
    assert outstanding(bill)==Decimal('160000')
    summary=report(Context(user,business),'profit_loss',{})['totals']
    assert summary['revenue']=='5000.00' and summary['profit']=='4000.00'
    sheet=report(Context(user,business),'balance_sheet',{})['totals']
    assert sheet['assets']=='214000.00' and sheet['liabilities']=='190000.00'
    assert sheet['equity_including_earnings']=='24000.00' and sheet['difference']=='0.00'
    inventory=report(Context(user,business),'inventory_reconciliation',{})['totals']
    assert inventory['stock_cost']=='199000.00' and inventory['difference']=='0.00'
