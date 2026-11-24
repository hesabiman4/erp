import json
from decimal import Decimal
from types import SimpleNamespace
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import override_settings
import pytest
from erp.tests.test_growth import growth_env,open_block
from erp.tests.test_api import environment,client_for
from erp.models import *
from erp.core import Context,outstanding
from erp.growth_hooks import lot_balance
from erp.messaging import send_queued

def test_portal_is_customer_business_scoped_and_has_no_staff_rights(growth_env):
 ctx,post,wh,sp,raw,customer,supplier=growth_env;client=client_for(ctx.user,ctx.business)
 bill=post('opening_receivable',{'location':wh.location_id,'party':customer.id,'amount':'1000','reason':'Recorded customer opening'})
 other_customer=Party.objects.create(business=ctx.business,name='Other customer',kind='customer')
 other_bill=post('opening_receivable',{'location':wh.location_id,'party':other_customer.id,'amount':'8000','reason':'Other opening'})
 created=client.post('/api/portal-access/',{'party':customer.id,'username':'customer_portal','password':'Portal-strong-synthetic-pass84'},content_type='application/json')
 assert created.status_code==201,created.content
 user=get_user_model().objects.get(username='customer_portal');assert not Membership.objects.filter(user=user).exists()
 portal=client_for(user,ctx.business);assert portal.get('/api/session/').json()['user']['portal_only'] is True
 rows=portal.get('/api/portal/').json()['results'];assert [r['id'] for r in rows]==[bill.id]
 assert set(rows[0])=={'id','number','date','total','outstanding','location','lines','payments','delivery_confirmed'}
 assert portal.get(f'/api/portal/{other_bill.id}/').status_code==403
 assert portal.get('/api/catalog/').status_code==403
 assert portal.post('/api/operations/receipt/',{'invoice':bill.id,'amount':'100','location':wh.location_id},content_type='application/json',HTTP_IDEMPOTENCY_KEY='portal-no-write').status_code==403
 assert outstanding(bill)==1000
 assert portal.get(f'/api/portal/{bill.id}/print/').status_code==200
 grant=PortalGrant.objects.get(user=user);client.patch('/api/portal-access/',{'id':grant.id,'active':False},content_type='application/json')
 assert portal.get('/api/portal/').status_code==403

def test_expired_lot_consumption_rolls_back_and_transfer_preserves_lot(growth_env):
 ctx,post,wh,sp,raw,customer,supplier=growth_env
 lot=post('lot_create',{'code':'LOT-1','product':raw.id,'expiry_date':'2026-06-10'})
 ident=lot.result['lot'];material_lot=MaterialLot.objects.get(pk=ident)
 post('purchase_receive',{'warehouse':wh.id,'supplier':supplier.id,'lines':[{'product':raw.id,'quantity':'100','unit_cost':'20','lot':ident}]})
 post('lot_tracking_enable',{'confirm':True})
 loc=Location.objects.create(business=ctx.business,name='Kabul',code='K');destination=Warehouse.objects.create(business=ctx.business,location=loc,name='Kabul store')
 transfer=post('transfer_dispatch',{'warehouse':wh.id,'destination':destination.id,'lines':[{'product':raw.id,'quantity':'20'}]})
 post('transfer_receive',{'transfer':transfer.id,'lines':[{'index':0,'quantity':'20'}]})
 assert lot_balance(material_lot,wh)==80 and lot_balance(material_lot,destination)==20
 pool=StockPool.objects.get(product=raw,warehouse=wh);before=(pool.quantity,pool.value,Document.objects.count())
 with pytest.raises(ValidationError):post('production',{'date':'2026-06-11','warehouse':wh.id,'inputs':[{'product':raw.id,'quantity':'10','lot':ident}],'outputs':[{'product':sp.id,'blocks':[{'length_mm':'2000','width_mm':'1000','height_mm':'1000'}]}]})
 pool.refresh_from_db();assert (pool.quantity,pool.value,Document.objects.count())==before
 assert lot_balance(material_lot,wh)==80

def test_maintenance_consumes_parts_once_and_posts_actual_cost(growth_env):
 ctx,post,wh,sp,raw,*_=growth_env
 post('stock_opening',{'warehouse':wh.id,'lines':[{'product':raw.id,'quantity':'10','value':'1000'}]})
 center=post('work_center',{'name':'Cutting','location':wh.location_id,'daily_minutes':480})
 equipment=post('equipment_create',{'name':'Cutting machine','work_center':center.result['work_center'],'service_interval_days':30,'next_service':'2026-06-01'})
 job=post('maintenance_open',{'equipment':equipment.result['equipment'],'due_date':'2026-06-01','reason':'Change worn parts'})
 completion=post('maintenance_complete',{'maintenance':job.result['maintenance'],'downtime_minutes':45,'lines':[{'warehouse':wh.id,'product':raw.id,'quantity':'2'}]})
 assert Decimal(completion.result['cost'])==200
 assert Entry.objects.get(document=completion,account__code='REPAIRS').debit==200
 assert StockPool.objects.get(product=raw,warehouse=wh).quantity==8
 with pytest.raises(ValidationError):post('maintenance_complete',{'maintenance':job.result['maintenance']})

def test_outbox_configuration_block_and_provider_acceptance_are_honest(growth_env,monkeypatch):
 ctx,post,wh,sp,raw,customer,*_=growth_env
 bill=post('opening_receivable',{'location':wh.location_id,'party':customer.id,'amount':'1000','reason':'Verified debt'})
 promise=post('collection_create',{'invoice':bill.id,'promised_amount':'1000','due_date':'2026-06-05'})
 payload={'task':promise.result['task'],'channel':'sms','consent_confirmed':True,'recipient':'+93700000000'}
 first=post('reminder_prepare',payload);message=ReminderMessage.objects.get(source=first)
 monkeypatch.delenv('ERP_MESSAGE_PROVIDER_URL',raising=False);monkeypatch.delenv('ERP_MESSAGE_PROVIDER_TOKEN',raising=False)
 assert send_queued()[0]['state']=='blocked';message.refresh_from_db();assert message.attempts==0 and message.sent_at is None
 second=post('reminder_prepare',payload);message=ReminderMessage.objects.get(source=second)
 class Reply:
    status=202
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def read(self,*args):return b'{"message_id":"synthetic-provider-reference"}'
 monkeypatch.setenv('ERP_MESSAGE_PROVIDER_URL','https://provider.example.invalid/messages');monkeypatch.setenv('ERP_MESSAGE_PROVIDER_TOKEN','synthetic-token')
 monkeypatch.setattr('erp.messaging.urllib.request.urlopen',lambda *args,**kwargs:Reply())
 result=send_queued()[0];assert result['state']=='accepted' and result['delivered'] is False
 message.refresh_from_db();assert message.attempts==1 and message.provider_reference=='synthetic-provider-reference'

def test_maintenance_tick_and_runtime_explicitly_defer_backups(growth_env,tmp_path,monkeypatch):
 ctx,*_=growth_env;monkeypatch.delenv('ERP_BACKUP_DIRECTORY',raising=False)
 monkeypatch.setattr('erp.management.commands.run_maintenance.subprocess.run',lambda *args,**kwargs:SimpleNamespace(returncode=0))
 with override_settings(ROOT_DIR=tmp_path):
    call_command('run_maintenance')
    state=json.loads(next((tmp_path/'.local').glob('runtime-status-*.json')).read_text())
    assert state['backup']['state']=='not_configured' and state['reconciliation']['state']=='succeeded'
    data=client_for(ctx.user,ctx.business).get('/api/growth/runtime/').json()
    assert data['backup_destination_configured'] is False and data['recovery_verified'] is False

def test_contract_price_is_available_to_sales_without_override_permission(growth_env):
 ctx,post,wh,sp,raw,customer,*_=growth_env;block=open_block(post,wh,sp)
 post('customer_price',{'party':customer.id,'product':sp.id,'profile':block.profile,'unit_price':'400','effective_from':'2026-06-01'})
 ctx.membership.permissions=['sales.post','sales.view','sales.credit'];ctx.membership.approval_limit=100000;ctx.membership.save()
 client=client_for(ctx.user,ctx.business);rates=client.get('/api/growth/effective_prices/',{'party':customer.id,'date':'2026-06-01'})
 assert rates.status_code==200 and len(rates.json()['results'])==1
 sale=post('sale',{'warehouse':wh.id,'party':customer.id,'lines':[{'product':sp.id,'block':block.id,'thickness_mm':'10','sheet_count':'1','unit_price':'400'}]})
 assert sale.amount==400

def test_receipt_quality_and_supplier_actual_metrics(growth_env):
 ctx,post,wh,sp,raw,customer,supplier=growth_env
 order=post('purchase_order',{'warehouse':wh.id,'supplier':supplier.id,'expected_date':'2026-06-03','lines':[{'product':raw.id,'quantity':'10','unit_price':'20'}]})
 receipt=post('purchase_receive',{'date':'2026-06-04','warehouse':wh.id,'supplier':supplier.id,'order':order.id,'lines':[{'order_index':0,'product':raw.id,'quantity':'10','unit_cost':'20'}]})
 template=post('inspection_template',{'product':raw.id,'name':'Incoming material','criteria':[{'name':'seal','type':'pass_fail'},{'name':'mass','type':'number','min':'9','max':'11'}]})
 with pytest.raises(ValidationError):post('quality_inspect',{'date':'2026-06-04','template':template.result['template'],'batch':receipt.id,'measurements':{'seal':False,'mass':'bad'}})
 post('quality_inspect',{'date':'2026-06-04','template':template.result['template'],'batch':receipt.id,'measurements':{'seal':False,'mass':'10'}})
 result=client_for(ctx.user,ctx.business).get('/api/growth/supplier_performance/').json()['rows'][0]
 assert result['receipts']==1 and result['late']==1 and result['rejected_receipts']==1 and result['average_lead_days']=='3.0'

def test_print_profile_escapes_html_and_respects_calendar(growth_env):
 ctx,post,wh,sp,raw,customer,*_=growth_env
 post('print_profile',{'legal_name':'Manufacturing <script>alert(1)</script>','footer':'Retain your invoice','address':'Herat'})
 bill=post('opening_receivable',{'location':wh.location_id,'party':customer.id,'amount':'100','reason':'Verified opening'})
 client=client_for(ctx.user,ctx.business);assert client.patch('/api/preferences/',{'calendar':'jalali'},content_type='application/json').status_code==200
 html=client.get(f'/api/documents/{bill.id}/print/').content.decode()
 assert '1405-03-11' in html and '&lt;script&gt;' in html and '<script>alert' not in html and 'Retain your invoice' in html

def test_outbox_does_not_demand_already_paid_or_changed_debt(growth_env,monkeypatch):
 ctx,post,wh,sp,raw,customer,*_=growth_env
 bill=post('opening_receivable',{'location':wh.location_id,'party':customer.id,'amount':'1000','reason':'Verified debt'})
 promise=post('collection_create',{'invoice':bill.id,'promised_amount':'1000','due_date':'2026-06-05'})
 post('reminder_prepare',{'task':promise.result['task'],'channel':'sms','consent_confirmed':True,'recipient':'+93700000000'})
 post('receipt',{'location':wh.location_id,'invoice':bill.id,'amount':'500'})
 def no_network(*args,**kwargs):raise AssertionError('Stale debt reminder must not reach provider')
 monkeypatch.setattr('erp.messaging.urllib.request.urlopen',no_network)
 assert send_queued()[0]['state']=='blocked'

def test_required_block_inspection_holds_production_and_prevents_uninspected_sale(growth_env):
 ctx,post,wh,sp,raw,customer,*_=growth_env
 ctx.business.settings={**ctx.business.settings,'require_inspection':True};ctx.business.save(update_fields=['settings'])
 post('stock_opening',{'warehouse':wh.id,'lines':[{'product':raw.id,'quantity':'10','value':'1000'}]})
 batch=post('production',{'warehouse':wh.id,'inputs':[{'product':raw.id,'quantity':'10'}],'outputs':[{'product':sp.id,'blocks':[{'length_mm':'2000','width_mm':'1000','height_mm':'1000'}]}]})
 block=Block.objects.get(batch=batch);assert block.status=='inspection'
 with pytest.raises(ValidationError):post('sale',{'warehouse':wh.id,'party':customer.id,'lines':[{'product':sp.id,'block':block.id,'thickness_mm':'10','sheet_count':'1'}]})
 template=post('inspection_template',{'product':sp.id,'name':'Required finish','criteria':[{'name':'finish','type':'pass_fail'}]})
 post('quality_inspect',{'template':template.result['template'],'block':block.id,'measurements':{'finish':True}})
 post('quality_release',{'block':block.id,'reason':'Approved quality'})
 cut=post('cut',{'warehouse':wh.id,'block':block.id,'thickness_mm':'20','sheet_count':'1'})
 child=Block.objects.get(pk=cut.result['blocks'][0]);assert child.parent_id==block.id
 sale=post('sale',{'warehouse':wh.id,'party':customer.id,'lines':[{'product':sp.id,'block':child.id,'thickness_mm':'20','sheet_count':'1'}]})
 assert sale.amount==1000

def test_work_center_update_cannot_move_or_expose_another_location(growth_env):
 from django.core.exceptions import PermissionDenied
 ctx,post,wh,*_=growth_env
 post('work_center',{'name':'Protected center','location':wh.location_id,'daily_minutes':480})
 other=Location.objects.create(business=ctx.business,name='Other branch',code='O')
 ctx.membership.all_locations=False;ctx.membership.location_ids=[other.id];ctx.membership.save()
 with pytest.raises(PermissionDenied):post('work_center',{'name':'Protected center','location':other.id,'daily_minutes':480})
 assert WorkCenter.objects.get(name='Protected center').location_id==wh.location_id

def test_reorder_and_customer_price_normalize_compatible_footprint(growth_env):
 ctx,post,wh,sp,raw,customer,*_=growth_env
 policy=post('reorder_policy',{'warehouse':wh.id,'product':sp.id,'profile':'۲۰۰۰ × ۱۰۰۰','minimum':'100','target':'200'})
 assert ReorderPolicy.objects.get(pk=policy.result['policy']).profile=='2000.000x1000.000'
 price=post('customer_price',{'party':customer.id,'product':sp.id,'profile':'2000x1000','unit_price':'500','effective_from':'2026-06-01'})
 assert CustomerPrice.objects.get(pk=price.result['customer_price']).profile=='2000.000x1000.000'

def test_staged_lot_traceability_and_delivery_confirmation_conserve_sales(growth_env):
 ctx,post,wh,sp,raw,customer,supplier=growth_env
 lot=post('lot_create',{'product':raw.id,'code':'WIP-TRACE'})
 post('purchase_receive',{'warehouse':wh.id,'supplier':supplier.id,'lines':[{'product':raw.id,'quantity':'10','unit_cost':'100','lot':lot.result['lot']}]})
 start=post('production_start',{'warehouse':wh.id})
 post('lot_status',{'lot':lot.result['lot'],'state':'held','reason':'Quarantine pending seal check'})
 with pytest.raises(ValidationError):post('production_consume',{'warehouse':wh.id,'batch':start.id,'inputs':[{'product':raw.id,'quantity':'10','lot':lot.result['lot']}]})
 post('lot_status',{'lot':lot.result['lot'],'state':'released','reason':'Authorized material release after check'})
 post('production_consume',{'warehouse':wh.id,'batch':start.id,'inputs':[{'product':raw.id,'quantity':'10','lot':lot.result['lot']}]})
 complete=post('production_complete',{'batch':start.id,'warehouse':wh.id,'outputs':[{'product':sp.id,'blocks':[{'length_mm':'2000','width_mm':'1000','height_mm':'1000'}]}]})
 block=Block.objects.get(batch=complete)
 sale=post('sale',{'warehouse':wh.id,'party':customer.id,'lines':[{'product':sp.id,'block':block.id,'thickness_mm':'10','sheet_count':'1'}]})
 confirmation=post('delivery_confirm',{'invoice':sale.id,'recipient':'Verified customer recipient'})
 assert confirmation.result['revenue_posted'] is False and not Entry.objects.filter(document=confirmation).exists()
 with pytest.raises(ValidationError):post('delivery_confirm',{'invoice':sale.id,'recipient':'Duplicate'})
 opening=post('opening_receivable',{'location':wh.location_id,'party':customer.id,'amount':'100','reason':'Legacy opening'})
 with pytest.raises(ValidationError):post('delivery_confirm',{'invoice':opening.id,'recipient':'No actual delivery'})
 traced=client_for(ctx.user,ctx.business).get('/api/growth/traceability/',{'lot':lot.result['lot']}).json()
 assert block.id in [b['id'] for b in traced['output_blocks']] and sale.id in [d['document'] for d in traced['deliveries']]
 assert sum(Entry.objects.filter(account__code='SALES').values_list('credit',flat=True))==500
