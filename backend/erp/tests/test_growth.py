import json
from datetime import date,timedelta
from decimal import Decimal
from uuid import uuid4
import pytest
from django.core.exceptions import ValidationError,PermissionDenied
from django.db import DatabaseError,transaction
from erp.tests.test_api import environment,client_for
from erp.models import *
from erp.core import Context,execute,outstanding,balance
from erp.growth import replenishment,cut_preview
from erp.growth_hooks import lot_balance
from erp.localization import convert_calendar

@pytest.fixture
def growth_env(environment):
 user,business,member,loc,warehouse,sponge=environment
 raw=Product.objects.create(business=business,code='RAW-TEST',name='Test material',kind='raw',line='sponge',unit='kg')
 customer=Party.objects.create(business=business,name='Customer',kind='customer',phone='0700000000')
 supplier=Party.objects.create(business=business,name='Supplier',kind='supplier')
 ctx=Context(user,business)
 def post(action,payload,key=None):return execute(ctx,action,{'date':'2026-06-01',**payload},key or str(uuid4()))
 return ctx,post,warehouse,sponge,raw,customer,supplier

def open_block(post,warehouse,sponge,height='1000'):
 doc=post('stock_opening',{'warehouse':warehouse.id,'lines':[{'product':sponge.id,'value':'10000','blocks':[{'length_mm':'2000','width_mm':'1000','height_mm':height}]}]})
 return Block.objects.get(batch=doc)

def test_calendar_validates_nowruz_leap_days_and_canonical_roundtrip():
 assert convert_calendar('1405-01-01','jalali')['gregorian']=='2026-03-21'
 assert convert_calendar('۱۳۹۹/۱۲/۳۰','jalali')['gregorian']=='2021-03-20'
 assert convert_calendar('2026-10-30','gregorian')['jalali']=='1405-08-08'
 with pytest.raises(ValidationError):convert_calendar('1400-12-30','jalali')
 with pytest.raises(ValidationError):convert_calendar('2026-02-30','gregorian')

def test_collection_promises_followups_and_reminders_never_repost_revenue(growth_env):
 ctx,post,wh,sp,raw,customer,supplier=growth_env
 b=open_block(post,wh,sp)
 sale=post('sale',{'warehouse':wh.id,'party':customer.id,'lines':[{'product':sp.id,'block':b.id,'thickness_mm':'100','unit_price':'500'}],'paid':'3500'})
 task=post('collection_create',{'invoice':sale.id,'due_date':'2026-06-10','promised_amount':'1500'})
 with pytest.raises(ValidationError):post('collection_create',{'invoice':sale.id,'due_date':'2026-06-11','promised_amount':'1'})
 message=post('reminder_prepare',{'task':task.result['task'],'channel':'manual'})
 assert message.result['delivered'] is False and ReminderMessage.objects.get(pk=message.result['message']).state=='prepared'
 with pytest.raises(ValidationError):post('reminder_prepare',{'task':task.result['task'],'channel':'sms'})
 post('collection_note',{'task':task.result['task'],'outcome':'rescheduled','next_date':'2026-06-12','note':'Customer promised next week'})
 with pytest.raises(ValidationError):post('collection_note',{'task':task.result['task'],'outcome':'kept','note':'Not yet paid'})
 post('receipt',{'invoice':sale.id,'amount':'1500','location':wh.location_id})
 post('collection_note',{'task':task.result['task'],'outcome':'kept','note':'Receipt matched'})
 assert CollectionTask.objects.get(pk=task.result['task']).state=='kept'
 assert balance(ctx,'SALES')==Decimal('-5000') and outstanding(sale)==0

def test_reorder_request_conversion_counts_unreceived_order_once(growth_env):
 ctx,post,wh,sp,raw,customer,supplier=growth_env
 post('stock_opening',{'warehouse':wh.id,'lines':[{'product':raw.id,'quantity':'10','value':'100'}]})
 rule=post('reorder_policy',{'warehouse':wh.id,'product':raw.id,'minimum':'20','target':'50','supplier':supplier.id})
 rows=replenishment(ctx)['rows'];assert Decimal(rows[0]['suggested_quantity'])==40
 request=post('purchase_request',{'policy':rule.result['policy']})
 assert Decimal(replenishment(ctx)['rows'][0]['suggested_quantity'])==0
 converted=post('request_order',{'request':request.result['request'],'unit_price':'10'})
 order=Document.objects.get(pk=converted.result['order']);assert order.kind=='purchase_order'
 with pytest.raises(ValidationError):post('request_order',{'request':request.result['request']})
 assert Decimal(replenishment(ctx)['rows'][0]['on_order'])==40
 post('purchase_receive',{'warehouse':wh.id,'supplier':supplier.id,'order':order.id,'lines':[{'product':raw.id,'quantity':'15','unit_cost':'10','order_index':0}]})
 row=replenishment(ctx)['rows'][0]
 assert Decimal(row['on_hand'])==25 and Decimal(row['on_order'])==25 and Decimal(row['projected'])==50

def test_cut_plan_reserves_then_executes_exact_physical_sheets_idempotently(growth_env):
 ctx,post,wh,sp,*_=growth_env;b=open_block(post,wh,sp)
 payload={'warehouse':wh.id,'product':sp.id,'profile':b.profile,'cutting_loss_mm':'1','lines':[{'thickness_mm':'22','sheet_count':3},{'thickness_mm':'50','sheet_count':1}]}
 preview=cut_preview(ctx,payload);assert Decimal(preview['billable_cm'])==Decimal('11.6')
 plan=post('cut_plan',payload);b.refresh_from_db();assert b.reserved_height_mm==Decimal('120')
 before=balance(ctx,'FG');done=post('cut_execute',{'plan':plan.result['plan']},'cut-plan-once')
 assert post('cut_execute',{'plan':plan.result['plan']},'cut-plan-once').id==done.id
 b.refresh_from_db();assert b.remaining_height_mm==880 and b.reserved_height_mm==0
 assert Block.objects.filter(pk__in=done.result['blocks']).count()==4
 assert sum((block.remaining_height_mm for block in Block.objects.filter(pk__in=done.result['blocks'])),Decimal(0))==116
 assert balance(ctx,'FG')==before and balance(ctx,'SALES')==0
 with pytest.raises(ValidationError):post('cut_execute',{'plan':plan.result['plan']})

def test_workcenter_capacity_jobcard_and_output_completion(growth_env):
 ctx,post,wh,sp,raw,*_=growth_env
 center=post('work_center',{'name':'Mixing','location':wh.location_id,'daily_minutes':480})
 work=post('work_order',{'work_center':center.result['work_center'],'warehouse':wh.id,'product':sp.id,'planned_quantity':'100','scheduled_date':'2026-06-01','planned_minutes':300})
 with pytest.raises(ValidationError):post('work_order',{'work_center':center.result['work_center'],'warehouse':wh.id,'product':sp.id,'planned_quantity':'100','scheduled_date':'2026-06-01','planned_minutes':200})
 post('job_card',{'work_order':work.result['work_order'],'operation':'Mix and cure','minutes':120})
 with pytest.raises(ValidationError):post('work_close',{'work_order':work.result['work_order']})
 post('stock_opening',{'warehouse':wh.id,'lines':[{'product':raw.id,'quantity':'10','value':'1000'}]})
 batch=post('production',{'warehouse':wh.id,'work_order':work.result['work_order'],'inputs':[{'product':raw.id,'quantity':'10'}],'outputs':[{'product':sp.id,'blocks':[{'length_mm':'2000','width_mm':'1000','height_mm':'1000'}]}]})
 assert batch.result['work_order']==work.result['work_order']
 assert post('work_close',{'work_order':work.result['work_order']}).result['actual_quantity']=='100.000000'

def test_lot_quantities_quality_release_and_qr_business_isolation(growth_env):
 ctx,post,wh,sp,raw,customer,supplier=growth_env
 lot=post('lot_create',{'code':'SUPPLIER-A','product':raw.id,'supplier':supplier.id,'expiry_date':'2027-01-01'})
 lot_id=lot.result['lot']
 post('purchase_receive',{'warehouse':wh.id,'supplier':supplier.id,'lines':[{'product':raw.id,'quantity':'100','unit_cost':'10','lot':lot_id}]})
 post('lot_tracking_enable',{'confirm':True})
 batch=post('production',{'warehouse':wh.id,'inputs':[{'product':raw.id,'quantity':'10','lot':lot_id}],'outputs':[{'product':sp.id,'blocks':[{'length_mm':'2000','width_mm':'1000','height_mm':'1000'}]}]})
 assert lot_balance(MaterialLot.objects.get(pk=lot_id),wh)==90
 block=Block.objects.get(batch=batch)
 template=post('inspection_template',{'name':'Size and finish','product':sp.id,'criteria':[{'name':'height','type':'number','min':'999','max':'1001'},{'name':'finish','type':'pass_fail'}]})
 post('quality_inspect',{'template':template.result['template'],'block':block.id,'measurements':{'height':'1000','finish':False}})
 with pytest.raises(ValidationError):post('quality_release',{'block':block.id,'reason':'Cannot release failure'})
 post('quality_inspect',{'template':template.result['template'],'block':block.id,'measurements':{'height':'1000','finish':True}})
 post('quality_release',{'block':block.id,'reason':'Inspector signed'})
 block.refresh_from_db();assert block.status=='ready'
 client=client_for(ctx.user,ctx.business)
 label=json.dumps({'type':'erp-block','version':1,'business':ctx.business.id,'block':block.id,'code':block.code})
 assert client.get('/api/scan/',{'code':label}).status_code==200
 wrong=json.loads(label);wrong['business']+=100
 assert client.get('/api/scan/',{'code':json.dumps(wrong)}).status_code==403
 old=LotMovement.objects.filter(lot_id=lot_id).first()
 with pytest.raises(DatabaseError),transaction.atomic():LotMovement.objects.filter(pk=old.id).update(quantity=999)

def test_bins_budgets_forecasts_and_tenant_guards(growth_env):
 ctx,post,wh,sp,*_=growth_env;block=open_block(post,wh,sp)
 bin_doc=post('bin_create',{'warehouse':wh.id,'code':'RACK-A1'});post('block_place',{'block':block.id,'bin':bin_doc.result['bin']})
 account=Account.objects.get(business=ctx.business,code='RENT')
 post('budget_set',{'period':'2026-06','location':wh.location_id,'account':account.id,'line':'shared','amount':'1000'})
 post('expense_post',{'location':wh.location_id,'amount':'700','expense_account':'RENT'})
 client=client_for(ctx.user,ctx.business)
 result=client.get('/api/growth/budgets_actual/',{'period':'2026-06'}).json()['rows'][0]
 assert Decimal(result['actual'])==700 and Decimal(result['variance'])==-300 and result['favorable'] is True
 other=Business.objects.create(name='Other tenant',slug='growth-other')
 foreign=Warehouse.objects.create(business=other,location=Location.objects.create(business=other,name='Other',code='O'),name='Other')
 with pytest.raises(DatabaseError),transaction.atomic():BinLocation.objects.create(business=ctx.business,warehouse=foreign,code='BAD')
 ctx.membership.permissions=['sales.view'];ctx.membership.save()
 assert client.get('/api/growth/budgets_actual/').status_code==403
 assert client.get('/api/growth/lots/').status_code==403
